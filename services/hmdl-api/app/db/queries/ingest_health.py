"""Read-only ingest freshness report (TASK-M1).

Source: hmdl.hmdl_datalake_coverage_endpoint
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.db import pool

_SCHEMA = settings.hmdl_schema

_VERDICTS = (
    "healthy",
    "no_network",
    "network_ok_no_data",
    "stale",
    "unmatched",
)


def _empty_summary() -> dict[str, int]:
    return {v: 0 for v in _VERDICTS} | {"total": 0}


def _tally(summary: dict[str, int], verdict: str) -> None:
    summary["total"] += 1
    if verdict in summary:
        summary[verdict] += 1


def _fetch_rows(
    *,
    dc: str | None,
    collector_type: str | None,
    verdict: str | None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if dc:
        clauses.append("UPPER(dc_code) = %s")
        params.append(dc.strip().upper())
    if collector_type:
        clauses.append("collector_type = %s")
        params.append(collector_type.strip())
    if verdict:
        clauses.append("verdict = %s")
        params.append(verdict.strip())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return pool.fetch_all(
        f"""
        SELECT
            endpoint_ip, collector_type, proxy_id, entity_name, dc_code, tenant_name,
            network_access, check_status, last_check_at,
            match_mode, match_key, bridge_via, bridge_resolved,
            last_ingest_at, ingest_age_hours, ingest_stale, stale_after_hours,
            verdict, detail_message, checked_at
        FROM {_SCHEMA}.hmdl_datalake_coverage_endpoint
        {where}
        ORDER BY dc_code, collector_type, endpoint_ip, proxy_id
        """,
        tuple(params) if params else None,
    )


def build_ingest_health(
    *,
    dc: str | None = None,
    collector_type: str | None = None,
    verdict: str | None = None,
) -> dict[str, Any]:
    dc_norm = (dc or "").strip().upper() or None
    type_norm = (collector_type or "").strip() or None
    verdict_norm = (verdict or "").strip() or None

    rows = _fetch_rows(dc=dc_norm, collector_type=type_norm, verdict=verdict_norm)
    summary = _empty_summary()
    items: list[dict[str, Any]] = []
    for r in rows:
        v = r.get("verdict") or "unmatched"
        _tally(summary, v)
        items.append(
            {
                "endpoint_ip": r.get("endpoint_ip"),
                "collector_type": r.get("collector_type"),
                "proxy_id": r.get("proxy_id") or "",
                "entity_name": r.get("entity_name"),
                "dc_code": r.get("dc_code"),
                "tenant_name": r.get("tenant_name"),
                "network_access": bool(r.get("network_access")),
                "check_status": r.get("check_status"),
                "last_check_at": r.get("last_check_at"),
                "match_mode": r.get("match_mode"),
                "match_key": r.get("match_key"),
                "bridge_via": r.get("bridge_via"),
                "bridge_resolved": r.get("bridge_resolved"),
                "last_ingest_at": r.get("last_ingest_at"),
                "ingest_age_hours": float(r["ingest_age_hours"])
                if r.get("ingest_age_hours") is not None
                else None,
                "ingest_stale": bool(r.get("ingest_stale")),
                "stale_after_hours": int(r.get("stale_after_hours") or 6),
                "verdict": v,
                "detail_message": r.get("detail_message") or "",
                "checked_at": r.get("checked_at"),
            }
        )

    return {
        "summary": summary,
        "items": items,
        "dc_filter": dc_norm,
        "collector_type_filter": type_norm,
        "verdict_filter": verdict_norm,
    }
