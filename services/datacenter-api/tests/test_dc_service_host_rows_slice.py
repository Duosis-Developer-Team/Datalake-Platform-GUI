"""P8 mirror: full-DC host rows cached once; cluster subset sliced in-process."""
from unittest.mock import MagicMock, patch

from app.services.dc_service import DatabaseService


def _classic_host_rows():
    return [
        ("h1", "DC13-KM1", 100.0, 50.0, 512.0, 256.0),
        ("h2", "DC13-KM2", 100.0, 40.0, 512.0, 200.0),
        ("h3", "DC13-KM1", 100.0, 30.0, 512.0, 150.0),
    ]


def test_classic_host_rows_single_sql_for_cluster_subsets():
    svc = DatabaseService()
    svc._pool = MagicMock()
    conn = MagicMock()
    svc._pool.getconn.return_value = conn
    cur = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    sql_calls = {"n": 0}

    def fake_run_rows(cursor, query, params):
        sql_calls["n"] += 1
        if "vmhost_metrics" in query:
            assert params[1] == [] and params[2] == [], "SQL must use empty cluster filter"
            return _classic_host_rows()
        if "vm_metrics" in query:
            return []
        return []

    with patch.object(svc, "_run_rows", side_effect=fake_run_rows), patch.object(
        svc, "_load_host_ghz_map", return_value={}
    ), patch.object(svc, "_get_default_host_cpu_ghz", return_value=2.0), patch(
        "app.services.dc_service.cache.get", return_value=None
    ), patch("app.services.dc_service.cache.run_singleflight") as mock_sf:
        def capture_sf(key, factory):
            return factory()

        mock_sf.side_effect = capture_sf

        tr = {"start": "2026-01-01", "end": "2026-01-31"}
        sub1 = svc.get_classic_host_rows("DC13", ["DC13-KM1"], tr)
        sub2 = svc.get_classic_host_rows("DC13", ["DC13-KM2"], tr)
        allh = svc.get_classic_host_rows("DC13", None, tr)

    assert sql_calls["n"] == 2, "one host query + one allocation query for full DC"
    assert {h["host"] for h in sub1["hosts"]} == {"h1", "h3"}
    assert {h["host"] for h in sub2["hosts"]} == {"h2"}
    assert allh["host_count"] == 3


def test_slice_host_rows_payload_static():
    full = {
        "hosts": [
            {"host": "a", "cluster": "C1"},
            {"host": "b", "cluster": "C2"},
        ],
        "host_count": 2,
    }
    sliced = DatabaseService._slice_host_rows_payload(full, ["C1"])
    assert sliced["host_count"] == 1
    assert sliced["hosts"][0]["host"] == "a"
