"""Frontend chatbot server-side client tests."""

from unittest.mock import MagicMock, patch

import src.services.chatbot_client as cc


def test_send_posts_to_chatbot_api_and_forwards_auth():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"answer": "ok", "model": "gpt-oss-120b", "request_id": "x"}
    mock_resp.raise_for_status.return_value = None

    with patch.object(cc, "_headers", return_value={"Authorization": "Bearer TESTJWT"}), patch(
        "src.services.chatbot_client.httpx.post", return_value=mock_resp
    ) as mock_post:
        out = cc.send_chat_message(
            "DC13 durumu",
            [{"role": "user", "content": "merhaba", "ts": "2026-06-04T00:00:00Z"}],
            {"pathname": "/datacenter/DC13"},
        )

    assert out["answer"] == "ok"

    _args, kwargs = mock_post.call_args
    url = _args[0] if _args else kwargs.get("url")
    assert url.endswith("/api/v1/chatbot/messages")
    assert cc.CHATBOT_API_URL in url
    # JWT forwarded verbatim.
    assert kwargs["headers"] == {"Authorization": "Bearer TESTJWT"}
    # Only role/content forwarded — UI metadata (ts) stripped.
    payload = kwargs["json"]
    assert payload["message"] == "DC13 durumu"
    assert payload["conversation"] == [{"role": "user", "content": "merhaba"}]
    assert payload["frontend_context"] == {"pathname": "/datacenter/DC13"}


def test_default_url_targets_internal_service():
    # Default must be the internal Docker/K8s service name, never the public LLM.
    assert cc.CHATBOT_API_URL.endswith(":8000") or "chatbot-api" in cc.CHATBOT_API_URL


def test_module_source_has_no_secret_or_llm_url():
    import inspect

    src = inspect.getsource(cc)
    assert "sk-proj" not in src
    assert "api.bulutistan.ai" not in src
