"""Tests for chatbot-log-api (mocked Mongo)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


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
