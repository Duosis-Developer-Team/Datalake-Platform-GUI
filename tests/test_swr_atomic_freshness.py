"""A cached value and its fetch time must live or die together.

Freshness was tracked in a *second* cache entry: the value went to `api:<key>`
and its timestamp to `api:__ts__:<key>`. Redis has no idea the two are related,
so eviction took them independently — and `_is_fresh` read a missing timestamp
as "unknown age, treat as fresh":

    return age is None or age <= _SWR_TTL_SECONDS

Lose the small timestamp twin and keep the big data key, and that entry becomes
permanently fresh. It is never refetched again for the life of the process: the
page shows one snapshot forever while the rest of the UI moves on. Live audit
found 7 data keys in this state with no surviving twin.

Storing both halves in one entry removes the failure mode rather than narrowing
it — eviction now takes the value and its age together, which is just a miss,
and a miss is a case the code already handles correctly. Entries with no
timestamp (anything written before this change) read as stale rather than fresh,
so the worst case is one refetch instead of a permanent freeze.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from src.services import api_client
from src.services import cache_service


@pytest.fixture
def fresh_cache():
    """Give each test its own in-process backend so keys cannot leak between them."""
    previous = cache_service.get_backend()
    cache_service.set_backend(cache_service.InProcessBackend(max_size=64))
    try:
        yield cache_service.get_backend()
    finally:
        cache_service.set_backend(previous)


def test_value_and_timestamp_occupy_a_single_entry(fresh_cache):
    """The whole point: one key, so eviction cannot split them."""
    with patch.object(cache_service, "set", wraps=cache_service.set) as spy:
        api_client._cache_store("api:demo", {"vms": 12})

    written = [call.args[0] for call in spy.call_args_list]
    assert written == ["api:demo"], f"expected one key, got {written}"


def test_stored_value_reads_back_unchanged(fresh_cache):
    """The envelope must be invisible to callers."""
    payload = {"vms": 12, "nested": {"a": [1, 2, 3]}}
    api_client._cache_store("api:demo", payload)

    value, age = api_client._cache_load("api:demo")

    assert value == payload
    assert age is not None and age < 5


def test_a_missing_key_reads_as_absent(fresh_cache):
    value, age = api_client._cache_load("api:nothing_here")

    assert value is None
    assert age is None


def test_entry_without_a_timestamp_is_stale_not_fresh(fresh_cache):
    """The inverted default. A raw value left by the previous release has no
    recorded age; treating that as fresh is what froze keys permanently."""
    cache_service.set("api:legacy", {"vms": 1})

    assert api_client._is_fresh("api:legacy") is False


def test_a_just_written_entry_is_fresh(fresh_cache):
    api_client._cache_store("api:demo", {"vms": 1})

    assert api_client._is_fresh("api:demo") is True


def test_an_entry_past_the_window_is_stale(fresh_cache):
    api_client._cache_store("api:demo", {"vms": 1})

    later = time.time() + api_client._SWR_TTL_SECONDS + 1
    with patch("src.services.api_client.time.time", return_value=later):
        assert api_client._is_fresh("api:demo") is False


def test_deleting_the_old_side_car_key_cannot_freeze_an_entry(fresh_cache):
    """The exact live failure: the twin disappears, the data key stays.

    With the side-car gone there is no twin to lose, so removing a key shaped
    like the old one leaves freshness untouched.
    """
    api_client._cache_store("api:demo", {"vms": 1})
    cache_service.delete("api:__ts__:api:demo")

    assert api_client._is_fresh("api:demo") is True
    value, age = api_client._cache_load("api:demo")
    assert value == {"vms": 1}
    assert age is not None


def test_evicting_the_entry_loses_the_age_with_it(fresh_cache):
    """Eviction degrades to a plain miss, which the callers already handle."""
    api_client._cache_store("api:demo", {"vms": 1})
    cache_service.delete("api:demo")

    value, age = api_client._cache_load("api:demo")

    assert value is None
    assert age is None
    assert api_client._is_fresh("api:demo") is False


def test_get_cache_as_of_reports_the_stored_fetch_time(fresh_cache):
    """The UI "as-of HH:MM" stamp reads the same timestamp the freshness check does."""
    before = time.time()
    api_client._cache_store("api:demo", {"vms": 1})
    after = time.time()

    stamp = api_client.get_cache_as_of("api:demo")

    assert stamp is not None
    assert before <= stamp <= after


def test_get_cache_as_of_is_none_for_a_legacy_entry(fresh_cache):
    cache_service.set("api:legacy", {"vms": 1})

    assert api_client.get_cache_as_of("api:legacy") is None


def test_the_side_car_helpers_are_gone():
    """Pinning the removal: a leftover _mark_fetched call would write a timestamp
    nothing reads, and the entry it belongs to would read as stale forever."""
    assert not hasattr(api_client, "_mark_fetched")
    assert not hasattr(api_client, "_fetched_ts_key")
