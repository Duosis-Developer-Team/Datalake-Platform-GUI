"""Discover collected data tables and compute their freshness, grouped by family.

Expensive (max() over ~120 tables) — call ONLY from the background refresher
(app.services.freshness_snapshot), never on the request path.
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.db import pool
from app.services import automation_health as ah
from app.services import freshness_registry as reg
from app.services import freshness_rollup as roll


def discover_specs() -> list[dict[str, Any]]:
    """Public base tables that carry a freshness column, minus excluded ones,
    resolved to monitoring specs (table/column/label/family/thresholds)."""
    rows = pool.fetch_all(
        """
        SELECT c.table_name, array_agg(c.column_name::text) AS cols
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema AND t.table_name = c.table_name
         AND t.table_type = 'BASE TABLE'
        WHERE c.table_schema = 'public'
          AND c.column_name = ANY(%s)
        GROUP BY c.table_name
        ORDER BY c.table_name
        """,
        (reg.FRESHNESS_COLUMNS,),
    )
    specs: list[dict[str, Any]] = []
    for r in rows or []:
        spec = reg.resolve(
            r["table_name"], list(r.get("cols") or []),
            default_warn=settings.ah_data_warn_hours,
            default_dead=settings.ah_data_dead_hours,
        )
        if spec:
            specs.append(spec)
    return specs


def _age_hours(table: str, col: str) -> float | None:
    r = pool.fetch_one(
        f"SELECT EXTRACT(EPOCH FROM (now() - max({col}::timestamptz)))/3600.0 AS age_hours "
        f"FROM public.{table}"
    )
    if not r or r.get("age_hours") is None:
        return None
    age = float(r["age_hours"])
    return 0.0 if age < 0 else age  # naive-tz skew reads slightly ahead of now()


def compute_freshness() -> dict[str, Any]:
    """{families, flows, unmonitored, missing, counts}.

    `families` is the per-table view kept for drill-down. `flows` is what the page
    and the badge read: one row per collection flow, so a dead collector is one
    alert however many tables it feeds. `counts` is tallied over FLOWS — tallying
    tables is what produced 40 alerts for 2 incidents.

    Tables no service queries land in `unmonitored`: still reported, never counted.
    `missing` names MONITORED tables discovery did not return — a renamed or
    dropped table must be visible, or the curated set rots silently.
    """
    families: dict[str, list[dict]] = {}
    by_flow: dict[str, list[dict]] = {}
    unmonitored: list[dict] = []
    seen: set[str] = set()

    for spec in discover_specs():
        seen.add(spec["table"])
        try:
            age = _age_hours(spec["table"], spec["column"])
        except Exception:  # noqa: BLE001 — one bad table never breaks the sweep
            age = None
        row = ah.build_data_source_row(
            key=spec["table"], label=spec["label"], table=spec["table"],
            last_data_at=None, age_hours=age,
            warn_hours=spec["warn_hours"], dead_hours=spec["dead_hours"],
        )
        # Absent key defaults to MONITORED. resolve() always sets it, so a spec
        # without it is a bug — and the safe direction for a bug in a monitoring
        # system is to keep alerting, not to fall silent across the board.
        if not spec.get("monitored", True):
            unmonitored.append(row)
            continue
        families.setdefault(spec["family"], []).append(row)
        by_flow.setdefault(
            roll.flow_key_for(spec["table"], spec["family"]), []
        ).append(row)

    fam_list = [
        {
            "family": fam,
            "counts": ah.overall_status_counts([s["status"] for s in families[fam]]),
            "sources": families[fam],
        }
        for fam in sorted(families)
    ]
    flows = roll.build_flow_rows(by_flow)
    return {
        "families": fam_list,
        "flows": flows,
        "unmonitored": sorted(unmonitored, key=lambda r: r["key"]),
        "missing": sorted(reg.MONITORED - seen),
        "counts": roll.flow_counts(flows),
    }
