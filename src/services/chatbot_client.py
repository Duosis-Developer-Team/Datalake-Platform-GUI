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
import requests

from src.auth.api_jwt import create_service_token

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
    *,
    include_debug: bool = False,
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
        "include_debug": include_debug,
    }
    resp = httpx.post(
        url,
        json=payload,
        headers=_headers(),
        timeout=timeout or CHATBOT_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def generate_release_note(
    payload: dict,
    *,
    strict: bool = False,
    complaint: str | None = None,
    model: str | None = None,
    timeout: int = 60,
) -> dict:
    """chatbot-api'den release note ister.

    Asla exception fırlatmaz; her yolda `status` anahtarı olan bir sözlük döner,
    çünkü çağıran taraf başarısızlıkta merdivende ilerlemek zorunda.

    Bu yol kullanıcı isteğine bağlı değil (script ve arka plan işleri de çağırır),
    o yüzden oturum JWT'si yerine ``create_service_token()`` kullanılır.
    """
    body = dict(payload)
    body["strict"] = bool(strict)
    body["complaint"] = complaint
    body["model"] = model
    headers = {
        "Authorization": f"Bearer {create_service_token()}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            f"{CHATBOT_API_URL}/api/v1/release-notes/generate",
            json=body,
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("release note request failed: %s", exc)
        return {"status": "failed", "detail": "transport"}
    if not isinstance(data, dict) or "status" not in data:
        return {"status": "failed", "detail": "shape"}
    return data
