"""Tests for POST /api/v1/admin/cache/refresh."""

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_admin_cache_refresh_calls_warm_and_flush(client: TestClient, mock_db):
    with patch("app.routers.admin_cache.cache_flush_pattern") as mock_flush:
        r = client.post("/api/v1/admin/cache/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    assert "cache" in body
    mock_flush.assert_called_once_with("*")
    mock_db.warm_cache.assert_called_once()
    mock_db.warm_additional_ranges.assert_called_once()
    mock_db.warm_s3_cache.assert_called_once()
