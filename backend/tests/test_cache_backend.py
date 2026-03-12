from datetime import datetime
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from typing import cast
from unittest.mock import MagicMock
from unittest.mock import patch

import fakeredis

from app.core import cache_backend as cb


def _fresh():
    cb._memory_cache.clear()


def test_cache_set_and_get_roundtrip_via_redis():
    fake = fakeredis.FakeRedis(decode_responses=True)
    _fresh()
    with patch("app.core.cache_backend.get_redis_client", return_value=fake):
        cb.cache_set("k1", {"a": 1})
        result = cb.cache_get("k1")
    assert result == {"a": 1}


def test_cache_get_returns_none_on_full_miss():
    fake = fakeredis.FakeRedis(decode_responses=True)
    _fresh()
    with patch("app.core.cache_backend.get_redis_client", return_value=fake):
        result = cb.cache_get("nonexistent_xyz")
    assert result is None


def test_cache_set_writes_to_memory_when_redis_unavailable():
    _fresh()
    with patch("app.core.cache_backend.get_redis_client", return_value=None):
        cb.cache_set("mem_only", {"x": 42})
    assert cb._memory_cache.get("mem_only") == {"x": 42}


def test_cache_get_falls_back_to_memory_when_redis_unavailable():
    _fresh()
    cb._memory_cache["fallback_key"] = {"y": 99}
    with patch("app.core.cache_backend.get_redis_client", return_value=None):
        result = cb.cache_get("fallback_key")
    assert result == {"y": 99}


def test_cache_delete_removes_from_both_layers():
    fake = fakeredis.FakeRedis(decode_responses=True)
    _fresh()
    with patch("app.core.cache_backend.get_redis_client", return_value=fake):
        cb.cache_set("del_key", "value")
        cb.cache_delete("del_key")
        result = cb.cache_get("del_key")
    assert result is None
    assert cb._memory_cache.get("del_key") is None


def test_cache_flush_pattern_clears_memory_and_redis():
    fake = fakeredis.FakeRedis(decode_responses=True)
    _fresh()
    with patch("app.core.cache_backend.get_redis_client", return_value=fake):
        cb.cache_set("dc:DC11:2026-01-01", "v1")
        cb.cache_set("dc:DC12:2026-01-01", "v2")
        cb.cache_flush_pattern("dc:*")
        assert cb.cache_get("dc:DC11:2026-01-01") is None
    assert len(cb._memory_cache) == 0


def test_cache_stats_returns_correct_shape_when_redis_available():
    fake = fakeredis.FakeRedis(decode_responses=True)
    _fresh()
    with patch("app.core.cache_backend.get_redis_client", return_value=fake):
        result = cb.cache_stats()
    assert result["redis_available"] is True
    assert "redis_keys" in result
    assert "memory_size" in result
    assert "memory_max" in result
    assert "ttl" in result


def test_cache_stats_redis_unavailable_flag():
    _fresh()
    with patch("app.core.cache_backend.get_redis_client", return_value=None):
        result = cb.cache_stats()
    assert result["redis_available"] is False
    assert result["redis_keys"] == 0


def test_datetime_serialization_survives_redis_roundtrip():
    fake = fakeredis.FakeRedis(decode_responses=True)
    _fresh()
    with patch("app.core.cache_backend.get_redis_client", return_value=fake):
        cb.cache_set("dt_key", {"ts": datetime(2026, 3, 1, 12, 0, 0)})
        result = cb.cache_get("dt_key")
    assert result["ts"] == "2026-03-01T12:00:00"


def test_decimal_serialization_survives_redis_roundtrip():
    fake = fakeredis.FakeRedis(decode_responses=True)
    _fresh()
    with patch("app.core.cache_backend.get_redis_client", return_value=fake):
        cb.cache_set("dec_key", {"v": Decimal("3.14")})
        result = cb.cache_get("dec_key")
    assert abs(result["v"] - 3.14) < 1e-9


def test_l2_backfill_writes_memory_hit_to_redis():
    fake = fakeredis.FakeRedis(decode_responses=True)
    _fresh()
    cb._memory_cache["backfill_key"] = {"data": "here"}
    with patch("app.core.cache_backend.get_redis_client", return_value=fake):
        result = cb.cache_get("backfill_key")
    assert result == {"data": "here"}
    assert fake.get("backfill_key") is not None


def test_redis_get_error_falls_back_to_memory():
    _fresh()
    cb._memory_cache["safe_key"] = {"z": 7}
    mock_redis = fakeredis.FakeRedis(decode_responses=True)

    with patch.object(mock_redis, "get", MagicMock(side_effect=Exception("network error"))):
        with patch("app.core.cache_backend.get_redis_client", return_value=mock_redis):
            result = cb.cache_get("safe_key")
    assert result == {"z": 7}


def test_cache_set_with_custom_ttl_is_accepted():
    fake = fakeredis.FakeRedis(decode_responses=True)
    _fresh()
    with patch("app.core.cache_backend.get_redis_client", return_value=fake):
        cb.cache_set("ttl_key", "value", ttl=300)
        result = cb.cache_get("ttl_key")
    assert result == "value"


def test_cache_delete_with_redis_unavailable_only_clears_memory():
    _fresh()
    cb._memory_cache["only_mem"] = "data"
    with patch("app.core.cache_backend.get_redis_client", return_value=None):
        cb.cache_delete("only_mem")
    assert cb._memory_cache.get("only_mem") is None


def test_cache_get_returns_none_after_ttl_expiry_in_both_layers():
    import time
    fake = fakeredis.FakeRedis(decode_responses=True)
    _fresh()
    with patch("app.core.cache_backend.get_redis_client", return_value=fake):
        cb.cache_set("exp_key", "temp_value", ttl=1)
    time.sleep(1.1)
    cb._memory_cache.pop("exp_key", None)
    with patch("app.core.cache_backend.get_redis_client", return_value=fake):
        result = cb.cache_get("exp_key")
    assert result is None


def test_cache_set_stores_key_with_ttl_on_redis():
    fake = fakeredis.FakeRedis(decode_responses=True)
    _fresh()
    with patch("app.core.cache_backend.get_redis_client", return_value=fake):
        cb.cache_set("ttl_check_key", {"v": 1}, ttl=300)
    remaining = int(cast(int, fake.ttl("ttl_check_key")))
    assert 0 < remaining <= 300


def test_cache_memory_operations_remain_stable_under_concurrent_access():
    _fresh()

    def work(i: int):
        key = f"concurrent:{i}"
        cb.cache_set(key, {"v": i})
        return cb.cache_get(key)

    with patch("app.core.cache_backend.get_redis_client", return_value=None):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(work, range(50)))

    assert results[0] == {"v": 0}
    assert results[-1] == {"v": 49}
    assert len(cb._memory_cache) == 50
