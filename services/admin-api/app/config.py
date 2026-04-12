"""Admin API configuration — loaded from environment variables."""

from __future__ import annotations

import os

AUTH_DB_HOST: str = os.getenv("AUTH_DB_HOST", "auth-db")
AUTH_DB_PORT: int = int(os.getenv("AUTH_DB_PORT", "5432"))
AUTH_DB_NAME: str = os.getenv("AUTH_DB_NAME", "bulutauth")
AUTH_DB_USER: str = os.getenv("AUTH_DB_USER", "authadmin")
AUTH_DB_PASS: str = os.getenv("AUTH_DB_PASS", "change_me_auth")

SECRET_KEY: str = os.getenv("SECRET_KEY", "change_me_secret_key")
FERNET_KEY: str = os.getenv("FERNET_KEY", "")

API_AUTH_REQUIRED: bool = os.getenv("API_AUTH_REQUIRED", "false").lower() in ("1", "true", "yes")
API_JWT_SECRET: str = (os.getenv("API_JWT_SECRET") or SECRET_KEY)
