#!/usr/bin/env python3
"""
One-time migration: recompute the fingerprints of ledger rows written before the
timestamp fix (BUGS.md B2-B4).

Why this is needed: an item's identity used to hash the raw `started` string,
which the old create_datetime() built by subtracting an hour and hardcoding
+0000. Now that timestamps are correct, the same CSV row produces a different
`started` -- so without this migration every previously-logged item would look
new and be logged to JIRA a second time.

The old transformation was deterministic (always exactly minus one hour), so the
original wall-clock time can be recovered and the corrected slot and fingerprint
derived from it.

The `started` column is left as it was, on purpose: it records what was actually
sent to JIRA at the time. Identity now lives in `slot`.

Usage:
    uv run scripts/migrate_fingerprints.py            # migrate
    uv run scripts/migrate_fingerprints.py --dry-run  # report only, change nothing

Requires sql/03_add_slot_and_fingerprint_version.sql to have been applied first.
Safe to re-run: only rows below the current fingerprint version are considered.
"""

import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import ledger


def legacy_local_slot(started) -> str:
    """
    Recover the CSV's original local wall-clock slot from a pre-fix `started`.

    Pre-fix values look like '2025-07-09T7:30:00.000+0000', where the hour is
    the real local hour minus one (and so can be '-1' for a midnight start).
    Adding that hour back gives the time as it appeared in the CSV.
    """
    date_part, _, time_part = str(started).partition("T")
    year, month, day = (int(part) for part in date_part.split("-"))
    pieces = time_part.split(":")
    hour = int(pieces[0]) + 1  # undo the old hardcoded -1 hour
    minute = int(pieces[1])

    local = datetime(year, month, day, hour, minute)
    return local.strftime("%Y-%m-%dT%H:%M")


def migrate(conn, dry_run=False):
    """Returns (migrated, collisions) counts."""
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT fingerprint, jira_issue, started, time_spent_seconds "
            "FROM logged_worklogs WHERE fingerprint_version < %s",
            (ledger.FINGERPRINT_VERSION,),
        )
        rows = cursor.fetchall()

    if not rows:
        print("Nothing to migrate - every row is already on the current scheme.")
        return 0, 0

    print(f"Found {len(rows)} row(s) on an older fingerprint scheme.")
    migrated = 0
    collisions = 0

    for old_fingerprint, jira_issue, started, time_spent in rows:
        try:
            slot = legacy_local_slot(started)
        except (ValueError, IndexError) as exc:
            print(f"  ! {jira_issue} {started!r}: cannot parse, leaving alone ({exc})")
            collisions += 1
            continue

        new_fingerprint = ledger.fingerprint_from_parts(jira_issue, slot, time_spent)

        if dry_run:
            print(f"  {jira_issue:<12} {started} -> slot {slot}")
            migrated += 1
            continue

        with conn.cursor() as cursor:
            # Another row may already hold the new fingerprint (e.g. the same
            # work item logged twice under the old scheme). Drop this duplicate
            # rather than failing the whole migration on a primary key clash.
            already_there = False
            if new_fingerprint != old_fingerprint:
                cursor.execute(
                    "SELECT 1 FROM logged_worklogs WHERE fingerprint = %s",
                    (new_fingerprint,),
                )
                already_there = cursor.fetchone() is not None

            if already_there:
                cursor.execute("DELETE FROM logged_worklogs WHERE fingerprint = %s", (old_fingerprint,))
                collisions += 1
                print(f"  {jira_issue:<12} {slot}: already present under new scheme, removed duplicate")
                continue

            cursor.execute(
                "UPDATE logged_worklogs SET fingerprint = %s, slot = %s, fingerprint_version = %s "
                "WHERE fingerprint = %s",
                (new_fingerprint, slot, ledger.FINGERPRINT_VERSION, old_fingerprint),
            )
            migrated += 1

    return migrated, collisions


def main(argv):
    dry_run = "--dry-run" in argv

    load_dotenv()
    try:
        conn = ledger.connect()
    except ledger.DatabaseConnectionError as exc:
        print(f"❌ {exc}")
        return 1

    if dry_run:
        print("Dry run - no changes will be written.\n")

    migrated, collisions = migrate(conn, dry_run=dry_run)
    conn.close()

    print("-" * 78)
    if dry_run:
        print(f"Dry run complete. {migrated} row(s) would be migrated.")
    else:
        summary = f"Done. {migrated} row(s) migrated."
        if collisions:
            summary += f" {collisions} duplicate/unparseable row(s) handled."
        print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
