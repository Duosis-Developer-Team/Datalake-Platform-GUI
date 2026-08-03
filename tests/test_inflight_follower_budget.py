"""P0-4, part 1: a follower must wait for the leader's *worst* case, not its best.

Three different waits used to share one number:

  ev.wait(timeout=_INFLIGHT_WAIT_SECONDS)                   # in-process follower
  _api_response_cache.try_acquire(key, _INFLIGHT_WAIT_SECONDS)   # cross-pod lock TTL
  _wait_for_shared_result(key, _INFLIGHT_WAIT_SECONDS)      # losing pod waits

That is wrong for the first one, because the leader's path can contain the third
one *plus* a fetch. A per-process leader that loses the cross-pod lock waits for
the winning pod's result, and when that does not arrive it fetches itself — so
the leader can legitimately take shared-wait + fetch, while its own followers
gave up after shared-wait alone. The followers then return the empty fallback:
fabricated zeros, rendered as if they were data, and replaced by real numbers on
the next callback. That replacement is the "page goes and comes back" the
customer keeps reporting.

The fix splits the number in two. This file pins the relationship, because the
value is easy to "simplify" back into one constant later.
"""
from __future__ import annotations

import threading
import time

import pytest

from src.services import api_client as api
from src.services import cache_service


@pytest.fixture(autouse=True)
def clean_cache():
    cache_service.clear()
    api._inflight.clear()
    yield
    cache_service.clear()
    api._inflight.clear()


def test_follower_budget_covers_the_leaders_worst_case():
    """The invariant, stated as arithmetic: shared-wait + one fetch."""
    assert api._INFLIGHT_WAIT_SECONDS >= (
        api._SHARED_RESULT_WAIT_SECONDS + api._INTERACTIVE_READ_TIMEOUT
    ), (
        "a follower that expires before the leader returns hands the caller the "
        "empty fallback while the answer is seconds away"
    )


def test_shared_wait_covers_one_fetch():
    """The cross-pod half: a losing pod must outlast the winner's fetch, or it
    starts a duplicate fetch of the same key — the stampede this exists to stop."""
    assert api._SHARED_RESULT_WAIT_SECONDS >= api._INTERACTIVE_READ_TIMEOUT


def test_the_two_budgets_are_not_the_same_number():
    """Equal budgets are precisely the bug. Kept as its own assertion so that
    collapsing them back into one constant fails here with the reason attached."""
    assert api._INFLIGHT_WAIT_SECONDS > api._SHARED_RESULT_WAIT_SECONDS


def test_follower_gets_real_data_when_the_leader_takes_the_slow_path(monkeypatch):
    """The behaviour the arithmetic buys, exercised end to end.

    The leader loses the cross-pod lock, waits out the shared-result poll, then
    fetches. With the budgets equal the follower expires mid-fetch; with them
    split it is still waiting when ev.set() fires.
    """
    monkeypatch.setattr(api, "_SHARED_RESULT_WAIT_SECONDS", 0.3)
    monkeypatch.setattr(api, "_INFLIGHT_WAIT_SECONDS", 3.0)
    monkeypatch.setattr(api._api_response_cache, "try_acquire", lambda k, ttl: False)

    def slow_fetch():
        time.sleep(0.4)
        return {"vms": 4242}

    results: dict[str, object] = {}

    def leader():
        results["leader"] = api._api_cache_get_with_stale("api:slowk", slow_fetch, {"vms": 0})

    def follower():
        time.sleep(0.05)  # let the leader claim the in-process slot first
        results["follower"] = api._api_cache_get_with_stale("api:slowk", slow_fetch, {"vms": 0})

    threads = [threading.Thread(target=leader), threading.Thread(target=follower)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert results["leader"] == {"vms": 4242}
    assert results["follower"] == {"vms": 4242}, (
        "follower returned the fallback while the leader had the answer"
    )


def test_equal_budgets_reproduce_the_fabricated_empty(monkeypatch):
    """The defect itself, pinned so the split is not mistaken for decoration."""
    monkeypatch.setattr(api, "_SHARED_RESULT_WAIT_SECONDS", 0.3)
    monkeypatch.setattr(api, "_INFLIGHT_WAIT_SECONDS", 0.3)  # the old shared number
    monkeypatch.setattr(api._api_response_cache, "try_acquire", lambda k, ttl: False)

    def slow_fetch():
        time.sleep(0.5)
        return {"vms": 4242}

    results: dict[str, object] = {}

    def leader():
        results["leader"] = api._api_cache_get_with_stale("api:slowk2", slow_fetch, {"vms": 0})

    def follower():
        time.sleep(0.05)
        results["follower"] = api._api_cache_get_with_stale("api:slowk2", slow_fetch, {"vms": 0})

    threads = [threading.Thread(target=leader), threading.Thread(target=follower)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert results["leader"] == {"vms": 4242}
    assert api.is_degraded(results["follower"]), (
        "this is what the old single budget produced — the fallback, then the "
        "real number one callback later. It is tagged degraded now (P0-4 part 2) "
        "so the page renders a notice instead of the zeros, but the wasted trip "
        "is the thing the split budget removes."
    )
    assert results["follower"]["vms"] == 0


def test_env_override_still_wins(monkeypatch):
    """Operators can still pin the follower budget; the derived default only
    applies when API_INFLIGHT_WAIT_SECONDS is unset or non-positive."""
    import importlib

    monkeypatch.setenv("API_INFLIGHT_WAIT_SECONDS", "90")
    reloaded = importlib.reload(api)
    try:
        assert reloaded._INFLIGHT_WAIT_SECONDS == 90.0
    finally:
        monkeypatch.delenv("API_INFLIGHT_WAIT_SECONDS", raising=False)
        importlib.reload(api)
