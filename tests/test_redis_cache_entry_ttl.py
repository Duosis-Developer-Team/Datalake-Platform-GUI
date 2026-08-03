"""Cache entries must carry a TTL, and Redis must only evict entries that have one.

Today's configuration contradicts itself. cache_service's docstring states that
"cache entries never disappear until explicitly overwritten by fresh data", but
RedisBackend.set writes without an expiry while Redis runs `allkeys-lru` on a
256 MB budget. allkeys-lru evicts *any* key, TTL or not, so the invariant is
silently false under memory pressure: measured, 427 `dl:fecache:*` keys dropped
to 415 when the budget tightened. A key vanishing between two renders is one of
the shapes of "sayfa gidip geliyor" — the page loses the value it just showed.

The fix makes the two halves agree: every entry gets a bounded TTL, and Redis
switches to `volatile-lru` so it can only reclaim keys that were declared
expendable. Keys without a TTL — none of ours, but anything a future caller
writes — are then protected rather than silently reaped.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

from src.services import cache_service

ROOT = Path(__file__).resolve().parents[1]


def _redis_command() -> str:
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    block = text.split("\n  redis:\n", 1)[1]
    match = re.search(r"^\s+command:\s*(.+)$", block, re.MULTILINE)
    assert match, "the redis service must pin its eviction policy explicitly"
    return match.group(1)


def test_redis_only_evicts_keys_that_declared_a_ttl():
    assert "volatile-lru" in _redis_command()
    assert "allkeys-lru" not in _redis_command()


def test_redis_still_has_a_memory_budget():
    """volatile-lru without maxmemory is just noeviction with extra steps."""
    assert "--maxmemory " in _redis_command()


def test_k8s_redis_uses_the_same_policy_as_compose():
    """The manifest is what production runs; compose only describes the laptop.

    Reads the argument that follows --maxmemory-policy rather than searching the
    file, so the comment above it can name the policy it replaced.
    """
    text = (ROOT / "k8s/redis/deployment.yaml").read_text(encoding="utf-8")
    match = re.search(r"-\s*--maxmemory-policy\s*\n\s*-\s*(\S+)", text)

    assert match, "the redis manifest must pass --maxmemory-policy explicitly"
    assert match.group(1) == "volatile-lru"


def test_set_writes_an_expiry():
    client = MagicMock()
    backend = cache_service.RedisBackend(client)

    backend.set("api:global_dashboard:7d", {"vms": 1})

    _, kwargs = client.set.call_args
    assert kwargs.get("ex") == cache_service.MAX_ENTRY_AGE_SECONDS


def test_set_accepts_a_caller_supplied_ttl():
    client = MagicMock()
    backend = cache_service.RedisBackend(client)

    backend.set("api:global_dashboard:7d", {"vms": 1}, ttl=60)

    _, kwargs = client.set.call_args
    assert kwargs.get("ex") == 60


def test_ttl_is_a_large_multiple_of_the_swr_window():
    """The TTL is an eviction hint, not a freshness one. If it were close to the
    SWR window, an entry could expire while it was still the best value we had,
    and the stale-over-empty fallback would have nothing to fall back to."""
    from src.services.api_client import _SWR_TTL_SECONDS

    assert cache_service.MAX_ENTRY_AGE_SECONDS >= 8 * _SWR_TTL_SECONDS


def test_ttl_is_bounded():
    """Not indefinite either — a value nobody has refreshed in hours is not
    'last known good', it is a value from a pipeline that has been dead all day."""
    assert cache_service.MAX_ENTRY_AGE_SECONDS <= 24 * 3600


def test_in_process_backend_ignores_the_ttl_argument():
    """Same interface both ways; the in-process cache has its own LRU bound."""
    backend = cache_service.InProcessBackend(max_size=4)

    backend.set("k", "v", ttl=1)

    assert backend.get("k") == "v"


def test_module_level_set_passes_the_ttl_through():
    backend = MagicMock()
    previous = cache_service.get_backend()
    cache_service.set_backend(backend)
    try:
        cache_service.set("k", "v", ttl=42)
    finally:
        cache_service.set_backend(previous)

    backend.set.assert_called_once_with("k", "v", ttl=42)
