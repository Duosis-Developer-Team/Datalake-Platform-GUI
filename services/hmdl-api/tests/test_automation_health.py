"""Unit tests for HMDL automation-health classification logic (pure, no DB)."""

from datetime import datetime, timezone

from app.services.automation_health import (
    age_in_hours,
    build_automation_row,
    classify,
    overall_status_counts,
)


def test_classify_fresh_below_warn():
    assert classify(5.0, warn_hours=12, dead_hours=24) == "fresh"


def test_classify_stale_between_warn_and_dead():
    assert classify(18.0, warn_hours=12, dead_hours=24) == "stale"


def test_classify_dead_at_or_above_dead():
    assert classify(24.0, warn_hours=12, dead_hours=24) == "dead"
    assert classify(100.0, warn_hours=12, dead_hours=24) == "dead"


def test_classify_boundary_warn_counts_as_stale():
    # Exactly at the warn threshold is no longer fresh.
    assert classify(12.0, warn_hours=12, dead_hours=24) == "stale"


def test_classify_unknown_when_age_none():
    assert classify(None, warn_hours=12, dead_hours=24) == "unknown"


def test_age_in_hours_computes_delta():
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    last = datetime(2026, 7, 23, 6, 0, tzinfo=timezone.utc)
    assert age_in_hours(last, now) == 6.0


def test_age_in_hours_none_when_no_last():
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    assert age_in_hours(None, now) is None


def test_build_automation_row_sets_status_and_age():
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    last = datetime(2026, 7, 21, 2, 0, tzinfo=timezone.utc)  # 58h ago
    row = build_automation_row(
        key="collector_sync",
        label="Collector Sync",
        cadence="günlük 02:00",
        last_run_at=last,
        now=now,
        warn_hours=26,
        dead_hours=50,
        extra={"proxy_coverage": "4/23"},
    )
    assert row["key"] == "collector_sync"
    assert row["label"] == "Collector Sync"
    assert row["age_hours"] == 58.0
    assert row["status"] == "dead"
    assert row["last_run_at"] == last
    assert row["extra"] == {"proxy_coverage": "4/23"}


def test_build_automation_row_unknown_when_no_run():
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    row = build_automation_row(
        key="x", label="X", cadence="", last_run_at=None, now=now,
        warn_hours=1, dead_hours=2,
    )
    assert row["status"] == "unknown"
    assert row["age_hours"] is None
    assert row["extra"] == {}


def test_overall_status_counts_alert_is_stale_plus_dead():
    counts = overall_status_counts(["fresh", "stale", "dead", "dead", "unknown"])
    assert counts["fresh"] == 1
    assert counts["stale"] == 1
    assert counts["dead"] == 2
    assert counts["unknown"] == 1
    assert counts["alert"] == 3  # stale + dead
