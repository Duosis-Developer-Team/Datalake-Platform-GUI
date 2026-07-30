"""Pytest / test defaults so DatabaseService can initialize a pool when patched."""

import os

# Required for src.services.db_service.DatabaseService.__init__ when not fully mocked.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PASS", "test-secret")

# Importing app.py starts a background thread that calls warm_common() immediately,
# which can race a test that monkeypatches warm_common's internals (see
# tests/test_warm_common.py). Disable it for the whole test session.
os.environ.setdefault("APP_DISABLE_BACKGROUND_WARM", "1")
