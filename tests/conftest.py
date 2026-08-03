"""Pytest / test defaults so DatabaseService can initialize a pool when patched."""

import os

# Required for src.services.db_service.DatabaseService.__init__ when not fully mocked.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PASS", "test-secret")

# Importing app.py starts a background thread that calls warm_common() immediately,
# which can race a test that monkeypatches warm_common's internals (see
# tests/test_warm_common.py). Disable it for the whole test session.
os.environ.setdefault("APP_DISABLE_BACKGROUND_WARM", "1")


def seed_cache_entry(key, value, age_seconds=0.0):
    """Put `value` in the API response cache as if it had been fetched that long ago.

    Tests used to seed freshness by writing two keys — the value, and a separate
    `api:__ts__:<key>` timestamp. That side-car is gone (the pair could be split
    by eviction, which froze entries permanently), so the age now lives inside
    the entry. Going through this helper keeps the storage format in one place
    instead of spread across a dozen test files.
    """
    import time

    from src.services import api_client, cache_service

    cache_service.set(key, {api_client._SWR_STAMP: time.time() - age_seconds, "value": value})


def seed_unstamped_entry(key, value):
    """Write a bare value with no recorded fetch time, the way a pre-upgrade
    release left entries in Redis. These read as stale and cost one refetch."""
    from src.services import cache_service

    cache_service.set(key, value)
