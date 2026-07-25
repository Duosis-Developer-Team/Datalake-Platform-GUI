"""Data-collection freshness: _data_sources() reads the newest row age of each
collected DATA table (public schema) and classifies it — separate from the AWX
job-log automations, so a dead data flow (e.g. datastore stale 10 days) is caught
even when the collector job itself reports 'fresh'."""
from datetime import datetime, timezone
from unittest.mock import patch

from app.db.queries import automation_health as q


def test_data_sources_builds_rows_and_counts():
    fresh = {"ts": datetime(2026, 7, 26, tzinfo=timezone.utc), "age_hours": 1.0}
    dead = {"ts": datetime(2026, 7, 16, tzinfo=timezone.utc), "age_hours": 240.0}
    # one fetch_one per source, in _DATA_SOURCES order
    responses = [fresh, fresh, fresh, dead, dead, fresh]

    with patch.object(q.pool, "fetch_one", side_effect=responses):
        rows, counts = q._data_sources()

    assert len(rows) == 6
    by_key = {r["key"]: r for r in rows}
    assert by_key["vmware_datastore_metrics"]["status"] == "dead"
    assert by_key["vmware_clusters"]["status"] == "fresh"
    assert counts["dead"] == 2
    assert counts["alert"] == 2          # 2 dead datastore flows surface as alerts
    # each row carries its source table for the UI
    assert by_key["vmware_datastore_metrics"]["cadence"] == "public.raw_vmware_datastore_metrics_agg"


def test_data_sources_unknown_when_table_empty():
    empty = {"ts": None, "age_hours": None}
    with patch.object(q.pool, "fetch_one", side_effect=[empty] * 6):
        rows, counts = q._data_sources()
    assert all(r["status"] == "unknown" for r in rows)
    assert counts["alert"] == 0
