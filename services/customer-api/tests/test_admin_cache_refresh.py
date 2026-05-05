"""Tests for POST /api/v1/admin/cache/refresh."""

from unittest.mock import patch


def test_admin_cache_refresh_calls_warm_and_flush(mock_customer_service):
    client, mock_svc = mock_customer_service
    with patch("app.routers.admin_cache.cache_flush_pattern") as mock_flush:
        r = client.post("/api/v1/admin/cache/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    assert "cache" in body
    mock_flush.assert_called_once_with("*")
    mock_svc.warm_cache.assert_called_once()
