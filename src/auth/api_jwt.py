"""Short-lived JWT for Dash -> FastAPI microservice calls (shared secret)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt

# Same env as Flask SECRET_KEY by default so docker-compose stays simple
_API_SECRET = (os.environ.get("API_JWT_SECRET") or os.environ.get("SECRET_KEY") or "change_me_secret_key").encode(
    "utf-8"
)
_ALGO = "HS256"
_TTL_MIN = int(os.environ.get("API_JWT_TTL_MIN", "15"))


def create_api_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=_TTL_MIN),
        "typ": "api",
    }
    return jwt.encode(payload, _API_SECRET, algorithm=_ALGO)


def decode_api_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _API_SECRET, algorithms=[_ALGO])
    except Exception:
        return None
