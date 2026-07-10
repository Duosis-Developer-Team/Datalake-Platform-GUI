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

from src.utils.time_range import cache_time_ranges, default_time_range
from src.services import sla_service
from src.services import api_client as api
from src.services.db_service import WARMED_CUSTOMERS

if TYPE_CHECKING:
    from src.services.db_service import DatabaseService

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_MINUTES = 15
SLA_REFRESH_INTERVAL_MINUTES = 60


def refresh_warmed_customer_availability_bundles() -> None:
    """
    Force-refresh AuraNotify customer availability cache for WARMED_CUSTOMERS × cache_time_ranges.
    Used by scheduler so page loads hit TTL cache instead of live HTTP every time.
    """
    for tr in cache_time_ranges():
        for name in WARMED_CUSTOMERS:
            api.get_customer_availability_bundle(name, tr, force_refresh=True)


def _warm_dc_network_for_range(tr: dict) -> None:
    """Prime GUI in-process api:* cache for Zabbix network endpoints (unfiltered default view)."""
    try:
        summaries = api.get_all_datacenters_summary(tr)
    except Exception as exc:
        logger.warning("GUI network warm: datacenter summary failed: %s", exc)
        return

    dc_ids = [dc.get("id") for dc in (summaries or []) if dc.get("id")]
    for dc_id in dc_ids:
        try:
            filters = api.get_dc_network_filters(dc_id, tr)
            if not filters.get("manufacturers"):
                continue
            api.get_dc_network_port_summary(dc_id, tr)
            api.get_dc_network_95th_percentile(dc_id, tr, top_n=20)
            api.get_dc_network_interface_table(dc_id, tr, page=1, page_size=50)
        except Exception as exc:
            logger.warning("GUI network warm failed for DC %s: %s", dc_id, exc)


def warm_dc_network_caches() -> None:
    """Warm GUI HTTP response cache for network panels (default reporting range)."""
    logger.info("Warming GUI network cache for default time range…")
    try:
        _warm_dc_network_for_range(default_time_range())
        logger.info("GUI network cache warm-up complete for default range.")
    except Exception as exc:
        logger.warning("GUI network cache warm-up failed: %s", exc)


def refresh_dc_network_caches() -> None:
    """Refresh GUI network HTTP cache for all standard reporting ranges."""
    logger.info("GUI network cache refresh started.")
    try:
        for tr in cache_time_ranges():
            _warm_dc_network_for_range(tr)
        logger.info("GUI network cache refresh complete.")
    except Exception as exc:
        logger.warning("GUI network cache refresh failed: %s", exc)


def _warm_dc_nutanix_for_range(tr: dict) -> None:
    """Prime GUI api:* cache for the Nutanix snapshot panel (summary + first page)."""
    try:
        summaries = api.get_all_datacenters_summary(tr)
    except Exception as exc:
        logger.warning("GUI nutanix warm: datacenter summary failed: %s", exc)
        return

    dc_ids = [dc.get("id") for dc in (summaries or []) if dc.get("id")]
    for dc_id in dc_ids:
        try:
            snap = api.get_dc_nutanix_snapshots(dc_id, tr)
            if not (snap or {}).get("rows"):
                continue
            api.get_dc_nutanix_snapshot_table(dc_id, tr, page=1, page_size=50)
            api.get_dc_nutanix_missing(dc_id, tr, page=1, page_size=50)
        except Exception as exc:
            logger.warning("GUI nutanix warm failed for DC %s: %s", dc_id, exc)


def warm_dc_nutanix_snapshots() -> None:
    """Warm GUI HTTP response cache for Nutanix snapshot panels (default range)."""
    logger.info("Warming GUI nutanix snapshot cache for default time range…")
    try:
        _warm_dc_nutanix_for_range(default_time_range())
        logger.info("GUI nutanix snapshot cache warm-up complete for default range.")
    except Exception as exc:
        logger.warning("GUI nutanix snapshot cache warm-up failed: %s", exc)


def refresh_dc_nutanix_snapshot_caches() -> None:
    """Refresh GUI nutanix snapshot cache for all standard reporting ranges."""
    logger.info("GUI nutanix snapshot cache refresh started.")
    try:
        for tr in cache_time_ranges():
            _warm_dc_nutanix_for_range(tr)
        logger.info("GUI nutanix snapshot cache refresh complete.")
    except Exception as exc:
        logger.warning("GUI nutanix snapshot cache refresh failed: %s", exc)


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

    # SLA availability cache warm-up + hourly refresh (default report range).
    try:
        def _refresh_sla_default_range():
            tr = default_time_range()
            sla_service.refresh_sla_cache(tr)

        scheduler.add_job(
            func=_refresh_sla_default_range,
            trigger=DateTrigger(run_date=datetime.now()),
            id="sla_initial_warm",
            name="Initial SLA availability warm-up (default range)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled initial SLA availability warm-up (default range).")
    except Exception as exc:
        logger.warning("Failed to schedule initial SLA warm-up: %s", exc)

    try:
        scheduler.add_job(
            func=lambda: sla_service.refresh_sla_cache(default_time_range()),
            trigger=IntervalTrigger(minutes=SLA_REFRESH_INTERVAL_MINUTES),
            id="sla_hourly_refresh",
            name="SLA availability cache refresh (hourly, default range)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled SLA availability refresh every %d minutes.", SLA_REFRESH_INTERVAL_MINUTES)
    except Exception as exc:
        logger.warning("Failed to schedule SLA hourly refresh: %s", exc)

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

    # Customer-view resource cache is warmed by app_background_warm.warm_common on the
    # 240s server-side timer (and both anchor variants, under warm_mode). The former
    # 15-min scheduler jobs here were a NO-OP and have been removed.

    # Step 4a: customer availability (AuraNotify) — initial warm + same interval as DC cache refresh.
    try:
        scheduler.add_job(
            func=refresh_warmed_customer_availability_bundles,
            trigger=DateTrigger(run_date=datetime.now()),
            id="customer_avail_initial_warm",
            name="Initial customer availability bundle warm-up (AuraNotify)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled initial customer availability bundle warm-up.")
    except Exception as exc:
        logger.warning("Failed to schedule initial customer availability warm-up: %s", exc)

    try:
        scheduler.add_job(
            func=refresh_warmed_customer_availability_bundles,
            trigger=IntervalTrigger(minutes=REFRESH_INTERVAL_MINUTES),
            id="customer_avail_refresh",
            name="Customer availability bundle refresh (AuraNotify)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info(
            "Scheduled customer availability bundle refresh every %d minutes.",
            REFRESH_INTERVAL_MINUTES,
        )
    except Exception as exc:
        logger.warning("Failed to schedule customer availability refresh: %s", exc)

    # Step 6: warm S3 cache once in the background (default range) so first S3 visits are fast.
    try:
        scheduler.add_job(
            func=db_service.warm_s3_cache,
            trigger=DateTrigger(run_date=datetime.now()),
            id="s3_initial_warm",
            name="Initial S3 cache warm-up (default range)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled initial S3 cache warm-up for default range.")
    except Exception as exc:
        logger.warning("Failed to schedule initial S3 cache warm-up: %s", exc)

    # Step 7: schedule periodic S3 cache refresh (every 30 minutes, write-through pattern).
    try:
        scheduler.add_job(
            func=db_service.refresh_s3_cache,
            trigger=IntervalTrigger(minutes=30),
            id="s3_refresh",
            name="S3 cache refresh (30 minutes)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled S3 cache refresh every 30 minutes.")
    except Exception as exc:
        logger.warning("Failed to schedule S3 cache refresh: %s", exc)

    # Step 8: schedule periodic backup cache refresh (every 30 minutes, write-through pattern).
    try:
        scheduler.add_job(
            func=db_service.refresh_backup_cache,
            trigger=IntervalTrigger(minutes=30),
            id="backup_refresh",
            name="Backup cache refresh (30 minutes)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled Backup cache refresh every 30 minutes.")
    except Exception as exc:
        logger.warning("Failed to schedule Backup cache refresh: %s", exc)

    # Step 8a: warm network cache once in the background (default range).
    try:
        scheduler.add_job(
            func=warm_dc_network_caches,
            trigger=DateTrigger(run_date=datetime.now()),
            id="network_initial_warm",
            name="Initial network cache warm-up (default range)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled initial network cache warm-up for default range.")
    except Exception as exc:
        logger.warning("Failed to schedule initial network cache warm-up: %s", exc)

    # Step 8b: periodic network cache refresh (every 30 minutes).
    try:
        scheduler.add_job(
            func=refresh_dc_network_caches,
            trigger=IntervalTrigger(minutes=30),
            id="network_refresh",
            name="Network cache refresh (30 minutes)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled network cache refresh every 30 minutes.")
    except Exception as exc:
        logger.warning("Failed to schedule network cache refresh: %s", exc)

    # Step 8c: warm nutanix snapshot cache once in the background (default range).
    try:
        scheduler.add_job(
            func=warm_dc_nutanix_snapshots,
            trigger=DateTrigger(run_date=datetime.now()),
            id="nutanix_snapshot_initial_warm",
            name="Initial nutanix snapshot cache warm-up (default range)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled initial nutanix snapshot cache warm-up for default range.")
    except Exception as exc:
        logger.warning("Failed to schedule initial nutanix snapshot cache warm-up: %s", exc)

    # Step 8d: periodic nutanix snapshot cache refresh (every 30 minutes).
    try:
        scheduler.add_job(
            func=refresh_dc_nutanix_snapshot_caches,
            trigger=IntervalTrigger(minutes=30),
            id="nutanix_snapshot_refresh",
            name="Nutanix snapshot cache refresh (30 minutes)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled nutanix snapshot cache refresh every 30 minutes.")
    except Exception as exc:
        logger.warning("Failed to schedule nutanix snapshot cache refresh: %s", exc)

    # Step 9: schedule periodic physical inventory cache refresh (every 30 minutes).
    try:
        scheduler.add_job(
            func=db_service.warm_physical_inventory,
            trigger=IntervalTrigger(minutes=30),
            id="phys_inv_refresh",
            name="Physical inventory cache refresh (30 minutes)",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled physical inventory cache refresh every 30 minutes.")
    except Exception as exc:
        logger.warning("Failed to schedule physical inventory cache refresh: %s", exc)

    # Step 10: clean shutdown on process exit
    atexit.register(lambda: _stop(scheduler))

    return scheduler


def _stop(scheduler: BackgroundScheduler) -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped.")
