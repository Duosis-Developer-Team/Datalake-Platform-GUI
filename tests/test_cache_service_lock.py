"""GAP1.1: atomic cross-pod lock primitive on the cache backend (Redis SET NX EX;
in-process expiry dict) — the building block for shared single-flight so N pods
don't all fire the same slow cold query at once.

P2-6 changed the return type: try_acquire hands back the holder's token instead
of True, and release() takes that token and only deletes a lock the token still
owns. The assertions here follow suit (truthy/None rather than True/False); what
the token is *for* is pinned in test_singleflight_lock_safety.py.
"""
import time

import pytest

from src.services import cache_service


def test_inprocess_try_acquire_and_release():
    b = cache_service.InProcessBackend()
    token = b.try_acquire("lk", ttl=30)
    assert token
    assert b.try_acquire("lk", ttl=30) is None  # held
    b.release("lk", token)
    assert b.try_acquire("lk", ttl=30)  # released -> re-acquirable


def test_inprocess_lock_expires():
    b = cache_service.InProcessBackend()
    assert b.try_acquire("lk", ttl=0.05)
    time.sleep(0.08)
    assert b.try_acquire("lk", ttl=30)  # expired -> re-acquirable


def test_redis_try_acquire_and_release():
    fakeredis = pytest.importorskip("fakeredis")
    b = cache_service.RedisBackend(fakeredis.FakeStrictRedis())
    token = b.try_acquire("lk", ttl=30)
    assert token
    assert b.try_acquire("lk", ttl=30) is None
    b.release("lk", token)
    assert b.try_acquire("lk", ttl=30)


def test_redis_try_acquire_degrades_to_leader_on_error():
    class Broken:
        def set(self, *a, **k):
            raise ConnectionError("down")

    b = cache_service.RedisBackend(Broken())
    # On Redis error, act as leader (fetch) rather than block forever.
    assert b.try_acquire("lk", ttl=30)


def test_module_try_acquire_release_delegate():
    cache_service.set_backend(cache_service.InProcessBackend())
    token = cache_service.try_acquire("lk", ttl=30)
    assert token
    assert cache_service.try_acquire("lk", ttl=30) is None
    cache_service.release("lk", token)
    assert cache_service.try_acquire("lk", ttl=30)
