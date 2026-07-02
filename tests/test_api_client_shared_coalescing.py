"""GAP1.2: cross-pod single-flight. On a cold miss the per-process leader also
tries the shared lock; if another pod holds it (is already fetching), this pod
waits for that pod's result in the shared cache instead of firing the same slow
query — killing the cross-pod stampede.
"""
import pytest

from src.services import api_client as api
from src.services import cache_service


@pytest.fixture(autouse=True)
def _isolated_backend():
    """Fresh backend per test so a held lock never leaks into another test."""
    orig = cache_service.get_backend()
    cache_service.set_backend(cache_service.InProcessBackend())
    yield
    cache_service.set_backend(orig)


def test_leader_waits_for_other_pod_result_instead_of_fetching(monkeypatch):
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    # Another pod holds the shared lock.
    monkeypatch.setattr(api._api_response_cache, "try_acquire", lambda k, ttl: False)

    calls = {"n": 0}

    def fake_get(k):
        if k != "mk":
            return None  # ts / other keys
        calls["n"] += 1
        # miss at the top, then the other pod's result appears during the poll
        return None if calls["n"] == 1 else {"v": "from_other_pod"}

    monkeypatch.setattr(api._api_response_cache, "get", fake_get)

    fetched = []
    out = api._api_cache_get_with_stale("mk", lambda: fetched.append(1) or {"v": "mine"}, {})

    assert fetched == [], "must not fetch when another pod is already fetching"
    assert out == {"v": "from_other_pod"}


def test_global_leader_with_lock_fetches_and_releases(monkeypatch):
    cache_service.set_backend(cache_service.InProcessBackend())
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)

    out = api._api_cache_get_with_stale("mk2", lambda: {"v": "mine"}, {})
    assert out == {"v": "mine"}
    # lock released after fetch -> re-acquirable
    assert cache_service.try_acquire("mk2", ttl=30) is True
