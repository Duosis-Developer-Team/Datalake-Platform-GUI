"""Auth database and security configuration (environment-driven)."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

AUTH_DB_HOST = os.environ.get("AUTH_DB_HOST", "localhost")
AUTH_DB_PORT = int(os.environ.get("AUTH_DB_PORT", "5433"))
AUTH_DB_NAME = os.environ.get("AUTH_DB_NAME", "bulutauth")
AUTH_DB_USER = os.environ.get("AUTH_DB_USER", "authadmin")
AUTH_DB_PASS = os.environ.get("AUTH_DB_PASS", "change_me_auth")

SECRET_KEY = os.environ.get("SECRET_KEY", "change_me_secret_key")
ADMIN_DEFAULT_PASSWORD = os.environ.get("ADMIN_DEFAULT_PASSWORD", "Admin123!")
ADMIN_DEFAULT_USERNAME = os.environ.get("ADMIN_DEFAULT_USERNAME", "admin")

FERNET_KEY = os.environ.get("FERNET_KEY", "").strip() or None

SESSION_TTL_HOURS = int(os.environ.get("SESSION_TTL_HOURS", "24"))
AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")

# Cookie / session
SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "dl_session")
