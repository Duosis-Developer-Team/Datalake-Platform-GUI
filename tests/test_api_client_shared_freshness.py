"""Item 2.1: cache freshness (age) must be tracked in the SHARED cache backend
using wall-clock time, not a per-process monotonic dict — otherwise pods can't
agree on whether an entry is fresh, and the no-stale rule (item 2.2) can't hold
across pods.
"""
import time

from src.services import api_client as api
from src.services import cache_service


def test_fetched_ts_key_is_namespaced():
    assert api._fetched_ts_key("api:foo:1") == "api:__ts__:api:foo:1"


def test_mark_fetched_stores_walltime_in_shared_cache():
    cache_service.clear()
    before = time.time()
    api._mark_fetched("api:foo:1")
    ts = cache_service.get(api._fetched_ts_key("api:foo:1"))
    assert ts is not None
    assert before <= ts <= time.time() + 1


def test_swr_age_reads_from_shared_cache():
    cache_service.clear()
    cache_service.set(api._fetched_ts_key("api:foo:1"), time.time() - 42.0)
    age = api._swr_age("api:foo:1")
    assert age is not None
    assert 40.0 <= age <= 60.0


def test_swr_age_none_when_no_timestamp():
    cache_service.clear()
    assert api._swr_age("api:never:stamped") is None


def test_leader_fetch_stamps_shared_timestamp():
    cache_service.clear()
    api._api_cache_get_with_stale("api:leaderk", lambda: {"v": 9}, {})
    ts = cache_service.get(api._fetched_ts_key("api:leaderk"))
    assert ts is not None, "leader fetch must stamp freshness in the shared cache"
