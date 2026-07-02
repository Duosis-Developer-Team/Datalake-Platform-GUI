"""GAP1.1: atomic cross-pod lock primitive on the cache backend (Redis SET NX EX;
in-process expiry dict) — the building block for shared single-flight so N pods
don't all fire the same slow cold query at once.
"""
import time

import pytest

from src.services import cache_service


def test_inprocess_try_acquire_and_release():
    b = cache_service.InProcessBackend()
    assert b.try_acquire("lk", ttl=30) is True
    assert b.try_acquire("lk", ttl=30) is False  # held
    b.release("lk")
    assert b.try_acquire("lk", ttl=30) is True  # released -> re-acquirable


def test_inprocess_lock_expires():
    b = cache_service.InProcessBackend()
    assert b.try_acquire("lk", ttl=0.05) is True
    time.sleep(0.08)
    assert b.try_acquire("lk", ttl=30) is True  # expired -> re-acquirable


def test_redis_try_acquire_and_release():
    fakeredis = pytest.importorskip("fakeredis")
    b = cache_service.RedisBackend(fakeredis.FakeStrictRedis())
    assert b.try_acquire("lk", ttl=30) is True
    assert b.try_acquire("lk", ttl=30) is False
    b.release("lk")
    assert b.try_acquire("lk", ttl=30) is True


def test_redis_try_acquire_degrades_to_leader_on_error():
    class Broken:
        def set(self, *a, **k):
            raise ConnectionError("down")

    b = cache_service.RedisBackend(Broken())
    # On Redis error, act as leader (fetch) rather than block forever.
    assert b.try_acquire("lk", ttl=30) is True


def test_module_try_acquire_release_delegate():
    cache_service.set_backend(cache_service.InProcessBackend())
    assert cache_service.try_acquire("lk", ttl=30) is True
    assert cache_service.try_acquire("lk", ttl=30) is False
    cache_service.release("lk")
    assert cache_service.try_acquire("lk", ttl=30) is True
