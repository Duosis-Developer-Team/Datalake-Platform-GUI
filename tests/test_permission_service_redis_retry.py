"""R7 (adjacent): the permission-map Redis client used to latch permanently to
None on the first failure (import/boot race). Now, when REDIS_URL is set but Redis
was unreachable, it retries (throttled) instead of staying off for the process life.
"""
from unittest.mock import MagicMock, patch

import pytest

from src.auth import permission_service as ps


@pytest.fixture(autouse=True)
def _reset_redis_state():
    ps._REDIS = None
    ps._REDIS_LAST_ATTEMPT = 0.0
    try:
        yield
    finally:
        ps._REDIS = None
        ps._REDIS_LAST_ATTEMPT = 0.0


def test_retries_and_connects_when_redis_becomes_reachable():
    ok_client = MagicMock()
    ok_client.ping.return_value = True
    with patch.dict("os.environ", {"REDIS_URL": "redis://x:6379/0"}):
        # 1st attempt: Redis unreachable -> None, but NOT latched off forever.
        with patch("redis.Redis.from_url", side_effect=OSError("down")):
            assert ps._redis_client() is None
        assert ps._REDIS is not False  # not permanently latched

        # 2nd attempt (time-gate reset): Redis now reachable -> returns the client.
        ps._REDIS_LAST_ATTEMPT = 0.0
        with patch("redis.Redis.from_url", return_value=ok_client):
            assert ps._redis_client() is ok_client


def test_no_attempt_when_redis_url_unset():
    with patch.dict("os.environ", {}, clear=True):
        with patch("redis.Redis.from_url") as m:
            assert ps._redis_client() is None
        m.assert_not_called()
