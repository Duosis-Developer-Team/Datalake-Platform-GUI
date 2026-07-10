"""Availability tab renders summary tiles + readable outage lists."""
from __future__ import annotations

from src.pages.customer_view import _tab_customer_availability
from src.utils.availability_summary import format_downtime


def _text_blob(component) -> str:
    out = []

    def walk(c):
        if isinstance(c, (str, int, float)):
            out.append(str(c))
            return
        title = getattr(c, "title", None)
        if isinstance(title, str):
            out.append(title)
        children = getattr(c, "children", None)
        if children is None:
            return
        if not isinstance(children, (list, tuple)):
            children = [children]
        for ch in children:
            walk(ch)

    walk(component)
    return " ".join(out)


def _avail_with_outages():
    return {
        "customer_id": 1504,
        "customer_ids": [1504],
        "service_downtimes": [
            {"category": "Klasik Mimari DR", "group_name": "Equinix IL2 - DC13", "type": "Plansız",
             "start_time": "2026-06-30T18:31", "end_time": "2026-06-30T19:31",
             "duration_minutes": 60, "service_impact": "Degraded"},
        ],
        "vm_downtimes": [
            {"vm_name": "web-01", "cluster": "DC16-G2-CLS-HYBRID", "host": "g2hv2dc16.blt.vc",
             "type": "Plansız", "start_time": "2026-01-23T10:00", "end_time": "2026-01-23T14:34",
             "duration_minutes": 274, "category": "DC Elektrik Altyapısı"},
        ],
        "vm_outage_counts": {"web-01": 1},
    }


def test_tab_shows_tiles_and_readable_rows():
    blob = _text_blob(_tab_customer_availability(_avail_with_outages()))
    # summary tiles
    assert "Total outages" in blob
    assert "Total downtime" in blob
    # total downtime 60+274=334 min rendered via format_downtime
    assert format_downtime(334) in blob
    # readable rows: vm identity + cluster + type badge + formatted duration
    assert "web-01" in blob
    assert "DC16-G2-CLS-HYBRID" in blob
    assert "Plansız" in blob
    assert format_downtime(274) in blob


def test_tab_empty_state():
    avail = {"customer_id": 1, "customer_ids": [1], "service_downtimes": [],
             "vm_downtimes": [], "vm_outage_counts": {}}
    blob = _text_blob(_tab_customer_availability(avail))
    assert "No outages in period" in blob
    assert "Total outages" in blob  # tiles still render (all zero)
