"""Server-side client for chatbot-log-api (read turn logs from MongoDB).

Runs inside the Dash/Flask process only. Uses the internal API key — never expose
this to the browser.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

CHATBOT_LOG_API_URL = os.getenv("CHATBOT_LOG_API_URL", "http://chatbot-log-api:8000").rstrip("/")
CHATBOT_LOG_API_KEY = os.getenv("CHATBOT_LOG_API_KEY", "")
CHATBOT_LOG_TIMEOUT = float(os.getenv("CHATBOT_LOG_CLIENT_TIMEOUT", "15"))


def _headers() -> dict[str, str]:
    key = (CHATBOT_LOG_API_KEY or "").strip()
    return {"X-Internal-Api-Key": key} if key else {}


def list_turns(
    *,
    skip: int = 0,
    limit: int = 50,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    status: Optional[str] = None,
    response_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict[str, Any]:
    """Return paginated turn list from chatbot-log-api."""
    params: dict[str, Any] = {"skip": skip, "limit": limit}
    if user_id:
        params["user_id"] = user_id
    if username:
        params["username"] = username
    if status:
        params["status"] = status
    if response_type:
        params["response_type"] = response_type
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to
    url = f"{CHATBOT_LOG_API_URL}/api/v1/logs/turns"
    try:
        resp = httpx.get(url, params=params, headers=_headers(), timeout=CHATBOT_LOG_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("chatbot log list failed: %s", exc)
        return {"items": [], "total": 0, "skip": skip, "limit": limit, "error": str(exc)}


def get_turn(request_id: str) -> Optional[dict[str, Any]]:
    """Return a single turn by request_id, or None if not found."""
    rid = (request_id or "").strip()
    if not rid:
        return None
    url = f"{CHATBOT_LOG_API_URL}/api/v1/logs/turns/{rid}"
    try:
        resp = httpx.get(url, headers=_headers(), timeout=CHATBOT_LOG_TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError:
        raise
    except Exception as exc:
        logger.warning("chatbot log get failed for %s: %s", rid, exc)
        return None
