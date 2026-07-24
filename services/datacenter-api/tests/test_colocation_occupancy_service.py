"""get_dc_racks_occupancy: 6h singleflight cache; delegates the math to the
shared colocation module; DB-down returns the empty shape."""
from unittest.mock import patch

from psycopg2 import OperationalError

from app.services.dc_service import DatabaseService


def _svc_no_db():
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool",
               side_effect=OperationalError("no db")):
        return DatabaseService()


def test_occupancy_cache_miss_uses_singleflight_6h_ttl():
    svc = _svc_no_db()
    fake = {"racks": [], "summary": {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0}}
    with patch("app.services.dc_service.cache.get", return_value=None), \
         patch("app.services.dc_service.cache.run_singleflight", return_value=fake) as sf:
        result = svc.get_dc_racks_occupancy("DC13")
    assert result == fake
    assert sf.call_count == 1
    assert sf.call_args[1].get("ttl") == 21600


def test_occupancy_cache_hit_short_circuits():
    svc = _svc_no_db()
    cached = {"racks": [{"rack_name": "116"}], "summary": {}}
    with patch("app.services.dc_service.cache.get", return_value=cached), \
         patch("app.services.dc_service.cache.run_singleflight") as sf:
        result = svc.get_dc_racks_occupancy("DC13")
    assert result == cached
    sf.assert_not_called()


def test_occupancy_blank_dc_returns_empty():
    svc = _svc_no_db()
    result = svc.get_dc_racks_occupancy("   ")
    assert result == {"racks": [], "summary": {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0}}
