"""Background cache refresh for customer-api (aligned with datacenter-api scheduler cadence)."""

from __future__ import annotations

import atexit
import logging
import threading
import time
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

if TYPE_CHECKING:
    from app.services.customer_service import CustomerService
    from app.services.sellable_service import SellableService

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_MINUTES = 15


def start_scheduler(
    svc: "CustomerService",
    sellable: "SellableService | None" = None,
) -> BackgroundScheduler:
    def _warm_cache_bg() -> None:
        logger.info("Customer API: initial cache warm-up started (background).")
        t0 = time.perf_counter()
        try:
            svc.warm_cache()
            logger.info(
                "Customer API: initial cache warm-up finished in %.2fs.",
                time.perf_counter() - t0,
            )
        except Exception:  # noqa: BLE001 - never abort startup
            logger.exception("Customer API: initial cache warm-up failed")

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func=svc.refresh_all_data,
        trigger=IntervalTrigger(minutes=REFRESH_INTERVAL_MINUTES),
        id="customer_cache_refresh",
        name="Customer API cache refresh",
        replace_existing=True,
        misfire_grace_time=60,
    )
    if sellable is not None:
        scheduler.add_job(
            func=sellable.snapshot_all,
            trigger=IntervalTrigger(minutes=REFRESH_INTERVAL_MINUTES),
            id="sellable_snapshot",
            name="Sellable Potential snapshot",
            replace_existing=True,
            misfire_grace_time=60,
            next_run_time=None,  # initial pass triggered explicitly below
        )
        try:
            sellable.snapshot_all()
        except Exception:  # noqa: BLE001 - never abort startup
            logger.exception("Initial sellable snapshot failed")
    scheduler.start()
    threading.Thread(
        target=_warm_cache_bg,
        daemon=True,
        name="customer-initial-warm",
    ).start()
    logger.info(
        "Customer API background scheduler started (refresh every %d minutes).",
        REFRESH_INTERVAL_MINUTES,
    )

    atexit.register(lambda: _stop(scheduler))
    return scheduler


def _stop(scheduler: BackgroundScheduler) -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Customer API background scheduler stopped.")
