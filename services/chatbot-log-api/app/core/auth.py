"""Internal service-to-service authentication."""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.config import settings


def verify_internal_api_key(x_internal_api_key: str | None = Header(default=None)) -> None:
    expected = (settings.internal_api_key or "").strip()
    if not expected:
        return
    if (x_internal_api_key or "").strip() != expected:
        raise HTTPException(status_code=401, detail="invalid_internal_api_key")
