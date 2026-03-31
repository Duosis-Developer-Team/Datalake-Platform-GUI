import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from src.services import cache_service as cache

logger = logging.getLogger(__name__)

SLA_API_URL = os.getenv("SLA_API_URL", "http://10.34.8.154:5001/api/sla/datacenters")
SLA_API_KEY = (os.getenv("SLA_API_KEY") or "").strip()

_DC_CODE_RE = re.compile(r"(DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+)", re.IGNORECASE)
_STALE_AFTER_SECONDS = 60 * 60  # 1 hour


@dataclass(frozen=True)
class SlaEntry:
    dc_code: str
    availability_pct: float
    period_hours: float
    downtime_hours: float
    group_id: Optional[int] = None
    group_name: Optional[str] = None


def _cache_key(tr: dict) -> str:
    return f"sla_availability:{tr.get('start','')}:{tr.get('end','')}"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dc_code(group_name: str) -> Optional[str]:
    if not group_name:
        return None
    m = _DC_CODE_RE.search(group_name)
    return m.group(1).upper() if m else None


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _minutes_to_hours(mins: Any) -> float:
    return _safe_float(mins, 0.0) / 60.0


def _fetch_sla_raw(tr: dict) -> dict:
    if not SLA_API_KEY:
        logger.warning("SLA_API_KEY is not set; SLA API requests are disabled.")
        return {}
    params = {
        "start_date": f"{tr.get('start','')}T00:00:00",
        "end_date": f"{tr.get('end','')}T00:00:00",
    }
    headers = {"X-API-Key": SLA_API_KEY}
    resp = requests.get(SLA_API_URL, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _build_entries(payload: dict) -> tuple[dict[str, SlaEntry], dict[int, SlaEntry]]:
    by_dc: dict[str, SlaEntry] = {}
    by_group_id: dict[int, SlaEntry] = {}

    for item in (payload or {}).get("items", []) or []:
        group_name = str(item.get("group_name", "") or "")
        dc_code = _parse_dc_code(group_name)
        if not dc_code:
            continue

        entry = SlaEntry(
            dc_code=dc_code,
            availability_pct=_safe_float(item.get("availability_pct", 0.0), 0.0),
            period_hours=_minutes_to_hours(item.get("period_min", 0.0)),
            downtime_hours=_minutes_to_hours(item.get("total_downtime_min", 0.0)),
            group_id=int(item["group_id"]) if item.get("group_id") is not None else None,
            group_name=group_name,
        )
        by_dc[dc_code] = entry
        if entry.group_id is not None:
            by_group_id[entry.group_id] = entry

    return by_dc, by_group_id


def refresh_sla_cache(time_range: dict) -> dict[str, Any]:
    """
    Fetch SLA data from API and store in cache for the given time range.
    Returns the cached payload (normalized dict).
    """
    tr = time_range or {}
    if not tr.get("start") or not tr.get("end"):
        raise ValueError("time_range must include 'start' and 'end' (YYYY-MM-DD)")
    key = _cache_key(tr)

    payload = _fetch_sla_raw(tr)
    by_dc, by_group_id = _build_entries(payload)

    cached_payload: dict[str, Any] = {
        "fetched_at": _now_utc().isoformat(),
        "time_range": {"start": tr.get("start", ""), "end": tr.get("end", "")},
        "period_start": payload.get("period_start"),
        "period_end": payload.get("period_end"),
        "period_min": payload.get("period_min"),
        "by_dc": {k: vars(v) for k, v in by_dc.items()},
        "by_group_id": {str(k): vars(v) for k, v in by_group_id.items()},
    }

    cache.set(key, cached_payload)
    return cached_payload


def get_sla_data(time_range: dict, allow_refresh_if_stale: bool = True) -> dict[str, dict]:
    """
    Return SLA entries keyed by DC code for the given time range.
    If not in cache, fetches immediately. If cached but stale (>1h) and
    allow_refresh_if_stale=True, refreshes synchronously.
    """
    tr = time_range or {}
    if not tr.get("start") or not tr.get("end"):
        return {}
    key = _cache_key(tr)
    hit = cache.get(key)

    if hit is None:
        try:
            hit = refresh_sla_cache(tr)
        except Exception as exc:
            logger.warning("SLA fetch failed (cold): %s", exc)
            return {}

    if allow_refresh_if_stale:
        try:
            fetched_at = hit.get("fetched_at")
            if fetched_at:
                dt = datetime.fromisoformat(fetched_at)
                age = (_now_utc() - dt).total_seconds()
                if age > _STALE_AFTER_SECONDS:
                    hit = refresh_sla_cache(tr)
        except Exception as exc:
            logger.debug("SLA staleness check failed: %s", exc)

    return (hit or {}).get("by_dc", {}) or {}


def format_availability_tooltip(entry: Optional[dict]) -> str:
    if not entry:
        return "Availability: —"
    try:
        return f"Availability: %{format_pct(float(entry.get('availability_pct', 0.0)))}"
    except Exception:
        return "Availability: —"


def format_pct(value: float, max_decimals: int = 2) -> str:
    """
    Format percentage with up to `max_decimals` digits.
    Trailing zeros are removed (e.g., 100.00 -> 100, 99.40 -> 99.4).
    """
    try:
        s = f"{float(value):.{int(max_decimals)}f}"
    except Exception:
        return "—"
    s = s.rstrip("0").rstrip(".")
    return s

