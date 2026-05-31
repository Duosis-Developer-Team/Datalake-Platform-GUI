"""Data Centers page — virt sellable TL resolution and loading state."""
from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.services import api_client as api
from src.utils.virt_sellable_aggregate import collect_virt_sellable_panels, total_potential_tl

_VIRT_TL_CACHE: dict[str, float] = {}
_VIRT_CACHE_WARMING = False
_VIRT_CACHE_TR_KEY = ""
_VIRT_CACHE_LOCK = threading.Lock()


def virt_cache_tr_key(tr: dict | None) -> str:
    tr = tr or {}
    return f"{tr.get('preset', '')}|{tr.get('start', '')}|{tr.get('end', '')}"


def _virt_sellable_tl_for_dc(dc_id: str, family_workers: int) -> float:
    return total_potential_tl(
        collect_virt_sellable_panels(
            str(dc_id),
            None,
            None,
            max_family_workers=family_workers,
        )
    )


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
        global _VIRT_CACHE_WARMING, _VIRT_TL_CACHE, _VIRT_CACHE_TR_KEY
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
                        continue
            with _VIRT_CACHE_LOCK:
                _VIRT_TL_CACHE = local_vals
                _VIRT_CACHE_TR_KEY = tr_key
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

    Uses in-process warm cache when complete; otherwise triggers background warm
    and returns partial/zero map with ``loading=True`` until warm finishes.
    Tier-2 durable snapshots in crm-engine reduce cold-start zeros after restart.
    """
    tr = tr or {}
    tr_key = virt_cache_tr_key(tr)
    configured_family_workers = int(os.getenv("DC_OVERVIEW_VIRT_FAMILY_WORKERS", "1") or "1")
    fw = max(1, family_workers if family_workers is not None else configured_family_workers)
    configured_workers = int(os.getenv("DC_OVERVIEW_VIRT_WORKERS", "4") or "4")
    mw = min(max(1, max_workers if max_workers is not None else configured_workers), max(1, len(dc_ids)))

    with _VIRT_CACHE_LOCK:
        cache_snapshot = dict(_VIRT_TL_CACHE)
        cache_key = _VIRT_CACHE_TR_KEY
        warming = _VIRT_CACHE_WARMING

    cache_hit_count = sum(1 for dc_id in dc_ids if dc_id in cache_snapshot and cache_key == tr_key)
    cache_complete = cache_hit_count >= len(dc_ids) and len(dc_ids) > 0

    if not cache_complete and not warming:
        start_virt_cache_warm(dc_ids, tr, max_workers=mw, family_workers=fw)
        with _VIRT_CACHE_LOCK:
            warming = _VIRT_CACHE_WARMING

    virt_tl_by_dc: dict[str, float] = {}
    total = 0.0
    for dc_id in dc_ids:
        dc_virt = cache_snapshot.get(dc_id, 0.0) if cache_key == tr_key else 0.0
        virt_tl_by_dc[dc_id] = dc_virt
        total += dc_virt

    loading = warming or (not cache_complete and total == 0.0)
    return {
        "virt_tl_by_dc": virt_tl_by_dc,
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
                continue

    with _VIRT_CACHE_LOCK:
        global _VIRT_TL_CACHE, _VIRT_CACHE_TR_KEY, _VIRT_CACHE_WARMING
        _VIRT_TL_CACHE = local_vals
        _VIRT_CACHE_TR_KEY = tr_key
        _VIRT_CACHE_WARMING = False

    total = sum(local_vals.values())
    return {
        "virt_tl_by_dc": local_vals,
        "total_potential_tl": total,
        "loading": False,
        "cache_complete": True,
        "tr_key": tr_key,
    }
