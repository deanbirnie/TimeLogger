"""
Persistence helpers for TimeLogger: a MySQL-backed ledger of already-logged
worklog items (for de-duplication across devices and re-runs) and archiving of
processed CSV files.

This module is deliberately free of any I/O against JIRA and does not import the
rest of the app, so it can be unit-tested in isolation.

A "work item" is the 4-element list used throughout time_logger.py:

    [time_spent_seconds (int), started (str), description (str), jira_issue (str)]
"""

import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import pymysql


class DatabaseConnectionError(RuntimeError):
    """Raised when the MySQL ledger database cannot be reached."""


# --- Configuration / paths ----------------------------------------------------

def project_root() -> Path:
    """Repository root (the parent of the app/ package)."""
    return Path(__file__).resolve().parent.parent


def get_archive_dir() -> Path:
    """
    Directory into which processed CSV files are copied.

    Overridable via the ARCHIVE_DIR environment variable (.env); defaults to
    ``<project>/archive``.
    """
    override = os.getenv("ARCHIVE_DIR")
    if override:
        return Path(override).expanduser()
    return project_root() / "archive"


def get_db_config() -> dict:
    """
    MySQL connection settings, read from the environment (.env): DB_HOST,
    DB_PORT (default 3306), DB_NAME, DB_USER, DB_PASSWORD.
    """
    return {
        "host": os.getenv("DB_HOST"),
        "port": int(os.getenv("DB_PORT") or 3306),
        "database": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
    }


# --- Fingerprinting -----------------------------------------------------------

def fingerprint(item) -> str:
    """
    Stable identity for a work item.

    The natural key is (jira_issue, started, time_spent_seconds); the description
    is intentionally excluded so that fixing a typo and re-running does not create
    a duplicate worklog. Returns a SHA-1 hex digest.

    :param item: [time_spent_seconds, started, description, jira_issue]
    """
    time_spent, started, _description, jira_issue = item
    key = f"{jira_issue}\x00{started}\x00{time_spent}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


# --- Database connection -------------------------------------------------------

def connect():
    """
    Open a connection to the ledger database.

    :raises DatabaseConnectionError: if the server cannot be reached. Callers
        should treat this as fatal for the run: logging without being able to
        record the result risks duplicate worklogs on the next run.
    """
    config = get_db_config()
    try:
        return pymysql.connect(autocommit=True, **config)
    except pymysql.MySQLError as exc:
        raise DatabaseConnectionError(
            "DB connection failed - please ensure you are connected to the DB "
            "server on the same network and try again."
        ) from exc


# --- Ledger read/write ----------------------------------------------------------

def load_ledger(conn) -> dict:
    """
    Load the ledger as a dict keyed by fingerprint, from the logged_worklogs
    table.
    """
    ledger = {}
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT fingerprint, jira_issue, started, time_spent_seconds, "
            "description, source_file, logged_at FROM logged_worklogs"
        )
        for row in cursor.fetchall():
            fp, jira_issue, started, time_spent_seconds, description, source_file, logged_at = row
            ledger[fp] = {
                "issue": jira_issue,
                "started": started,
                "timeSpentSeconds": time_spent_seconds,
                "description": description,
                "source": source_file,
                "logged_at": logged_at.isoformat(),
            }
    return ledger


def is_logged(ledger: dict, item) -> bool:
    """True if this item's fingerprint is already recorded in the ledger."""
    return fingerprint(item) in ledger


def filter_new(ledger: dict, items):
    """
    Partition items into (new_items, already_logged), preserving order.

    :return: tuple(list, list)
    """
    new_items = []
    already_logged = []
    for item in items:
        if is_logged(ledger, item):
            already_logged.append(item)
        else:
            new_items.append(item)
    return new_items, already_logged


def record_logged(conn, ledger: dict, item, source_name: str = "") -> None:
    """
    Mark an item as logged and persist immediately.

    Called only after JIRA accepts the worklog (HTTP 201), once per success, so a
    mid-run crash leaves already-succeeded items recorded (no double-logging on the
    retry) while failed items stay absent and are retried next run.

    Mutates ``ledger`` in place and inserts a row into logged_worklogs. Uses
    INSERT IGNORE keyed on the fingerprint primary key, so re-recording the same
    item (e.g. a re-run racing another device) is a harmless no-op rather than an
    error.
    """
    time_spent, started, description, jira_issue = item
    fp = fingerprint(item)
    # Naive local time: a tz-aware value would serialise with a UTC offset
    # suffix that MySQL's DATETIME column does not accept.
    logged_at = datetime.now().astimezone().replace(tzinfo=None)

    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT IGNORE INTO logged_worklogs "
            "(fingerprint, jira_issue, started, time_spent_seconds, description, "
            "source_file, logged_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (fp, jira_issue, started, time_spent, description, source_name, logged_at),
        )

    ledger[fp] = {
        "issue": jira_issue,
        "started": started,
        "timeSpentSeconds": time_spent,
        "description": description,
        "source": source_name,
        "logged_at": logged_at.isoformat(timespec="seconds"),
    }


# --- Legacy JSON ledger (migration only) ---------------------------------------

def load_legacy_json_ledger(path) -> dict:
    """
    Read an old file-based ledger (state/logged.json from before the MySQL
    migration), keyed by fingerprint, in the same shape load_ledger() returns.

    Used only by scripts/migrate_ledger_to_db.py. Returns an empty dict if the
    file does not exist or is unreadable/corrupt.
    """
    path = Path(path)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
        return {}
    except (json.JSONDecodeError, OSError):
        return {}


# --- Archiving ----------------------------------------------------------------

def archive_file(src_path, archive_dir, now=None) -> Path:
    """
    Copy the processed CSV into the archive directory, preserving the original
    file (which typically lives in the user's downloads dir). The copy is
    timestamp-prefixed so re-processing a same-named file on different days does
    not overwrite earlier history.

    :return: Path to the archived copy.
    """
    src_path = Path(src_path)
    archive_dir = Path(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)

    stamp = (now or datetime.now()).strftime("%Y-%m-%dT%H-%M-%S")
    dest = archive_dir / f"{stamp}_{src_path.name}"

    # Guard against clobbering an existing copy (e.g. two runs within the same
    # second) by appending an incrementing suffix.
    if dest.exists():
        counter = 1
        while True:
            candidate = archive_dir / f"{stamp}_{src_path.stem}_{counter}{src_path.suffix}"
            if not candidate.exists():
                dest = candidate
                break
            counter += 1

    shutil.copy2(src_path, dest)
    return dest
