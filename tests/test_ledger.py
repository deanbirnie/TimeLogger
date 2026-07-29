import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app import ledger


# A work item is [time_spent_seconds, started, description, jira_issue].
ITEM_A = [1380, "2025-07-09T08:30:00.000+0000", "Testing the login flow", "JIRA-123"]
ITEM_B = [2700, "2025-07-10T10:00:00.000+0000", "Second task", "JIRA-456"]


class TestFingerprint(unittest.TestCase):
    def test_stable_across_calls(self):
        self.assertEqual(ledger.fingerprint(ITEM_A), ledger.fingerprint(list(ITEM_A)))

    def test_description_ignored(self):
        same_but_different_desc = [ITEM_A[0], ITEM_A[1], "totally different text", ITEM_A[3]]
        self.assertEqual(ledger.fingerprint(ITEM_A), ledger.fingerprint(same_but_different_desc))

    def test_issue_change_differs(self):
        other = [ITEM_A[0], ITEM_A[1], ITEM_A[2], "JIRA-999"]
        self.assertNotEqual(ledger.fingerprint(ITEM_A), ledger.fingerprint(other))

    def test_started_change_differs(self):
        other = [ITEM_A[0], "2025-07-09T09:30:00.000+0000", ITEM_A[2], ITEM_A[3]]
        self.assertNotEqual(ledger.fingerprint(ITEM_A), ledger.fingerprint(other))

    def test_duration_change_differs(self):
        other = [999, ITEM_A[1], ITEM_A[2], ITEM_A[3]]
        self.assertNotEqual(ledger.fingerprint(ITEM_A), ledger.fingerprint(other))


class TestLedgerIO(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "state" / "logged.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_load_missing_returns_empty(self):
        self.assertEqual(ledger.load_ledger(self.path), {})

    def test_load_corrupt_returns_empty(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{ this is not valid json", encoding="utf-8")
        self.assertEqual(ledger.load_ledger(self.path), {})

    def test_record_and_reload(self):
        book = {}
        ledger.record_logged(self.path, book, ITEM_A, "file.csv")
        self.assertTrue(self.path.exists())

        reloaded = ledger.load_ledger(self.path)
        self.assertIn(ledger.fingerprint(ITEM_A), reloaded)
        entry = reloaded[ledger.fingerprint(ITEM_A)]
        self.assertEqual(entry["issue"], "JIRA-123")
        self.assertEqual(entry["timeSpentSeconds"], 1380)
        self.assertEqual(entry["source"], "file.csv")

    def test_record_is_atomic_no_tmp_left(self):
        book = {}
        ledger.record_logged(self.path, book, ITEM_A)
        leftovers = list(self.path.parent.glob("*.tmp"))
        self.assertEqual(leftovers, [])

    def test_save_creates_parent_dirs(self):
        ledger.save_ledger(self.path, {"x": {"issue": "JIRA-1"}})
        self.assertTrue(self.path.exists())
        self.assertEqual(json.loads(self.path.read_text())["x"]["issue"], "JIRA-1")


class TestFilterNew(unittest.TestCase):
    def test_partitions_and_preserves_order(self):
        book = {ledger.fingerprint(ITEM_A): {"issue": "JIRA-123"}}
        new_items, already = ledger.filter_new(book, [ITEM_A, ITEM_B])
        self.assertEqual(already, [ITEM_A])
        self.assertEqual(new_items, [ITEM_B])

    def test_empty_ledger_all_new(self):
        new_items, already = ledger.filter_new({}, [ITEM_A, ITEM_B])
        self.assertEqual(new_items, [ITEM_A, ITEM_B])
        self.assertEqual(already, [])

    def test_is_logged(self):
        book = {ledger.fingerprint(ITEM_A): {}}
        self.assertTrue(ledger.is_logged(book, ITEM_A))
        self.assertFalse(ledger.is_logged(book, ITEM_B))


class TestArchive(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.src = self.root / "TimeFile.csv"
        self.src.write_text("some,csv,content\n", encoding="utf-8")
        self.archive_dir = self.root / "archive"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_copy_preserves_original(self):
        dest = ledger.archive_file(self.src, self.archive_dir,
                                   now=datetime(2026, 7, 29, 14, 3, 5))
        self.assertTrue(self.src.exists(), "source must be copied, not moved")
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_text(), self.src.read_text())

    def test_timestamp_prefixed_name(self):
        dest = ledger.archive_file(self.src, self.archive_dir,
                                   now=datetime(2026, 7, 29, 14, 3, 5))
        self.assertEqual(dest.name, "2026-07-29T14-03-05_TimeFile.csv")

    def test_creates_archive_dir(self):
        self.assertFalse(self.archive_dir.exists())
        ledger.archive_file(self.src, self.archive_dir)
        self.assertTrue(self.archive_dir.exists())

    def test_same_second_collision_does_not_overwrite(self):
        fixed = datetime(2026, 7, 29, 14, 3, 5)
        first = ledger.archive_file(self.src, self.archive_dir, now=fixed)
        second = ledger.archive_file(self.src, self.archive_dir, now=fixed)
        self.assertNotEqual(first, second)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        self.assertEqual(second.name, "2026-07-29T14-03-05_TimeFile_1.csv")
        self.assertEqual(len(list(self.archive_dir.glob("*.csv"))), 2)


class TestConfigPaths(unittest.TestCase):
    def _clear(self):
        for key in ("LEDGER_PATH", "ARCHIVE_DIR"):
            os.environ.pop(key, None)

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("LEDGER_PATH", "ARCHIVE_DIR")}
        self._clear()

    def tearDown(self):
        self._clear()
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v

    def test_default_ledger_path(self):
        self.assertEqual(ledger.get_ledger_path(), ledger.project_root() / "state" / "logged.json")

    def test_default_archive_dir(self):
        self.assertEqual(ledger.get_archive_dir(), ledger.project_root() / "archive")

    def test_env_override_ledger(self):
        os.environ["LEDGER_PATH"] = "/custom/led.json"
        self.assertEqual(ledger.get_ledger_path(), Path("/custom/led.json"))

    def test_env_override_archive(self):
        os.environ["ARCHIVE_DIR"] = "/custom/arch"
        self.assertEqual(ledger.get_archive_dir(), Path("/custom/arch"))


if __name__ == "__main__":
    unittest.main()
