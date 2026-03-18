"""
Unit tests for DatabaseService and cache_service.
All DB calls are mocked — no live database connection required.
"""

import unittest
from unittest.mock import MagicMock, patch, call
from contextlib import contextmanager

# Patch the pool init before importing the service so no real DB connection is attempted.
with patch("psycopg2.pool.ThreadedConnectionPool"):
    from src.services.db_service import (
        DatabaseService, _EMPTY_DC, _FALLBACK_DC_LIST
    )
from src.services import cache_service as cache
from src.utils.time_range import default_time_range, cache_time_ranges

# Alias for backward compatibility in existing tests
DC_LIST = _FALLBACK_DC_LIST


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
            nutanix_vms=10,
            nutanix_mem=(2.0, 1.0),          # TB raw → ×1024 → GB
            nutanix_storage=(10.0, 5.0),     # TB raw
            nutanix_cpu=(100.0, 50.0),       # GHz raw
            vmware_counts=(3, 2, 20),
            vmware_mem=(1024 ** 3, 512 * (1024 ** 2)),  # bytes
            vmware_storage=(1024 ** 4, 512 * (1024 ** 3)),  # KB
            vmware_cpu=(2_000_000_000, 1_000_000_000),  # Hz
            power_hosts=2,
            power_vios=1,
            power_lpar_count=5,
            power_mem=(64.0, 32.0),
            power_cpu=(4.0, 2.0, 8.0),
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
        # No classic_row → cl_vms=0; intel.vms = cl_vms(0) + nutanix_vms(10) = 10
        self.assertEqual(intel["vms"], 10)
        # Power
        self.assertEqual(result["power"]["hosts"], 2)
        self.assertEqual(result["power"]["vios"], 1)
        self.assertEqual(result["power"]["lpar_count"], 5)
        self.assertAlmostEqual(result["power"]["memory_total"], 64.0, places=1)
        self.assertAlmostEqual(result["power"]["cpu_assigned"], 8.0, places=1)
        # Platforms
        self.assertIn("platforms", result)
        self.assertEqual(result["platforms"]["nutanix"]["hosts"], 4)
        self.assertEqual(result["platforms"]["nutanix"]["vms"], 10)
        self.assertEqual(result["platforms"]["ibm"]["lpars"], 5)
        # Energy: (500+500)/1000 = 1.0 kW (IBM + vCenter only)
        self.assertAlmostEqual(result["energy"]["total_kw"], 1.0, places=2)
        self.assertAlmostEqual(result["energy"]["ibm_kw"], 0.5, places=2)
        self.assertAlmostEqual(result["energy"]["vcenter_kw"], 0.5, places=2)

    def test_none_inputs_default_to_zero(self):
        result = DatabaseService._aggregate_dc(
            dc_code="AZ11",
            nutanix_host_count=None,
            nutanix_vms=None,
            nutanix_mem=None,
            nutanix_storage=None,
            nutanix_cpu=None,
            vmware_counts=None,
            vmware_mem=None,
            vmware_storage=None,
            vmware_cpu=None,
            power_hosts=None,
            power_vios=None,
            power_lpar_count=None,
            power_mem=None,
            power_cpu=None,
            ibm_w=None,
            vcenter_w=None,
        )
        self.assertEqual(result["intel"]["hosts"], 0)
        self.assertEqual(result["intel"]["cpu_cap"], 0.0)
        self.assertEqual(result["energy"]["total_kw"], 0.0)
        self.assertIn("platforms", result)

    def test_location_fallback(self):
        result = DatabaseService._aggregate_dc(
            "DC14",
            nutanix_host_count=0,
            nutanix_vms=0,
            nutanix_mem=None,
            nutanix_storage=None,
            nutanix_cpu=None,
            vmware_counts=None,
            vmware_mem=None,
            vmware_storage=None,
            vmware_cpu=None,
            power_hosts=0,
            power_vios=0,
            power_lpar_count=0,
            power_mem=None,
            power_cpu=None,
            ibm_w=0,
            vcenter_w=0,
        )
        # DC14 is present in DC_LOCATIONS mapping, so location should resolve.
        self.assertEqual(result["meta"]["location"], "Ankara")


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
        self.assertIn("platforms", result)

    def test_cache_hit_skips_db(self):
        tr = default_time_range()
        cache.set(f"dc_details:DC11:{tr.get('start','')}:{tr.get('end','')}", {"meta": {"name": "DC11"}, "cached": True})
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

        tr = default_time_range()
        self.svc.get_dc_details("DC12")
        self.assertIsNotNone(cache.get(f"dc_details:DC12:{tr.get('start','')}:{tr.get('end','')}"))

    def test_dc_details_uses_aggregate_dc_directly(self):
        """get_dc_details should use _aggregate_dc values without dedup override."""
        cur = self._mock_cursor()
        conn_mock = MagicMock()
        conn_mock.__enter__ = MagicMock(return_value=conn_mock)
        conn_mock.__exit__ = MagicMock(return_value=False)
        conn_mock.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn_mock.cursor.return_value.__exit__ = MagicMock(return_value=False)
        self.svc._pool.getconn.return_value = conn_mock

        base_dc = _EMPTY_DC("DC11")
        base_dc["intel"]["vms"] = 10

        with patch.object(
            DatabaseService,
            "_aggregate_dc",
            return_value=base_dc,
        ) as mock_agg:
            result = self.svc.get_dc_details("DC11")

        mock_agg.assert_called_once()
        self.assertEqual(result["intel"]["vms"], 10)


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

    def test_each_item_has_required_keys(self):
        dc_codes = _FALLBACK_DC_LIST
        empty_data = {dc: _EMPTY_DC(dc) for dc in dc_codes}
        for dc in dc_codes:
            empty_data[dc]["intel"]["hosts"] = 1

        def _fake_batch(cursor, dc_list, start_ts, end_ts):
            return empty_data, {dc: 1 for dc in dc_list}

        with patch.object(self.svc, "_fetch_all_batch", side_effect=_fake_batch):
            result = self.svc.get_all_datacenters_summary()
        for item in result:
            self.assertIn("id", item)
            self.assertIn("name", item)
            self.assertIn("stats", item)
            self.assertIn("host_count", item)
            self.assertIn("vm_count", item)

    def test_cached_result_skips_db(self):
        tr = default_time_range()
        cached_summary = [{"id": dc, "name": dc} for dc in DC_LIST]
        cache.set(f"all_dc_summary:{tr.get('start','')}:{tr.get('end','')}", cached_summary)
        result = self.svc.get_all_datacenters_summary()
        self.svc._pool.getconn.assert_not_called()
        self.assertEqual(result, cached_summary)

    def test_rebuild_summary_uses_aggregate_vm_count(self):
        """_rebuild_summary should use _aggregate_dc intel['vms'] directly in vm_count."""
        dc_code = "DC11"

        base_dc = _EMPTY_DC(dc_code)
        base_dc["intel"]["vms"] = 15
        base_dc["intel"]["hosts"] = 3
        platform_counts = {code: 1 for code in DC_LIST}

        def _fake_fetch_all_batch(cursor, dc_list, start_ts, end_ts):
            all_dc_data = {code: (base_dc if code == dc_code else _EMPTY_DC(code)) for code in dc_list}
            return all_dc_data, platform_counts

        with patch.object(
            self.svc,
            "_fetch_all_batch",
            side_effect=_fake_fetch_all_batch,
        ) as mock_fetch:
            result = self.svc._rebuild_summary(default_time_range())

        mock_fetch.assert_called_once()
        dc_summary = next(item for item in result if item["id"] == dc_code)
        self.assertEqual(dc_summary["vm_count"], 15)

    def test_rebuild_summary_host_count_uses_classic_hyperconv_and_power(self):
        """host_count must be derived from classic.hosts + hyperconv.hosts + power.hosts."""
        dc_code = "DC11"

        base_dc = _EMPTY_DC(dc_code)
        base_dc["classic"] = {"hosts": 10}
        base_dc["hyperconv"] = {"hosts": 5}
        base_dc["power"]["hosts"] = 2
        # intel.hosts should not affect the final host_count
        base_dc["intel"]["hosts"] = 999

        platform_counts = {code: 1 for code in DC_LIST}

        def _fake_fetch_all_batch(cursor, dc_list, start_ts, end_ts):
            all_dc_data = {code: (base_dc if code == dc_code else _EMPTY_DC(code)) for code in dc_list}
            return all_dc_data, platform_counts

        with patch.object(
            self.svc,
            "_fetch_all_batch",
            side_effect=_fake_fetch_all_batch,
        ):
            result = self.svc._rebuild_summary(default_time_range())

        dc_summary = next(item for item in result if item["id"] == dc_code)
        self.assertEqual(dc_summary["host_count"], 17)

    def test_rebuild_summary_vm_count_uses_intel_vms_plus_power_lpars(self):
        """vm_count must be intel.vms + power.lpar_count."""
        dc_code = "DC11"

        base_dc = _EMPTY_DC(dc_code)
        base_dc["intel"]["vms"] = 80
        base_dc["power"]["lpar_count"] = 20

        platform_counts = {code: 1 for code in DC_LIST}

        def _fake_fetch_all_batch(cursor, dc_list, start_ts, end_ts):
            all_dc_data = {code: (base_dc if code == dc_code else _EMPTY_DC(code)) for code in dc_list}
            return all_dc_data, platform_counts

        with patch.object(
            self.svc,
            "_fetch_all_batch",
            side_effect=_fake_fetch_all_batch,
        ):
            result = self.svc._rebuild_summary(default_time_range())

        dc_summary = next(item for item in result if item["id"] == dc_code)
        self.assertEqual(dc_summary["vm_count"], 100)

    def test_rebuild_summary_filters_out_fully_empty_dcs(self):
        """Datacenters with both host_count and vm_count equal to 0 should be excluded from the summary."""
        dc_codes = ["DC_A", "DC_B", "DC_C"]

        dc_a = _EMPTY_DC("DC_A")
        # Non-empty host_count via classic hosts
        dc_a["classic"] = {"hosts": 1}
        dc_a["intel"]["vms"] = 0

        dc_b = _EMPTY_DC("DC_B")
        # Non-empty vm_count via Power LPARs
        dc_b["power"]["lpar_count"] = 2
        dc_b["intel"]["vms"] = 0

        dc_c = _EMPTY_DC("DC_C")

        platform_counts = {code: 0 for code in dc_codes}

        def _fake_fetch_all_batch(cursor, dc_list, start_ts, end_ts):
            return {"DC_A": dc_a, "DC_B": dc_b, "DC_C": dc_c}, platform_counts

        with patch.object(
            self.svc,
            "_fetch_all_batch",
            side_effect=_fake_fetch_all_batch,
        ) as mock_fetch, patch.object(
            self.svc,
            "_load_dc_list",
            return_value=dc_codes,
        ):
            result = self.svc._rebuild_summary(default_time_range())

        mock_fetch.assert_called_once()

        ids = {item["id"] for item in result}
        self.assertIn("DC_A", ids)
        self.assertIn("DC_B", ids)
        self.assertNotIn("DC_C", ids)


# ---------------------------------------------------------------------------
# DatabaseService — get_global_overview
# ---------------------------------------------------------------------------

class TestGetGlobalOverview(unittest.TestCase):

    def setUp(self):
        cache.clear()
        self.svc = _make_service()

    def test_returns_aggregated_totals(self):
        tr = default_time_range()
        mock_summary = [
            {"host_count": 10, "vm_count": 50, "platform_count": 3, "stats": {"total_energy_kw": 5.0}},
            {"host_count": 5,  "vm_count": 30, "platform_count": 2, "stats": {"total_energy_kw": 3.0}},
        ]
        cache.set(f"all_dc_summary:{tr.get('start','')}:{tr.get('end','')}", mock_summary)
        result = self.svc.get_global_overview()
        self.assertEqual(result["total_hosts"], 15)
        self.assertEqual(result["total_vms"], 80)
        self.assertEqual(result["total_platforms"], 5)
        self.assertAlmostEqual(result["total_energy_kw"], 8.0)
        self.assertEqual(result["dc_count"], 2)

    def test_cached_global_overview_skips_db(self):
        tr = default_time_range()
        cache.set(f"global_overview:{tr.get('start','')}:{tr.get('end','')}", {"total_hosts": 99})
        result = self.svc.get_global_overview()
        self.assertEqual(result["total_hosts"], 99)


# ---------------------------------------------------------------------------
# DatabaseService — get_global_dashboard, get_customer_resources, get_customer_list
# ---------------------------------------------------------------------------

class TestGetGlobalDashboard(unittest.TestCase):

    def setUp(self):
        cache.clear()
        self.svc = _make_service()

    def test_returns_overview_and_platforms(self):
        tr = default_time_range()
        cache.set(f"global_dashboard:{tr.get('start','')}:{tr.get('end','')}", {
            "overview": {"dc_count": 5, "total_hosts": 100},
            "platforms": {"nutanix": {"hosts": 40, "vms": 200}, "vmware": {}, "ibm": {}},
            "energy_breakdown": {"ibm_kw": 5, "vcenter_kw": 3},
        })
        result = self.svc.get_global_dashboard()
        self.assertEqual(result["overview"]["dc_count"], 5)
        self.assertEqual(result["platforms"]["nutanix"]["hosts"], 40)
        self.assertEqual(result["energy_breakdown"]["ibm_kw"], 5)
        self.assertEqual(result["energy_breakdown"]["vcenter_kw"], 3)


class TestGetCustomerResources(unittest.TestCase):

    def setUp(self):
        cache.clear()
        self.svc = _make_service()

    def test_returns_totals_and_by_platform(self):
        tr = default_time_range()
        cache.set(f"customer_assets:boyner:{tr.get('start','')}:{tr.get('end','')}", {
            "totals": {
                "vms_total": 13,
                "intel_vms_total": 10,
                "power_lpar_total": 3,
                "cpu_total": 42.0,
                "intel_cpu_total": 30.0,
                "power_cpu_total": 12.0,
                "backup": {
                    "veeam_defined_sessions": 5,
                    "zerto_protected_vms": 7,
                    "storage_volume_gb": 100.0,
                    "netbackup_pre_dedup_gib": 200.0,
                    "netbackup_post_dedup_gib": 50.0,
                    "zerto_provisioned_gib": 75.0,
                },
            },
            "assets": {
                "intel": {
                    "vms": {"vmware": 6, "nutanix": 8, "total": 10},
                    "cpu": {"vmware": 10.0, "nutanix": 20.0, "total": 30.0},
                    "memory_gb": {"vmware": 100.0, "nutanix": 200.0, "total": 300.0},
                    "disk_gb": {"vmware": 50.0, "nutanix": 75.0, "total": 125.0},
                    "vm_list": [
                        {"name": "vm1", "source": "VMware", "cpu": 2.0, "memory_gb": 8.0, "disk_gb": 100.0},
                    ],
                },
                "power": {
                    "cpu_total": 12.0,
                    "lpar_count": 3,
                    "memory_total_gb": 64.0,
                    "vm_list": [
                        {"name": "lpar1", "source": "Power HMC", "cpu": 4.0, "memory_gb": 16.0, "state": "Running"},
                    ],
                },
                "backup": {
                    "veeam": {
                        "defined_sessions": 5,
                        "session_types": [],
                        "platforms": [],
                    },
                    "zerto": {
                        "protected_total_vms": 7,
                        "provisioned_storage_gib_total": 75.0,
                        "vpgs": [
                            {"name": "vpg1", "provisioned_storage_gib": 50.0},
                            {"name": "vpg2", "provisioned_storage_gib": 25.0},
                        ],
                    },
                    "storage": {
                        "total_volume_capacity_gb": 100.0,
                    },
                    "netbackup": {
                        "pre_dedup_size_gib": 200.0,
                        "post_dedup_size_gib": 50.0,
                        "deduplication_factor": "4x",
                    },
                },
            },
        })
        result = self.svc.get_customer_resources("boyner")
        self.assertEqual(result["totals"]["vms_total"], 13)
        self.assertEqual(result["totals"]["intel_vms_total"], 10)
        self.assertEqual(result["totals"]["power_lpar_total"], 3)
        self.assertEqual(result["totals"]["cpu_total"], 42.0)
        self.assertEqual(result["totals"]["backup"]["zerto_protected_vms"], 7)
        self.assertEqual(result["totals"]["backup"]["netbackup_pre_dedup_gib"], 200.0)
        self.assertEqual(result["totals"]["backup"]["netbackup_post_dedup_gib"], 50.0)
        self.assertEqual(result["totals"]["backup"]["zerto_provisioned_gib"], 75.0)
        self.assertIn("intel", result["assets"])
        self.assertIn("power", result["assets"])
        # Intel VM detail list
        intel_vms = result["assets"]["intel"]["vm_list"]
        self.assertGreaterEqual(len(intel_vms), 1)
        self.assertIn("cpu", intel_vms[0])
        self.assertIn("memory_gb", intel_vms[0])
        self.assertIn("disk_gb", intel_vms[0])
        # Power LPAR detail list
        power_vms = result["assets"]["power"]["vm_list"]
        self.assertGreaterEqual(len(power_vms), 1)
        self.assertIn("cpu", power_vms[0])
        self.assertIn("memory_gb", power_vms[0])
        self.assertIn("state", power_vms[0])
        # Backup services detail structures
        backup_assets = result["assets"]["backup"]
        self.assertIn("netbackup", backup_assets)
        self.assertIn("zerto", backup_assets)
        self.assertIn("storage", backup_assets)
        self.assertEqual(backup_assets["netbackup"]["pre_dedup_size_gib"], 200.0)
        self.assertEqual(backup_assets["netbackup"]["post_dedup_size_gib"], 50.0)
        self.assertEqual(backup_assets["zerto"]["provisioned_storage_gib_total"], 75.0)

    def test_db_error_returns_empty_structure(self):
        from psycopg2 import OperationalError
        self.svc._pool.getconn.side_effect = OperationalError("timeout")
        result = self.svc.get_customer_resources("boyner")
        self.assertIn("totals", result)
        self.assertEqual(result["totals"]["vms_total"], 0)


class TestGetCustomerList(unittest.TestCase):

    def test_returns_list(self):
        from psycopg2 import OperationalError
        with patch("psycopg2.pool.ThreadedConnectionPool"):
            svc = DatabaseService()
        # Force DB error so fallback path is exercised (no real DB in tests).
        svc._pool.getconn.side_effect = OperationalError("timeout")
        result = svc.get_customer_list()
        self.assertIsInstance(result, list)
        self.assertIn("Boyner", result)


# ---------------------------------------------------------------------------
# DatabaseService — _EMPTY_DC, _prepare_params
# ---------------------------------------------------------------------------

class TestEmptyDc(unittest.TestCase):

    def test_has_platforms_key(self):
        empty = _EMPTY_DC("DC11")
        self.assertIn("platforms", empty)
        self.assertIn("nutanix", empty["platforms"])
        self.assertIn("vmware", empty["platforms"])
        self.assertIn("ibm", empty["platforms"])
        self.assertIn("energy", empty)
        self.assertIn("ibm_kw", empty["energy"])
        self.assertIn("vcenter_kw", empty["energy"])


class TestPrepareParams(unittest.TestCase):

    def test_wildcard_pair_returns_two_same_values(self):
        result = DatabaseService._prepare_params("wildcard_pair", "boyner")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], "%boyner%")
        self.assertEqual(result[1], "%boyner%")


# ---------------------------------------------------------------------------
# Query module integrity checks
# ---------------------------------------------------------------------------

class TestQueryModules(unittest.TestCase):

    def test_nutanix_queries_are_strings(self):
        from src.queries import nutanix
        for attr in ["HOST_COUNT", "VM_COUNT", "MEMORY", "STORAGE", "CPU",
                     "BATCH_HOST_COUNT", "BATCH_VM_COUNT", "BATCH_MEMORY", "BATCH_STORAGE", "BATCH_CPU"]:
            self.assertIsInstance(getattr(nutanix, attr), str, f"nutanix.{attr} should be a string")

    def test_vmware_queries_are_strings(self):
        from src.queries import vmware
        for attr in ["COUNTS", "MEMORY", "STORAGE", "CPU",
                     "BATCH_COUNTS", "BATCH_MEMORY", "BATCH_STORAGE", "BATCH_CPU"]:
            self.assertIsInstance(getattr(vmware, attr), str, f"vmware.{attr} should be a string")

    def test_ibm_queries_are_strings(self):
        from src.queries import ibm
        for attr in ["HOST_COUNT", "VIOS_COUNT", "LPAR_COUNT", "MEMORY", "CPU",
                     "BATCH_HOST_COUNT", "BATCH_VIOS_COUNT", "BATCH_LPAR_COUNT", "BATCH_MEMORY", "BATCH_CPU"]:
            self.assertIsInstance(getattr(ibm, attr), str, f"ibm.{attr} should be a string")

    def test_energy_queries_are_strings(self):
        from src.queries import energy
        for attr in ["IBM", "VCENTER", "BATCH_IBM", "BATCH_VCENTER"]:
            self.assertIsInstance(getattr(energy, attr), str, f"energy.{attr} should be a string")

    def test_registry_has_all_expected_keys(self):
        from src.queries.registry import QUERY_REGISTRY
        expected_keys = [
            "nutanix_host_count", "nutanix_memory", "nutanix_storage", "nutanix_cpu",
            "vmware_counts", "vmware_memory", "vmware_storage", "vmware_cpu",
            "ibm_host_count", "ibm_vios_count", "ibm_lpar_count", "ibm_memory", "ibm_cpu",
            "energy_ibm", "energy_vcenter",
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

    def test_ibm_raw_batch_queries_exist(self):
        from src.queries import ibm
        for attr in ["BATCH_RAW_HOST", "BATCH_RAW_VIOS", "BATCH_RAW_LPAR", "BATCH_RAW_MEMORY", "BATCH_RAW_CPU"]:
            self.assertIsInstance(getattr(ibm, attr), str, f"ibm.{attr} should be a string")
            self.assertIn("%s", getattr(ibm, attr))


# ---------------------------------------------------------------------------
# IBM DC code extraction (Python-side regex)
# ---------------------------------------------------------------------------

class TestIbmDcCodeExtraction(unittest.TestCase):

    def test_dc_code_regex_extracts_known_patterns(self):
        from src.services.db_service import _DC_CODE_RE
        cases = {
            "G2HV19DC13": "DC13",
            "server-AZ11-prod": "AZ11",
            "ICT11-backup01": "ICT11",
            "srv-DC15-node3": "DC15",
        }
        for server_name, expected in cases.items():
            m = _DC_CODE_RE.search(server_name.upper())
            self.assertIsNotNone(m, f"No match for {server_name}")
            self.assertEqual(m.group(1), expected)

    def test_dc_code_regex_returns_none_for_unknown(self):
        from src.services.db_service import _DC_CODE_RE
        m = _DC_CODE_RE.search("UNKNOWN_SERVER_NAME")
        self.assertIsNone(m)


# ---------------------------------------------------------------------------
# DC_LIST completeness
# ---------------------------------------------------------------------------

class TestDcList(unittest.TestCase):

    def test_dc_list_has_9_entries(self):
        self.assertEqual(len(DC_LIST), 9)

    def test_dc_list_contains_expected_codes(self):
        expected = {"AZ11", "DC11", "DC12", "DC13", "DC14", "DC15", "DC16", "DC17", "ICT11"}
        self.assertEqual(set(DC_LIST), expected)


# ---------------------------------------------------------------------------
# Dynamic DC list (_load_dc_list)
# ---------------------------------------------------------------------------

class TestLoadDcList(unittest.TestCase):

    def setUp(self):
        cache.clear()
        self.svc = _make_service()

    def _attach_conn(self, cursor):
        conn_mock = MagicMock()
        conn_mock.__enter__ = MagicMock(return_value=conn_mock)
        conn_mock.__exit__ = MagicMock(return_value=False)
        conn_mock.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        conn_mock.cursor.return_value.__exit__ = MagicMock(return_value=False)
        self.svc._pool.getconn.return_value = conn_mock

    def test_load_dc_list_from_db(self):
        cur = MagicMock()
        # First call (with status filter) returns data
        cur.fetchall.return_value = [("DC11",), ("AZ11",), ("ICT11",)]
        self._attach_conn(cur)
        result = self.svc._load_dc_list()
        self.assertEqual(set(result), {"DC11", "AZ11", "ICT11"})

    def test_load_dc_list_falls_back_to_no_status(self):
        cur = MagicMock()
        # First call returns empty (status filter), second call returns data
        cur.fetchall.side_effect = [[], [("DC12",), ("DC13",)]]
        self._attach_conn(cur)
        result = self.svc._load_dc_list()
        self.assertIn("DC12", result)
        self.assertIn("DC13", result)

    def test_load_dc_list_fallback_on_db_error(self):
        from psycopg2 import OperationalError
        self.svc._pool.getconn.side_effect = OperationalError("timeout")
        result = self.svc._load_dc_list()
        self.assertEqual(set(result), set(_FALLBACK_DC_LIST))

    def test_load_dc_list_fallback_on_empty_result(self):
        cur = MagicMock()
        cur.fetchall.return_value = []
        self._attach_conn(cur)
        result = self.svc._load_dc_list()
        self.assertEqual(set(result), set(_FALLBACK_DC_LIST))

    def test_dc_list_property(self):
        self.svc._dc_list = ["DC11", "AZ11"]
        self.assertEqual(self.svc.dc_list, ["DC11", "AZ11"])

    def test_dc_list_property_returns_copy(self):
        self.svc._dc_list = ["DC11"]
        lst = self.svc.dc_list
        lst.append("INJECTED")
        self.assertNotIn("INJECTED", self.svc.dc_list)


# ---------------------------------------------------------------------------
# warm_cache and refresh_all_data
# ---------------------------------------------------------------------------

class TestCacheWarming(unittest.TestCase):

    def setUp(self):
        cache.clear()
        self.svc = _make_service()

    def _empty_batch(self, cursor, dc_list, start_ts, end_ts):
        """Fake _fetch_all_batch returning empty data for all DCs."""
        data = {}
        for dc in dc_list:
            d = _EMPTY_DC(dc)
            d["intel"]["hosts"] = 1
            data[dc] = d
        return data, {dc: 1 for dc in dc_list}

    def test_warm_cache_populates_summary(self):
        with patch.object(self.svc, "_fetch_all_batch", side_effect=self._empty_batch):
            self.svc.warm_cache()
        tr = cache_time_ranges()[0]
        key = f"all_dc_summary:{tr.get('start','')}:{tr.get('end','')}"
        self.assertIsNotNone(cache.get(key))

    def test_warm_cache_populates_global_overview(self):
        with patch.object(self.svc, "_fetch_all_batch", side_effect=self._empty_batch):
            self.svc.warm_cache()
        tr = cache_time_ranges()[0]
        key = f"global_overview:{tr.get('start','')}:{tr.get('end','')}"
        self.assertIsNotNone(cache.get(key))

    def test_warm_cache_does_not_raise_on_db_error(self):
        from psycopg2 import OperationalError
        self.svc._pool.getconn.side_effect = OperationalError("down")
        try:
            self.svc.warm_cache()
        except Exception as exc:
            self.fail(f"warm_cache() raised unexpectedly: {exc}")

    def test_refresh_all_data_clears_and_rebuilds(self):
        tr = cache_time_ranges()[0]
        suffix = f"{tr.get('start','')}:{tr.get('end','')}"
        cache.set(f"all_dc_summary:{suffix}", [{"stale": True}])
        with patch.object(self.svc, "_fetch_all_batch", side_effect=self._empty_batch):
            self.svc.refresh_all_data()
        summary = cache.get(f"all_dc_summary:{suffix}")
        self.assertIsNotNone(summary)
        self.assertFalse(any(item.get("stale") for item in summary))

    def test_refresh_all_data_does_not_raise_on_db_error(self):
        from psycopg2 import OperationalError
        self.svc._pool.getconn.side_effect = OperationalError("down")
        try:
            self.svc.refresh_all_data()
        except Exception as exc:
            self.fail(f"refresh_all_data() raised unexpectedly: {exc}")

    def test_rebuild_summary_populates_per_dc_cache(self):
        self.svc._dc_list = ["DC11", "AZ11"]
        with patch.object(self.svc, "_fetch_all_batch", side_effect=self._empty_batch):
            tr = default_time_range()
            self.svc._rebuild_summary(tr)
        suffix = f"{tr.get('start','')}:{tr.get('end','')}"
        self.assertIsNotNone(cache.get(f"dc_details:DC11:{suffix}"))
        self.assertIsNotNone(cache.get(f"dc_details:AZ11:{suffix}"))


# ---------------------------------------------------------------------------
# Scheduler service
# ---------------------------------------------------------------------------

class TestSchedulerService(unittest.TestCase):

    def test_start_scheduler_calls_warm_cache(self):
        from src.services.scheduler_service import start_scheduler
        svc_mock = MagicMock()
        scheduler = start_scheduler(svc_mock)
        svc_mock.warm_cache.assert_called_once()
        scheduler.shutdown(wait=False)

    def test_start_scheduler_returns_running_scheduler(self):
        from src.services.scheduler_service import start_scheduler
        svc_mock = MagicMock()
        scheduler = start_scheduler(svc_mock)
        self.assertTrue(scheduler.running)
        scheduler.shutdown(wait=False)

    def test_refresh_job_registered(self):
        from src.services.scheduler_service import start_scheduler
        svc_mock = MagicMock()
        scheduler = start_scheduler(svc_mock)
        job_ids = [job.id for job in scheduler.get_jobs()]
        self.assertIn("cache_refresh", job_ids)
        scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# loki query module
# ---------------------------------------------------------------------------

class TestLokiQueries(unittest.TestCase):

    def test_dc_list_query_is_string(self):
        from src.queries.loki import DC_LIST, DC_LIST_NO_STATUS
        self.assertIsInstance(DC_LIST, str)
        self.assertIsInstance(DC_LIST_NO_STATUS, str)

    def test_dc_list_query_contains_loki_locations(self):
        from src.queries.loki import DC_LIST
        self.assertIn("loki_locations", DC_LIST)

    def test_dc_list_query_handles_hierarchy(self):
        from src.queries.loki import DC_LIST
        self.assertIn("parent_id", DC_LIST)
        self.assertIn("parent_name", DC_LIST)

    def test_energy_ibm_uses_correct_table(self):
        from src.queries.energy import IBM, BATCH_IBM
        self.assertIn("ibm_server_power", IBM)
        self.assertNotIn("ibm_server_power_sum", IBM)
        self.assertIn("ibm_server_power", BATCH_IBM)
        self.assertNotIn("ibm_server_power_sum", BATCH_IBM)

    def test_nutanix_batch_uses_cluster_name_pattern(self):
        from src.queries.nutanix import BATCH_HOST_COUNT, BATCH_MEMORY, BATCH_STORAGE, BATCH_CPU
        for sql in [BATCH_HOST_COUNT, BATCH_MEMORY, BATCH_STORAGE, BATCH_CPU]:
            self.assertIn("cluster_name", sql, "Nutanix batch query must filter by cluster_name")
            self.assertIn("unnest", sql, "Nutanix batch query must use unnest for dc/pattern list")


# ---------------------------------------------------------------------------
# format_units utility
# ---------------------------------------------------------------------------

class TestFormatUnits(unittest.TestCase):

    def test_smart_storage_mb(self):
        from src.utils.format_units import smart_storage
        result = smart_storage(0.5)
        self.assertIn("MB", result)

    def test_smart_storage_gb(self):
        from src.utils.format_units import smart_storage
        result = smart_storage(500)
        self.assertIn("GB", result)

    def test_smart_storage_tb(self):
        from src.utils.format_units import smart_storage
        result = smart_storage(2048)
        self.assertIn("TB", result)
        self.assertIn("2.0", result)

    def test_smart_storage_zero(self):
        from src.utils.format_units import smart_storage
        result = smart_storage(0)
        self.assertIn("0", result)

    def test_smart_storage_none(self):
        from src.utils.format_units import smart_storage
        result = smart_storage(None)
        self.assertIn("0", result)

    def test_smart_memory_matches_storage(self):
        from src.utils.format_units import smart_memory, smart_storage
        self.assertEqual(smart_memory(100), smart_storage(100))

    def test_smart_cpu_mhz(self):
        from src.utils.format_units import smart_cpu
        result = smart_cpu(0.5)
        self.assertIn("MHz", result)

    def test_smart_cpu_ghz(self):
        from src.utils.format_units import smart_cpu
        result = smart_cpu(2.4)
        self.assertIn("GHz", result)
        self.assertIn("2.4", result)

    def test_smart_cpu_none(self):
        from src.utils.format_units import smart_cpu
        result = smart_cpu(None)
        self.assertIn("0", result)

    def test_pct_float_returns_correct_percentage(self):
        from src.utils.format_units import pct_float
        self.assertAlmostEqual(pct_float(50, 200), 25.0)

    def test_pct_float_zero_cap_returns_zero(self):
        from src.utils.format_units import pct_float
        self.assertEqual(pct_float(100, 0), 0.0)

    def test_pct_float_caps_at_100(self):
        from src.utils.format_units import pct_float
        self.assertEqual(pct_float(200, 100), 100.0)

    def test_pct_str_format(self):
        from src.utils.format_units import pct_str
        result = pct_str(1, 4)
        self.assertIn("25.0%", result)


# ---------------------------------------------------------------------------
# _aggregate_dc — Classic / Hyperconv sections
# ---------------------------------------------------------------------------

class TestAggregateClassicHyperconv(unittest.TestCase):

    def _call(self, classic_row=None, classic_avg30=None,
              hyperconv_row=None, hyperconv_avg30=None):
        return DatabaseService._aggregate_dc(
            dc_code="DC13",
            nutanix_host_count=4,
            nutanix_vms=20,
            nutanix_mem=(2.0, 1.0),
            # nutanix_cluster_metrics storage is in bytes; pass 10 TB / 5 TB in bytes.
            nutanix_storage=(10.0 * (1024 ** 4), 5.0 * (1024 ** 4)),
            nutanix_cpu=(100.0, 50.0),
            vmware_counts=(3, 2, 20),
            vmware_mem=(1024 ** 3, 512 * (1024 ** 2)),
            vmware_storage=(1024 ** 4, 512 * (1024 ** 3)),
            vmware_cpu=(2_000_000_000, 1_000_000_000),
            power_hosts=2,
            power_vios=1,
            power_lpar_count=5,
            power_mem=(64.0, 32.0),
            power_cpu=(4.0, 2.0, 8.0),
            ibm_w=500.0,
            vcenter_w=500.0,
            classic_row=classic_row,
            classic_avg30=classic_avg30,
            hyperconv_row=hyperconv_row,
            hyperconv_avg30=hyperconv_avg30,
        )

    def test_classic_section_present(self):
        result = self._call()
        self.assertIn("classic", result)
        classic = result["classic"]
        for key in ("hosts", "vms", "cpu_cap", "cpu_used", "mem_cap", "mem_used",
                    "stor_cap", "stor_used", "cpu_pct", "mem_pct"):
            self.assertIn(key, classic, f"classic missing key: {key}")

    def test_hyperconv_section_present(self):
        result = self._call()
        self.assertIn("hyperconv", result)

    def test_classic_defaults_to_zero_when_no_row(self):
        result = self._call()
        self.assertEqual(result["classic"]["hosts"], 0)
        self.assertEqual(result["classic"]["cpu_cap"], 0.0)

    def test_classic_row_populated_correctly(self):
        # (hosts, vms, cpu_cap_ghz, cpu_used_ghz, mem_cap_gb, mem_used_gb, stor_cap_gb, stor_used_gb)
        cl_row = (10, 50, 200.0, 120.0, 1024.0, 600.0, 20480.0, 10240.0)
        result = self._call(classic_row=cl_row)
        classic = result["classic"]
        self.assertEqual(classic["hosts"], 10)
        self.assertEqual(classic["vms"], 50)
        self.assertAlmostEqual(classic["cpu_cap"], 200.0)
        self.assertAlmostEqual(classic["mem_cap"], 1024.0)
        # Storage: 20480 GB → 20 TB
        self.assertAlmostEqual(classic["stor_cap"], 20480.0 / 1024.0, places=2)

    def test_classic_avg30_populated(self):
        cl_avg = (65.5, 72.3)
        result = self._call(classic_avg30=cl_avg)
        self.assertAlmostEqual(result["classic"]["cpu_pct"], 65.5)
        self.assertAlmostEqual(result["classic"]["mem_pct"], 72.3)

    def test_hyperconv_storage_uses_nutanix(self):
        # nutanix_storage = (10.0, 5.0) TB
        result = self._call()
        hc = result["hyperconv"]
        self.assertAlmostEqual(hc["stor_cap"], 10.0)
        self.assertAlmostEqual(hc["stor_used"], 5.0)

    def test_legacy_intel_section_still_present(self):
        result = self._call()
        self.assertIn("intel", result)
        self.assertIn("hosts", result["intel"])

    def test_empty_dc_contains_classic_hyperconv(self):
        from src.services.db_service import _EMPTY_DC
        empty = _EMPTY_DC("DC11")
        self.assertIn("classic", empty)
        self.assertIn("hyperconv", empty)
        self.assertEqual(empty["classic"]["hosts"], 0)
        self.assertEqual(empty["hyperconv"]["vms"], 0)


# ---------------------------------------------------------------------------
# New VMware cluster_metrics queries
# ---------------------------------------------------------------------------

class TestVmwareClusterQueries(unittest.TestCase):

    def test_classic_metrics_query_filters_km(self):
        from src.queries.vmware import CLASSIC_METRICS, CLASSIC_AVG30
        self.assertIn("KM", CLASSIC_METRICS)
        self.assertIn("cluster_metrics", CLASSIC_METRICS)
        self.assertIn("KM", CLASSIC_AVG30)

    def test_hyperconv_metrics_query_excludes_km(self):
        from src.queries.vmware import HYPERCONV_METRICS, HYPERCONV_AVG30
        self.assertIn("NOT ILIKE", HYPERCONV_METRICS)
        self.assertIn("cluster_metrics", HYPERCONV_METRICS)

    def test_batch_classic_has_unnest(self):
        from src.queries.vmware import BATCH_CLASSIC_METRICS, BATCH_HYPERCONV_METRICS
        self.assertIn("unnest", BATCH_CLASSIC_METRICS)
        self.assertIn("unnest", BATCH_HYPERCONV_METRICS)

    def test_batch_classic_avg30_exists(self):
        from src.queries.vmware import BATCH_CLASSIC_AVG30, BATCH_HYPERCONV_AVG30
        self.assertIn("cpu_usage_avg_perc", BATCH_CLASSIC_AVG30)
        self.assertIn("cpu_usage_avg_perc", BATCH_HYPERCONV_AVG30)


# ---------------------------------------------------------------------------
# New customer.py queries — Classic / Hyperconv split
# ---------------------------------------------------------------------------

class TestCustomerClassicHyperconvQueries(unittest.TestCase):

    def test_classic_vm_count_filters_km(self):
        from src.queries.customer import CUSTOMER_CLASSIC_VM_COUNT
        self.assertIn("KM", CUSTOMER_CLASSIC_VM_COUNT)
        self.assertIn("vm_metrics", CUSTOMER_CLASSIC_VM_COUNT)

    def test_hyperconv_vm_count_excludes_km(self):
        from src.queries.customer import CUSTOMER_HYPERCONV_VM_COUNT
        self.assertIn("NOT ILIKE", CUSTOMER_HYPERCONV_VM_COUNT)
        self.assertIn("nutanix_vm_metrics", CUSTOMER_HYPERCONV_VM_COUNT)

    def test_classic_vm_list_includes_cluster(self):
        from src.queries.customer import CUSTOMER_CLASSIC_VM_LIST
        self.assertIn("cluster", CUSTOMER_CLASSIC_VM_LIST)
        self.assertIn("Classic", CUSTOMER_CLASSIC_VM_LIST)

    def test_hyperconv_vm_list_includes_source_classification(self):
        from src.queries.customer import CUSTOMER_HYPERCONV_VM_LIST
        self.assertIn("Nutanix (VMware Managed)", CUSTOMER_HYPERCONV_VM_LIST)

    def test_classic_resource_totals_has_required_columns(self):
        from src.queries.customer import CUSTOMER_CLASSIC_RESOURCE_TOTALS
        for col in ("cpu_total", "memory_gb", "disk_gb"):
            self.assertIn(col, CUSTOMER_CLASSIC_RESOURCE_TOTALS)


# ---------------------------------------------------------------------------
# Cluster-level VM deduplication — _aggregate_dc
# ---------------------------------------------------------------------------

class TestClusterLevelVmDedup(unittest.TestCase):
    """Verifies that intel.vms uses cluster-level dedup (cl_vms + nutanix_vms)
    instead of naively summing nutanix_vms + vmware_counts[2], which would
    double-count VMs on Nutanix hardware managed by vCenter."""

    def _call(self, nutanix_vms, vmware_counts_vm_total, classic_row_vms):
        """Helper: build _aggregate_dc result with controlled VM inputs."""
        classic_row = (0, classic_row_vms, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        return DatabaseService._aggregate_dc(
            dc_code="DC11",
            nutanix_host_count=4,
            nutanix_vms=nutanix_vms,
            nutanix_mem=None,
            nutanix_storage=None,
            nutanix_cpu=None,
            vmware_counts=(2, 4, vmware_counts_vm_total),
            vmware_mem=None,
            vmware_storage=None,
            vmware_cpu=None,
            power_hosts=0,
            power_vios=0,
            power_lpar_count=0,
            power_mem=None,
            power_cpu=None,
            ibm_w=0,
            vcenter_w=0,
            classic_row=classic_row,
        )

    def test_intel_vms_equals_classic_plus_nutanix(self):
        """intel.vms must be cl_vms + nutanix_vms, not nutanix_vms + vmware_total."""
        # Scenario: 30 Classic KM VMs + 50 Nutanix VMs = 80 unique VMs.
        # vmware_counts[2]=70 would double-count 40 hyperconv VMs (in both Nutanix and VMware).
        result = self._call(nutanix_vms=50, vmware_counts_vm_total=70, classic_row_vms=30)
        self.assertEqual(result["intel"]["vms"], 80)  # 30 classic + 50 nutanix

    def test_intel_vms_no_classic_uses_only_nutanix(self):
        """When there are no KM clusters (cl_vms=0), intel.vms = nutanix_vms only."""
        result = self._call(nutanix_vms=25, vmware_counts_vm_total=20, classic_row_vms=0)
        self.assertEqual(result["intel"]["vms"], 25)

    def test_intel_vms_no_nutanix_uses_only_classic(self):
        """When there are no Nutanix VMs, intel.vms = cl_vms (Classic KM VMs only)."""
        result = self._call(nutanix_vms=0, vmware_counts_vm_total=15, classic_row_vms=15)
        self.assertEqual(result["intel"]["vms"], 15)

    def test_intel_vms_does_not_include_vmware_total(self):
        """intel.vms must NOT equal nutanix_vms + vmware_counts[2] (old formula)."""
        result = self._call(nutanix_vms=50, vmware_counts_vm_total=70, classic_row_vms=30)
        old_formula_result = 50 + 70  # 120 — the double-count value
        self.assertNotEqual(result["intel"]["vms"], old_formula_result)

    def test_platforms_vmware_vms_is_classic_only(self):
        """platforms.vmware.vms must equal cl_vms (Classic/KM only), not vmware_counts[2]."""
        result = self._call(nutanix_vms=50, vmware_counts_vm_total=70, classic_row_vms=30)
        self.assertEqual(result["platforms"]["vmware"]["vms"], 30)

    def test_platforms_vmware_vms_excludes_hyperconv_overlap(self):
        """platforms.vmware.vms must NOT include hyperconv VMs (overlap with Nutanix)."""
        result = self._call(nutanix_vms=50, vmware_counts_vm_total=70, classic_row_vms=30)
        # If it used vmware_counts[2]=70, it would include ~40 hyperconv VMs (overlap with Nutanix).
        self.assertLess(result["platforms"]["vmware"]["vms"], 70)

    def test_platforms_nutanix_vms_unchanged(self):
        """platforms.nutanix.vms must still equal the full nutanix_vms count."""
        result = self._call(nutanix_vms=50, vmware_counts_vm_total=70, classic_row_vms=30)
        self.assertEqual(result["platforms"]["nutanix"]["vms"], 50)

    def test_intel_plus_power_equals_dc_card_vm_count(self):
        """DC card vm_count = intel.vms + power.lpars — verify consistency."""
        result = DatabaseService._aggregate_dc(
            dc_code="DC11",
            nutanix_host_count=4,
            nutanix_vms=50,
            nutanix_mem=None,
            nutanix_storage=None,
            nutanix_cpu=None,
            vmware_counts=(2, 4, 70),
            vmware_mem=None,
            vmware_storage=None,
            vmware_cpu=None,
            power_hosts=2,
            power_vios=1,
            power_lpar_count=8,
            power_mem=None,
            power_cpu=None,
            ibm_w=0,
            vcenter_w=0,
            classic_row=(0, 30, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
        expected_dc_vm_count = result["intel"]["vms"] + result["power"]["lpar_count"]
        self.assertEqual(expected_dc_vm_count, 88)  # (30 classic + 50 nutanix) + 8 lpars


if __name__ == "__main__":
    unittest.main()
