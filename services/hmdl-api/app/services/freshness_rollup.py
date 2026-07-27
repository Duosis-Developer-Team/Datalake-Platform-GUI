"""Collapse per-table freshness rows into per-collection-flow rows (pure, no DB).

A dead collector feeds N dead tables. Counting tables made one incident read as N
alerts — 10 for the Panduit PDU collector, 5 for the hypervisor performance
rollup. This module counts incidents instead.

Kept separate from app.db.queries.freshness because that module touches the
database; the rollup is pure and testable without one.
"""
from __future__ import annotations

from typing import Any

from app.services import automation_health as ah
from app.services import freshness_registry as reg

_FAMILY_PREFIX = "family:"

# Worst-first. `unknown` sits below the alerting states but above fresh only when
# it is ALL a flow has — a flow with one fresh member is working.
_ALERTING = ("dead", "stale")


def worst_status(statuses: list[str]) -> str:
    """The status a flow reports, given its members' statuses."""
    if not statuses:
        return "unknown"
    for s in _ALERTING:
        if s in statuses:
            return s
    if all(s == "unknown" for s in statuses):
        return "unknown"
    return "fresh"


def _label_for_flow(key: str) -> str:
    if key.startswith(_FAMILY_PREFIX):
        return key[len(_FAMILY_PREFIX):]
    flow = reg.FLOWS.get(key) or {}
    return flow.get("label") or key


def build_flow_rows(rows_by_flow: dict[str, list[dict]]) -> list[dict[str, Any]]:
    """One row per flow. Alerting flows sort first, then by key.

    `age_hours` is the age of the OLDEST alerting member, or None when the flow
    is not alerting — a healthy flow has no incident age to report.
    """
    out: list[dict[str, Any]] = []
    for key in sorted(rows_by_flow):
        sources = rows_by_flow[key]
        statuses = [s.get("status") for s in sources]
        status = worst_status([s for s in statuses if s])
        alerting_ages = [
            float(s["age_hours"])
            for s in sources
            if s.get("status") in _ALERTING and s.get("age_hours") is not None
        ]
        counts = ah.overall_status_counts([s for s in statuses if s])
        # The flow itself is one alert, not one per member.
        counts["alert"] = 1 if status in _ALERTING else 0
        out.append({
            "key": key,
            "label": _label_for_flow(key),
            "status": status,
            "age_hours": max(alerting_ages) if alerting_ages else None,
            "counts": counts,
            "sources": sources,
        })
    out.sort(key=lambda r: (0 if r["status"] in _ALERTING else 1, r["key"]))
    return out


def flow_key_for(table: str, family: str) -> str:
    """Flow key a monitored table rolls up under; falls back to its family."""
    return reg.flow_of(table) or f"{_FAMILY_PREFIX}{family}"


def flow_counts(flow_rows: list[dict]) -> dict[str, int]:
    """Status tally ACROSS flows — this is what the badge and banner show."""
    return ah.overall_status_counts([r["status"] for r in flow_rows])
