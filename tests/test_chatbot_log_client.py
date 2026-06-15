"""Tests for chatbot_log_client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.services import chatbot_log_client


def test_list_turns_success():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"items": [{"request_id": "a1"}], "total": 1, "skip": 0, "limit": 50}
    mock_resp.raise_for_status = MagicMock()
    with patch("src.services.chatbot_log_client.httpx.get", return_value=mock_resp) as mock_get:
        data = chatbot_log_client.list_turns(skip=0, limit=10, status="success")
    assert data["total"] == 1
    mock_get.assert_called_once()
    assert mock_get.call_args.kwargs["params"]["status"] == "success"


def test_list_turns_error_returns_empty():
    with patch("src.services.chatbot_log_client.httpx.get", side_effect=Exception("down")):
        data = chatbot_log_client.list_turns()
    assert data["items"] == []
    assert data["total"] == 0
    assert "error" in data


def test_get_turn_found():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"request_id": "x"}
    mock_resp.raise_for_status = MagicMock()
    with patch("src.services.chatbot_log_client.httpx.get", return_value=mock_resp):
        turn = chatbot_log_client.get_turn("x")
    assert turn["request_id"] == "x"


def test_get_turn_not_found():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch("src.services.chatbot_log_client.httpx.get", return_value=mock_resp):
        turn = chatbot_log_client.get_turn("missing")
    assert turn is None
