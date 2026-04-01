from __future__ import annotations

from datetime import datetime, timedelta, timezone

PRESET_1_HOUR = "1h"
PRESET_1_DAY = "1d"
PRESET_7_DAYS = "7d"
PRESET_30_DAYS = "30d"
PRESET_CUSTOM = "custom"

DEFAULT_PRESET = PRESET_7_DAYS


def _today_utc():
    return datetime.now(timezone.utc).date()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def default_time_range():
    end = _today_utc()
    start = end - timedelta(days=6)
    return {"start": start.isoformat(), "end": end.isoformat(), "preset": DEFAULT_PRESET}


def preset_to_range(preset: str):
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


def _has_time_component(s: str) -> bool:
    s = s.strip()
    if "T" in s or " " in s[:13]:
        return True
    return len(s) > 10


def _parse_to_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def time_range_to_bounds(tr: dict | None):
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
