"""Pytest / test defaults so DatabaseService can initialize a pool when patched."""

import os

# Required for src.services.db_service.DatabaseService.__init__ when not fully mocked.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PASS", "test-secret")
