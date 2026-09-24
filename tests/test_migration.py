import importlib.util
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from app import ledger
from app.time_logger import create_datetime

JOHANNESBURG = ZoneInfo("Africa/Johannesburg")

_spec = importlib.util.spec_from_file_location(
    "migrate_fingerprints",
    Path(__file__).resolve().parent.parent / "scripts" / "migrate_fingerprints.py",
)
migrate_fingerprints = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_fingerprints)

legacy_local_slot = migrate_fingerprints.legacy_local_slot


def legacy_started(date_ddmmyyyy, hhmm):
    """Reproduce exactly what the pre-fix create_datetime() emitted."""
    day, month, year = date_ddmmyyyy.split("-")
    hour, minute = hhmm.split(":")
    return f"{year}-{month}-{day}T{int(hour) - 1}:{minute}:00.000+0000"


class TestLegacyLocalSlot(unittest.TestCase):
    def test_undoes_the_hour_shift(self):
        self.assertEqual(legacy_local_slot("2025-07-09T7:30:00.000+0000"), "2025-07-09T08:30")

    def test_recovers_midnight_from_negative_hour(self):
        self.assertEqual(legacy_local_slot("2025-07-09T-1:30:00.000+0000"), "2025-07-09T00:30")

    def test_pads_the_recovered_hour(self):
        self.assertEqual(legacy_local_slot("2025-07-09T8:00:00.000+0000"), "2025-07-09T09:00")

    def test_late_evening(self):
        self.assertEqual(legacy_local_slot("2025-07-09T22:00:00.000+0000"), "2025-07-09T23:00")


class TestMigrationPreservesIdentity(unittest.TestCase):
    """
    The property the whole migration rests on: for a given CSV row, the slot
    recovered from the OLD stored timestamp must equal the slot derived from the
    NEW one. If these ever diverge, every previously-logged item looks new and
    gets logged to JIRA a second time.
    """

    def _assert_round_trip(self, date, hhmm):
        old_slot = legacy_local_slot(legacy_started(date, hhmm))
        new_slot = ledger.slot_key(create_datetime(date, hhmm, timezone=JOHANNESBURG))
        self.assertEqual(old_slot, new_slot, f"slot mismatch for {date} {hhmm}")

    def test_morning(self):
        self._assert_round_trip("09-07-2025", "08:30")

    def test_midnight(self):
        self._assert_round_trip("09-07-2025", "00:30")

    def test_single_digit_hour(self):
        self._assert_round_trip("09-07-2025", "09:05")

    def test_late_evening(self):
        self._assert_round_trip("09-07-2025", "23:45")

    def test_across_a_range_of_times(self):
        for hour in range(24):
            for minute in (0, 7, 30, 59):
                self._assert_round_trip("09-07-2025", f"{hour:02d}:{minute:02d}")

    def test_fingerprint_matches_after_migration(self):
        # End to end: the fingerprint computed from a migrated legacy row must
        # equal the one a fresh run produces for the same CSV row.
        date, hhmm, seconds, issue = "09-07-2025", "08:30", 1380, "JIRA-123"

        migrated = ledger.fingerprint_from_parts(
            issue, legacy_local_slot(legacy_started(date, hhmm)), seconds
        )
        fresh = ledger.fingerprint(
            [seconds, create_datetime(date, hhmm, timezone=JOHANNESBURG), "desc", issue]
        )
        self.assertEqual(migrated, fresh)


if __name__ == "__main__":
    unittest.main()
