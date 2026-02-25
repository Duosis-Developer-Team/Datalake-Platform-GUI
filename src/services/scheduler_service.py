# Background scheduler service.
# Keeps the cache warm by calling DatabaseService.refresh_all_data() every 15 minutes.
# Uses APScheduler's BackgroundScheduler so the job runs in a daemon thread without
# blocking the Dash/Flask request loop.

import logging
import atexit
from datetime import datetime
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

from src.utils.time_range import preset_to_range, PRESET_30_DAYS

if TYPE_CHECKING:
    from src.services.db_service import DatabaseService

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_MINUTES = 15


def start_scheduler(db_service: "DatabaseService") -> BackgroundScheduler:
    """
    1. Warm the cache immediately (blocking, runs in the calling thread).
    2. Start a background scheduler that refreshes every 15 minutes.
    3. Register atexit hook to stop the scheduler on app shutdown.

    Returns the running BackgroundScheduler instance.
    """
    # Step 1: warm cache synchronously so the first page load is instant
    logger.info("Starting initial cache warm-up before scheduler launch.")
    db_service.warm_cache()

    # Step 2: launch background scheduler
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func=db_service.refresh_all_data,
        trigger=IntervalTrigger(minutes=REFRESH_INTERVAL_MINUTES),
        id="cache_refresh",
        name="DB cache refresh",
        replace_existing=True,
        misfire_grace_time=60,   # allow 60 s late start before skipping
    )
    scheduler.start()
    logger.info(
        "Background scheduler started. Cache refresh every %d minutes.",
        REFRESH_INTERVAL_MINUTES,
    )

    # Step 3: immediately warm customer cache for Boyner (last 30 days) in background
    try:
        customer_range = preset_to_range(PRESET_30_DAYS)
        scheduler.add_job(
            func=lambda: db_service.get_customer_resources("Boyner", customer_range),
            trigger=DateTrigger(run_date=datetime.now()),
            id="customer_boyner_initial_warm",
            name="Initial Boyner customer cache warm-up (30d)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled initial Boyner customer cache warm-up (last 30 days).")
    except Exception as exc:
        logger.warning("Failed to schedule initial Boyner customer cache warm-up: %s", exc)

    # Step 4: clean shutdown on process exit
    atexit.register(lambda: _stop(scheduler))

    return scheduler


def _stop(scheduler: BackgroundScheduler) -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped.")
