"""Evidence evaluator — technical (LLM-free) assessment of tool results.

Before the model writes a word, this layer checks whether the gathered evidence
is sufficient and recommends *which allowlisted tool* to run next (if any). It
never invents tools: follow-ups are registry tool names with bound args.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from app.config import settings
from app.services.planner import IntentPlan
from app.services.tool_registry import ToolResult, get_tool

logger = logging.getLogger("chatbot-api.evaluator")

# Entity -> (top, latest, summary) registry tool names.
_ENTITY_TOOLS = {
    "vm": ("get_dc_vm_cpu_top", "get_dc_vm_cpu_latest", "get_dc_vm_cpu_summary"),
    "host": ("get_dc_host_cpu_top", "get_dc_host_cpu_latest", "get_dc_host_cpu_summary"),
}


@dataclass
class ToolRequest:
    tool: str
    args: dict[str, Any]


@dataclass
class EvidenceEvaluation:
    enough_for_answer: bool = False
    confidence: str = "medium"  # high | medium | low
    missing_fields: list[str] = field(default_factory=list)
    recommended_followup_tools: list[ToolRequest] = field(default_factory=list)
    data_quality_warnings: list[str] = field(default_factory=list)
    primary_rows: list[dict[str, Any]] = field(default_factory=list)
    primary_source: Optional[str] = None


def _rows_of(result: ToolResult) -> list[dict[str, Any]]:
    summ = result.summary if isinstance(result.summary, dict) else {}
    rows = summ.get("rows")
    return rows if isinstance(rows, list) else []


def _primary(results: list[ToolResult]) -> tuple[list[dict], Optional[str], Optional[str]]:
    """Return (rows, source, tool_name) from the best per-entity data result.

    Prefers a top/latest result (per-entity rows) over a summary (per-source).
    """
    best = None
    for r in results:
        if r.status != "success" or not (r.source or "").startswith("postgres"):
            continue
        if "_summary" in r.name:  # per-source aggregate, not per-entity rows
            continue
        rows = _rows_of(r)
        if not rows:
            continue
        if "_top" in r.name or "variability" in r.name:
            k = 0
        elif "_latest" in r.name:
            k = 1
        else:
            k = 2
        if best is None or k < best[0]:
            best = (k, rows, r.source, r.name)
    if best:
        return best[1], best[2], best[3]
    return [], None, None


def _num(row: dict, *keys: str) -> Optional[float]:
    for k in keys:
        v = row.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _freshness(rows: list[dict]) -> tuple[bool, Optional[str], Optional[float]]:
    """Return (is_stale, latest_str, age_hours) using the rows' collection time."""
    times = []
    for r in rows:
        ts = r.get("last_collection_time") or r.get("collection_time")
        if isinstance(ts, str) and ts:
            times.append(ts)
    if not times:
        return False, None, None
    latest = max(times)
    try:
        dt = datetime.strptime(latest[:16], "%Y-%m-%d %H:%M")
        age_h = (datetime.now() - dt).total_seconds() / 3600.0
        return age_h > settings.chatbot_stale_hours, latest, round(age_h, 1)
    except Exception:  # pragma: no cover - defensive parse
        return False, latest, None


def _concentrated(rows: list[dict], top_n: int = 5) -> Optional[str]:
    """If the top entities cluster on few hosts, return a short note."""
    hosts = [r.get("host_name") for r in rows[:top_n] if r.get("host_name")]
    if len(hosts) >= 3 and len(set(hosts)) <= max(1, len(hosts) // 2):
        return f"top {len(hosts)} -> {len(set(hosts))} distinct host(s)"
    return None


def _followup_args(plan: IntentPlan) -> dict[str, Any]:
    return {"dc_code": plan.dc_code, "days": plan.days, "limit": plan.limit}


def evaluate(plan: IntentPlan, results: list[ToolResult]) -> EvidenceEvaluation:
    run = {r.name for r in results}
    rows, source, primary_tool = _primary(results)
    ev = EvidenceEvaluation(primary_rows=rows, primary_source=source)

    # cpu_usage profile drives the host/vm fallback + concentration follow-ups.
    cpu_usage = plan.analysis_profile == "cpu_usage"
    tools = _ENTITY_TOOLS.get(plan.entity_type) if cpu_usage else None

    # --- empty result -> deterministic fallbacks (latest, then summary) ----- #
    if tools and not rows:
        top, latest, summ = tools
        if latest not in run:
            ev.recommended_followup_tools = [ToolRequest(latest, _followup_args(plan))]
            ev.data_quality_warnings.append("no rows from the primary query; trying latest snapshot")
            return ev
        if summ not in run:
            ev.recommended_followup_tools = [ToolRequest(summ, _followup_args(plan))]
            ev.data_quality_warnings.append("no rows; trying per-source summary")
            return ev
        ev.enough_for_answer = True
        ev.confidence = "low"
        ev.data_quality_warnings.append("no rows after all attempted sources")
        return ev

    if not rows:
        # Non host/vm entity (or no data tool) — single-pass-style sufficiency.
        ev.enough_for_answer = True
        ev.confidence = "medium"
        return ev

    # --- data quality on the rows ------------------------------------------ #
    if cpu_usage and plan.entity_type == "vm":
        ev.data_quality_warnings.append(
            "VMware VM CPU% bu veri setinde yok (kapasite kolonu boş); Nutanix + IBM gösteriliyor."
        )
    if cpu_usage:
        if not any(_num(r, "cpu_pct_avg", "cpu_pct") is not None for r in rows):
            ev.missing_fields.append("cpu_pct_avg")
        if not any(_num(r, "cpu_pct_max") is not None for r in rows):
            ev.missing_fields.append("cpu_pct_max")

    samples = [s for s in (_num(r, "sample_count") for r in rows) if s is not None]
    if samples and (sum(samples) / len(samples)) < 5:
        ev.confidence = "medium"
        ev.data_quality_warnings.append("low sample_count per entity")

    is_stale, latest_str, age_h = _freshness(rows)
    if is_stale and latest_str:
        ev.data_quality_warnings.append(
            f"data is stale (latest {latest_str}, ~{age_h}h old)"
        )

    # --- follow-up: summary for source breakdown / totals ------------------- #
    if tools and plan.needs_analysis:
        summ = tools[2]
        if summ not in run and get_tool(summ) is not None:
            ev.recommended_followup_tools = [ToolRequest(summ, _followup_args(plan))]
            return ev

    # --- follow-up: host context when VMs concentrate on few hosts ---------- #
    if plan.entity_type == "vm":
        note = _concentrated(rows)
        if note and "get_dc_host_cpu_summary" not in run and get_tool("get_dc_host_cpu_summary"):
            ev.data_quality_warnings.append(f"host concentration ({note}) — pulling host context")
            ev.recommended_followup_tools = [
                ToolRequest("get_dc_host_cpu_summary", {"dc_code": plan.dc_code})
            ]
            return ev

    # Enough evidence gathered.
    ev.enough_for_answer = True
    if not ev.data_quality_warnings and ev.confidence != "medium":
        ev.confidence = "high"
    return ev
