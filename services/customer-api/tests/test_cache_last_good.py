"""Tests for customer-api cache last_good shadow keys."""
from __future__ import annotations

from app.core import cache_backend as cb


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value

    def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)


def test_cache_set_writes_last_good(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(cb, "get_redis_client", lambda: fake)
    cb.cache_set("customer_assets:test", {"totals": {"vm_count": 1}})
    assert "customer_assets:test" in fake.store
    assert "customer_assets:test:last_good" in fake.store


def test_cache_get_last_good_reads_shadow_key(monkeypatch):
    fake = _FakeRedis()
    fake.store["customer_assets:test:last_good"] = '{"totals": {"vm_count": 5}}'
    monkeypatch.setattr(cb, "get_redis_client", lambda: fake)
    hit = cb.cache_get_last_good("customer_assets:test")
    assert hit == {"totals": {"vm_count": 5}}


def test_cache_get_falls_back_to_last_good(monkeypatch):
    fake = _FakeRedis()
    fake.store["customer_assets:test:last_good"] = '{"totals": {"vm_count": 2}}'
    monkeypatch.setattr(cb, "get_redis_client", lambda: fake)
    with cb._memory_lock:
        cb._memory_cache.clear()
    hit = cb.cache_get("customer_assets:test")
    assert hit == {"totals": {"vm_count": 2}}
