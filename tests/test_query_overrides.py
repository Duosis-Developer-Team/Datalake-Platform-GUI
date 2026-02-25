"""
Unit tests for query_overrides and execute_registered_query.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.queries.registry import QUERY_REGISTRY


class TestQueryOverrides(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        self.tmp.write("{}")
        self.tmp.close()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp_path.unlink(missing_ok=True)

    @patch("src.services.query_overrides._OVERRIDES_PATH", new_callable=lambda: None)
    def _patch_path(self, path_mock):
        # Allow test to set _OVERRIDES_PATH to self.tmp_path
        with patch.object(Path, "__new__", return_value=self.tmp_path):
            pass

    def test_load_overrides_empty_file(self):
        with patch("src.services.query_overrides._OVERRIDES_PATH", self.tmp_path):
            from src.services.query_overrides import load_overrides
            self.assertEqual(load_overrides(), {})

    def test_load_overrides_with_data(self):
        data = {"energy_racks": {"sql": "SELECT 1"}}
        self.tmp_path.write_text(json.dumps(data), encoding="utf-8")
        with patch("src.services.query_overrides._OVERRIDES_PATH", self.tmp_path):
            from src.services.query_overrides import load_overrides
            self.assertEqual(load_overrides(), data)

    def test_get_merged_entry_registry_key(self):
        with patch("src.services.query_overrides._OVERRIDES_PATH", self.tmp_path):
            from src.services.query_overrides import get_merged_entry
            entry = get_merged_entry("energy_racks")
            self.assertIsNotNone(entry)
            self.assertIn("sql", entry)
            self.assertEqual(entry.get("params_style"), "exact")
            self.assertEqual(entry.get("result_type"), "value")

    def test_get_merged_entry_unknown_key_no_override(self):
        with patch("src.services.query_overrides._OVERRIDES_PATH", self.tmp_path):
            from src.services.query_overrides import get_merged_entry
            self.assertIsNone(get_merged_entry("nonexistent_key_xyz"))

    def test_get_merged_entry_custom_key_in_overrides(self):
        data = {"custom_q": {"sql": "SELECT 2", "result_type": "value", "params_style": "wildcard"}}
        self.tmp_path.write_text(json.dumps(data), encoding="utf-8")
        with patch("src.services.query_overrides._OVERRIDES_PATH", self.tmp_path):
            from src.services.query_overrides import get_merged_entry
            entry = get_merged_entry("custom_q")
            self.assertIsNotNone(entry)
            self.assertEqual(entry["sql"], "SELECT 2")
            self.assertEqual(entry["result_type"], "value")
            self.assertEqual(entry["params_style"], "wildcard")

    def test_list_all_query_keys_includes_registry(self):
        with patch("src.services.query_overrides._OVERRIDES_PATH", self.tmp_path):
            from src.services.query_overrides import list_all_query_keys
            keys = list_all_query_keys()
            self.assertIn("energy_racks", keys)
            self.assertIn("nutanix_host_count", keys)

    def test_set_and_remove_override(self):
        with patch("src.services.query_overrides._OVERRIDES_PATH", self.tmp_path):
            from src.services.query_overrides import load_overrides, set_override, remove_override, get_merged_entry
            set_override("energy_racks", "SELECT 999", source="loki_racks")
            overrides = load_overrides()
            self.assertIn("energy_racks", overrides)
            self.assertEqual(overrides["energy_racks"]["sql"], "SELECT 999")
            entry = get_merged_entry("energy_racks")
            self.assertEqual(entry["sql"], "SELECT 999")
            removed = remove_override("energy_racks")
            self.assertTrue(removed)
            overrides2 = load_overrides()
            self.assertNotIn("energy_racks", overrides2)
            self.assertFalse(remove_override("energy_racks"))


class TestPrepareParams(unittest.TestCase):

    def test_wildcard(self):
        with patch("psycopg2.pool.ThreadedConnectionPool"):
            from src.services.db_service import DatabaseService
            out = DatabaseService._prepare_params("wildcard", "DC11")
            self.assertEqual(out, ("%DC11%",))

    def test_exact(self):
        with patch("psycopg2.pool.ThreadedConnectionPool"):
            from src.services.db_service import DatabaseService
            out = DatabaseService._prepare_params("exact", "AZ11")
            self.assertEqual(out, ("AZ11",))

    def test_array_exact(self):
        with patch("psycopg2.pool.ThreadedConnectionPool"):
            from src.services.db_service import DatabaseService
            out = DatabaseService._prepare_params("array_exact", "DC11, DC12")
            self.assertEqual(out, (["DC11", "DC12"],))

    def test_array_wildcard(self):
        with patch("psycopg2.pool.ThreadedConnectionPool"):
            from src.services.db_service import DatabaseService
            out = DatabaseService._prepare_params("array_wildcard", "DC11,DC12")
            self.assertEqual(out, (["%DC11%", "%DC12%"],))


class TestExecuteRegisteredQuery(unittest.TestCase):

    def setUp(self):
        from unittest.mock import patch
        with patch("psycopg2.pool.ThreadedConnectionPool"):
            from src.services.db_service import DatabaseService
            self.svc = DatabaseService()
        self.svc._pool = MagicMock()

    def test_unknown_key_returns_error(self):
        with patch("src.services.db_service.qo.get_merged_entry", return_value=None):
            result = self.svc.execute_registered_query("unknown_key", "")
        self.assertIn("error", result)

    def test_execute_returns_value_result(self):
        with patch("src.services.db_service.qo.get_merged_entry") as m:
            m.return_value = {
                "sql": "SELECT 42",
                "result_type": "value",
                "params_style": "exact",
            }
            conn = MagicMock()
            cur = MagicMock()
            cur.description = [("col",)]
            cur.fetchone.return_value = (42,)
            conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
            conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            self.svc._pool.getconn.return_value = conn

            result = self.svc.execute_registered_query("test", "x")
            self.assertEqual(result.get("result_type"), "value")
            self.assertEqual(result.get("value"), 42)

    def test_execute_returns_row_result(self):
        with patch("src.services.db_service.qo.get_merged_entry") as m:
            m.return_value = {
                "sql": "SELECT a, b",
                "result_type": "row",
                "params_style": "exact",
            }
            conn = MagicMock()
            cur = MagicMock()
            cur.description = [("a",), ("b",)]
            cur.fetchone.return_value = (10, 20)
            conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
            conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            self.svc._pool.getconn.return_value = conn

            result = self.svc.execute_registered_query("test", "x")
            self.assertEqual(result.get("result_type"), "row")
            self.assertEqual(result.get("columns"), ["a", "b"])
            self.assertEqual(result.get("data"), [10, 20])

    def test_execute_returns_rows_result(self):
        with patch("src.services.db_service.qo.get_merged_entry") as m:
            m.return_value = {
                "sql": "SELECT id",
                "result_type": "rows",
                "params_style": "exact",
            }
            conn = MagicMock()
            cur = MagicMock()
            cur.description = [("id",)]
            cur.fetchall.return_value = [(1,), (2,)]
            conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
            conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            self.svc._pool.getconn.return_value = conn

            result = self.svc.execute_registered_query("test", "x")
            self.assertEqual(result.get("result_type"), "rows")
            self.assertEqual(result.get("columns"), ["id"])
            self.assertEqual(result.get("data"), [[1], [2]])

    def test_execute_db_error_returns_error_dict(self):
        from psycopg2 import OperationalError
        with patch("src.services.db_service.qo.get_merged_entry") as m:
            m.return_value = {"sql": "SELECT 1", "result_type": "value", "params_style": "exact"}
            self.svc._pool.getconn.side_effect = OperationalError("connection failed")
            result = self.svc.execute_registered_query("test", "x")
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
