"""The periodic warm loop must not have every worker warm at the same instant.

With more than one gunicorn worker, each process runs its own
_periodic_common_warm thread. They all start when the container boots, so
without a stagger they call warm_common() simultaneously on a cold cache.

The fetch layer already single-flights across processes (api_client takes a
Redis SET NX EX lock per cache key), so the duplicate work is bounded — but the
losers of that race then block up to _INFLIGHT_WAIT_SECONDS waiting for the
leader, which is exactly the stall this branch is trying to remove. A small
random delay ahead of the first warm keeps them out of each other's way.

Tests the delay function, not the thread: sleeping for real in a unit test buys
nothing.
"""

import app


def test_initial_warm_delay_is_within_the_declared_window():
    low, high = app._INITIAL_WARM_JITTER_SECONDS

    for _ in range(50):
        assert low <= app._initial_warm_delay_seconds() <= high


def test_initial_warm_delay_actually_varies():
    """A constant delay would stagger nothing — every worker would still align."""
    values = {app._initial_warm_delay_seconds() for _ in range(50)}

    assert len(values) > 1


def test_initial_warm_delay_can_be_disabled(monkeypatch):
    """A single-worker deployment wants its cache warm as early as possible."""
    monkeypatch.setenv("APP_WARM_JITTER_SECONDS", "0")

    assert app._initial_warm_delay_seconds() == 0.0


def test_initial_warm_delay_ignores_a_malformed_override(monkeypatch):
    monkeypatch.setenv("APP_WARM_JITTER_SECONDS", "soon")

    low, high = app._INITIAL_WARM_JITTER_SECONDS
    assert low <= app._initial_warm_delay_seconds() <= high


def test_initial_warm_delay_never_exceeds_the_warm_interval(monkeypatch):
    """A jitter longer than the loop interval would just skip warms."""
    monkeypatch.setenv("APP_WARM_JITTER_SECONDS", "9999")

    interval = float(app._common_warm_interval_seconds())
    assert app._initial_warm_delay_seconds() <= interval
