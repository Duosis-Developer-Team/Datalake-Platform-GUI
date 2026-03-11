import pytest

from app.services import cache_service as cache


def test_cache_set_and_get_returns_same_value():
    cache.set("test_key_1", {"data": 42})
    result = cache.get("test_key_1")
    assert result == {"data": 42}


def test_cache_get_returns_none_for_missing_key():
    assert cache.get("nonexistent_key_xyz") is None


def test_cache_delete_removes_key():
    cache.set("test_del_key", "value")
    cache.delete("test_del_key")
    assert cache.get("test_del_key") is None


def test_cache_delete_nonexistent_key_does_not_raise():
    cache.delete("never_set_key_abc")


def test_cache_clear_removes_all_keys():
    cache.set("clear_test_a", 1)
    cache.set("clear_test_b", 2)
    cache.clear()
    assert cache.get("clear_test_a") is None
    assert cache.get("clear_test_b") is None


def test_cache_set_overwrites_existing_value():
    cache.set("overwrite_key", "old_value")
    cache.set("overwrite_key", "new_value")
    assert cache.get("overwrite_key") == "new_value"


def test_cache_stats_returns_dict_with_required_fields():
    stats = cache.stats()
    assert "current_size" in stats
    assert "max_size" in stats
    assert "ttl_seconds" in stats
    assert "keys" in stats


def test_cache_stats_max_size_is_100():
    stats = cache.stats()
    assert stats["max_size"] == 100


def test_cache_stats_ttl_is_1200():
    stats = cache.stats()
    assert stats["ttl_seconds"] == 1200


def test_dc_details_cache_key_format_is_consistent():
    dc = "DC11"
    start = "2026-03-01"
    end = "2026-03-07"
    key = f"dc_details:{dc}:{start}:{end}"
    cache.set(key, {"test": True})
    assert cache.get(key) == {"test": True}


def test_global_dashboard_cache_key_format_is_consistent():
    range_suffix = "2026-03-01:2026-03-07"
    key = f"global_dashboard:{range_suffix}"
    cache.set(key, {"overview": {}})
    assert cache.get(key) == {"overview": {}}


def test_all_dc_summary_cache_key_format_is_consistent():
    range_suffix = "2026-03-01:2026-03-07"
    key = f"all_dc_summary:{range_suffix}"
    cache.set(key, [{"id": "DC11"}])
    assert cache.get(key) == [{"id": "DC11"}]


def test_cached_decorator_returns_cached_value_on_second_call():
    call_count = {"n": 0}

    @cache.cached(lambda x: f"decorated_test_{x}")
    def expensive(x):
        call_count["n"] += 1
        return x * 2

    cache.delete("decorated_test_5")
    result1 = expensive(5)
    result2 = expensive(5)
    assert result1 == 10
    assert result2 == 10
    assert call_count["n"] == 1
