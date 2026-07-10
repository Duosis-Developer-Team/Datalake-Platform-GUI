"""Pure availability-summary helpers."""
from __future__ import annotations

from src.utils.availability_summary import summarize_outages, format_downtime


def test_summarize_counts_split_longest_locations():
    svc = [
        {"type": "Plansız", "duration_minutes": 60, "group_name": "DC13"},
        {"type": "Planlı", "duration_minutes": 30, "group_name": "DC13"},
    ]
    vm = [{"type": "Plansız", "duration_minutes": 274, "cluster": "DC16-CLS", "vm_name": "web-01"}]
    s = summarize_outages(svc, vm)
    assert s["total_outages"] == 3
    assert s["service_outages"] == 2
    assert s["vm_outages"] == 1
    assert s["total_downtime_min"] == 364
    assert s["unplanned_count"] == 2
    assert s["planned_count"] == 1
    assert s["longest"]["duration_minutes"] == 274
    assert s["locations"] == ["DC13", "DC16-CLS"]


def test_summarize_empty_and_defensive():
    s = summarize_outages([], [])
    assert s["total_outages"] == 0
    assert s["longest"] is None
    assert s["locations"] == []
    s2 = summarize_outages([None, {"duration_minutes": "x", "type": ""}], [])
    assert s2["total_outages"] == 1
    assert s2["total_downtime_min"] == 0
    assert s2["planned_count"] == 0
    assert s2["unplanned_count"] == 0


def test_format_downtime_units():
    assert format_downtime(45) == "45 dk"
    assert format_downtime(0) == "0 dk"
    assert format_downtime(90) == "1,5 sa"
    assert format_downtime(2880) == "2,0 gün"
    assert format_downtime(None) == "-"
    assert format_downtime("x") == "-"
