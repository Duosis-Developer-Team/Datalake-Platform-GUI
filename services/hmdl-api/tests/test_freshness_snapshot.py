"""In-process freshness snapshot + background refresher (hmdl-api has no Redis)."""
from unittest.mock import patch

from app.services import freshness_snapshot as snap


def test_snapshot_is_computing_before_first_refresh():
    snap._reset_for_test()
    s = snap.get_snapshot()
    assert s["status"] == "computing"
    assert s["families"] == []
    assert s["counts"]["alert"] == 0


def test_refresh_now_stores_ok_snapshot():
    snap._reset_for_test()
    computed = {"families": [{"family": "VMware", "counts": {"dead": 1}, "sources": []}],
                "counts": {"fresh": 0, "stale": 0, "dead": 1, "unknown": 0, "alert": 1}}
    with patch("app.services.freshness_snapshot.compute_freshness", return_value=computed):
        snap.refresh_now()
    s = snap.get_snapshot()
    assert s["status"] == "ok"
    assert s["counts"]["alert"] == 1
    assert s["generated_at"] is not None
