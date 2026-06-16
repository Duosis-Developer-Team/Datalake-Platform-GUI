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

from app.catalog import domain_catalog
from app.config import settings
from app.services import datacenter_ranking
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
    return {
        "dc_code": plan.dc_code,
        "customer_name": plan.customer_name,
        "days": plan.days,
        "limit": plan.limit,
    }


_CUSTOMER_CRM_TOOLS = frozenset({
    "get_customer_catalog",
    "get_customer_sales_summary",
    "get_customer_sales_active_orders",
    "get_customer_itsm_summary",
    "get_customer_itsm_extremes",
    "get_customer_itsm_tickets",
    "get_customer_resource_compliance",
    "get_customer_efficiency_by_category",
})


def _customer_crm_has_data(result: ToolResult) -> bool:
    if result.status != "success":
        return False
    summ = result.summary if isinstance(result.summary, dict) else {}
    if result.rows and result.rows > 0:
        return True
    if summ.get("_count", 0) > 0:
        return True
    rows = summ.get("rows")
    if isinstance(rows, list) and rows:
        return True
    for key in ("ytd_revenue", "active_order_count", "total_orders", "open_tickets"):
        if summ.get(key) is not None:
            return True
    return False


def _customer_overview_has_crm_evidence(results: list[ToolResult]) -> bool:
    return any(r.name in _CUSTOMER_CRM_TOOLS and _customer_crm_has_data(r) for r in results)


def _pending_fallbacks(plan: IntentPlan, run: set[str]) -> list[ToolRequest]:
    """Catalog fallback tools not yet executed."""
    pending: list[ToolRequest] = []
    for req in plan.fallback_tools:
        tool, args = (req.get("tool"), dict(req.get("args") or {})) if isinstance(req, dict) else (req.tool, dict(req.args or {}))
        if tool and tool not in run:
            pending.append(ToolRequest(tool, args))
    if plan.metric_key:
        md = domain_catalog.get_by_key(plan.metric_key)
        if md:
            for t in md.fallback_tools:
                if t not in run and not any(p.tool == t for p in pending):
                    pending.append(ToolRequest(t, _followup_args(plan)))
    return pending


def _aggregate_only_without_rows(results: list[ToolResult]) -> bool:
    """True when only platform/DC aggregate API tools ran (no per-entity rows)."""
    if not results:
        return False
    aggregate_tools = {"get_dashboard_overview", "get_datacenters_summary", "get_dc_compute_classic"}
    ran = {r.name for r in results if r.status in ("success", "error", "skipped")}
    if not ran.issubset(aggregate_tools | {"get_dc_classic_clusters"}):
        return False
    return not any(_rows_of(r) for r in results if r.status == "success")


def evaluate(
    plan: IntentPlan,
    results: list[ToolResult],
    tool_budget_exhausted: bool = False,
) -> EvidenceEvaluation:
    run = {r.name for r in results}
    rows, source, primary_tool = _primary(results)
    ev = EvidenceEvaluation(primary_rows=rows, primary_source=source)

    if plan.analysis_profile == "datacenter_ranking":
        ranking_rows, expected = datacenter_ranking.collect_ranking_rows(results)
        if ranking_rows:
            ev.primary_rows = ranking_rows
            ev.enough_for_answer = True
            analyzed = len(ranking_rows)
            if expected and analyzed >= expected:
                ev.confidence = "high"
            elif expected and analyzed < expected:
                ev.confidence = "medium"
                ev.data_quality_warnings.append(
                    f"partial datacenter coverage: {analyzed}/{expected}"
                )
            else:
                ev.confidence = "high"
            missing_metrics = datacenter_ranking.rows_missing_metrics(ranking_rows)
            if missing_metrics and "get_datacenter_detail" not in run:
                ev.recommended_followup_tools = [
                    ToolRequest(
                        "get_datacenter_detail",
                        {"dc_code": dc, "days": plan.days, "limit": plan.limit},
                    )
                    for dc in missing_metrics[: settings.chatbot_max_tool_calls_per_iteration]
                ]
                ev.enough_for_answer = False
            return ev
        if "get_datacenters_summary" not in run and not tool_budget_exhausted:
            ev.recommended_followup_tools = [ToolRequest("get_datacenters_summary", {})]
            ev.data_quality_warnings.append("datacenter ranking requires summary list")
            return ev
        ev.enough_for_answer = bool(results)
        ev.confidence = "low"
        ev.data_quality_warnings.append("no datacenter ranking rows after tools")
        return ev

    if plan.metric_key in (
        "customer_overview",
        "customer_sales_summary",
        "customer_itsm_risk",
        "customer_compliance",
    ) or plan.analysis_profile == "customer_overview":
        if _customer_overview_has_crm_evidence(results) or any(
            r.name == "get_customer_resources" and r.status == "success" for r in results
        ):
            ev.enough_for_answer = True
            ev.confidence = "medium"
            if any(
                r.name == "get_customer_resources"
                and r.error
                and "Timeout" in str(r.error)
                for r in results
            ):
                ev.data_quality_warnings.append(
                    "infrastructure resources endpoint timed out; CRM/commercial data still available"
                )
            return ev
        fallbacks = _pending_fallbacks(plan, run)
        if fallbacks and not tool_budget_exhausted:
            ev.recommended_followup_tools = fallbacks[: settings.chatbot_max_tool_calls_per_iteration]
            return ev
        ev.enough_for_answer = bool(results)
        ev.confidence = "low"
        return ev

    if plan.metric_key == "crm_sellable":
        sellable_ok = any(
            r.name.startswith("get_sellable") and r.status == "success" for r in results
        )
        if sellable_ok:
            ev.enough_for_answer = True
            ev.confidence = "medium" if plan.dc_code else "high"
            return ev
        fallbacks = _pending_fallbacks(plan, run)
        if fallbacks and not tool_budget_exhausted:
            ev.recommended_followup_tools = fallbacks[: settings.chatbot_max_tool_calls_per_iteration]
            return ev
        ev.enough_for_answer = bool(results)
        ev.confidence = "low"
        return ev

    # cpu_usage profile drives the host/vm fallback + concentration follow-ups.
    cpu_usage = plan.analysis_profile == "cpu_usage"
    memory_usage = plan.analysis_profile == "memory_usage"
    tools = _ENTITY_TOOLS.get(plan.entity_type) if cpu_usage else None

    # --- cluster memory top: API aggregates are insufficient --------------- #
    if memory_usage and plan.entity_type == "cluster" and not rows:
        db_tool = "get_global_km_cluster_memory_top"
        if db_tool not in run:
            args: dict[str, Any] = {"limit": plan.limit or 5}
            if plan.dc_code:
                args["dc_code"] = plan.dc_code
            ev.recommended_followup_tools = [ToolRequest(db_tool, args)]
            ev.data_quality_warnings.append(
                "per-cluster memory ranking is not available via API; trying read-only DB template"
            )
            return ev
        ev.enough_for_answer = True
        ev.confidence = "low"
        for r in results:
            if r.name == db_tool and r.error == "db_disabled":
                ev.data_quality_warnings.append("host-level DB tools are disabled (CHATBOT_DB_ENABLED=false)")
            elif r.name == db_tool and r.status == "error":
                ev.data_quality_warnings.append(f"DB query failed: {r.error}")
        if not ev.data_quality_warnings:
            ev.data_quality_warnings.append("no rows after DB cluster memory query")
        return ev

    if not rows and _aggregate_only_without_rows(results) and memory_usage:
        db_tool = "get_global_km_cluster_memory_top"
        if db_tool not in run:
            args = {"limit": plan.limit or 5}
            if plan.dc_code:
                args["dc_code"] = plan.dc_code
            ev.recommended_followup_tools = [ToolRequest(db_tool, args)]
            ev.data_quality_warnings.append("dashboard/overview lacks per-cluster memory; routing to DB")
            return ev

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
        # Non host/vm entity — try catalog fallbacks before giving up.
        if _aggregate_only_without_rows(results) and plan.metric_key == "global_km_cluster_memory_top":
            db_tool = "get_global_km_cluster_memory_top"
            if db_tool not in run:
                ev.recommended_followup_tools = [
                    ToolRequest(db_tool, {"limit": plan.limit or 5, **({"dc_code": plan.dc_code} if plan.dc_code else {})})
                ]
                return ev
        fallbacks = _pending_fallbacks(plan, run)
        if fallbacks and not tool_budget_exhausted:
            ev.recommended_followup_tools = fallbacks[: settings.chatbot_max_tool_calls_per_iteration]
            ev.data_quality_warnings.append("primary tools returned no rows; trying catalog fallbacks")
            return ev
        if _aggregate_only_without_rows(results) and not tool_budget_exhausted:
            ev.recommended_followup_tools = [
                ToolRequest("get_datacenters_summary", {}),
            ]
            ev.data_quality_warnings.append("only aggregates ran; broadening to datacenter summary")
            return ev
        ev.enough_for_answer = True
        ev.confidence = "low" if not results else "medium"
        if not results:
            ev.data_quality_warnings.append("no tools returned usable rows after investigation")
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
