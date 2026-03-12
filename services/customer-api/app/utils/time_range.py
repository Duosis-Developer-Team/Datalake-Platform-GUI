from __future__ import annotations

from datetime import datetime, timedelta, timezone

PRESET_1_DAY = "1d"
PRESET_7_DAYS = "7d"
PRESET_30_DAYS = "30d"
PRESET_CUSTOM = "custom"

DEFAULT_PRESET = PRESET_7_DAYS


def _today_utc():
    return datetime.now(timezone.utc).date()


def default_time_range():
    end = _today_utc()
    start = end - timedelta(days=6)
    return {"start": start.isoformat(), "end": end.isoformat(), "preset": DEFAULT_PRESET}


def preset_to_range(preset: str):
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
    end = _today_utc()
    first_this_month = end.replace(day=1)
    last_prev = first_this_month - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return {
        "start": first_prev.isoformat(),
        "end": last_prev.isoformat(),
        "preset": "previous_month",
    }


def cache_time_ranges():
    end = _today_utc()
    return [
        {"start": (end - timedelta(days=6)).isoformat(), "end": end.isoformat(), "preset": PRESET_7_DAYS},
        {"start": (end - timedelta(days=29)).isoformat(), "end": end.isoformat(), "preset": PRESET_30_DAYS},
        previous_month_range(),
    ]


def time_range_to_bounds(tr: dict | None):
    if not tr or "start" not in tr or "end" not in tr:
        tr = default_time_range()
    try:
        start_d = datetime.fromisoformat(tr["start"].replace("Z", "+00:00")).date()
        end_d = datetime.fromisoformat(tr["end"].replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        tr = default_time_range()
        start_d = datetime.fromisoformat(tr["start"]).date()
        end_d = datetime.fromisoformat(tr["end"]).date()
    start_ts = datetime(start_d.year, start_d.month, start_d.day, 0, 0, 0, tzinfo=timezone.utc)
    end_ts = datetime(end_d.year, end_d.month, end_d.day, 23, 59, 59, tzinfo=timezone.utc)
    return (start_ts, end_ts)
