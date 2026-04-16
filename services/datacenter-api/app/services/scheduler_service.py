import logging
import atexit
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

S3_BACKUP_REFRESH_INTERVAL_MINUTES = 30

if TYPE_CHECKING:
    from app.services.dc_service import DatabaseService

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_MINUTES = 15
INITIAL_WARM_DELAY_SECONDS = 2


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
    scheduler.add_job(
        func=db_service.refresh_s3_cache,
        trigger=IntervalTrigger(minutes=S3_BACKUP_REFRESH_INTERVAL_MINUTES),
        id="s3_cache_refresh",
        name="S3 pool/vault cache refresh",
        replace_existing=True,
        misfire_grace_time=120,
    )
    scheduler.add_job(
        func=db_service.refresh_backup_cache,
        trigger=IntervalTrigger(minutes=S3_BACKUP_REFRESH_INTERVAL_MINUTES),
        id="backup_cache_refresh",
        name="Backup (NetBackup/Zerto/Veeam) cache refresh",
        replace_existing=True,
        misfire_grace_time=120,
    )
    scheduler.start()
    logger.info(
        "Background scheduler started: DB/overview every %d min; S3/backup every %d min.",
        REFRESH_INTERVAL_MINUTES,
        S3_BACKUP_REFRESH_INTERVAL_MINUTES,
    )

    initial_run_time = datetime.now() + timedelta(seconds=INITIAL_WARM_DELAY_SECONDS)

    try:
        scheduler.add_job(
            func=db_service.warm_additional_ranges,
            trigger=DateTrigger(run_date=initial_run_time),
            id="dc_long_ranges_initial_warm",
            name="Initial DC cache warm-up (30d + previous month)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled initial DC cache warm-up for 30d and previous month.")
    except Exception as exc:
        logger.warning("Failed to schedule initial DC long-range warm-up: %s", exc)

    atexit.register(lambda: _stop(scheduler))

    return scheduler


def _stop(scheduler: BackgroundScheduler) -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped.")
