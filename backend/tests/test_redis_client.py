from unittest.mock import MagicMock, patch

import fakeredis

from app.core import redis_client as rc


def setup_function():
    rc._client = None


def test_init_redis_pool_sets_client_and_returns_it():
    fake = fakeredis.FakeRedis(decode_responses=True)
    with patch("app.core.redis_client.redis.Redis", return_value=fake):
        result = rc.init_redis_pool()
    assert result is fake
    assert rc._client is fake


def test_init_redis_pool_returns_none_when_ping_raises():
    mock = MagicMock()
    mock.ping.side_effect = Exception("connection refused")
    with patch("app.core.redis_client.redis.Redis", return_value=mock):
        result = rc.init_redis_pool()
    assert result is None
    assert rc._client is None


def test_init_redis_pool_does_not_raise_on_failure():
    with patch("app.core.redis_client.redis.Redis", side_effect=Exception("no host")):
        result = rc.init_redis_pool()
    assert result is None


def test_get_redis_client_returns_current_client():
    rc._client = "sentinel_value"
    assert rc.get_redis_client() == "sentinel_value"
    rc._client = None


def test_get_redis_client_returns_none_when_not_initialized():
    rc._client = None
    assert rc.get_redis_client() is None


def test_close_redis_pool_closes_and_clears_client():
    fake = fakeredis.FakeRedis(decode_responses=True)
    rc._client = fake
    rc.close_redis_pool()
    assert rc._client is None


def test_close_redis_pool_is_safe_when_client_already_none():
    rc._client = None
    rc.close_redis_pool()
    assert rc._client is None


def test_close_redis_pool_handles_close_exception_silently():
    mock = MagicMock()
    mock.close.side_effect = Exception("already closed")
    rc._client = mock
    rc.close_redis_pool()
    assert rc._client is None


def test_redis_is_healthy_returns_true_when_ping_succeeds():
    fake = fakeredis.FakeRedis(decode_responses=True)
    rc._client = fake
    assert rc.redis_is_healthy() is True
    rc._client = None


def test_redis_is_healthy_returns_false_when_client_is_none():
    rc._client = None
    assert rc.redis_is_healthy() is False


def test_redis_is_healthy_returns_false_when_ping_raises():
    mock = MagicMock()
    mock.ping.side_effect = Exception("broken pipe")
    rc._client = mock
    assert rc.redis_is_healthy() is False
    rc._client = None


def test_init_redis_pool_then_healthy_then_close_then_not_healthy():
    fake = fakeredis.FakeRedis(decode_responses=True)
    with patch("app.core.redis_client.redis.Redis", return_value=fake):
        rc.init_redis_pool()
    assert rc.redis_is_healthy() is True
    rc.close_redis_pool()
    assert rc.redis_is_healthy() is False
