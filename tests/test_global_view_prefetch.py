"""Unit tests for global_view_prefetch guards and throttling logic."""
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_prefetch_state():
    """Reset all module-level mutable state between tests."""
    import src.services.global_view_prefetch as gvp
    with gvp._lock:
        gvp._in_flight.clear()
        gvp._last_warm.clear()
        gvp._warm_stats.clear()
    with gvp._prio_lock:
        gvp._prio_in_flight.clear()
    gvp._phase2_pause.clear()


# ---------------------------------------------------------------------------
# set_phase2_pause
# ---------------------------------------------------------------------------

class TestSetPhase2Pause:
    def setup_method(self):
        _reset_prefetch_state()

    def test_pause_sets_event(self):
        from src.services.global_view_prefetch import set_phase2_pause, _phase2_pause
        set_phase2_pause(True)
        assert _phase2_pause.is_set()

    def test_resume_clears_event(self):
        from src.services.global_view_prefetch import set_phase2_pause, _phase2_pause
        _phase2_pause.set()
        set_phase2_pause(False)
        assert not _phase2_pause.is_set()

    def test_idempotent_pause(self):
        from src.services.global_view_prefetch import set_phase2_pause, _phase2_pause
        set_phase2_pause(True)
        set_phase2_pause(True)
        assert _phase2_pause.is_set()


# ---------------------------------------------------------------------------
# warm_dc_priority dedup guard
# ---------------------------------------------------------------------------

class TestWarmDcPriorityDedup:
    def setup_method(self):
        _reset_prefetch_state()

    def test_second_call_for_same_dc_skipped_while_first_alive(self):
        import src.services.global_view_prefetch as gvp

        barrier = threading.Barrier(2)
        started = threading.Event()
        completed_calls = []

        def slow_warm(dc_id):
            started.set()
            barrier.wait(timeout=5)
            completed_calls.append(dc_id)

        with patch.object(gvp, "_warm_dc_devices", side_effect=slow_warm):
            # First call — spawns thread, blocks at barrier
            gvp.warm_dc_priority("DC13")
            started.wait(timeout=2)

            # Second call while first is alive — must be a no-op
            gvp.warm_dc_priority("DC13")

            with gvp._prio_lock:
                threads_count = len(gvp._prio_in_flight)
            assert threads_count == 1, "only one prio thread should be in-flight"

            # Release barrier so thread can finish
            barrier.wait(timeout=5)
            time.sleep(0.05)  # let cleanup run

    def test_second_call_after_first_done_spawns_new_thread(self):
        import src.services.global_view_prefetch as gvp
        calls = []

        def quick_warm(dc_id):
            calls.append(dc_id)

        with patch.object(gvp, "_warm_dc_devices", side_effect=quick_warm):
            gvp.warm_dc_priority("DC13")
            time.sleep(0.1)  # first thread should have finished

            gvp.warm_dc_priority("DC13")
            time.sleep(0.1)

        assert calls.count("DC13") == 2, "second call after completion should spawn a new thread"

    def test_different_dc_ids_do_not_block_each_other(self):
        import src.services.global_view_prefetch as gvp
        calls = []

        def quick_warm(dc_id):
            calls.append(dc_id)

        with patch.object(gvp, "_warm_dc_devices", side_effect=quick_warm):
            gvp.warm_dc_priority("DC11")
            gvp.warm_dc_priority("DC13")
            time.sleep(0.1)

        assert "DC11" in calls
        assert "DC13" in calls


# ---------------------------------------------------------------------------
# Phase-2 pause in _run_device_phase
# ---------------------------------------------------------------------------

class TestRunDevicePhasePause:
    def setup_method(self):
        _reset_prefetch_state()

    def test_phase2_skips_batches_when_paused(self):
        import src.services.global_view_prefetch as gvp

        fetched = []

        def fake_get_rack_devices(dc, rack):
            fetched.append((dc, rack))

        # Pause BEFORE running so all batches are skipped after the first
        gvp._phase2_pause.set()

        # 50 pairs — with BATCH=24, first batch (i=0) starts before the pause
        # check; subsequent batches see the pause. But since we set pause before
        # the loop starts, the very first iteration check should catch it.
        pairs = [("DC13", f"R{i:03d}") for i in range(50)]

        with patch("src.services.api_client.get_rack_devices", side_effect=fake_get_rack_devices):
            gvp._run_device_phase(pairs, "testkey", time.monotonic())

        # All 50 should be skipped (pause was set before any batch ran)
        assert len(fetched) == 0, f"expected 0 fetched, got {len(fetched)}"

        with gvp._lock:
            stats = gvp._warm_stats.get("testkey", {})
        assert stats.get("phase2_paused") is True
        assert stats.get("pairs_skipped") == 50

    def test_phase2_completes_when_not_paused(self):
        import src.services.global_view_prefetch as gvp

        fetched = []

        def fake_get_rack_devices(dc, rack):
            fetched.append((dc, rack))

        gvp._phase2_pause.clear()
        pairs = [("DC13", f"R{i:03d}") for i in range(10)]

        with patch("src.services.api_client.get_rack_devices", side_effect=fake_get_rack_devices):
            gvp._run_device_phase(pairs, "testkey2", time.monotonic())

        assert len(fetched) == 10

        with gvp._lock:
            stats = gvp._warm_stats.get("testkey2", {})
        assert stats.get("phase2_paused") is False
        assert stats.get("pairs_skipped") == 0
        assert stats.get("device_request_count") == 10


# ---------------------------------------------------------------------------
# is_warm TTL
# ---------------------------------------------------------------------------

class TestIsWarm:
    def setup_method(self):
        _reset_prefetch_state()

    def test_not_warm_initially(self):
        from src.services.global_view_prefetch import is_warm
        assert is_warm({"preset": "7d"}) is False

    def test_warm_after_phase1_completes(self):
        import src.services.global_view_prefetch as gvp
        import time as _t
        key = gvp._tr_key({"preset": "7d"})
        with gvp._lock:
            gvp._last_warm[key] = _t.monotonic()
        assert gvp.is_warm({"preset": "7d"}) is True

    def test_not_warm_after_ttl_expires(self):
        import src.services.global_view_prefetch as gvp
        import time as _t
        key = gvp._tr_key({"preset": "7d"})
        with gvp._lock:
            # Simulate last warm happened longer ago than TTL
            gvp._last_warm[key] = _t.monotonic() - gvp.GLOBAL_VIEW_PREFETCH_INTERVAL_SECONDS - 1
        assert gvp.is_warm({"preset": "7d"}) is False
