"""Item 2.1: cache freshness (age) must be tracked in the SHARED cache backend
using wall-clock time, not a per-process monotonic dict — otherwise pods can't
agree on whether an entry is fresh, and the no-stale rule (item 2.2) can't hold
across pods.

That requirement is unchanged. What changed is where the timestamp sits: it used
to be a second shared key (`api:__ts__:<key>`) and is now a field inside the
entry itself, because Redis evicted the two independently and a value that
outlived its timestamp was read as fresh forever. Both properties still have to
hold — shared, and wall-clock — so they are still tested here, just through
_cache_store / _cache_load.
"""
import time

import pytest

from tests.conftest import seed_cache_entry
from src.services import api_client as api
from src.services import cache_service


@pytest.fixture(autouse=True)
def clean_cache():
    cache_service.clear()
    yield
    cache_service.clear()


def test_the_timestamp_lands_in_the_shared_backend():
    """Another pod reading the same backend must see the age, so it cannot live
    in a process-local dict."""
    api._cache_store("api:foo:1", {"v": 1})

    raw = cache_service.get("api:foo:1")

    assert isinstance(raw, dict) and api._SWR_STAMP in raw, (
        "freshness must be readable from the shared backend by any pod"
    )


def test_the_timestamp_is_wall_clock_not_monotonic():
    """time.monotonic() is meaningless across processes; epoch seconds are not."""
    before = time.time()
    api._cache_store("api:foo:1", {"v": 1})
    after = time.time()

    raw = cache_service.get("api:foo:1")

    assert before <= raw[api._SWR_STAMP] <= after


def test_age_is_derived_from_the_shared_timestamp():
    seed_cache_entry("api:foo:1", {"v": 1}, age_seconds=42.0)

    _, age = api._cache_load("api:foo:1")

    assert age is not None
    assert 40.0 <= age <= 60.0


def test_age_is_none_when_nothing_was_stamped():
    _, age = api._cache_load("api:never:stamped")

    assert age is None


def test_leader_fetch_stamps_the_shared_entry():
    api._api_cache_get_with_stale("api:leaderk", lambda: {"v": 9}, {})

    raw = cache_service.get("api:leaderk")

    assert isinstance(raw, dict) and raw.get(api._SWR_STAMP) is not None, (
        "leader fetch must stamp freshness in the shared cache"
    )


def test_a_second_pod_reading_the_same_backend_agrees_on_freshness():
    """The whole reason the timestamp is shared: two processes, one verdict."""
    seed_cache_entry("api:foo:1", {"v": 1}, age_seconds=10)
    assert api._is_fresh("api:foo:1") is True

    seed_cache_entry("api:foo:1", {"v": 1}, age_seconds=10_000)
    assert api._is_fresh("api:foo:1") is False
