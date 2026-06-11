from unittest.mock import MagicMock

import pytest

from app.services import llm_client
from app.services.llm_client import LLMClient, LLMError, MSG_AUTH_FAILED, MSG_NOT_CONFIGURED


def test_auth_error_maps_to_api_token_message_not_jwt(monkeypatch):
    # Simulate upstream 401. The credential is a Bulutistan LLMaaS API token, so
    # the user-facing message must talk about an "API token", never a JWT.
    class _FakeAuth(Exception):
        pass

    monkeypatch.setattr(llm_client, "AuthenticationError", _FakeAuth)

    c = LLMClient()
    monkeypatch.setattr(c.settings, "bulutistan_llm_api_key", "sk-proj-FAKE000000")
    fake = MagicMock()
    fake.chat.completions.create.side_effect = _FakeAuth("401 unauthorized")
    monkeypatch.setattr(c, "_get_client", lambda: fake)

    with pytest.raises(LLMError) as ei:
        c.complete([{"role": "user", "content": "hi"}])

    assert ei.value.error_type == "auth"
    assert ei.value.user_message == MSG_AUTH_FAILED
    assert "jwt" not in ei.value.user_message.lower()
    assert "api token" in ei.value.user_message.lower()
    # Auth failures must NOT trigger a fallback-model retry.
    assert fake.chat.completions.create.call_count == 1


def test_missing_key_uses_not_configured_message(monkeypatch):
    c = LLMClient()
    monkeypatch.setattr(c.settings, "bulutistan_llm_api_key", "")
    with pytest.raises(LLMError) as ei:
        c.complete([{"role": "user", "content": "hi"}])
    assert ei.value.error_type == "not_configured"
    assert ei.value.user_message == MSG_NOT_CONFIGURED
    assert "jwt" not in ei.value.user_message.lower()
