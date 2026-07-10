"""R7: a frontend pod that boots before Redis is reachable used to latch onto the
per-pod InProcessBackend for its whole life (import-time ping, no retry). Now, when
REDIS_URL is set but the active backend is in-process, cache ops retry the connection
(throttled) and upgrade to the shared RedisBackend once Redis is reachable.
"""
from unittest.mock import patch

import pytest

from src.services import cache_service as cs


@pytest.fixture(autouse=True)
def _restore_backend():
    """These tests mutate the module-global backend + retry clock; restore them so
    state never leaks into other tests (e.g. test_default_backend_is_inprocess)."""
    saved_backend = cs.get_backend()
    saved_attempt = cs._last_backend_attempt
    try:
        yield
    finally:
        cs.set_backend(saved_backend)
        cs._last_backend_attempt = saved_attempt


def _install_inprocess():
    cs.set_backend(cs.InProcessBackend(8))
    cs._last_backend_attempt = 0.0  # force the retry time-gate open


def test_inprocess_upgrades_to_redis_when_redis_becomes_reachable():
    _install_inprocess()
    fake = cs.RedisBackend(client=_FakeClient())
    with patch.dict("os.environ", {"REDIS_URL": "redis://x:6379/0"}), \
         patch.object(cs, "make_backend_from_env", return_value=fake):
        cs.get("some-key")  # any cache op triggers the throttled re-check
    assert isinstance(cs.get_backend(), cs.RedisBackend), "should upgrade to shared Redis on retry"


def test_no_upgrade_when_redis_url_unset():
    _install_inprocess()
    with patch.dict("os.environ", {}, clear=True), \
         patch.object(cs, "make_backend_from_env") as m:
        cs.get("k")
    m.assert_not_called()
    assert isinstance(cs.get_backend(), cs.InProcessBackend)


def test_no_reattempt_when_already_redis():
    cs.set_backend(cs.RedisBackend(client=_FakeClient()))
    cs._last_backend_attempt = 0.0
    with patch.dict("os.environ", {"REDIS_URL": "redis://x:6379/0"}), \
         patch.object(cs, "make_backend_from_env") as m:
        cs.get("k")
    m.assert_not_called()


class _FakeClient:
    def get(self, *a, **k):
        return None

    def set(self, *a, **k):
        return True
