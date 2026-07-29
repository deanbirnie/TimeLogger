"""
Persistence helpers for TimeLogger: a ledger of already-logged worklog items
(for de-duplication across re-runs) and archiving of processed CSV files.

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


# --- Configuration / paths ----------------------------------------------------

def project_root() -> Path:
    """Repository root (the parent of the app/ package)."""
    return Path(__file__).resolve().parent.parent


def get_ledger_path() -> Path:
    """
    Path to the JSON ledger of logged items.

    Overridable via the LEDGER_PATH environment variable (.env); defaults to
    ``<project>/state/logged.json``.
    """
    override = os.getenv("LEDGER_PATH")
    if override:
        return Path(override).expanduser()
    return project_root() / "state" / "logged.json"


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


# --- Ledger read/write --------------------------------------------------------

def load_ledger(path) -> dict:
    """
    Load the ledger as a dict keyed by fingerprint. Returns an empty dict if the
    file does not exist or is unreadable/corrupt (the ledger is a cache, so a bad
    file should never crash a run — worst case, items get re-logged once).
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


def save_ledger(path, ledger: dict) -> None:
    """
    Write the ledger atomically: serialise to a temp file in the same directory,
    then os.replace() over the target so a crash mid-write cannot corrupt it.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


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


def record_logged(path, ledger: dict, item, source_name: str = "") -> None:
    """
    Mark an item as logged and persist immediately.

    Called only after JIRA accepts the worklog (HTTP 201), once per success, so a
    mid-run crash leaves already-succeeded items recorded (no double-logging on the
    retry) while failed items stay absent and are retried next run.

    Mutates ``ledger`` in place and rewrites the ledger file atomically.
    """
    time_spent, started, description, jira_issue = item
    ledger[fingerprint(item)] = {
        "issue": jira_issue,
        "started": started,
        "timeSpentSeconds": time_spent,
        "description": description,
        "source": source_name,
        "logged_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    save_ledger(path, ledger)


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
