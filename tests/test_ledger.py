import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pymysql

from app import ledger


# A work item is [time_spent_seconds, started, description, jira_issue].
ITEM_A = [1380, "2025-07-09T08:30:00.000+0000", "Testing the login flow", "JIRA-123"]
ITEM_B = [2700, "2025-07-10T10:00:00.000+0000", "Second task", "JIRA-456"]


def _fake_conn(fetchall_rows=None):
    """A MagicMock standing in for a pymysql connection, supporting the
    ``with conn.cursor() as cursor:`` pattern used throughout ledger.py."""
    cursor = MagicMock()
    cursor.fetchall.return_value = fetchall_rows or []
    cursor.rowcount = 1
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn, cursor


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


class TestConnect(unittest.TestCase):
    def test_raises_clear_error_when_unreachable(self):
        with patch("app.ledger.pymysql.connect", side_effect=pymysql.OperationalError("boom")):
            with self.assertRaises(ledger.DatabaseConnectionError) as cm:
                ledger.connect()
        self.assertIn("DB connection failed", str(cm.exception))

    def test_returns_connection_on_success(self):
        fake = MagicMock()
        with patch("app.ledger.pymysql.connect", return_value=fake) as mock_connect:
            result = ledger.connect()
        self.assertIs(result, fake)
        self.assertTrue(mock_connect.call_args.kwargs.get("autocommit"))


class TestGetDbConfig(unittest.TestCase):
    ENV_KEYS = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in self.ENV_KEYS}
        for k in self.ENV_KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_reads_env_vars(self):
        os.environ["DB_HOST"] = "dbhost"
        os.environ["DB_PORT"] = "3307"
        os.environ["DB_NAME"] = "tl"
        os.environ["DB_USER"] = "tluser"
        os.environ["DB_PASSWORD"] = "secret"
        config = ledger.get_db_config()
        self.assertEqual(config, {
            "host": "dbhost", "port": 3307, "database": "tl",
            "user": "tluser", "password": "secret",
        })

    def test_defaults_port_to_3306(self):
        os.environ["DB_HOST"] = "dbhost"
        config = ledger.get_db_config()
        self.assertEqual(config["port"], 3306)


class TestLoadLedger(unittest.TestCase):
    def test_builds_dict_keyed_by_fingerprint(self):
        fp = ledger.fingerprint(ITEM_A)
        logged_at = datetime(2026, 7, 29, 18, 28, 41)
        conn, cursor = _fake_conn(fetchall_rows=[
            (fp, "JIRA-123", ITEM_A[1], 1380, "Testing the login flow", "file.csv", logged_at),
        ])
        result = ledger.load_ledger(conn)
        self.assertEqual(list(result.keys()), [fp])
        self.assertEqual(result[fp]["issue"], "JIRA-123")
        self.assertEqual(result[fp]["timeSpentSeconds"], 1380)
        self.assertEqual(result[fp]["logged_at"], "2026-07-29T18:28:41")

    def test_empty_table_returns_empty_dict(self):
        conn, _cursor = _fake_conn(fetchall_rows=[])
        self.assertEqual(ledger.load_ledger(conn), {})


class TestRecordLogged(unittest.TestCase):
    def test_inserts_and_updates_in_memory_ledger(self):
        conn, cursor = _fake_conn()
        book = {}
        ledger.record_logged(conn, book, ITEM_A, "file.csv")

        cursor.execute.assert_called_once()
        sql, params = cursor.execute.call_args.args
        self.assertIn("INSERT IGNORE INTO logged_worklogs", sql)
        self.assertEqual(params[0], ledger.fingerprint(ITEM_A))
        self.assertEqual(params[1], "JIRA-123")
        self.assertEqual(params[3], 1380)
        # A tz-aware logged_at would break MySQL's DATETIME column.
        self.assertIsNone(params[6].tzinfo)

        self.assertIn(ledger.fingerprint(ITEM_A), book)
        self.assertEqual(book[ledger.fingerprint(ITEM_A)]["issue"], "JIRA-123")


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


class TestLegacyJsonLedger(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "logged.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_missing_file_returns_empty(self):
        self.assertEqual(ledger.load_legacy_json_ledger(self.path), {})

    def test_corrupt_file_returns_empty(self):
        self.path.write_text("{ not valid json", encoding="utf-8")
        self.assertEqual(ledger.load_legacy_json_ledger(self.path), {})

    def test_reads_existing_entries(self):
        self.path.write_text(json.dumps({"abc123": {"issue": "JIRA-1"}}), encoding="utf-8")
        result = ledger.load_legacy_json_ledger(self.path)
        self.assertEqual(result, {"abc123": {"issue": "JIRA-1"}})


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
        os.environ.pop("ARCHIVE_DIR", None)

    def setUp(self):
        self._saved = os.environ.get("ARCHIVE_DIR")
        self._clear()

    def tearDown(self):
        self._clear()
        if self._saved is not None:
            os.environ["ARCHIVE_DIR"] = self._saved

    def test_default_archive_dir(self):
        self.assertEqual(ledger.get_archive_dir(), ledger.project_root() / "archive")

    def test_env_override_archive(self):
        os.environ["ARCHIVE_DIR"] = "/custom/arch"
        self.assertEqual(ledger.get_archive_dir(), Path("/custom/arch"))


if __name__ == "__main__":
    unittest.main()
