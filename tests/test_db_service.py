"""
Unit tests for DatabaseService and cache_service.
All DB calls are mocked — no live database connection required.
"""

import unittest
from unittest.mock import MagicMock, patch, call
from contextlib import contextmanager

# Patch the pool init before importing the service so no real DB connection is attempted.
with patch("psycopg2.pool.ThreadedConnectionPool"):
    from src.services.db_service import DatabaseService, DC_LIST, _EMPTY_DC
from src.services import cache_service as cache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service() -> DatabaseService:
    """Return a DatabaseService instance with a mocked pool."""
    with patch("psycopg2.pool.ThreadedConnectionPool"):
        svc = DatabaseService()
    svc._pool = MagicMock()
    return svc


@contextmanager
def _mock_connection(cursor_mock):
    """Context manager that yields a mocked connection containing cursor_mock."""
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor_mock)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    yield conn


# ---------------------------------------------------------------------------
# CacheService tests
# ---------------------------------------------------------------------------

class TestCacheService(unittest.TestCase):

    def setUp(self):
        cache.clear()

    def test_set_and_get(self):
        cache.set("key1", {"data": 42})
        self.assertEqual(cache.get("key1"), {"data": 42})

    def test_get_missing_key_returns_none(self):
        self.assertIsNone(cache.get("nonexistent"))

    def test_delete_removes_key(self):
        cache.set("key2", "value")
        cache.delete("key2")
        self.assertIsNone(cache.get("key2"))

    def test_clear_flushes_all(self):
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        self.assertIsNone(cache.get("a"))
        self.assertIsNone(cache.get("b"))

    def test_stats_reflects_stored_keys(self):
        cache.set("x", 99)
        stats = cache.stats()
        self.assertIn("x", stats["keys"])
        self.assertEqual(stats["current_size"], 1)

    def test_cached_decorator_calls_fn_once(self):
        call_count = [0]

        @cache.cached(lambda val: f"test:{val}")
        def expensive(val):
            call_count[0] += 1
            return val * 2

        result1 = expensive(5)
        result2 = expensive(5)
        self.assertEqual(result1, 10)
        self.assertEqual(result2, 10)
        self.assertEqual(call_count[0], 1, "Function should only be called once (cache hit on second)")

    def test_cached_decorator_different_keys(self):
        call_count = [0]

        @cache.cached(lambda val: f"multi:{val}")
        def compute(val):
            call_count[0] += 1
            return val

        compute(1)
        compute(2)
        self.assertEqual(call_count[0], 2)


# ---------------------------------------------------------------------------
# DatabaseService — low-level helpers
# ---------------------------------------------------------------------------

class TestLowLevelHelpers(unittest.TestCase):

    def test_run_value_returns_first_column(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (42,)
        result = DatabaseService._run_value(cursor, "SELECT 42")
        self.assertEqual(result, 42)

    def test_run_value_returns_zero_on_empty(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        result = DatabaseService._run_value(cursor, "SELECT NULL")
        self.assertEqual(result, 0)

    def test_run_value_returns_zero_on_null_column(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (None,)
        result = DatabaseService._run_value(cursor, "SELECT NULL")
        self.assertEqual(result, 0)

    def test_run_row_returns_tuple(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (10, 20)
        result = DatabaseService._run_row(cursor, "SELECT 10, 20")
        self.assertEqual(result, (10, 20))

    def test_run_row_returns_none_on_empty(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        self.assertIsNone(DatabaseService._run_row(cursor, "SELECT 1"))

    def test_run_rows_returns_list(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [(1,), (2,), (3,)]
        result = DatabaseService._run_rows(cursor, "SELECT generate_series(1,3)")
        self.assertEqual(result, [(1,), (2,), (3,)])

    def test_run_rows_returns_empty_list_on_none(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = None
        self.assertEqual(DatabaseService._run_rows(cursor, "SELECT 1"), [])

    def test_run_value_handles_exception_gracefully(self):
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("DB error")
        result = DatabaseService._run_value(cursor, "BAD SQL")
        self.assertEqual(result, 0)

    def test_run_row_handles_exception_gracefully(self):
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("DB error")
        self.assertIsNone(DatabaseService._run_row(cursor, "BAD SQL"))

    def test_run_rows_handles_exception_gracefully(self):
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("DB error")
        self.assertEqual(DatabaseService._run_rows(cursor, "BAD SQL"), [])


# ---------------------------------------------------------------------------
# DatabaseService — _aggregate_dc
# ---------------------------------------------------------------------------

class TestAggregatedc(unittest.TestCase):

    def test_full_aggregation(self):
        result = DatabaseService._aggregate_dc(
            dc_code="DC11",
            nutanix_host_count=4,
            nutanix_mem=(2.0, 1.0),          # TB raw → ×1024 → GB
            nutanix_storage=(10.0, 5.0),     # TB raw
            nutanix_cpu=(100.0, 50.0),       # GHz raw
            vmware_counts=(3, 2, 20),
            vmware_mem=(1024 ** 3, 512 * (1024 ** 2)),  # bytes
            vmware_storage=(1024 ** 4, 512 * (1024 ** 3)),  # KB
            vmware_cpu=(2_000_000_000, 1_000_000_000),  # Hz
            power_hosts=2,
            racks_w=1000.0,   # W
            ibm_w=500.0,      # W
            vcenter_w=500.0,  # W
        )
        # Meta
        self.assertEqual(result["meta"]["name"], "DC11")
        self.assertEqual(result["meta"]["location"], "Istanbul")
        # Intel
        intel = result["intel"]
        self.assertEqual(intel["clusters"], 3)
        self.assertEqual(intel["hosts"], 6)  # 4 nutanix + 2 vmware
        self.assertEqual(intel["vms"], 20)
        # Memory: 2TB×1024 + 1GB = 2049 GB cap
        self.assertAlmostEqual(intel["ram_cap"], 2049.0, places=1)
        # CPU: 100 GHz + 2 GHz = 102 GHz
        self.assertAlmostEqual(intel["cpu_cap"], 102.0, places=1)
        # Storage: 10 TB + 1 TB = 11 TB
        self.assertAlmostEqual(intel["storage_cap"], 11.0, places=1)
        # Power
        self.assertEqual(result["power"]["hosts"], 2)
        # Energy: (1000+500+500)/1000 = 2.0 kW
        self.assertAlmostEqual(result["energy"]["total_kw"], 2.0, places=2)

    def test_none_inputs_default_to_zero(self):
        result = DatabaseService._aggregate_dc(
            dc_code="AZ11",
            nutanix_host_count=None,
            nutanix_mem=None,
            nutanix_storage=None,
            nutanix_cpu=None,
            vmware_counts=None,
            vmware_mem=None,
            vmware_storage=None,
            vmware_cpu=None,
            power_hosts=None,
            racks_w=None,
            ibm_w=None,
            vcenter_w=None,
        )
        self.assertEqual(result["intel"]["hosts"], 0)
        self.assertEqual(result["intel"]["cpu_cap"], 0.0)
        self.assertEqual(result["energy"]["total_kw"], 0.0)

    def test_location_fallback(self):
        result = DatabaseService._aggregate_dc(
            "DC14", 0, None, None, None, None, None, None, None, 0, 0, 0, 0
        )
        self.assertEqual(result["meta"]["location"], "Unknown Data Center")


# ---------------------------------------------------------------------------
# DatabaseService — get_dc_details (with cache and pool mocks)
# ---------------------------------------------------------------------------

class TestGetDcDetails(unittest.TestCase):

    def setUp(self):
        cache.clear()
        self.svc = _make_service()

    def _mock_cursor(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        cur.fetchall.return_value = []
        return cur

    def test_returns_dict_with_expected_keys(self):
        cur = self._mock_cursor()
        conn_mock = MagicMock()
        conn_mock.__enter__ = MagicMock(return_value=conn_mock)
        conn_mock.__exit__ = MagicMock(return_value=False)
        conn_mock.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn_mock.cursor.return_value.__exit__ = MagicMock(return_value=False)
        self.svc._pool.getconn.return_value = conn_mock

        result = self.svc.get_dc_details("DC11")
        self.assertIn("meta", result)
        self.assertIn("intel", result)
        self.assertIn("power", result)
        self.assertIn("energy", result)

    def test_cache_hit_skips_db(self):
        cache.set("dc_details:DC11", {"meta": {"name": "DC11"}, "cached": True})
        result = self.svc.get_dc_details("DC11")
        self.assertTrue(result.get("cached"))
        self.svc._pool.getconn.assert_not_called()

    def test_db_error_returns_empty_structure(self):
        from psycopg2 import OperationalError
        self.svc._pool.getconn.side_effect = OperationalError("timeout")
        result = self.svc.get_dc_details("DC11")
        self.assertEqual(result["intel"]["hosts"], 0)
        self.assertEqual(result["meta"]["name"], "DC11")

    def test_result_is_cached_after_fetch(self):
        cur = self._mock_cursor()
        conn_mock = MagicMock()
        conn_mock.__enter__ = MagicMock(return_value=conn_mock)
        conn_mock.__exit__ = MagicMock(return_value=False)
        conn_mock.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn_mock.cursor.return_value.__exit__ = MagicMock(return_value=False)
        self.svc._pool.getconn.return_value = conn_mock

        self.svc.get_dc_details("DC12")
        self.assertIsNotNone(cache.get("dc_details:DC12"))


# ---------------------------------------------------------------------------
# DatabaseService — get_all_datacenters_summary
# ---------------------------------------------------------------------------

class TestGetAllDatacentersSummary(unittest.TestCase):

    def setUp(self):
        cache.clear()
        self.svc = _make_service()

    def _mock_cursor_empty(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        cur.fetchall.return_value = []
        return cur

    def _attach_conn(self, cursor):
        conn_mock = MagicMock()
        conn_mock.__enter__ = MagicMock(return_value=conn_mock)
        conn_mock.__exit__ = MagicMock(return_value=False)
        conn_mock.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        conn_mock.cursor.return_value.__exit__ = MagicMock(return_value=False)
        self.svc._pool.getconn.return_value = conn_mock

    def test_returns_list_of_9_dcs(self):
        cur = self._mock_cursor_empty()
        self._attach_conn(cur)
        result = self.svc.get_all_datacenters_summary()
        self.assertEqual(len(result), 9)

    def test_each_item_has_required_keys(self):
        cur = self._mock_cursor_empty()
        self._attach_conn(cur)
        result = self.svc.get_all_datacenters_summary()
        for item in result:
            self.assertIn("id", item)
            self.assertIn("name", item)
            self.assertIn("stats", item)
            self.assertIn("host_count", item)
            self.assertIn("vm_count", item)

    def test_cached_result_skips_db(self):
        cached_summary = [{"id": dc, "name": dc} for dc in DC_LIST]
        cache.set("all_dc_summary", cached_summary)
        result = self.svc.get_all_datacenters_summary()
        self.svc._pool.getconn.assert_not_called()
        self.assertEqual(result, cached_summary)

    def test_db_error_returns_empty_dcs(self):
        from psycopg2 import OperationalError
        self.svc._pool.getconn.side_effect = OperationalError("down")
        result = self.svc.get_all_datacenters_summary()
        self.assertEqual(len(result), 9)
        for item in result:
            self.assertEqual(item["host_count"], 0)


# ---------------------------------------------------------------------------
# DatabaseService — get_global_overview
# ---------------------------------------------------------------------------

class TestGetGlobalOverview(unittest.TestCase):

    def setUp(self):
        cache.clear()
        self.svc = _make_service()

    def test_returns_aggregated_totals(self):
        mock_summary = [
            {"host_count": 10, "vm_count": 50, "stats": {"total_energy_kw": 5.0}},
            {"host_count": 5,  "vm_count": 30, "stats": {"total_energy_kw": 3.0}},
        ]
        cache.set("all_dc_summary", mock_summary)
        result = self.svc.get_global_overview()
        self.assertEqual(result["total_hosts"], 15)
        self.assertEqual(result["total_vms"], 80)
        self.assertAlmostEqual(result["total_energy_kw"], 8.0)
        self.assertEqual(result["dc_count"], 2)

    def test_cached_global_overview_skips_db(self):
        cache.set("global_overview", {"total_hosts": 99})
        result = self.svc.get_global_overview()
        self.assertEqual(result["total_hosts"], 99)


# ---------------------------------------------------------------------------
# Query module integrity checks
# ---------------------------------------------------------------------------

class TestQueryModules(unittest.TestCase):

    def test_nutanix_queries_are_strings(self):
        from src.queries import nutanix
        for attr in ["HOST_COUNT", "MEMORY", "STORAGE", "CPU",
                     "BATCH_HOST_COUNT", "BATCH_MEMORY", "BATCH_STORAGE", "BATCH_CPU"]:
            self.assertIsInstance(getattr(nutanix, attr), str, f"nutanix.{attr} should be a string")

    def test_vmware_queries_are_strings(self):
        from src.queries import vmware
        for attr in ["COUNTS", "MEMORY", "STORAGE", "CPU",
                     "BATCH_COUNTS", "BATCH_MEMORY", "BATCH_STORAGE", "BATCH_CPU"]:
            self.assertIsInstance(getattr(vmware, attr), str, f"vmware.{attr} should be a string")

    def test_ibm_queries_are_strings(self):
        from src.queries import ibm
        for attr in ["HOST_COUNT", "BATCH_HOST_COUNT"]:
            self.assertIsInstance(getattr(ibm, attr), str, f"ibm.{attr} should be a string")

    def test_energy_queries_are_strings(self):
        from src.queries import energy
        for attr in ["RACKS", "IBM", "VCENTER", "BATCH_RACKS", "BATCH_IBM", "BATCH_VCENTER"]:
            self.assertIsInstance(getattr(energy, attr), str, f"energy.{attr} should be a string")

    def test_registry_has_all_expected_keys(self):
        from src.queries.registry import QUERY_REGISTRY
        expected_keys = [
            "nutanix_host_count", "nutanix_memory", "nutanix_storage", "nutanix_cpu",
            "vmware_counts", "vmware_memory", "vmware_storage", "vmware_cpu",
            "ibm_host_count",
            "energy_racks", "energy_ibm", "energy_vcenter",
        ]
        for key in expected_keys:
            self.assertIn(key, QUERY_REGISTRY, f"Registry missing key: {key}")

    def test_registry_entries_have_required_fields(self):
        from src.queries.registry import QUERY_REGISTRY
        required_fields = {"sql", "source", "result_type", "params_style", "provider"}
        for key, entry in QUERY_REGISTRY.items():
            for field in required_fields:
                self.assertIn(field, entry, f"Registry entry '{key}' missing field '{field}'")

    def test_queries_contain_placeholder(self):
        """All individual queries must use %s for parameterization."""
        from src.queries import nutanix, vmware, ibm, energy
        for sql in [nutanix.HOST_COUNT, nutanix.MEMORY, vmware.COUNTS, ibm.HOST_COUNT, energy.IBM]:
            self.assertIn("%s", sql, "Query must use %s parameter placeholder")


# ---------------------------------------------------------------------------
# DC_LIST completeness
# ---------------------------------------------------------------------------

class TestDcList(unittest.TestCase):

    def test_dc_list_has_9_entries(self):
        self.assertEqual(len(DC_LIST), 9)

    def test_dc_list_contains_expected_codes(self):
        expected = {"AZ11", "DC11", "DC12", "DC13", "DC14", "DC15", "DC16", "DC17", "ICT11"}
        self.assertEqual(set(DC_LIST), expected)


if __name__ == "__main__":
    unittest.main()
