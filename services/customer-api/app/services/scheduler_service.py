"""Background cache refresh for customer-api (aligned with datacenter-api scheduler cadence)."""

from __future__ import annotations

import atexit
import logging
import time
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

if TYPE_CHECKING:
    from app.services.customer_service import CustomerService

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_MINUTES = 15


def start_scheduler(svc: "CustomerService") -> BackgroundScheduler:
    logger.info("Customer API: initial cache warm-up before scheduler launch.")
    t0 = time.perf_counter()
    svc.warm_cache()
    logger.info(
        "Customer API: initial cache warm-up finished in %.2fs.",
        time.perf_counter() - t0,
    )

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func=svc.refresh_all_data,
        trigger=IntervalTrigger(minutes=REFRESH_INTERVAL_MINUTES),
        id="customer_cache_refresh",
        name="Customer API cache refresh",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.start()
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
