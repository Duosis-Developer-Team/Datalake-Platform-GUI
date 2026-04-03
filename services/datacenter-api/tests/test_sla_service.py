from unittest.mock import patch

from app.services.sla_service import SLA_CACHE_TTL_SECONDS, refresh_sla_cache


def test_refresh_sla_cache_passes_ttl_matching_stale_threshold():
    raw = {
        "items": [],
        "period_start": None,
        "period_end": None,
        "period_min": 0,
    }
    with patch("app.services.sla_service._fetch_sla_raw", return_value=raw), \
         patch("app.services.sla_service.cache.set") as set_mock:
        refresh_sla_cache({"start": "2025-01-01", "end": "2025-01-31"})

    set_mock.assert_called_once()
    assert set_mock.call_args.kwargs.get("ttl") == SLA_CACHE_TTL_SECONDS
