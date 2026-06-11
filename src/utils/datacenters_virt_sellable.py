"""Data Centers page — virt sellable TL resolution and loading state."""
from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.services import api_client as api
from src.utils.virt_sellable_aggregate import virt_tl_from_sellable_summary

logger = logging.getLogger(__name__)

_VIRT_TL_CACHE: dict[str, float] = {}
_VIRT_CACHE_WARMING = False
_VIRT_CACHE_TR_KEY = ""
_VIRT_CACHE_LOCK = threading.Lock()


def virt_cache_tr_key(tr: dict | None) -> str:
    tr = tr or {}
    return f"{tr.get('preset', '')}|{tr.get('start', '')}|{tr.get('end', '')}"


def _virt_sellable_tl_for_dc(dc_id: str, _family_workers: int) -> float:
    """Resolve virt sellable TL via lightweight CRM summary (rollup_only)."""
    summary = api.get_sellable_summary_light(str(dc_id))
    return virt_tl_from_sellable_summary(summary)


def _seed_from_api_cache(dc_ids: list[str]) -> dict[str, float]:
    """Publish any DC values already warm in api_client sellable summary cache."""
    seeded: dict[str, float] = {}
    for dc_id in dc_ids:
        try:
            summary = api.get_sellable_summary_light(str(dc_id))
            if summary:
                seeded[str(dc_id)] = virt_tl_from_sellable_summary(summary)
        except Exception:
            logger.debug("virt sellable seed failed dc=%s", dc_id, exc_info=True)
    return seeded


def _publish_virt_cache(
    local_vals: dict[str, float],
    dc_ids: list[str],
    tr_key: str,
) -> None:
    """Atomically publish warm results; never wipe prior cache on empty/partial failure."""
    global _VIRT_TL_CACHE, _VIRT_CACHE_TR_KEY
    if not local_vals:
        return
    with _VIRT_CACHE_LOCK:
        if len(local_vals) >= len(dc_ids) and len(dc_ids) > 0:
            _VIRT_TL_CACHE = dict(local_vals)
            _VIRT_CACHE_TR_KEY = tr_key
            return
        merged = dict(_VIRT_TL_CACHE)
        merged.update(local_vals)
        _VIRT_TL_CACHE = merged
        if set(dc_ids).issubset(local_vals.keys()):
            _VIRT_CACHE_TR_KEY = tr_key


def start_virt_cache_warm(
    dc_ids: list[str],
    tr: dict,
    *,
    max_workers: int,
    family_workers: int,
) -> bool:
    global _VIRT_CACHE_WARMING
    tr_key = virt_cache_tr_key(tr)
    with _VIRT_CACHE_LOCK:
        if _VIRT_CACHE_WARMING:
            return False
        _VIRT_CACHE_WARMING = True

    def _run() -> None:
        global _VIRT_CACHE_WARMING
        local_vals: dict[str, float] = {}
        try:

            def _compute(dc_id: str) -> tuple[str, float]:
                return dc_id, _virt_sellable_tl_for_dc(dc_id, family_workers)

            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = [pool.submit(_compute, dc_id) for dc_id in dc_ids]
                for fut in as_completed(futures):
                    try:
                        dc_id, val = fut.result()
                        local_vals[dc_id] = val
                    except Exception:
                        logger.warning("virt sellable warm failed", exc_info=True)
                        continue
            _publish_virt_cache(local_vals, dc_ids, tr_key)
        finally:
            with _VIRT_CACHE_LOCK:
                _VIRT_CACHE_WARMING = False

    threading.Thread(target=_run, daemon=True).start()
    return True


def is_virt_cache_warming() -> bool:
    with _VIRT_CACHE_LOCK:
        return _VIRT_CACHE_WARMING


def resolve_virt_sellable_for_dcs(
    dc_ids: list[str],
    tr: dict | None,
    *,
    family_workers: int | None = None,
    max_workers: int | None = None,
) -> dict[str, Any]:
    """Resolve per-DC virt sellable TL map and whether UI should show loading.

    Serves the last published in-process cache while a background warm runs (stale-while-refresh).
    Seeds from api_client sellable summary cache when available.
    """
    tr = tr or {}
    tr_key = virt_cache_tr_key(tr)
    configured_family_workers = int(os.getenv("DC_OVERVIEW_VIRT_FAMILY_WORKERS", "1") or "1")
    fw = max(1, family_workers if family_workers is not None else configured_family_workers)
    configured_workers = int(os.getenv("DC_OVERVIEW_VIRT_WORKERS", "4") or "4")
    mw = min(max(1, max_workers if max_workers is not None else configured_workers), max(1, len(dc_ids)))

    seeded = _seed_from_api_cache(dc_ids)
    if seeded:
        _publish_virt_cache(seeded, dc_ids, tr_key)

    with _VIRT_CACHE_LOCK:
        cache_snapshot = dict(_VIRT_TL_CACHE)
        cache_key = _VIRT_CACHE_TR_KEY
        warming = _VIRT_CACHE_WARMING

    cache_hit_count = sum(
        1 for dc_id in dc_ids
        if dc_id in cache_snapshot and cache_key == tr_key
    )
    cache_complete = cache_hit_count >= len(dc_ids) and len(dc_ids) > 0

    if not cache_complete and not warming:
        start_virt_cache_warm(dc_ids, tr, max_workers=mw, family_workers=fw)
        with _VIRT_CACHE_LOCK:
            warming = _VIRT_CACHE_WARMING
            cache_snapshot = dict(_VIRT_TL_CACHE)
            cache_key = _VIRT_CACHE_TR_KEY

    virt_tl_by_dc: dict[str, float] = {}
    loading_by_dc: dict[str, bool] = {}
    total = 0.0
    for dc_id in dc_ids:
        has_stale_val = dc_id in cache_snapshot
        in_cache_for_tr = has_stale_val and cache_key == tr_key
        dc_virt = float(cache_snapshot.get(dc_id, 0.0) or 0.0) if has_stale_val else 0.0
        virt_tl_by_dc[dc_id] = dc_virt
        loading_by_dc[dc_id] = (warming or not in_cache_for_tr) and not has_stale_val
        total += dc_virt

    any_resolved = any(not loading_by_dc.get(dc_id, True) for dc_id in dc_ids)
    has_stale = any(dc_id in cache_snapshot for dc_id in dc_ids)
    loading = (warming or not cache_complete) and not (has_stale and total > 0.0)
    return {
        "virt_tl_by_dc": virt_tl_by_dc,
        "loading_by_dc": loading_by_dc,
        "total_potential_tl": total,
        "loading": loading,
        "cache_complete": cache_complete,
        "tr_key": tr_key,
    }


def refresh_virt_sellable_cache(
    dc_ids: list[str],
    tr: dict | None,
    *,
    family_workers: int | None = None,
) -> dict[str, Any]:
    """Synchronously recompute virt TL for all DCs (used by poll callback)."""
    global _VIRT_CACHE_WARMING
    fw = max(1, int(family_workers or os.getenv("DC_OVERVIEW_VIRT_FAMILY_WORKERS", "1") or "1"))
    tr_key = virt_cache_tr_key(tr)
    local_vals: dict[str, float] = {}

    def _compute(dc_id: str) -> tuple[str, float]:
        return dc_id, _virt_sellable_tl_for_dc(dc_id, fw)

    mw = min(max(1, int(os.getenv("DC_OVERVIEW_VIRT_WORKERS", "4") or "4")), max(1, len(dc_ids)))
    with ThreadPoolExecutor(max_workers=mw) as pool:
        futures = [pool.submit(_compute, dc_id) for dc_id in dc_ids]
        for fut in as_completed(futures):
            try:
                dc_id, val = fut.result()
                local_vals[dc_id] = val
            except Exception:
                logger.warning("virt sellable refresh failed", exc_info=True)
                continue

    _publish_virt_cache(local_vals, dc_ids, tr_key)
    with _VIRT_CACHE_LOCK:
        _VIRT_CACHE_WARMING = False
        snapshot = dict(_VIRT_TL_CACHE)

    virt_tl_by_dc = {dc_id: float(snapshot.get(dc_id, 0.0) or 0.0) for dc_id in dc_ids}
    loading_by_dc = {dc_id: False for dc_id in dc_ids}
    total = sum(virt_tl_by_dc.values())
    cache_complete = set(dc_ids).issubset(snapshot.keys()) and len(dc_ids) > 0
    return {
        "virt_tl_by_dc": virt_tl_by_dc,
        "loading_by_dc": loading_by_dc,
        "total_potential_tl": total,
        "loading": False,
        "cache_complete": cache_complete,
        "tr_key": tr_key,
    }
