"""JWT bearer verification for admin API routes."""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Header, HTTPException

from app import config


def verify_api_user(authorization: Annotated[str | None, Header()] = None) -> str | None:
    """Return JWT subject when auth is required and token is valid."""
    if not config.API_AUTH_REQUIRED:
        return None
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(
            token,
            config.API_JWT_SECRET.encode("utf-8"),
            algorithms=["HS256"],
        )
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return str(sub)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
