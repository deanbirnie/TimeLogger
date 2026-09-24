import os
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from app import ledger
from app.time_logger import build_data, create_datetime, create_time_spent

JOHANNESBURG = ZoneInfo("Africa/Johannesburg")

CSV_HEADER = """subtotals,tag_groups,duration,date,start,stop,description,user,tags
0:00,Total,,,,,,,
,,,,,,,,
,,,,,,,,
"""


def write_csv(directory, body):
    path = Path(directory) / "TimeFile.csv"
    path.write_text(CSV_HEADER + body, encoding="utf-8")
    return path


class TestCreateDatetime(unittest.TestCase):
    def test_pads_single_digit_hour(self):
        # B2: the old code emitted 'T8:05', which is not valid ISO-8601.
        result = create_datetime("09-07-2025", "08:05", timezone=JOHANNESBURG)
        self.assertEqual(result, "2025-07-09T08:05:00.000+0200")

    def test_midnight_does_not_go_negative(self):
        # B3: the old code emitted 'T-1:30' for a 00:30 start.
        result = create_datetime("09-07-2025", "00:30", timezone=JOHANNESBURG)
        self.assertEqual(result, "2025-07-09T00:30:00.000+0200")

    def test_does_not_shift_the_hour(self):
        # B4: the old code subtracted an hour and hardcoded +0000.
        result = create_datetime("09-07-2025", "14:00", timezone=JOHANNESBURG)
        self.assertIn("T14:00", result)
        self.assertTrue(result.endswith("+0200"))

    def test_reorders_day_month_year_to_iso(self):
        result = create_datetime("01-12-2025", "09:00", timezone=JOHANNESBURG)
        self.assertTrue(result.startswith("2025-12-01T"))

    def test_honours_dst_for_a_zone_that_has_it(self):
        summer = create_datetime("09-07-2025", "09:00", timezone=ZoneInfo("Europe/London"))
        winter = create_datetime("09-01-2025", "09:00", timezone=ZoneInfo("Europe/London"))
        self.assertTrue(summer.endswith("+0100"))
        self.assertTrue(winter.endswith("+0000"))
        # The local wall-clock time is preserved in both cases.
        self.assertIn("T09:00", summer)
        self.assertIn("T09:00", winter)

    def test_timezone_comes_from_env_when_not_passed(self):
        previous = os.environ.get("TIMEZONE")
        os.environ["TIMEZONE"] = "Europe/London"
        try:
            self.assertTrue(create_datetime("09-01-2025", "09:00").endswith("+0000"))
        finally:
            if previous is None:
                os.environ.pop("TIMEZONE", None)
            else:
                os.environ["TIMEZONE"] = previous


class TestCreateTimeSpent(unittest.TestCase):
    def test_hours_and_minutes(self):
        self.assertEqual(create_time_spent("1:35"), 5700)

    def test_minutes_only(self):
        self.assertEqual(create_time_spent("0:23"), 1380)

    def test_non_numeric_raises(self):
        with self.assertRaises(ValueError):
            create_time_spent("BADVALUE")


class TestBuildData(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["TIMEZONE"] = "Africa/Johannesburg"

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("TIMEZONE", None)

    def test_parses_valid_rows(self):
        path = write_csv(self.tmpdir.name,
                         ',,0:23,09-07-2025,08:30,08:53,"Login flow #JIRA-123",user,#JIRA-123\n')
        items, skipped = build_data(path)
        self.assertEqual(skipped, [])
        self.assertEqual(items, [[1380, "2025-07-09T08:30:00.000+0200", "Login flow", "JIRA-123"]])

    def test_malformed_row_does_not_duplicate_previous_row(self):
        # B1: the append used to sit outside the try, so a bad row re-appended
        # the previous row's values - duplicating that worklog.
        path = write_csv(
            self.tmpdir.name,
            ',,0:23,09-07-2025,08:30,08:53,"First #JIRA-1",user,#JIRA-1\n'
            ',,BADDUR,09-07-2025,09:00,09:30,"Broken #JIRA-2",user,#JIRA-2\n'
            ',,0:45,09-07-2025,10:00,10:45,"Third #JIRA-3",user,#JIRA-3\n'
        )
        items, skipped = build_data(path)

        self.assertEqual([item[3] for item in items], ["JIRA-1", "JIRA-3"])
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0][0], 6)  # 4 header rows + 2

    def test_malformed_first_row_does_not_raise(self):
        # B1: with the first data row bad, the old code raised NameError.
        path = write_csv(
            self.tmpdir.name,
            ',,BADDUR,09-07-2025,09:00,09:30,"Broken #JIRA-2",user,#JIRA-2\n'
            ',,0:45,09-07-2025,10:00,10:45,"Good #JIRA-3",user,#JIRA-3\n'
        )
        items, skipped = build_data(path)
        self.assertEqual([item[3] for item in items], ["JIRA-3"])
        self.assertEqual(len(skipped), 1)

    def test_short_row_is_skipped_not_fatal(self):
        path = write_csv(self.tmpdir.name, ",,0:23\n")
        items, skipped = build_data(path)
        self.assertEqual(items, [])
        self.assertEqual(len(skipped), 1)
        self.assertIn("IndexError", skipped[0][1])

    def test_trailing_blank_line_is_not_reported_as_skipped(self):
        path = write_csv(self.tmpdir.name,
                         ',,0:23,09-07-2025,08:30,08:53,"Login flow #JIRA-123",user,#JIRA-123\n'
                         ',,,,,,,,\n')
        items, skipped = build_data(path)
        self.assertEqual(len(items), 1)
        self.assertEqual(skipped, [])

    def test_header_rows_are_skipped(self):
        path = write_csv(self.tmpdir.name, "")
        items, skipped = build_data(path)
        self.assertEqual(items, [])
        self.assertEqual(skipped, [])

    def test_reads_a_readonly_file(self):
        # B7: the file used to be opened 'r+', which fails when not writable.
        path = write_csv(self.tmpdir.name,
                         ',,0:23,09-07-2025,08:30,08:53,"Login flow #JIRA-123",user,#JIRA-123\n')
        path.chmod(0o444)
        try:
            items, _ = build_data(path)
            self.assertEqual(len(items), 1)
        finally:
            path.chmod(0o644)


class TestSlotKeyAndFingerprint(unittest.TestCase):
    def test_slot_excludes_the_utc_offset(self):
        self.assertEqual(ledger.slot_key("2025-07-09T08:30:00.000+0200"), "2025-07-09T08:30")

    def test_identity_survives_a_timezone_change(self):
        # The whole point of hashing the slot: the same CSV row logged under a
        # different configured timezone must keep its identity.
        sast = create_datetime("09-07-2025", "08:30", timezone=JOHANNESBURG)
        london = create_datetime("09-07-2025", "08:30", timezone=ZoneInfo("Europe/London"))
        self.assertNotEqual(sast, london)
        self.assertEqual(
            ledger.fingerprint([1380, sast, "x", "JIRA-1"]),
            ledger.fingerprint([1380, london, "x", "JIRA-1"]),
        )

    def test_different_slot_differs(self):
        a = create_datetime("09-07-2025", "08:30", timezone=JOHANNESBURG)
        b = create_datetime("09-07-2025", "09:30", timezone=JOHANNESBURG)
        self.assertNotEqual(
            ledger.fingerprint([1380, a, "x", "JIRA-1"]),
            ledger.fingerprint([1380, b, "x", "JIRA-1"]),
        )

    def test_parts_helper_matches_item_fingerprint(self):
        started = create_datetime("09-07-2025", "08:30", timezone=JOHANNESBURG)
        self.assertEqual(
            ledger.fingerprint([1380, started, "x", "JIRA-1"]),
            ledger.fingerprint_from_parts("JIRA-1", "2025-07-09T08:30", 1380),
        )


if __name__ == "__main__":
    unittest.main()
