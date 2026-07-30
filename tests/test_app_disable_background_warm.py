"""Pins app._background_warm_enabled(): the predicate that gates the startup
thread which calls warm_common() immediately on import (see app.py, near the
_periodic_common_warm thread start). Testing the predicate directly — instead
of reimporting app.py or asserting on the real thread — avoids starting a
background thread (and its real, unmocked warm_common() call) in the suite.
"""
import app


def test_background_warm_enabled_when_unset(monkeypatch):
    monkeypatch.delenv("APP_DISABLE_BACKGROUND_WARM", raising=False)
    assert app._background_warm_enabled() is True


def test_background_warm_enabled_for_falsy_values(monkeypatch):
    for value in ("0", "false", "False", "FALSE", ""):
        monkeypatch.setenv("APP_DISABLE_BACKGROUND_WARM", value)
        assert app._background_warm_enabled() is True, f"expected enabled for {value!r}"


def test_background_warm_disabled_for_truthy_values(monkeypatch):
    for value in ("1", "true", "yes", "anything"):
        monkeypatch.setenv("APP_DISABLE_BACKGROUND_WARM", value)
        assert app._background_warm_enabled() is False, f"expected disabled for {value!r}"
