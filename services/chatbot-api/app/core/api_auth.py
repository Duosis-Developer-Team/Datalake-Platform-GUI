"""API auth — byte-for-byte compatible with the other microservices.

Same env contract as ``services/datacenter-api/app/core/api_auth.py`` so the
JWT minted by the Dash frontend (``src.auth.api_jwt.create_api_token``) verifies
here unchanged:

* ``API_AUTH_REQUIRED`` toggles enforcement (default false for local/dev).
* Signing secret chain: ``API_JWT_SECRET`` -> ``SECRET_KEY`` -> dev default.
* ``HS256``; subject (``sub``) is the WebUI user id.
"""

import os
from typing import Annotated

import jwt
from fastapi import Header, HTTPException

_API_AUTH_REQUIRED = os.getenv("API_AUTH_REQUIRED", "false").lower() in ("1", "true", "yes")
_SECRET = (
    os.getenv("API_JWT_SECRET") or os.getenv("SECRET_KEY") or "change_me_secret_key"
).encode("utf-8")


def verify_api_user(authorization: Annotated[str | None, Header()] = None) -> str | None:
    """Return JWT subject (user id) when auth is required and the token is valid.

    Returns ``None`` when ``API_AUTH_REQUIRED`` is false (local/dev), matching the
    behaviour of the sibling services so the chatbot stays usable without auth in
    development while still enforcing identity in production.
    """
    if not _API_AUTH_REQUIRED:
        return None
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, _SECRET, algorithms=["HS256"])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return str(sub)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
