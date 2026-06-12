"""Tests for narrative retry in chatbot router."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.llm_client import LLMResult

client = TestClient(app)

TABLE_ONLY = "| VM | CPU |\n|---|---|\n| a | 90 |"

GOOD_NARRATIVE = (
    "**Analiz:** VM CPU verisi incelendi; yüksek tüketim tespit edildi.\n\n"
    "**Sonuç:** VM-A en yoğun kaynak.\n\n"
    "**Risk seviyesi:** medium"
)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    from app.services import log_client

    monkeypatch.setattr(settings, "chatbot_log_api_enabled", False)
    monkeypatch.setattr(log_client, "record_turn", lambda *a, **k: None)


@pytest.fixture
def enable_agentic(monkeypatch):
    monkeypatch.setattr(settings, "chatbot_agentic_mode", True)
    monkeypatch.setattr(settings, "chatbot_llm_react_mode", False)


def test_narrative_retry_on_table_only(monkeypatch, enable_agentic):
    from app.services import agent_loop

    mock_outcome = MagicMock()
    mock_outcome.plan.clarification = None
    mock_outcome.plan.clarification_block = None
    mock_outcome.results = []
    mock_outcome.analysis = None
    mock_outcome.iterations = 0
    mock_outcome.llm_rounds = 0
    mock_outcome.tool_call_count = 0
    mock_outcome.react_mode_used = False

    monkeypatch.setattr(agent_loop, "run", lambda *a, **k: mock_outcome)

    llm = MagicMock()
    llm.complete.side_effect = [
        LLMResult(answer=TABLE_ONLY, model="test", usage={"prompt_tokens": 1, "completion_tokens": 1}),
        LLMResult(answer=GOOD_NARRATIVE, model="test", usage={"prompt_tokens": 2, "completion_tokens": 2}),
    ]

    with patch("app.routers.chatbot.get_llm_client", return_value=llm):
        resp = client.post("/api/v1/chatbot/messages", json={"message": "DC13 VM cpu top"})

    assert resp.status_code == 200
    body = resp.json()
    assert "**Analiz:**" in body["answer"]
    assert "**Sonuç:**" in body["answer"]
    assert llm.complete.call_count == 2


def test_narrative_retry_skipped_when_already_good(monkeypatch, enable_agentic):
    from app.services import agent_loop

    mock_outcome = MagicMock()
    mock_outcome.plan.clarification = None
    mock_outcome.plan.clarification_block = None
    mock_outcome.results = []
    mock_outcome.analysis = None
    mock_outcome.iterations = 0
    mock_outcome.llm_rounds = 0
    mock_outcome.tool_call_count = 0
    mock_outcome.react_mode_used = False

    monkeypatch.setattr(agent_loop, "run", lambda *a, **k: mock_outcome)

    llm = MagicMock()
    llm.complete.return_value = LLMResult(
        answer=GOOD_NARRATIVE, model="test", usage={"prompt_tokens": 1, "completion_tokens": 1}
    )

    with patch("app.routers.chatbot.get_llm_client", return_value=llm):
        resp = client.post("/api/v1/chatbot/messages", json={"message": "hello capacity"})

    assert resp.status_code == 200
    assert llm.complete.call_count == 1
