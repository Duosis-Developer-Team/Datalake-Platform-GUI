import pytest
from datetime import date, timedelta, timezone

from app.utils.time_range import (
    default_time_range,
    preset_to_range,
    previous_month_range,
    cache_time_ranges,
    time_range_to_bounds,
    PRESET_1_DAY,
    PRESET_7_DAYS,
    PRESET_30_DAYS,
)


def test_default_time_range_returns_seven_day_window():
    tr = default_time_range()
    start = date.fromisoformat(tr["start"])
    end = date.fromisoformat(tr["end"])
    assert (end - start).days == 6


def test_default_time_range_end_is_today():
    tr = default_time_range()
    from datetime import datetime
    today = datetime.now(timezone.utc).date().isoformat()
    assert tr["end"] == today


def test_default_time_range_preset_is_7d():
    tr = default_time_range()
    assert tr["preset"] == PRESET_7_DAYS


def test_preset_to_range_1d_returns_same_start_and_end():
    tr = preset_to_range(PRESET_1_DAY)
    assert tr["start"] == tr["end"]


def test_preset_to_range_7d_returns_six_day_span():
    tr = preset_to_range(PRESET_7_DAYS)
    start = date.fromisoformat(tr["start"])
    end = date.fromisoformat(tr["end"])
    assert (end - start).days == 6


def test_preset_to_range_30d_returns_29_day_span():
    tr = preset_to_range(PRESET_30_DAYS)
    start = date.fromisoformat(tr["start"])
    end = date.fromisoformat(tr["end"])
    assert (end - start).days == 29


def test_preset_to_range_unknown_falls_back_to_7d():
    tr = preset_to_range("unknown_preset")
    start = date.fromisoformat(tr["start"])
    end = date.fromisoformat(tr["end"])
    assert (end - start).days == 6


def test_previous_month_range_returns_full_calendar_month():
    tr = previous_month_range()
    start = date.fromisoformat(tr["start"])
    end = date.fromisoformat(tr["end"])
    assert start.day == 1
    assert end.day >= 28


def test_previous_month_range_end_is_last_day_of_previous_month():
    tr = previous_month_range()
    end = date.fromisoformat(tr["end"])
    from datetime import datetime
    today = datetime.now(timezone.utc).date()
    first_this_month = today.replace(day=1)
    expected_end = first_this_month - timedelta(days=1)
    assert end == expected_end


def test_cache_time_ranges_returns_three_ranges():
    ranges = cache_time_ranges()
    assert len(ranges) == 3


def test_cache_time_ranges_first_is_7d():
    ranges = cache_time_ranges()
    assert ranges[0]["preset"] == PRESET_7_DAYS


def test_cache_time_ranges_second_is_30d():
    ranges = cache_time_ranges()
    assert ranges[1]["preset"] == PRESET_30_DAYS


def test_time_range_to_bounds_returns_midnight_to_end_of_day():
    tr = {"start": "2026-03-01", "end": "2026-03-07"}
    start_ts, end_ts = time_range_to_bounds(tr)
    assert start_ts.hour == 0
    assert start_ts.minute == 0
    assert end_ts.hour == 23
    assert end_ts.second == 59


def test_time_range_to_bounds_with_none_falls_back_to_default():
    start_ts, end_ts = time_range_to_bounds(None)
    assert start_ts is not None
    assert end_ts is not None


def test_time_range_to_bounds_with_invalid_dates_falls_back():
    tr = {"start": "not-a-date", "end": "also-not"}
    start_ts, end_ts = time_range_to_bounds(tr)
    assert start_ts is not None


def test_time_range_to_bounds_with_z_suffix_parses_correctly():
    tr = {"start": "2026-03-01T00:00:00Z", "end": "2026-03-07T00:00:00Z"}
    start_ts, end_ts = time_range_to_bounds(tr)
    assert start_ts.date().isoformat() == "2026-03-01"
