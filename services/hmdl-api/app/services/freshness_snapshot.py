"""In-process freshness snapshot + background refresher (hmdl-api has no Redis).

The endpoint serves the last snapshot instantly; a daemon thread recomputes it
every ah_freshness_refresh_min minutes so the expensive ~120-table sweep never
runs on the request path.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from app.config import settings
from app.db.queries.freshness import compute_freshness

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_snapshot: dict | None = None
_stop = threading.Event()
_thread: threading.Thread | None = None

_EMPTY_COUNTS = {"fresh": 0, "stale": 0, "dead": 0, "unknown": 0, "alert": 0}


def _reset_for_test() -> None:
    global _snapshot
    with _lock:
        _snapshot = None


def get_snapshot() -> dict:
    with _lock:
        if _snapshot is None:
            return {"families": [], "flows": [], "unmonitored": [], "missing": [],
                    "counts": dict(_EMPTY_COUNTS),
                    "generated_at": None, "status": "computing"}
        return _snapshot


def refresh_now() -> None:
    result = compute_freshness()
    result["generated_at"] = datetime.now(timezone.utc)
    result["status"] = "ok"
    global _snapshot
    with _lock:
        _snapshot = result


def _loop(interval_s: float) -> None:
    while not _stop.is_set():
        try:
            refresh_now()
        except Exception:  # noqa: BLE001
            logger.exception("freshness snapshot refresh failed")
        _stop.wait(interval_s)


def start_refresher() -> threading.Thread:
    global _thread
    _stop.clear()
    _thread = threading.Thread(
        target=_loop, args=(settings.ah_freshness_refresh_min * 60.0,),
        name="freshness-refresher", daemon=True,
    )
    _thread.start()
    return _thread
