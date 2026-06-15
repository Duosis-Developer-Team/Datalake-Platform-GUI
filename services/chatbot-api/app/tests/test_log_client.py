"""Tests for chatbot-log-api client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models.schemas import ChatResponse
from app.services import log_client
from app.services.audit_service import AuditRecord


def test_build_turn_payload_redacts_and_includes_fields():
    audit = AuditRecord(request_id="r1", user_id="u1", status="success", model="m1")
    response = ChatResponse(
        answer="answer text",
        model="m1",
        request_id="r1",
        response_type="answer",
    )
    payload = log_client.build_turn_payload(
        audit=audit,
        user_message="token=secret123",
        response=response,
        frontend_context=None,
    )
    assert payload["request_id"] == "r1"
    assert "[REDACTED]" in payload["user_message"] or "secret123" not in payload["user_message"]


def test_record_turn_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(log_client.settings, "chatbot_log_api_enabled", False)
    with patch("httpx.Client") as mock_client:
        log_client.record_turn({"request_id": "x"})
        mock_client.assert_not_called()


def test_record_turn_posts_when_enabled(monkeypatch):
    monkeypatch.setattr(log_client.settings, "chatbot_log_api_enabled", True)
    monkeypatch.setattr(log_client.settings, "chatbot_log_api_url", "http://log-api:8000")
    mock_http = MagicMock()
    mock_http.__enter__.return_value.post.return_value.status_code = 200
    with patch("httpx.Client", return_value=mock_http):
        log_client.record_turn({"request_id": "x", "status": "success"})
    mock_http.__enter__.return_value.post.assert_called_once()
