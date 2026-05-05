from __future__ import annotations
# Time range utilities for reporting.
# All screens use a single time range (presets or custom) passed to queries.

from datetime import date, datetime, timedelta, timezone

# Preset keys for UI
PRESET_1_HOUR = "1h"
PRESET_1_DAY = "1d"
PRESET_7_DAYS = "7d"
PRESET_30_DAYS = "30d"
PRESET_CUSTOM = "custom"

DEFAULT_PRESET = PRESET_7_DAYS

# Annual availability report: first selectable calendar year
MIN_REPORT_YEAR = 2022


def _today_utc():
    return datetime.now(timezone.utc).date()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def default_time_range():
    """Return default range as dict: last 7 days (date strings YYYY-MM-DD)."""
    end = _today_utc()
    start = end - timedelta(days=6)
    return {"start": start.isoformat(), "end": end.isoformat(), "preset": DEFAULT_PRESET}


def preset_to_range(preset: str):
    """Compute start/end for a preset key. 1h uses full ISO datetimes; others use date strings."""
    if preset == PRESET_1_HOUR:
        end = _now_utc()
        start = end - timedelta(hours=1)
        return {
            "start": start.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            "end": end.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            "preset": PRESET_1_HOUR,
        }
    end = _today_utc()
    if preset == PRESET_1_DAY:
        start = end
    elif preset == PRESET_7_DAYS:
        start = end - timedelta(days=6)
    elif preset == PRESET_30_DAYS:
        start = end - timedelta(days=29)
    else:
        start = end - timedelta(days=6)
    return {"start": start.isoformat(), "end": end.isoformat(), "preset": preset}


def previous_month_range():
    """
    Return time range dict for the previous calendar month (e.g. if today is Feb 2025, returns Jan 1–Jan 31).
    Used so cache always holds last week, last month, and previous month data.
    """
    end = _today_utc()
    first_this_month = end.replace(day=1)
    last_prev = first_this_month - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return {
        "start": first_prev.isoformat(),
        "end": last_prev.isoformat(),
        "preset": "previous_month",
    }


def calendar_year_range(year: int) -> dict:
    """
    Time range for calendar year `year` (UTC dates): Jan 1 … Dec 31, capped by today.

    - If `year` is the current year, `end` is today (inclusive of partial-year data).
    - Clamps `year` to [MIN_REPORT_YEAR, current calendar year].
    """
    today = _today_utc()
    cy = int(today.year)
    y = int(year)
    if y < MIN_REPORT_YEAR:
        y = MIN_REPORT_YEAR
    if y > cy:
        y = cy
    start_d = date(y, 1, 1)
    end_dec = date(y, 12, 31)
    end_d = min(end_dec, today)
    return {
        "start": start_d.isoformat(),
        "end": end_d.isoformat(),
        "preset": f"year_{y}",
    }


def cache_time_ranges():
    """
    Return the three time ranges that must always be present in cache:
    - Last 7 days
    - Last 30 days
    - Previous calendar month (month before current)
    Init and scheduler use this to warm/refresh cache for these ranges.
    """
    end = _today_utc()
    return [
        {"start": (end - timedelta(days=6)).isoformat(), "end": end.isoformat(), "preset": PRESET_7_DAYS},
        {"start": (end - timedelta(days=29)).isoformat(), "end": end.isoformat(), "preset": PRESET_30_DAYS},
        previous_month_range(),
    ]


def _has_time_component(s: str) -> bool:
    """True if string encodes a time (not date-only YYYY-MM-DD)."""
    s = s.strip()
    if "T" in s or " " in s[:13]:
        return True
    return len(s) > 10


def _parse_to_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def time_range_to_bounds(tr: dict | None):
    """
    Convert UI time range dict to (start_ts, end_ts) for SQL (UTC).

    - Date-only start/end (YYYY-MM-DD): start 00:00:00 UTC, end 23:59:59 UTC that day.
    - ISO datetimes (custom / 1h): exact bounds from strings.
    """
    if not tr or "start" not in tr or "end" not in tr:
        tr = default_time_range()
    start_s = str(tr["start"]).replace("Z", "+00:00")
    end_s = str(tr["end"]).replace("Z", "+00:00")
    try:
        start_dt = _parse_to_utc_aware(datetime.fromisoformat(start_s))
        end_dt = _parse_to_utc_aware(datetime.fromisoformat(end_s))
    except (ValueError, TypeError):
        tr = default_time_range()
        start_s = str(tr["start"]).replace("Z", "+00:00")
        end_s = str(tr["end"]).replace("Z", "+00:00")
        start_dt = _parse_to_utc_aware(datetime.fromisoformat(start_s))
        end_dt = _parse_to_utc_aware(datetime.fromisoformat(end_s))

    if not _has_time_component(str(tr["start"])):
        start_dt = datetime(
            start_dt.year, start_dt.month, start_dt.day, 0, 0, 0, tzinfo=timezone.utc
        )
    if not _has_time_component(str(tr["end"])):
        end_dt = datetime(
            end_dt.year, end_dt.month, end_dt.day, 23, 59, 59, tzinfo=timezone.utc
        )
    return (start_dt, end_dt)
