"""Post-login RBAC-scoped background cache warm (non-blocking, pausable).

Warms CRM sellable summaries, home dashboard keys, and global-view phase-1
for pages/DCs the user may access. Active-route requests always take priority.
"""
from __future__ import annotations

import logging
import os
import threading
import time as _time
from typing import Optional

logger = logging.getLogger(__name__)

# Re-warm throttle. Lowered so the periodic `app-warm-interval` (every ~5 min) keeps the
# backend overview/summary caches hot, instead of only re-warming on navigation every 15 min.
_WARM_INTERVAL_SECONDS = int(os.getenv("APP_WARM_INTERVAL_SECONDS", "240") or "240")
_MAX_DC_WORKERS = 2

_lock = threading.Lock()
_in_flight = False
_last_warm: float = 0.0
_pause = threading.Event()
_active_route: str | None = None


def set_active_route(pathname: str | None) -> None:
    """Pause background warm while a heavy DC route is loading."""
    global _active_route
    _active_route = pathname
    if pathname and pathname.startswith("/datacenter/"):
        _pause.set()
    else:
        _pause.clear()


def _should_pause() -> bool:
    return _pause.is_set()


def _warm_sellable_for_dcs(dc_codes: list[str], tr: dict) -> int:
    from src.utils.virt_sellable_aggregate import collect_virt_sellable_panels

    warmed = 0
    for dc in dc_codes:
        if _should_pause():
            break
        try:
            collect_virt_sellable_panels(str(dc))
            warmed += 1
        except Exception:
            logger.debug("background warm sellable failed dc=%s", dc, exc_info=True)
    return warmed


def _warm_home_bundle(tr: dict) -> None:
    from src.services import api_client as api

    if _should_pause():
        return
    try:
        api.get_global_dashboard(tr)
        api.get_all_datacenters_summary(tr)
    except Exception:
        logger.debug("background warm home failed", exc_info=True)


def _warm_global_phase1(tr: dict) -> None:
    if _should_pause():
        return
    try:
        from src.services.global_view_prefetch import set_phase2_pause, trigger_background

        set_phase2_pause(True)
        trigger_background(tr)
    except Exception:
        logger.debug("background warm global-view failed", exc_info=True)


def _warm_host_rows_for_dcs(dc_codes: list[str], tr: dict) -> int:
    """Prefetch full-DC host rows into GUI cache (L2) for sellable + hosts panel."""
    from src.services import api_client as api

    warmed = 0
    for dc in dc_codes:
        if _should_pause():
            break
        try:
            api.get_classic_host_rows(str(dc), None, tr)
            api.get_hyperconv_host_rows(str(dc), None, tr)
            warmed += 1
        except Exception:
            logger.debug("background warm host rows failed dc=%s", dc, exc_info=True)
    return warmed


def _warm_customer_view(customers, time_range: dict | None) -> int:
    """Pre-populate the shared cache with each warmed customer's customer-view
    data (resources, availability, ITSM, sales, efficiency, S3), so first visits
    hit the cache. Returns how many customers warmed without error."""
    from src.services import api_client as api

    warmed = 0
    for name in customers:
        name = (name or "").strip()
        if not name:
            continue
        try:
            api.get_customer_resources(name, time_range)
            api.get_customer_availability_bundle(name, time_range)
            api.get_customer_itsm_summary(name, time_range)
            api.get_customer_sales_summary(name)
            api.get_customer_efficiency_by_category(name, time_range)
            api.get_customer_s3_vaults(name, time_range)
            warmed += 1
        except Exception as exc:
            logger.warning("customer-view warm failed for %s: %s", name, exc)
    return warmed


def warm_rbac_scope(
    user_id: int,
    time_range: dict | None,
    *,
    page_codes: Optional[list[str]] = None,
) -> dict:
    """Run RBAC-scoped warm synchronously (used from daemon thread)."""
    from src.auth.permission_service import can_view, get_visible_sections
    from src.services import api_client as api
    from src.utils.time_range import default_time_range

    tr = time_range or default_time_range()
    stats = {"sellable_dcs": 0, "host_rows_dcs": 0, "home": False, "global": False}

    if can_view(user_id, "page:datacenters") or can_view(user_id, "page:dc_view"):
        try:
            rows = api.get_all_datacenters_summary(tr) or []
            dc_codes = [
                str(r.get("id") or r.get("dc_code") or r.get("code") or "").strip()
                for r in rows
                if isinstance(r, dict)
            ]
            dc_codes = [c for c in dc_codes if c]
        except Exception:
            dc_codes = []
        if dc_codes:
            stats["sellable_dcs"] = _warm_sellable_for_dcs(dc_codes[:12], tr)
            if can_view(user_id, "page:dc_view"):
                stats["host_rows_dcs"] = _warm_host_rows_for_dcs(dc_codes[:6], tr)

    if can_view(user_id, "page:overview"):
        _warm_home_bundle(tr)
        stats["home"] = True

    if can_view(user_id, "page:global_view"):
        _warm_global_phase1(tr)
        stats["global"] = True

    if can_view(user_id, "page:customer_view"):
        from src.services.db_service import WARMED_CUSTOMERS

        stats["customer_view"] = _warm_customer_view(WARMED_CUSTOMERS, tr)

    del page_codes, get_visible_sections  # reserved for future per-section warm
    return stats


def _warm_guarded(user_id: int, tr: dict | None) -> None:
    global _in_flight, _last_warm
    with _lock:
        if _in_flight:
            return
        if (_time.monotonic() - _last_warm) < _WARM_INTERVAL_SECONDS:
            return
        _in_flight = True
    try:
        stats = warm_rbac_scope(user_id, tr)
        logger.info("app_background_warm done uid=%s stats=%s", user_id, stats)
    finally:
        with _lock:
            _in_flight = False
            _last_warm = _time.monotonic()


def trigger_rbac_warm(user_id: int, time_range: dict | None) -> None:
    """Start RBAC warm in a daemon thread; returns immediately."""
    if not user_id:
        return
    t = threading.Thread(
        target=_warm_guarded,
        args=(int(user_id), time_range),
        daemon=True,
        name=f"rbac-warm-{user_id}",
    )
    t.start()
