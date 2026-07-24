"""HMDL automation-health logic — freshness classification (pure, no DB).

Each HMDL automation writes a run-log/observability table in the `hmdl` schema.
The query layer (`app.db.queries.automation_health`) computes the age of the most
recent run; this module turns that age into a single ``status`` against per-automation
warn/dead thresholds, so the GUI can surface "is this automation running on schedule?".

Status ladder:
  fresh   — age < warn_hours (running on schedule)
  stale   — warn_hours <= age < dead_hours (a run was missed)
  dead    — age >= dead_hours (automation effectively stopped)
  unknown — no run recorded at all (age is None)
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

Status = Literal["fresh", "stale", "dead", "unknown"]


def age_in_hours(last: datetime | None, now: datetime) -> float | None:
    """Hours between ``last`` and ``now``; None when there is no last run."""
    if last is None:
        return None
    return (now - last).total_seconds() / 3600.0


def classify(age_hours: float | None, warn_hours: float, dead_hours: float) -> Status:
    """Collapse an age (in hours) into a freshness status against thresholds."""
    if age_hours is None:
        return "unknown"
    if age_hours >= dead_hours:
        return "dead"
    if age_hours >= warn_hours:
        return "stale"
    return "fresh"


def build_automation_row(
    *,
    key: str,
    label: str,
    cadence: str,
    last_run_at: datetime | None,
    now: datetime,
    warn_hours: float,
    dead_hours: float,
    extra: dict | None = None,
) -> dict:
    """Assemble one automation's health row (stable shape the GUI consumes)."""
    age = age_in_hours(last_run_at, now)
    return {
        "key": key,
        "label": label,
        "cadence": cadence,
        "last_run_at": last_run_at,
        "age_hours": age,
        "status": classify(age, warn_hours, dead_hours),
        "warn_hours": warn_hours,
        "dead_hours": dead_hours,
        "extra": extra or {},
    }


def overall_status_counts(statuses: list[str]) -> dict[str, int]:
    """Tally statuses; ``alert`` = stale + dead (what the banner/badge shows)."""
    counts = {
        "fresh": 0,
        "stale": 0,
        "dead": 0,
        "unknown": 0,
    }
    for s in statuses:
        if s in counts:
            counts[s] += 1
    counts["alert"] = counts["stale"] + counts["dead"]
    return counts
