"""Collector script smoke results (AWX collector-probe JT).

Source: hmdl.hmdl_datalake_collector_probe_log — one row per probe (collector
script) × target endpoint × run.

Coverage answers "did the data land"; this answers "which collector script fails
on which endpoint, and why". A Nutanix endpoint runs three scripts
(cluster/host/vm), so an endpoint can be half-broken in a way cluster-grain
coverage cannot express.

Probes are scheduled per DC, so each DC gets its own `run_id`: the fleet state is
the *latest row per (probe_id, target_host)*, never a single run.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.config import settings
from app.db import pool
from app.services import probe as svc

_SCHEMA = settings.hmdl_schema

# Runner-level rows (batch JSON unparsable) carry no endpoint; they are a probe
# infrastructure fault, not a collector verdict.
_RUNNER_TYPE = "batch"

_LATEST_CTE = f"""
WITH latest AS (
    SELECT DISTINCT ON (probe_id, target_host)
           probe_id, collector_type, bucket, dc_code, proxy_id, target_host,
           entity_name, success, reason, exit_code, duration_sec,
           stdout_bytes, stderr_bytes, stdout_head, stderr_head,
           run_id, awx_job_id, started_at, finished_at
    FROM {_SCHEMA}.hmdl_datalake_collector_probe_log
    WHERE NOT dry_run AND collector_type <> '{_RUNNER_TYPE}'
    ORDER BY probe_id, target_host, finished_at DESC
)
"""


def _fetch_latest(*, dc: str | None, probe_id: str | None) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if dc:
        clauses.append("UPPER(dc_code) = %s")
        params.append(dc)
    if probe_id:
        clauses.append("probe_id = %s")
        params.append(probe_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return pool.fetch_all(
        f"""
        {_LATEST_CTE}
        SELECT * FROM latest
        {where}
        ORDER BY probe_id, dc_code, target_host
        """,
        tuple(params) if params else None,
    )


def _fetch_runner_errors() -> list[dict[str, Any]]:
    return pool.fetch_all(
        f"""
        SELECT run_id, awx_job_id, dc_code, proxy_id, reason, finished_at
        FROM {_SCHEMA}.hmdl_datalake_collector_probe_log
        WHERE collector_type = %s AND NOT success
        ORDER BY finished_at DESC
        LIMIT 20
        """,
        (_RUNNER_TYPE,),
    )


def _endpoint_row(r: dict[str, Any]) -> dict[str, Any]:
    reason = str(r.get("reason") or "")
    success = bool(r.get("success"))
    return {
        "probe_id": str(r.get("probe_id") or ""),
        "collector_type": str(r.get("collector_type") or ""),
        "product": svc.probe_product(str(r.get("collector_type") or "")),
        "bucket": str(r.get("bucket") or ""),
        "dc": str(r.get("dc_code") or "").strip().upper() or "UNKNOWN",
        "proxy_id": str(r.get("proxy_id") or "") or None,
        "target_host": str(r.get("target_host") or ""),
        "entity_name": str(r.get("entity_name") or "") or None,
        "success": success,
        "reason": reason,
        "reason_category": svc.reason_category(reason, success),
        "exit_code": r.get("exit_code"),
        "duration_sec": float(r["duration_sec"]) if r.get("duration_sec") is not None else None,
        "stdout_bytes": r.get("stdout_bytes"),
        "stderr_bytes": r.get("stderr_bytes"),
        "stdout_head": (r.get("stdout_head") or "")[:400] or None,
        "stderr_head": (r.get("stderr_head") or "")[:400] or None,
        "run_id": str(r.get("run_id") or ""),
        "awx_job_id": str(r.get("awx_job_id") or "") or None,
        "finished_at": r.get("finished_at"),
    }


def _counts(rows: list[dict[str, Any]]) -> tuple[int, int]:
    ok = sum(1 for r in rows if r["success"])
    return ok, len(rows) - ok


def build_probe_health(*, dc: str | None = None, probe_id: str | None = None) -> dict[str, Any]:
    dc_norm = (dc or "").strip().upper() or None
    probe_norm = (probe_id or "").strip() or None

    rows = [_endpoint_row(r) for r in _fetch_latest(dc=dc_norm, probe_id=probe_norm)]

    by_script: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_cell: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_reason: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_script[r["probe_id"]].append(r)
        by_cell[(r["probe_id"], r["dc"])].append(r)
        if not r["success"]:
            by_reason[(r["reason_category"], r["reason"])].append(r)

    scripts = []
    for pid, script_rows in by_script.items():
        ok, fail = _counts(script_rows)
        first = script_rows[0]
        scripts.append(
            {
                "probe_id": pid,
                "collector_type": first["collector_type"],
                "product": first["product"],
                "bucket": first["bucket"],
                "endpoints": len(script_rows),
                "ok": ok,
                "fail": fail,
                "status": svc.script_status(ok, len(script_rows)),
                "last_probe_at": max(
                    (r["finished_at"] for r in script_rows if r["finished_at"]), default=None
                ),
            }
        )
    scripts.sort(key=lambda s: (s["product"], s["probe_id"]))

    matrix = []
    for (pid, dc_code), cell_rows in by_cell.items():
        ok, fail = _counts(cell_rows)
        matrix.append(
            {
                "probe_id": pid,
                "dc": dc_code,
                "ok": ok,
                "fail": fail,
                "total": len(cell_rows),
                "status": svc.script_status(ok, len(cell_rows)),
                "last_probe_at": max(
                    (r["finished_at"] for r in cell_rows if r["finished_at"]), default=None
                ),
            }
        )
    matrix.sort(key=lambda c: (c["probe_id"], c["dc"]))

    reasons = [
        {
            "category": category,
            "reason": reason,
            "count": len(reason_rows),
            "probe_ids": sorted({r["probe_id"] for r in reason_rows}),
            "dcs": sorted({r["dc"] for r in reason_rows}),
        }
        for (category, reason), reason_rows in by_reason.items()
    ]
    reasons.sort(key=lambda x: (-x["count"], x["category"], x["reason"]))

    ok_total, fail_total = _counts(rows)
    return {
        "summary": {
            "endpoints": len({r["target_host"] for r in rows}),
            "probes": len(rows),
            "ok": ok_total,
            "fail": fail_total,
            "scripts": len(by_script),
            "last_probe_at": max(
                (r["finished_at"] for r in rows if r["finished_at"]), default=None
            ),
        },
        "scripts": scripts,
        "matrix": matrix,
        "reasons": reasons,
        "items": rows,
        "runner_errors": [
            {
                "run_id": str(r.get("run_id") or ""),
                "awx_job_id": str(r.get("awx_job_id") or "") or None,
                "dc": str(r.get("dc_code") or "").strip().upper() or "UNKNOWN",
                "proxy_id": str(r.get("proxy_id") or "") or None,
                "reason": str(r.get("reason") or ""),
                "finished_at": r.get("finished_at"),
            }
            for r in _fetch_runner_errors()
        ],
        "dcs": sorted({r["dc"] for r in rows}),
        "dc_filter": dc_norm,
        "probe_filter": probe_norm,
    }


def fetch_probe_rollup_by_host() -> dict[str, dict[str, Any]]:
    """`target_host` → script pass rate, for badges on Coverage parent rows."""
    rows = pool.fetch_all(
        f"""
        {_LATEST_CTE}
        SELECT target_host,
               count(*) AS total,
               count(*) FILTER (WHERE success) AS ok,
               max(finished_at) AS last_probe_at,
               string_agg(DISTINCT reason, ' | ') FILTER (WHERE NOT success) AS reasons
        FROM latest GROUP BY target_host
        """
    )
    rollup: dict[str, dict[str, Any]] = {}
    for r in rows:
        host = str(r.get("target_host") or "").strip()
        if not host:
            continue
        total = int(r.get("total") or 0)
        ok = int(r.get("ok") or 0)
        rollup[host] = {
            "probe_total": total,
            "probe_ok": ok,
            "probe_status": svc.script_status(ok, total),
            "probe_reasons": str(r.get("reasons") or "") or None,
            "probe_checked_at": r.get("last_probe_at"),
        }
    return rollup
