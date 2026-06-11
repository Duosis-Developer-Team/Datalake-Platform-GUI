"""Server-side client for the internal chatbot-api microservice.

IMPORTANT: this runs inside the Dash/Flask server process only. The browser must
never call the chatbot API (or the LLM) directly, so the Bulutistan LLM token
never reaches client-side code. The user's identity is forwarded using the same
JWT scheme as the other backend clients (``src.services.api_client._auth_headers``).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CHATBOT_API_URL = os.getenv("CHATBOT_API_URL", "http://chatbot-api:8000").rstrip("/")
CHATBOT_TIMEOUT_SECONDS = float(os.getenv("CHATBOT_CLIENT_TIMEOUT", "600"))


def _headers() -> dict[str, str]:
    """Forward the authenticated user's JWT, reusing the existing helper."""
    try:
        from src.services.api_client import _auth_headers

        return _auth_headers()
    except Exception:  # pragma: no cover - defensive (outside request context)
        return {}


def send_chat_message(
    message: str,
    conversation: list[dict[str, str]] | None,
    frontend_context: dict[str, Any] | None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """POST a chat message to chatbot-api and return the parsed response.

    Only ``role``/``content`` are forwarded from the conversation (UI metadata
    stays local, per CTO pack 08). Raises ``httpx.HTTPError`` on transport/HTTP
    failure so the caller can render a friendly error state.
    """
    url = f"{CHATBOT_API_URL}/api/v1/chatbot/messages"
    clean_history = [
        {"role": m.get("role"), "content": m.get("content", "")}
        for m in (conversation or [])
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    payload = {
        "message": message,
        "conversation": clean_history,
        "frontend_context": frontend_context or {},
    }
    resp = httpx.post(
        url,
        json=payload,
        headers=_headers(),
        timeout=timeout or CHATBOT_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()
