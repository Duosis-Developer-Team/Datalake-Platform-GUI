import logging
import atexit
import time
from datetime import datetime
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

from app.utils.time_range import preset_to_range, PRESET_30_DAYS

if TYPE_CHECKING:
    from app.services.db_service import DatabaseService

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_MINUTES = 15


def start_scheduler(db_service: "DatabaseService") -> BackgroundScheduler:
    logger.info("Starting initial cache warm-up before scheduler launch.")
    t0 = time.perf_counter()
    db_service.warm_cache()
    logger.info(
        "Initial cache warm-up finished in %.2fs.",
        time.perf_counter() - t0,
    )

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func=db_service.refresh_all_data,
        trigger=IntervalTrigger(minutes=REFRESH_INTERVAL_MINUTES),
        id="cache_refresh",
        name="DB cache refresh",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.start()
    logger.info(
        "Background scheduler started. Cache refresh every %d minutes.",
        REFRESH_INTERVAL_MINUTES,
    )

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

    try:
        def _refresh_boyner_customer_cache():
            current_range = preset_to_range(PRESET_30_DAYS)
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

    atexit.register(lambda: _stop(scheduler))

    return scheduler


def _stop(scheduler: BackgroundScheduler) -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped.")
