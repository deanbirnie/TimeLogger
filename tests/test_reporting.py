import unittest
from unittest.mock import MagicMock

from app.time_logger import (
    REPORT_WIDTH,
    classify_items,
    describe_failure,
    format_duration,
    format_started,
    render_items,
    render_report,
    render_section,
)


# A work item is [time_spent_seconds, started, description, jira_issue].
ITEM_A = [1380, "2025-07-09T08:30:00.000+0200", "Testing the login flow", "JIRA-123"]
ITEM_B = [5700, "2025-07-09T09:30:00.000+0200", "Fixing the CSV import bug", "JIRA-789"]
UNTAGGED = [900, "2025-07-09T11:00:00.000+0200", "Made coffee", "untagged"]


class TestFormatDuration(unittest.TestCase):
    def test_under_an_hour(self):
        self.assertEqual(format_duration(1380), "23m")

    def test_exactly_an_hour(self):
        self.assertEqual(format_duration(3600), "1h 00m")

    def test_over_an_hour_pads_minutes(self):
        self.assertEqual(format_duration(5700), "1h 35m")

    def test_zero(self):
        self.assertEqual(format_duration(0), "0m")

    def test_no_trailing_decimal(self):
        # The old output rendered 23.0m; durations are whole minutes.
        self.assertNotIn(".", format_duration(1380))


class TestFormatStarted(unittest.TestCase):
    def test_trims_to_date_and_hhmm(self):
        self.assertEqual(format_started("2025-07-09T08:30:00.000+0200"), "2025-07-09 08:30")

    def test_tolerates_malformed_hour(self):
        # B2/B3 can emit unpadded or negative hours; display must not explode.
        self.assertEqual(format_started("2025-07-09T7:30:00.000+0000"), "2025-07-09 7:30")
        self.assertEqual(format_started("2025-07-09T-1:30:00.000+0000"), "2025-07-09 -1:30")

    def test_empty_and_dateless(self):
        self.assertEqual(format_started(""), "")
        self.assertEqual(format_started(None), "")
        self.assertEqual(format_started("2025-07-09"), "2025-07-09")


class TestClassifyItems(unittest.TestCase):
    def test_splits_valid_and_invalid(self):
        valid, invalid = classify_items([ITEM_A, UNTAGGED, ITEM_B])
        self.assertEqual(valid, [ITEM_A, ITEM_B])
        self.assertEqual(invalid, [UNTAGGED])

    def test_zero_duration_is_invalid(self):
        valid, invalid = classify_items([[0, ITEM_A[1], "x", "JIRA-1"]])
        self.assertEqual(valid, [])
        self.assertEqual(len(invalid), 1)

    def test_empty_description_is_invalid(self):
        valid, _ = classify_items([[60, ITEM_A[1], "", "JIRA-1"]])
        self.assertEqual(valid, [])

    def test_missing_started_is_invalid(self):
        valid, _ = classify_items([[60, None, "x", "JIRA-1"]])
        self.assertEqual(valid, [])

    def test_non_int_duration_is_invalid_not_an_error(self):
        # Guards the ordering of the type check before the <= 0 comparison,
        # which would otherwise raise TypeError (BUGS.md B11).
        valid, invalid = classify_items([["1380", ITEM_A[1], "x", "JIRA-1"]])
        self.assertEqual(valid, [])
        self.assertEqual(len(invalid), 1)


class TestRenderItems(unittest.TestCase):
    def test_empty_renders_nothing(self):
        self.assertEqual(render_items([]), [])

    def test_columns_align_across_rows(self):
        lines = render_items([ITEM_A, ITEM_B])
        # Issue keys differ in length; the duration column must still line up.
        self.assertEqual(lines[0].index("23m") + len("23m"),
                         lines[1].index("1h 35m") + len("1h 35m"))

    def test_long_description_truncated_with_ellipsis(self):
        long_item = [1380, ITEM_A[1], "x" * 200, "JIRA-1"]
        line = render_items([long_item])[0]
        self.assertTrue(line.endswith("…"))
        self.assertLessEqual(len(line), REPORT_WIDTH)

    def test_short_rows_stay_within_width(self):
        for line in render_items([ITEM_A, ITEM_B]):
            self.assertLessEqual(len(line), REPORT_WIDTH)


class TestRenderSection(unittest.TestCase):
    def test_empty_section_renders_nothing(self):
        self.assertEqual(render_section("TO LOG", []), [])

    def test_heading_includes_count_and_note(self):
        lines = render_section("TO LOG", [ITEM_A], note="total 23m")
        self.assertEqual(lines[0], "TO LOG (1)  -  total 23m")


class TestRenderReport(unittest.TestCase):
    def test_each_item_appears_exactly_once(self):
        report = render_report("TimeFile.csv", [UNTAGGED], [ITEM_A], [ITEM_B])
        self.assertEqual(report.count("JIRA-123"), 1)
        self.assertEqual(report.count("JIRA-789"), 1)
        self.assertEqual(report.count("untagged"), 1)

    def test_omits_empty_sections(self):
        report = render_report("TimeFile.csv", [], [], [ITEM_A])
        self.assertNotIn("INVALID", report)
        self.assertNotIn("ALREADY LOGGED", report)
        self.assertIn("TO LOG", report)

    def test_shows_total_for_items_to_log(self):
        report = render_report("TimeFile.csv", [], [], [ITEM_A, ITEM_B])
        self.assertIn("total 1h 58m", report)

    def test_includes_source_name(self):
        self.assertIn("TimeFile.csv", render_report("TimeFile.csv", [], [], [ITEM_A]))


class TestDescribeFailure(unittest.TestCase):
    def _response(self, payload=None, text="", raises=False):
        response = MagicMock()
        if raises:
            response.json.side_effect = ValueError("not json")
        else:
            response.json.return_value = payload
        response.text = text
        return response

    def test_extracts_error_messages(self):
        reason = describe_failure(self._response({"errorMessages": ["Issue does not exist"]}))
        self.assertEqual(reason, "Issue does not exist")

    def test_extracts_field_errors(self):
        reason = describe_failure(self._response({"errorMessages": [], "errors": {"timeSpentSeconds": "must be > 0"}}))
        self.assertEqual(reason, "timeSpentSeconds: must be > 0")

    def test_falls_back_to_raw_text(self):
        reason = describe_failure(self._response(text="502 Bad Gateway", raises=True))
        self.assertEqual(reason, "502 Bad Gateway")

    def test_empty_body(self):
        self.assertEqual(describe_failure(self._response(text="", raises=True)), "no response body")

    def test_is_single_line(self):
        reason = describe_failure(self._response(text="line one\nline two", raises=True))
        self.assertNotIn("\n", reason)


if __name__ == "__main__":
    unittest.main()
