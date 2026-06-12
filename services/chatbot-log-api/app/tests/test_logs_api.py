"""Tests for chatbot-log-api (mocked Mongo)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_SAMPLE_TURN = {
    "request_id": "abc123",
    "status": "success",
    "model": "test-model",
    "user_message": "hello",
    "assistant_answer": "hi",
    "response_type": "answer",
    "created_at": datetime(2026, 6, 12, 10, 0, 0, tzinfo=timezone.utc),
    "expires_at": datetime(2026, 9, 10, 10, 0, 0, tzinfo=timezone.utc),
}


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "chatbot-log-api"


def test_create_turn_mocked():
    with patch("app.services.mongo_store.insert_turn", new_callable=AsyncMock) as mock_insert:
        payload = {
            "request_id": "abc123",
            "status": "success",
            "model": "test-model",
            "user_message": "hello",
            "assistant_answer": "hi",
            "response_type": "answer",
        }
        resp = client.post("/api/v1/logs/turns", json=payload)
        assert resp.status_code == 200
        assert resp.json()["request_id"] == "abc123"
        mock_insert.assert_awaited_once()


def test_list_turns_mocked():
    with patch(
        "app.services.mongo_store.list_turns",
        new_callable=AsyncMock,
        return_value=([_SAMPLE_TURN], 1),
    ):
        resp = client.get("/api/v1/logs/turns?skip=0&limit=10&status=success")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["skip"] == 0
        assert data["limit"] == 10
        assert len(data["items"]) == 1
        assert data["items"][0]["request_id"] == "abc123"


def test_get_turn_mocked():
    with patch(
        "app.services.mongo_store.get_turn_by_request_id",
        new_callable=AsyncMock,
        return_value=_SAMPLE_TURN,
    ):
        resp = client.get("/api/v1/logs/turns/abc123")
        assert resp.status_code == 200
        assert resp.json()["request_id"] == "abc123"


def test_get_turn_not_found():
    with patch(
        "app.services.mongo_store.get_turn_by_request_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = client.get("/api/v1/logs/turns/missing")
        assert resp.status_code == 404
