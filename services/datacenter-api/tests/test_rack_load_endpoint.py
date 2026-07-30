from app.db.queries import rack_load as q


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
