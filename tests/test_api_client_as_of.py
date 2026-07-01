"""Item 2.4: get_cache_as_of exposes the wall-clock time a cache key was last
fetched, so the UI can show an "as-of HH:MM" stamp and metrics can report the
data's age. Returns None when the key has no recorded fetch time.
"""
import time

from src.services import api_client as api
from src.services import cache_service


def test_get_cache_as_of_returns_none_when_unknown():
    cache_service.clear()
    assert api.get_cache_as_of("api:never") is None


def test_get_cache_as_of_returns_walltime_after_mark():
    cache_service.clear()
    before = time.time()
    api._mark_fetched("api:x")
    ts = api.get_cache_as_of("api:x")
    assert ts is not None
    assert before <= ts <= time.time() + 1


def test_get_cache_as_of_after_leader_fetch():
    cache_service.clear()
    api._api_cache_get_with_stale("api:k", lambda: {"v": 1}, {})
    assert api.get_cache_as_of("api:k") is not None
