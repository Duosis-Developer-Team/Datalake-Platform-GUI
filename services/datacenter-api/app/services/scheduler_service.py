import logging
import atexit
import threading
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
    # Warm in a background thread so FastAPI lifespan can yield immediately and
    # /health answers during the ~90s cold cache warm (unblocks crm-engine
    # depends_on: service_healthy). Same pattern as customer-api.
    def _warm_cache_bg() -> None:
        logger.info("Starting initial cache warm-up (background).")
        t0 = time.perf_counter()
        try:
            db_service.warm_cache()
            logger.info(
                "Initial cache warm-up finished in %.2fs.",
                time.perf_counter() - t0,
            )
        except Exception:  # noqa: BLE001 - never abort startup
            logger.exception("Initial cache warm-up failed")

    threading.Thread(
        target=_warm_cache_bg,
        daemon=True,
        name="datacenter-initial-cache-warm",
    ).start()

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
    scheduler.add_job(
        func=db_service.refresh_network_cache,
        trigger=IntervalTrigger(minutes=S3_BACKUP_REFRESH_INTERVAL_MINUTES),
        id="network_cache_refresh",
        name="Zabbix network cache refresh",
        replace_existing=True,
        misfire_grace_time=120,
    )
    scheduler.start()
    logger.info(
        "Background scheduler started: DB/overview every %d min; S3/backup/network every %d min.",
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

    try:
        scheduler.add_job(
            func=db_service.warm_network_cache,
            trigger=DateTrigger(run_date=initial_run_time),
            id="network_initial_warm",
            name="Initial Zabbix network cache warm-up (default range)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled initial network cache warm-up for default range.")
    except Exception as exc:
        logger.warning("Failed to schedule initial network cache warm-up: %s", exc)

    atexit.register(lambda: _stop(scheduler))

    return scheduler


def _stop(scheduler: BackgroundScheduler) -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped.")
