import re
from unittest.mock import patch

from psycopg2 import OperationalError

from app.db.queries import rack_load as q
from app.services.dc_service import DatabaseService


def test_device_query_filters_by_rack_name_array_and_active_status():
    sql = q.DEVICES_BY_RACK_NAMES
    assert "rack_name = ANY(%s::text[])" in sql
    assert "status_value = 'active'" in sql
    # DISTINCT ON keeps one row per device: the collector writes a new snapshot
    # every run, so without it a device is counted many times.
    assert "DISTINCT ON" in sql


def test_host_metric_queries_take_latest_row_per_host():
    for sql in (q.VMWARE_HOST_LATEST, q.NUTANIX_HOST_LATEST, q.IBM_SERVER_LATEST):
        assert "DISTINCT ON" in sql


def test_metric_queries_do_not_coalesce_null_readings_to_zero():
    # A NULL counter must reach the aggregation layer as NULL: it means
    # "not monitored", and 0 would render as "light load" (or, on IBM's
    # available-memory column, as a false 100% full).
    for sql in (q.VMWARE_HOST_LATEST, q.NUTANIX_HOST_LATEST, q.IBM_SERVER_LATEST):
        assert "COALESCE" not in sql.upper()


def test_endpoint_returns_racks_and_summary(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.routers.datacenters import get_db

    class FakeDB:
        def get_dc_racks_load(self, dc_code):
            return {
                "racks": [{"rack_name": "104", "load_pct": 73.2, "cpu_pct": 73.2,
                           "ram_pct": 61.0, "monitored_devices": 4,
                           "total_devices": 11, "hottest_device": "esx-13-04"}],
                "summary": {"monitored_racks": 1, "total_racks": 1},
            }

    app.dependency_overrides[get_db] = lambda: FakeDB()
    try:
        resp = TestClient(app).get("/api/v1/datacenters/DC13/racks/load")
        assert resp.status_code == 200
        body = resp.json()
        assert body["racks"][0]["rack_name"] == "104"
        assert body["summary"]["monitored_racks"] == 1
    finally:
        app.dependency_overrides.clear()


def test_blank_dc_code_returns_empty_without_touching_the_db():
    from app.services.dc_service import DatabaseService

    svc = DatabaseService.__new__(DatabaseService)
    assert svc.get_dc_racks_load("  ") == {
        "racks": [], "summary": {"monitored_racks": 0, "total_racks": 0}
    }


# --- get_dc_racks_load wiring + cache/failure contract ---------------------
#
# Everything above this line only inspects the SQL text. None of it proves
# that get_dc_racks_load actually feeds the *columns* those queries select
# into build_metric_index/aggregate_rack_load in the right order -- those
# functions read rows positionally (see app/services/rack_load.py's
# docstrings), so a future edit that transposed e.g. cpu_ghz_used and
# cpu_ghz_capacity in a SELECT would produce a plausible-but-wrong percentage
# and every test above would still pass. The tests below drive
# get_dc_racks_load end-to-end (real build_metric_index/aggregate_rack_load,
# fake cursor instead of a live DB) with canned rows chosen so a transposed
# used/capacity pair gives a visibly different, wrong percentage.
#
# Mocking style follows tests/test_colocation_occupancy_service.py.

def _svc_no_db():
    """A DatabaseService instance whose connection pool never touches a real
    DB -- same helper as test_colocation_occupancy_service.py."""
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool",
               side_effect=OperationalError("no db")):
        return DatabaseService()


class _FakeCursor:
    """Cursor stub that returns canned rows keyed by exact SQL text, so one
    fake connection can serve get_dc_racks_load's four distinct queries
    (device rows plus the three per-vendor metric queries)."""

    def __init__(self, rows_by_sql):
        self._rows_by_sql = rows_by_sql
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._rows = self._rows_by_sql.get(sql, [])

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self._cursor


def _run_load_with_canned_rows(device_rows, vmware_rows=(), nutanix_rows=(), ibm_rows=()):
    """Run the real get_dc_racks_load (real build_metric_index/
    aggregate_rack_load) against canned, SQL-shaped rows -- no live DB."""
    svc = _svc_no_db()
    rows_by_sql = {
        q.DEVICES_BY_RACK_NAMES: list(device_rows),
        q.VMWARE_HOST_LATEST: list(vmware_rows),
        q.NUTANIX_HOST_LATEST: list(nutanix_rows),
        q.IBM_SERVER_LATEST: list(ibm_rows),
    }
    fake_conn = _FakeConn(_FakeCursor(rows_by_sql))
    rack_names = sorted({row[0] for row in device_rows})
    with patch("app.services.dc_service.cache.get", return_value=None), \
         patch("app.services.dc_service.cache.run_singleflight",
               side_effect=lambda key, fn, ttl=None: fn()), \
         patch.object(svc, "_get_connection", return_value=fake_conn), \
         patch.object(svc, "get_dc_racks",
                      return_value={"racks": [{"name": n} for n in rack_names]}):
        return svc.get_dc_racks_load("DC13")


def _select_columns(sql: str) -> list[str]:
    """Bare column names of a `SELECT DISTINCT ON (...) col1, col2, ... FROM`
    query, in the exact order the DB would return them (any `alias.`
    qualifier stripped).

    Used by _row_from to build test rows from the SQL's *live* column order
    instead of a hand-picked tuple. A hand-picked tuple would stay "correct"
    forever even if a future edit transposed two columns in the real SELECT --
    exactly the gap this test exists to close.
    """
    m = re.search(r"SELECT DISTINCT ON\s*\([^)]*\)\s*(.*?)\s*FROM", sql, re.DOTALL)
    assert m, f"expected a SELECT DISTINCT ON (...) ... FROM column list in: {sql!r}"
    return [c.strip().split(".")[-1] for c in m.group(1).split(",")]


def _row_from(sql: str, values_by_column: dict) -> tuple:
    """Build a positional row tuple by reading `sql`'s live column order and
    looking each column's value up in `values_by_column`. If a future edit
    reorders the SELECT, this reorders right along with it -- so a test
    asserting a fixed expected percentage will fail exactly when the SQL's
    column order no longer matches what the aggregation layer expects.
    """
    return tuple(values_by_column[col] for col in _select_columns(sql))


def test_vmware_columns_are_wired_in_the_documented_order():
    # capacity=100, used=25 -> 25%, built from VMWARE_HOST_LATEST's live
    # column order (see _row_from). If a future edit transposed
    # cpu_ghz_used/cpu_ghz_capacity in that SELECT, this row's values would
    # shift with it and the assertion below would see 400%, not 25%.
    row = _row_from(q.VMWARE_HOST_LATEST, {
        "vmhost": "esx-13-01",
        "cpu_ghz_used": 25.0,
        "cpu_ghz_capacity": 100.0,
        "memory_used_gb": 10.0,
        "memory_capacity_gb": 100.0,
    })
    result = _run_load_with_canned_rows(
        device_rows=[("104", "esx-13-01")],
        vmware_rows=[row],
    )
    rack = result["racks"][0]
    assert rack["cpu_pct"] == 25.0
    assert rack["ram_pct"] == 10.0
    assert rack["load_pct"] == 25.0


def test_nutanix_columns_are_wired_in_the_documented_order():
    row = _row_from(q.NUTANIX_HOST_LATEST, {
        "host_name": "ntx-host-01",
        "cpu_usage_avg": 25.0,
        "total_cpu_capacity": 100.0,
        "memory_usage_avg": 10.0,
        "total_memory_capacity": 100.0,
    })
    result = _run_load_with_canned_rows(
        device_rows=[("104", "ntx-host-01")],
        nutanix_rows=[row],
    )
    rack = result["racks"][0]
    assert rack["cpu_pct"] == 25.0
    assert rack["ram_pct"] == 10.0
    assert rack["load_pct"] == 25.0


def test_ibm_columns_are_wired_in_the_documented_order():
    # total=200, available=150 -> used=50 -> 25%. A total/available
    # transposition would flip the sign of (total - available) instead of
    # merely scaling it, which a lax tolerance could otherwise miss.
    row = _row_from(q.IBM_SERVER_LATEST, {
        "server_details_servername": "pwr-host-01",
        "server_processor_utilizedprocunits": 25.0,
        "server_processor_totalprocunits": 100.0,
        "server_memory_totalmem": 200.0,
        "server_memory_availablemem": 150.0,
    })
    result = _run_load_with_canned_rows(
        device_rows=[("104", "pwr-host-01")],
        ibm_rows=[row],
    )
    rack = result["racks"][0]
    assert rack["cpu_pct"] == 25.0
    assert rack["ram_pct"] == 25.0
    assert rack["load_pct"] == 25.0


def test_load_cache_miss_uses_singleflight_6h_ttl():
    svc = _svc_no_db()
    fake = {"racks": [], "summary": {"monitored_racks": 0, "total_racks": 0}}
    with patch("app.services.dc_service.cache.get", return_value=None), \
         patch("app.services.dc_service.cache.run_singleflight", return_value=fake) as sf:
        result = svc.get_dc_racks_load("DC13")
    assert result == fake
    assert sf.call_count == 1
    assert sf.call_args[1].get("ttl") == 21600


def test_load_cache_hit_short_circuits_without_touching_the_db():
    svc = _svc_no_db()
    cached = {"racks": [{"rack_name": "104"}], "summary": {"monitored_racks": 1, "total_racks": 1}}
    with patch("app.services.dc_service.cache.get", return_value=cached), \
         patch("app.services.dc_service.cache.run_singleflight") as sf:
        result = svc.get_dc_racks_load("DC13")
    assert result == cached
    sf.assert_not_called()


def test_load_operational_error_returns_empty_payload():
    svc = _svc_no_db()
    with patch("app.services.dc_service.cache.get", return_value=None), \
         patch("app.services.dc_service.cache.run_singleflight",
               side_effect=OperationalError("db down")):
        result = svc.get_dc_racks_load("DC13")
    assert result == {"racks": [], "summary": {"monitored_racks": 0, "total_racks": 0}}
