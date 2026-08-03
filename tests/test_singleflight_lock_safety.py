"""P2-6: the cross-pod single-flight lock, now that there is more than one worker.

The audit filed this as P2 with a note attached: "Tek-worker'da erişilemez,
multi-pod'da gerçek. P0-7 ile 2 worker'a çıkınca **aktif hâle gelir** — birlikte
düzeltin." P0-7 raised gunicorn from one worker to two, so these paths went from
unreachable to routine in the same change set. This closes them.

Three defects, one lock:

1. `_wait_for_shared_result` returned as soon as *any* entry existed under the
   key. A lock loser only reaches it because the fast path already rejected the
   entry as stale — so the poll succeeded on its first iteration, on that same
   stale entry, and the loser returned the payload its own freshness check had
   thrown out five lines earlier. With two workers behind one Redis this is
   directly the reported symptom: worker A fetches and answers 16.903, worker B
   loses the lock and answers the old 16.892, and the page changes value
   depending on which worker the round-robin lands on.

2. `release()` deleted the lock key unconditionally. If the lease expired while
   its holder was still fetching, the holder's release deleted the *next*
   holder's lock, which lets a third fetcher in — the stampede the lock exists
   to prevent, now with no lock at all. Releasing must prove ownership.

3. The lease was the same number as the waiter's budget, so it could expire at
   the moment the fetch it protects finishes.

And one the fix for (1) created: once the wait insists on a *fresh* entry, a
holder whose fetch fails publishes nothing, and the waiter sits out its whole
budget before falling through — 25 s added to every request during a backend
outage. So the waiter also watches the lock, and stops the moment nobody holds
it. Fixing a wrong-value bug by adding a hang would not be a fix.
"""
from __future__ import annotations

import time

import pytest

from src.services import api_client as api
from src.services import cache_service


@pytest.fixture(autouse=True)
def _isolated_backend():
    """Fresh backend per test so a held lock never leaks into the next one."""
    orig = cache_service.get_backend()
    cache_service.set_backend(cache_service.InProcessBackend())
    yield
    cache_service.set_backend(orig)


def _seed(key, value, age_seconds):
    """Write `value` as if it had been fetched `age_seconds` ago."""
    cache_service.set(key, {api._SWR_STAMP: time.time() - age_seconds, "value": value})


def _lock_is_held_by_someone_else(monkeypatch, key):
    """Put the key's lock in someone else's hands, for real.

    Taking the lock on the backend rather than only stubbing try_acquire matters:
    the waiter now also probes whether the lock is still held, so a stub alone
    would describe a worker that holds nothing — and the waiter would rightly
    refuse to wait for it.
    """
    cache_service.get_backend().try_acquire(key, 300)
    monkeypatch.setattr(api._api_response_cache, "try_acquire", lambda k, ttl: None)


# --- 1. a lock loser must not replay the entry the fast path rejected --------


def test_a_lock_loser_does_not_serve_the_stale_entry_the_fast_path_just_rejected(monkeypatch):
    """The defect, at its smallest: stale entry present, lock held elsewhere.

    Before this, `_wait_for_shared_result` saw the stale entry, called it a
    result, and returned it — instantly, without waiting for the pod that was
    actually fetching.
    """
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    monkeypatch.setattr(api, "_SHARED_RESULT_WAIT_SECONDS", 0.3)
    _lock_is_held_by_someone_else(monkeypatch, "lk1")
    _seed("lk1", {"vms": 16_892}, age_seconds=9_999)

    fetched = []
    out = api._api_cache_get_with_stale(
        "lk1", lambda: fetched.append(1) or {"vms": 16_903}, {}
    )

    assert out == {"vms": 16_903}, "the stale copy must not be presented as the answer"
    assert fetched == [1], "nothing fresh arrived, so this worker fetches for itself"


def test_a_lock_loser_waits_the_full_budget_before_giving_up_on_the_other_worker(monkeypatch):
    """The wait is the point of the lock. Returning early on a stale entry did
    not just serve the wrong value — it also skipped the coalescing."""
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    monkeypatch.setattr(api, "_SHARED_RESULT_WAIT_SECONDS", 0.4)
    _lock_is_held_by_someone_else(monkeypatch, "lk2")
    _seed("lk2", {"vms": 1}, age_seconds=9_999)

    t0 = time.time()
    api._api_cache_get_with_stale("lk2", lambda: {"vms": 2}, {})
    waited = time.time() - t0

    assert waited >= 0.3, f"gave up after {waited:.2f}s instead of waiting for the other worker"


def test_a_lock_loser_returns_the_other_workers_result_as_soon_as_it_lands(monkeypatch):
    """The path that was always meant to happen: the winner publishes, the loser
    picks it up and never fetches."""
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    monkeypatch.setattr(api, "_SHARED_RESULT_WAIT_SECONDS", 2.0)
    _lock_is_held_by_someone_else(monkeypatch, "lk3")
    _seed("lk3", {"vms": 16_892}, age_seconds=9_999)

    calls = {"n": 0}
    real_get = api._api_response_cache.get

    def _get(k):
        if k == "lk3":
            calls["n"] += 1
            if calls["n"] > 2:  # the other worker finishes mid-poll
                _seed("lk3", {"vms": 16_903}, age_seconds=0)
        return real_get(k)

    monkeypatch.setattr(api._api_response_cache, "get", _get)

    fetched = []
    out = api._api_cache_get_with_stale(
        "lk3", lambda: fetched.append(1) or {"vms": -1}, {}
    )

    assert out == {"vms": 16_903}
    assert fetched == [], "must not fetch when another worker already answered"


def test_an_entry_with_no_recorded_fetch_time_does_not_end_the_wait(monkeypatch):
    """Unstamped entries are pre-upgrade leftovers and count as stale everywhere
    else (see _age_is_fresh). The waiter must not be the one place they pass."""
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    monkeypatch.setattr(api, "_SHARED_RESULT_WAIT_SECONDS", 0.3)
    _lock_is_held_by_someone_else(monkeypatch, "lk4")
    cache_service.set("lk4", {"vms": 5})  # bare value, no _SWR_STAMP

    fetched = []
    api._api_cache_get_with_stale("lk4", lambda: fetched.append(1) or {"vms": 6}, {})

    assert fetched == [1]


# --- 1b. ...but waiting for a worker that already gave up is its own bug -----


def test_the_waiter_stops_as_soon_as_the_holder_gives_up(monkeypatch):
    """Making the wait honest about freshness introduced a cost that has to be
    paid back here.

    When the fetch the other worker is running *fails* — the backend is down,
    which is exactly when this matters — nothing fresh is ever published, so a
    waiter that only watches the cache burns its entire budget before falling
    through to its own fetch. That is 25 seconds of a blank page added to every
    request during an outage, in exchange for fixing a wrong-value bug. Not a
    trade worth making.

    The lock itself is the signal: it is released (or its lease lapses) when the
    holder is done, one way or the other. Gone with nothing published means the
    fetch failed, and there is no longer anything to wait for.
    """
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    monkeypatch.setattr(api, "_SHARED_RESULT_WAIT_SECONDS", 10.0)
    _lock_is_held_by_someone_else(monkeypatch, "lk5")
    _seed("lk5", {"vms": 1}, age_seconds=9_999)

    polls = {"n": 0}

    def _is_locked(_key):
        polls["n"] += 1
        return polls["n"] <= 2  # the other worker fails and releases

    monkeypatch.setattr(api._api_response_cache, "is_locked", _is_locked)

    t0 = time.time()
    fetched = []
    api._api_cache_get_with_stale("lk5", lambda: fetched.append(1) or {"vms": 2}, {})
    waited = time.time() - t0

    assert fetched == [1], "nothing was published, so this worker has to fetch"
    assert waited < 2.0, f"waited {waited:.1f}s for a worker that had already given up"


def test_a_lock_that_cannot_be_checked_is_assumed_held(monkeypatch):
    """`is_locked` guards a wait, so an unknown answer must not shorten it —
    a Redis that cannot answer would otherwise turn every waiter loose at once,
    which is the stampede the lock exists to prevent."""

    class Broken:
        def exists(self, *a):
            raise ConnectionError("down")

    assert cache_service.RedisBackend(Broken()).is_locked("lk") is True


def test_is_locked_tracks_acquire_release_and_expiry():
    b = cache_service.InProcessBackend()
    assert b.is_locked("lk") is False

    token = b.try_acquire("lk", ttl=30)
    assert b.is_locked("lk") is True
    b.release("lk", token)
    assert b.is_locked("lk") is False

    b.try_acquire("lk", ttl=0.05)
    time.sleep(0.08)
    assert b.is_locked("lk") is False, "an expired lease is not held"


def test_redis_is_locked_tracks_acquire_and_release():
    fakeredis = pytest.importorskip("fakeredis")
    b = cache_service.RedisBackend(fakeredis.FakeStrictRedis())

    assert b.is_locked("lk") is False
    token = b.try_acquire("lk", ttl=30)
    assert b.is_locked("lk") is True
    b.release("lk", token)
    assert b.is_locked("lk") is False


# --- 2. releasing a lock you no longer hold ---------------------------------


def test_inprocess_release_after_the_lease_expired_leaves_the_new_holder_alone():
    """A holds the lock, its lease expires, B acquires, then A finishes and
    releases. A must not free B's lock."""
    b = cache_service.InProcessBackend()

    token_a = b.try_acquire("lk", ttl=0.05)
    assert token_a
    time.sleep(0.08)  # A's lease expires while A is still fetching
    token_b = b.try_acquire("lk", ttl=30)
    assert token_b, "the expired lease must be re-acquirable"

    b.release("lk", token_a)  # A returns and cleans up after itself

    assert not b.try_acquire("lk", ttl=30), "B still holds the lock"
    b.release("lk", token_b)
    assert b.try_acquire("lk", ttl=30), "B's own release still works"


def test_redis_release_after_the_lease_expired_leaves_the_new_holder_alone():
    """The one that matters: in-process locks are per-worker, so cross-worker
    stampedes are held off by the Redis one alone."""
    fakeredis = pytest.importorskip("fakeredis")
    b = cache_service.RedisBackend(fakeredis.FakeStrictRedis())

    token_a = b.try_acquire("lk", ttl=1)
    assert token_a
    b.release("lk", "some-other-workers-token")
    assert not b.try_acquire("lk", ttl=30), "a foreign token must not free the lock"

    b.release("lk", token_a)
    assert b.try_acquire("lk", ttl=30)


def test_two_holders_never_get_the_same_token():
    b = cache_service.InProcessBackend()
    first = b.try_acquire("lk", ttl=30)
    b.release("lk", first)
    second = b.try_acquire("lk", ttl=30)

    assert first != second, "tokens identify a holder; reusing one defeats the check"


def test_a_redis_error_still_makes_the_caller_the_leader():
    """Unchanged behaviour, restated against the new return type: if Redis
    cannot answer, fetch rather than block forever."""

    class Broken:
        def set(self, *a, **k):
            raise ConnectionError("down")

    token = cache_service.RedisBackend(Broken()).try_acquire("lk", ttl=30)
    assert token, "must read as acquired"


# --- 3. the lease has to outlast the fetch it protects ----------------------


def test_the_lease_outlasts_the_slowest_fetch_it_protects():
    """The lease and the waiter's budget were one constant. A lease that expires
    while its holder is still fetching lets a second worker start the same query,
    which is the stampede this lock exists to prevent."""
    worst_case_fetch = api._INTERACTIVE_READ_TIMEOUT + 5.0  # read + connect

    assert api._SHARED_LOCK_TTL_SECONDS > worst_case_fetch, (
        f"lease {api._SHARED_LOCK_TTL_SECONDS}s does not cover a "
        f"{worst_case_fetch}s fetch"
    )
    assert api._SHARED_LOCK_TTL_SECONDS >= api._SHARED_RESULT_WAIT_SECONDS, (
        "a waiter must not outlive the lock it is waiting on"
    )
