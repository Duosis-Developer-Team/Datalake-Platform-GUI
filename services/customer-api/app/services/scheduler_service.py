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
MAPPED_BATCH_WARM_INTERVAL_HOURS = 6
DELETED_VM_REGISTRY_INTERVAL_HOURS = 6


def start_scheduler(
    svc: "CustomerService",
    sellable: "SellableService | None" = None,
) -> BackgroundScheduler:
    def _warm_cache_bg() -> None:
        logger.info("Customer API: initial hot-tier cache warm-up started (background).")
        t0 = time.perf_counter()
        try:
            svc.warm_cache()
            logger.info(
                "Customer API: initial hot-tier cache warm-up finished in %.2fs.",
                time.perf_counter() - t0,
            )
        except Exception:  # noqa: BLE001 - never abort startup
            logger.exception("Customer API: initial hot-tier cache warm-up failed")

    def _warm_mapped_batch_bg() -> None:
        logger.info("Customer API: initial mapped non-VIP batch warm started (background).")
        t0 = time.perf_counter()
        try:
            svc.warm_mapped_non_vip_batch()
            logger.info(
                "Customer API: initial mapped batch warm finished in %.2fs.",
                time.perf_counter() - t0,
            )
        except Exception:  # noqa: BLE001 - never abort startup
            logger.exception("Customer API: initial mapped batch warm failed")

    def _refresh_deleted_vm_registry_bg() -> None:
        logger.info("Customer API: deleted-VM registry refresh started (background).")
        t0 = time.perf_counter()
        try:
            result = svc.refresh_deleted_vm_registry()
            logger.info(
                "Customer API: deleted-VM registry refresh finished in %.2fs (%s).",
                time.perf_counter() - t0,
                result,
            )
        except Exception:  # noqa: BLE001 - never abort startup
            logger.exception("Customer API: deleted-VM registry refresh failed")

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func=svc.refresh_all_data,
        trigger=IntervalTrigger(minutes=REFRESH_INTERVAL_MINUTES),
        id="customer_cache_refresh",
        name="Customer API hot-tier cache refresh (VIP/pinned)",
        replace_existing=True,
        misfire_grace_time=60,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        func=svc.warm_mapped_non_vip_batch,
        trigger=IntervalTrigger(hours=MAPPED_BATCH_WARM_INTERVAL_HOURS),
        id="mapped_non_vip_batch_warm",
        name="Customer API mapped non-VIP batch warm (6h)",
        replace_existing=True,
        misfire_grace_time=300,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        func=svc.refresh_deleted_vm_registry,
        trigger=IntervalTrigger(hours=DELETED_VM_REGISTRY_INTERVAL_HOURS),
        id="deleted_vm_registry_refresh",
        name="Deleted-VM registry refresh (all-time scan)",
        replace_existing=True,
        misfire_grace_time=600,
        max_instances=1,
        coalesce=True,
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
        name="customer-initial-hot-warm",
    ).start()
    threading.Thread(
        target=_warm_mapped_batch_bg,
        daemon=True,
        name="customer-initial-mapped-batch-warm",
    ).start()
    threading.Thread(
        target=_refresh_deleted_vm_registry_bg,
        daemon=True,
        name="customer-initial-deleted-vm-registry",
    ).start()
    logger.info(
        "Customer API background scheduler started (hot refresh every %d minutes, mapped batch every %dh).",
        REFRESH_INTERVAL_MINUTES,
        MAPPED_BATCH_WARM_INTERVAL_HOURS,
    )

    atexit.register(lambda: _stop(scheduler))
    return scheduler


def _stop(scheduler: BackgroundScheduler) -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Customer API background scheduler stopped.")
