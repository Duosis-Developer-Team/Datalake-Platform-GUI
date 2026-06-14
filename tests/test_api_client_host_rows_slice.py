"""P8: host rows fetched once (all clusters), then sliced in-process per subset."""
from unittest.mock import patch
from src.services import api_client as api
from src.services import cache_service


def test_classic_host_rows_fetched_once_for_multiple_subsets():
    cache_service.clear()
    full = {"hosts": [
        {"host": "h1", "cluster": "DC13-KM1"},
        {"host": "h2", "cluster": "DC13-KM2"},
        {"host": "h3", "cluster": "DC13-KM1"},
    ], "host_count": 3}
    calls = {"n": 0}

    def fake_get_json(client, path, params=None):
        calls["n"] += 1
        assert "clusters" not in (params or {}), "P8 must fetch all hosts, not a cluster subset"
        return full

    with patch.object(api, "_get_json", side_effect=fake_get_json):
        sub1 = api.get_classic_host_rows("DC13", ["DC13-KM1"], None)
        sub2 = api.get_classic_host_rows("DC13", ["DC13-KM2"], None)
        allh = api.get_classic_host_rows("DC13", None, None)

    assert calls["n"] == 1, "backend should be hit once; subsets served from the cached full list"
    assert {h["host"] for h in sub1["hosts"]} == {"h1", "h3"} and sub1["host_count"] == 2
    assert {h["host"] for h in sub2["hosts"]} == {"h2"} and sub2["host_count"] == 1
    assert allh["host_count"] == 3


def test_hyperconv_host_rows_sliced(monkeypatch):
    cache_service.clear()
    full = {"hosts": [{"host": "n1", "cluster": "AZ-NTNX1"}, {"host": "n2", "cluster": "AZ-NTNX2"}], "host_count": 2}
    monkeypatch.setattr(api, "_get_json", lambda *a, **k: full)
    out = api.get_hyperconv_host_rows("AZ11", ["AZ-NTNX2"], None)
    assert {h["host"] for h in out["hosts"]} == {"n2"} and out["host_count"] == 1
