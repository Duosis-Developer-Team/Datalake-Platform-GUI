"""Tests for POST /api/v1/admin/cache/refresh."""

from unittest.mock import patch


def test_admin_cache_refresh_rebuilds_without_flush(mock_customer_service):
    client, mock_svc = mock_customer_service
    with patch("app.core.cache_backend.cache_flush_pattern") as mock_flush, patch(
        "app.routers.admin_cache.threading.Thread"
    ) as mock_thread:
        mock_thread.return_value.start.return_value = None
        r = client.post("/api/v1/admin/cache/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    assert body.get("warm_tier") == "background"
    assert "cache" in body
    mock_flush.assert_not_called()
    mock_svc.warm_cache.assert_called_once()
    mock_thread.assert_called_once()
    assert mock_thread.call_args.kwargs.get("target") is mock_svc.refresh_warm_tier_caches
