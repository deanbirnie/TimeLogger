#!/usr/bin/env python3
"""
One-time migration: import one or more old file-based ledgers
(state/logged.json, from before the MySQL-backed ledger) into the
logged_worklogs table.

Safe to run multiple times, and against multiple files (e.g. once per device
that had its own logged.json): each work item's fingerprint is the table's
primary key, so an item already present in the database is skipped rather than
duplicated.

Usage:
    uv run scripts/migrate_ledger_to_db.py path/to/logged.json [more paths...]

Requires the same DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD
environment variables (.env) as the main script, and the schema from
sql/02_schema.sql already applied.
"""

import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import ledger


def _parse_logged_at(value):
    """Old ledger entries store logged_at as an ISO string, possibly with a
    UTC offset; MySQL's DATETIME column needs a naive value."""
    if not value:
        return datetime.now()
    dt = datetime.fromisoformat(value)
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def migrate_file(conn, path: Path) -> tuple[int, int]:
    """Returns (inserted, skipped) counts for one legacy ledger file."""
    entries = ledger.load_legacy_json_ledger(path)
    if not entries:
        print(f"  {path}: no entries found (missing, empty, or unreadable)")
        return 0, 0

    inserted = 0
    skipped = 0
    with conn.cursor() as cursor:
        for fp, entry in entries.items():
            cursor.execute(
                "INSERT IGNORE INTO logged_worklogs "
                "(fingerprint, jira_issue, started, time_spent_seconds, description, "
                "source_file, logged_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    fp,
                    entry.get("issue"),
                    entry.get("started"),
                    entry.get("timeSpentSeconds"),
                    entry.get("description"),
                    entry.get("source"),
                    _parse_logged_at(entry.get("logged_at")),
                ),
            )
            if cursor.rowcount:
                inserted += 1
            else:
                skipped += 1

    print(f"  {path}: {inserted} inserted, {skipped} already present")
    return inserted, skipped


def main(paths):
    if not paths:
        print(__doc__)
        return 1

    load_dotenv()
    try:
        conn = ledger.connect()
    except ledger.DatabaseConnectionError as exc:
        print(f"❌ {exc}")
        return 1

    total_inserted = 0
    total_skipped = 0
    print("Migrating legacy JSON ledger(s) into the database:")
    for raw_path in paths:
        inserted, skipped = migrate_file(conn, Path(raw_path))
        total_inserted += inserted
        total_skipped += skipped

    conn.close()
    print("-" * 100)
    print(f"Done. {total_inserted} item(s) migrated, {total_skipped} already present.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
