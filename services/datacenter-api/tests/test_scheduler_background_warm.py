"""Initial cache warm must not block start_scheduler (lifespan /health)."""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

from app.services.scheduler_service import start_scheduler


def test_start_scheduler_warms_in_background_thread():
    """warm_cache runs on a daemon thread; start_scheduler returns quickly."""
    entered = threading.Event()
    release = threading.Event()

    def blocking_warm():
        entered.set()
        release.wait(timeout=5)

    db = MagicMock()
    db.warm_cache.side_effect = blocking_warm
    db.refresh_all_data = MagicMock()
    db.refresh_s3_cache = MagicMock()
    db.refresh_backup_cache = MagicMock()
    db.refresh_network_cache = MagicMock()
    db.warm_additional_ranges = MagicMock()
    db.warm_network_cache = MagicMock()

    with patch("app.services.scheduler_service.BackgroundScheduler") as SchedCls:
        sched = MagicMock()
        SchedCls.return_value = sched
        t0 = time.perf_counter()
        result = start_scheduler(db)
        elapsed = time.perf_counter() - t0

    assert result is sched
    assert elapsed < 1.0, f"start_scheduler blocked for {elapsed:.2f}s (expected background warm)"
    assert entered.wait(timeout=2.0), "warm_cache was never started in background"
    release.set()
    # Give the thread a moment to finish after release
    time.sleep(0.05)
    db.warm_cache.assert_called_once()
    sched.start.assert_called_once()


def test_start_scheduler_warm_failure_does_not_raise():
    db = MagicMock()
    db.warm_cache.side_effect = RuntimeError("db down")
    db.refresh_all_data = MagicMock()
    db.refresh_s3_cache = MagicMock()
    db.refresh_backup_cache = MagicMock()
    db.refresh_network_cache = MagicMock()
    db.warm_additional_ranges = MagicMock()
    db.warm_network_cache = MagicMock()

    with patch("app.services.scheduler_service.BackgroundScheduler") as SchedCls:
        sched = MagicMock()
        SchedCls.return_value = sched
        start_scheduler(db)

    # Wait briefly for the background thread to hit the exception path
    time.sleep(0.2)
    db.warm_cache.assert_called_once()
    sched.start.assert_called_once()
