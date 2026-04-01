"""Unit tests for src.utils.time_range."""

from datetime import datetime, timedelta, timezone

import pytest

from src.utils import time_range as tr


def test_preset_1h_returns_datetime_strings_and_preset_key():
    out = tr.preset_to_range(tr.PRESET_1_HOUR)
    assert out["preset"] == tr.PRESET_1_HOUR
    assert "T" in out["start"]
    assert "T" in out["end"]
    assert out["start"].endswith("Z")
    assert out["end"].endswith("Z")


def test_time_range_to_bounds_date_only_uses_day_edges():
    start_ts, end_ts = tr.time_range_to_bounds(
        {"start": "2025-06-01", "end": "2025-06-02", "preset": "custom"}
    )
    assert start_ts == datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert end_ts == datetime(2025, 6, 2, 23, 59, 59, tzinfo=timezone.utc)


def test_time_range_to_bounds_iso_respects_time():
    start_ts, end_ts = tr.time_range_to_bounds(
        {
            "start": "2025-06-01T10:00:00Z",
            "end": "2025-06-01T11:30:00Z",
            "preset": "custom",
        }
    )
    assert start_ts.hour == 10
    assert end_ts.hour == 11
    assert end_ts.minute == 30


def test_time_range_to_bounds_1h_span_under_one_day():
    now = datetime(2025, 8, 15, 12, 0, 0, tzinfo=timezone.utc)
    start = now - timedelta(hours=1)
    tr_dict = {
        "start": start.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        "end": now.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        "preset": tr.PRESET_1_HOUR,
    }
    s, e = tr.time_range_to_bounds(tr_dict)
    assert (e - s).total_seconds() == pytest.approx(3600.0, rel=0.01)
