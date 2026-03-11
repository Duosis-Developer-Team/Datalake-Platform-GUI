# Background scheduler service.
# Keeps the cache warm by calling DatabaseService.refresh_all_data() every 15 minutes.
# Uses APScheduler's BackgroundScheduler so the job runs in a daemon thread without
# blocking the Dash/Flask request loop.

import logging
import atexit
import time
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
    t0 = time.perf_counter()
    db_service.warm_cache()
    logger.info(
        "Initial cache warm-up finished in %.2fs.",
        time.perf_counter() - t0,
    )

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

    # Step 2a: schedule background warm-up for longer DC ranges
    # (last 30 days and previous calendar month) so they do not delay startup.
    try:
        scheduler.add_job(
            func=db_service.warm_additional_ranges,
            trigger=DateTrigger(run_date=datetime.now()),
            id="dc_long_ranges_initial_warm",
            name="Initial DC cache warm-up (30d + previous month)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled initial DC cache warm-up for 30d and previous month.")
    except Exception as exc:
        logger.warning("Failed to schedule initial DC long-range warm-up: %s", exc)

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

    # Step 4: schedule periodic Boyner customer cache refresh without clearing existing data first.
    # This keeps the Customer View cache warm in the background and replaces entries in place.
    try:
        def _refresh_boyner_customer_cache():
            # Always use a fresh 30-day range so the cache represents the latest period.
            current_range = preset_to_range(PRESET_30_DAYS)
            from src.services import cache_service as cache

            cache_key = f"customer_assets:Boyner:{current_range.get('start','')}:{current_range.get('end','')}"
            cache.delete(cache_key)
            db_service.get_customer_resources("Boyner", current_range)

        scheduler.add_job(
            func=_refresh_boyner_customer_cache,
            trigger=IntervalTrigger(minutes=REFRESH_INTERVAL_MINUTES),
            id="customer_boyner_refresh",
            name="Boyner customer cache refresh (30d)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info(
            "Scheduled Boyner customer cache refresh every %d minutes (30-day range).",
            REFRESH_INTERVAL_MINUTES,
        )
    except Exception as exc:
        logger.warning("Failed to schedule Boyner customer cache refresh: %s", exc)

    # Step 5: clean shutdown on process exit
    atexit.register(lambda: _stop(scheduler))

    return scheduler


def _stop(scheduler: BackgroundScheduler) -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped.")
