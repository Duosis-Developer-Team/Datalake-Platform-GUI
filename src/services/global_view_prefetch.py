"""Background prefetch service for Global View.

Two-phase warm strategy:
  Phase 1 – critical: summary + all DC details + all rack lists + floor-map figures.
             Completes in a few seconds when the backend cache is hot.
             Sets `is_warm()` to True so callers know the click path is ready.
  Phase 2 – devices: rack-device details for every rack across all DCs.
             Runs in a separate daemon thread after Phase 1 logs done.
             May take tens of seconds for large installs (189 racks × ~1ms hot = ~2s at 12 workers).

Priority warm:
  `warm_dc_priority(dc_id)` warms one DC's rack devices immediately in a daemon
  thread. Call it on DC pin click so the first rack detail panel is fast even
  before the global device phase finishes.

Public API:
    trigger_background(tr)         non-blocking global warm
    warm_dc_priority(dc_id)        non-blocking DC-scoped device warm
    is_warm(tr)                    True if Phase 1 done within TTL
    last_warm_stats(tr)            stats dict from last completed warm
"""

import logging
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

logger = logging.getLogger(__name__)

GLOBAL_VIEW_PREFETCH_INTERVAL_SECONDS = 900  # 15 minutes

_CRITICAL_WORKERS = 8   # details + rack-list fetches
_DEVICE_WORKERS = 12    # rack-device fetches (hot backend → fast at high concurrency)
_FIGURE_WORKERS = 4     # parallel floor-map figure builds
_DEVICE_BATCH = 24      # pairs per Phase-2 batch (checked against pause flag between batches)

_lock = threading.Lock()
_in_flight: set[str] = set()
_last_warm: dict[str, float] = {}       # key -> monotonic time of last Phase 1 completion
_warm_stats: dict[str, dict] = {}       # key -> stats dict

_prio_lock = threading.Lock()
_prio_in_flight: dict[str, threading.Thread] = {}  # dc_id -> active priority-warm thread

_phase2_pause = threading.Event()  # set() = paused, clear() = running


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _tr_key(tr: Optional[dict]) -> str:
    import json
    if not tr:
        return "noparams"
    return json.dumps(sorted(tr.items()), separators=(",", ":"), ensure_ascii=False)


def is_warm(tr: Optional[dict]) -> bool:
    """Return True if Phase 1 completed within the 15-minute TTL window."""
    key = _tr_key(tr)
    with _lock:
        last = _last_warm.get(key)
        if last is None:
            return False
        return (_time.monotonic() - last) < GLOBAL_VIEW_PREFETCH_INTERVAL_SECONDS


def last_warm_stats(tr: Optional[dict]) -> dict:
    """Return stats dict from the last completed warm for this time range."""
    key = _tr_key(tr)
    with _lock:
        return dict(_warm_stats.get(key, {}))


def set_phase2_pause(paused: bool) -> None:
    """Pause or resume Phase-2 device fetches.

    Call with paused=True when the user enters floor_map/building mode so
    background device fetches don't compete with user-driven rack detail calls.
    """
    if paused:
        _phase2_pause.set()
        logger.debug("prefetch phase2 paused")
    else:
        _phase2_pause.clear()
        logger.debug("prefetch phase2 resumed")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def trigger_background(tr: Optional[dict]) -> None:
    """Start warm() in a daemon thread; returns immediately without blocking."""
    t = threading.Thread(target=warm, args=(tr,), daemon=True, name="gv-prefetch")
    t.start()


def warm_dc_priority(dc_id: str) -> None:
    """Warm rack-device details for a single DC immediately (non-blocking).

    Guarded against duplicate calls: if an active priority-warm thread is already
    running for this dc_id, the new call is a no-op.
    """
    with _prio_lock:
        existing = _prio_in_flight.get(dc_id)
        if existing is not None and existing.is_alive():
            logger.debug("warm_dc_priority skip reason=in_flight dc=%s", dc_id)
            return
        t = threading.Thread(
            target=_warm_dc_devices_guarded,
            args=(dc_id,),
            daemon=True,
            name=f"gv-prio-{dc_id}",
        )
        _prio_in_flight[dc_id] = t
        t.start()


def _warm_dc_devices_guarded(dc_id: str) -> None:
    """Wrapper that removes dc_id from _prio_in_flight when done."""
    try:
        _warm_dc_devices(dc_id)
    finally:
        with _prio_lock:
            _prio_in_flight.pop(dc_id, None)


# ---------------------------------------------------------------------------
# Core warm logic
# ---------------------------------------------------------------------------

def warm(tr: Optional[dict]) -> None:
    """Check TTL/in-flight guards then run Phase 1 + spawn Phase 2."""
    key = _tr_key(tr)
    now = _time.monotonic()

    with _lock:
        if key in _in_flight:
            logger.info("prefetch skip reason=in_flight key=%s", key)
            return
        last = _last_warm.get(key)
        if last is not None and (now - last) < GLOBAL_VIEW_PREFETCH_INTERVAL_SECONDS:
            remaining = GLOBAL_VIEW_PREFETCH_INTERVAL_SECONDS - (now - last)
            logger.info(
                "prefetch skip reason=ttl_active skipped_due_to_ttl=true "
                "key=%s remaining_s=%.0f",
                key, remaining,
            )
            return
        _in_flight.add(key)

    try:
        _run_warm(tr, key)
    finally:
        with _lock:
            _in_flight.discard(key)


def _run_warm(tr: Optional[dict], key: str) -> None:
    from src.services import api_client as api
    from src.pages.floor_map import build_floor_map_figure

    t0 = _time.monotonic()
    logger.info("prefetch start key=%s time_range=%s", key, tr)

    # ── Phase 1: critical ──────────────────────────────────────────────────

    # 1a. Summary
    try:
        summaries = api.get_all_datacenters_summary(tr)
    except Exception as exc:
        logger.warning("prefetch summary failed: %s", exc)
        summaries = []

    dc_ids = [dc.get("id") for dc in (summaries or []) if dc.get("id")]
    dc_count = len(dc_ids)

    # 1b. DC details — parallel
    def _fetch_details(dc_id: str) -> None:
        try:
            api.get_dc_details(dc_id, tr)
        except Exception as exc:
            logger.debug("prefetch dc_details failed dc=%s: %s", dc_id, exc)

    with ThreadPoolExecutor(max_workers=_CRITICAL_WORKERS) as pool:
        list(pool.map(_fetch_details, dc_ids))

    # 1c. Rack lists — parallel
    def _fetch_racks(dc_id: str) -> tuple[str, list]:
        try:
            resp = api.get_dc_racks(dc_id)
            return dc_id, resp.get("racks", [])
        except Exception as exc:
            logger.debug("prefetch racks failed dc=%s: %s", dc_id, exc)
            return dc_id, []

    racks_by_dc: dict[str, list] = {}
    with ThreadPoolExecutor(max_workers=_CRITICAL_WORKERS) as pool:
        for dc_id, racks in pool.map(_fetch_racks, dc_ids):
            racks_by_dc[dc_id] = racks

    rack_count = sum(len(v) for v in racks_by_dc.values())

    # 1d. Floor-map figures — parallel (bounded workers; order-independent)
    def _build_one_figure(dc_racks: tuple[str, list]) -> int:
        dc, racks = dc_racks
        if not racks:
            return 0
        try:
            build_floor_map_figure(racks, dc_id=dc)
            return 1
        except Exception as exc:
            logger.debug("prefetch figure failed dc=%s: %s", dc, exc)
            return 0

    with ThreadPoolExecutor(max_workers=_FIGURE_WORKERS) as fig_pool:
        figure_count = sum(fig_pool.map(_build_one_figure, racks_by_dc.items()))

    critical_ms = int((_time.monotonic() - t0) * 1000)
    logger.info(
        "prefetch phase=critical done key=%s dc_count=%d rack_count=%d "
        "figure_count=%d elapsed_ms=%d",
        key, dc_count, rack_count, figure_count, critical_ms,
    )

    # Mark Phase 1 complete so is_warm() returns True immediately
    with _lock:
        _last_warm[key] = _time.monotonic()
        _warm_stats[key] = {
            "dc_count": dc_count,
            "rack_count": rack_count,
            "device_request_count": None,
            "critical_ms": critical_ms,
            "device_ms": None,
            "total_ms": None,
        }

    # ── Phase 2: device details (spawn and return) ─────────────────────────
    # Sort DCs by rack count descending so large DCs are warmed first.
    ordered_pairs: list[tuple[str, str]] = []
    for dc_id, racks in sorted(
        racks_by_dc.items(), key=lambda kv: len(kv[1]), reverse=True
    ):
        for rack in racks:
            rack_name = rack.get("name") or rack.get("id")
            if rack_name:
                ordered_pairs.append((dc_id, rack_name))

    if ordered_pairs:
        t2_thread = threading.Thread(
            target=_run_device_phase,
            args=(ordered_pairs, key, t0),
            daemon=True,
            name="gv-devices",
        )
        t2_thread.start()


def _run_device_phase(
    pairs: list[tuple[str, str]],
    key: str,
    t0: float,
) -> None:
    from src.services import api_client as api

    t2 = _time.monotonic()
    pairs_done = 0
    pairs_skipped = 0

    def _fetch(pair: tuple[str, str]) -> None:
        dc_id, rack_name = pair
        try:
            api.get_rack_devices(dc_id, rack_name)
        except Exception as exc:
            logger.debug("prefetch devices failed dc=%s rack=%s: %s", dc_id, rack_name, exc)

    with ThreadPoolExecutor(max_workers=_DEVICE_WORKERS) as pool:
        for i in range(0, len(pairs), _DEVICE_BATCH):
            if _phase2_pause.is_set():
                pairs_skipped = len(pairs) - i
                logger.info(
                    "prefetch phase=devices paused key=%s at_index=%d pairs_skipped=%d",
                    key, i, pairs_skipped,
                )
                break
            batch = pairs[i : i + _DEVICE_BATCH]
            list(pool.map(_fetch, batch))
            pairs_done += len(batch)
            _time.sleep(0)  # cooperative yield between batches

    device_ms = int((_time.monotonic() - t2) * 1000)
    total_ms = int((_time.monotonic() - t0) * 1000)
    logger.info(
        "prefetch phase=devices done key=%s pairs_done=%d pairs_skipped=%d "
        "phase_ms=%d total_ms=%d",
        key, pairs_done, pairs_skipped, device_ms, total_ms,
    )
    with _lock:
        stats = _warm_stats.get(key, {})
        stats["device_request_count"] = pairs_done
        stats["device_ms"] = device_ms
        stats["total_ms"] = total_ms
        stats["phase2_paused"] = pairs_skipped > 0
        stats["pairs_skipped"] = pairs_skipped
        _warm_stats[key] = stats


# ---------------------------------------------------------------------------
# Priority warm for a single DC
# ---------------------------------------------------------------------------

def _warm_dc_devices(dc_id: str) -> None:
    from src.services import api_client as api

    try:
        resp = api.get_dc_racks(dc_id)
        racks = resp.get("racks", [])
    except Exception as exc:
        logger.debug("warm_dc_priority racks failed dc=%s: %s", dc_id, exc)
        return

    pairs = [
        (dc_id, rack.get("name") or rack.get("id"))
        for rack in racks
        if rack.get("name") or rack.get("id")
    ]
    if not pairs:
        return

    def _fetch(pair: tuple[str, str]) -> None:
        d, r = pair
        try:
            api.get_rack_devices(d, r)
        except Exception as exc:
            logger.debug("warm_dc_priority devices failed dc=%s rack=%s: %s", d, r, exc)

    t0 = _time.monotonic()
    with ThreadPoolExecutor(max_workers=_DEVICE_WORKERS) as pool:
        list(pool.map(_fetch, pairs))

    elapsed_ms = int((_time.monotonic() - t0) * 1000)
    logger.info(
        "prefetch dc_priority done dc=%s rack_count=%d elapsed_ms=%d",
        dc_id, len(pairs), elapsed_ms,
    )
