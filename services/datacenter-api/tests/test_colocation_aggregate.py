"""get_colocation_aggregate rolls the shared occupancy rows up per DC (all DCs
in one query); summary enrichment merges coloc_* fields onto each DC dict."""
from unittest.mock import patch

from psycopg2 import OperationalError

from app.services.dc_service import DatabaseService


def _svc_no_db():
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool",
               side_effect=OperationalError("no db")):
        return DatabaseService()


def test_colocation_aggregate_cached_singleflight():
    svc = _svc_no_db()
    fake = {"DC13": {"total_u": 94, "used_u": 55, "free_u": 39, "rack_count": 2}}
    with patch("app.services.dc_service.cache.get", return_value=None), \
         patch("app.services.dc_service.cache.run_singleflight", return_value=fake) as sf:
        out = svc.get_colocation_aggregate()
    assert out == fake
    assert sf.call_args[1].get("ttl") == 21600


def test_enrich_summary_merges_coloc_fields():
    svc = _svc_no_db()
    summaries = [{"id": "DC13", "site_name": "IST"}, {"id": "DC99", "site_name": "X"}]
    agg = {"DC13": {"total_u": 94, "used_u": 55, "free_u": 39, "rack_count": 2}}
    out = svc._merge_colocation_into_summaries(summaries, agg)
    dc13 = next(d for d in out if d["id"] == "DC13")
    dc99 = next(d for d in out if d["id"] == "DC99")
    assert dc13["coloc_total_u"] == 94 and dc13["coloc_used_u"] == 55 and dc13["coloc_free_u"] == 39
    assert dc99["coloc_total_u"] == 0 and dc99["coloc_free_u"] == 0
