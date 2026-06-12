"""Deterministic intent planner for the agentic loop.

Produces a structured ``IntentPlan`` (entity / metric / scope / time / source /
output / sort / limit) and the *initial* tool plan. It is rule-based on purpose:
no LLM picks tools, so the tool allowlist in ``tool_registry`` is never bypassed.
The initial tool selection reuses ``tool_orchestrator.select_tools`` (the same
heuristics + allowlist the single-pass path uses).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.models.schemas import ClarificationBlock, FrontendContext
from app.services import tool_orchestrator as orch


@dataclass
class IntentPlan:
    entity_type: str = "datacenter"  # vm | host | cluster | customer | datacenter | sla | backup | s3 | crm
    metric: Optional[str] = None  # cpu | memory | storage | network | availability | ...
    dc_code: Optional[str] = None
    customer_name: Optional[str] = None
    days: Optional[int] = None
    requested_source: str = "auto"  # db | api | auto
    requested_output: str = "summary"  # top_list | summary | latest | comparison
    limit: Optional[int] = None
    sort_by: str = "avg"  # avg | max | latest
    needs_analysis: bool = True
    initial_tools: list[dict[str, Any]] = field(default_factory=list)
    fallback_tools: list[dict[str, Any]] = field(default_factory=list)
    # --- domain-catalog enrichment (query_planner) ---
    architecture: Optional[str] = None  # classic | hyperconverged
    calculation: Optional[str] = None  # top | summary | variability | trend | comparison | risk
    metric_key: Optional[str] = None  # catalog key
    analysis_profile: str = "generic"  # which synthesizer profile to apply
    missing_required_params: list[str] = field(default_factory=list)
    clarification: Optional[str] = None  # set when a required param can't be resolved
    clarification_block: Optional[ClarificationBlock] = None
    answer_guidance: list[str] = field(default_factory=list)  # metric-specific LLM guidance
    ranking_metric: Optional[str] = None  # cpu | memory | vm_count | composite (datacenter_ranking)

    def as_context(self) -> dict[str, Any]:
        """Compact, LLM-safe view of the plan (no internals/secrets)."""
        return {
            "entity_type": self.entity_type,
            "metric": self.metric,
            "metric_key": self.metric_key,
            "architecture": self.architecture,
            "calculation": self.calculation,
            "dc_code": self.dc_code,
            "customer": self.customer_name,
            "days": self.days,
            "requested_source": self.requested_source,
            "requested_output": self.requested_output,
            "limit": self.limit,
            "sort_by": self.sort_by,
            "ranking_metric": self.ranking_metric,
        }


def make_plan(message: str, ctx: Optional[FrontendContext]) -> IntentPlan:
    text = (message or "").lower()
    dc_code = orch._extract_dc(message, ctx)
    customer = ctx.selected_customer if ctx and ctx.selected_customer else None
    memory_intent = orch._has(text, "memory") and not orch._has(text, "storage")
    cpu_intent = ("cpu" in text or orch._has(text, "compute")) and not memory_intent

    # --- entity ---
    if orch._has(text, "cluster") and memory_intent and orch._has(text, "top"):
        entity = "cluster"
    elif orch._has(text, "vm") and cpu_intent:
        entity = "vm"
    elif orch._has(text, "host") and cpu_intent:
        entity = "host"
    elif orch._has(text, "customer") or customer:
        entity = "customer"
    elif orch._has(text, "sla"):
        entity = "sla"
    elif orch._has(text, "backup"):
        entity = "backup"
    elif orch._has(text, "s3"):
        entity = "s3"
    elif orch._has(text, "crm"):
        entity = "crm"
    elif dc_code:
        entity = "datacenter"
    else:
        entity = "datacenter"

    # --- metric ---
    if memory_intent:
        metric = "memory"
    elif cpu_intent:
        metric = "cpu"
    elif orch._has(text, "storage"):
        metric = "storage"
    elif orch._has(text, "network"):
        metric = "network"
    elif orch._has(text, "sla"):
        metric = "availability"
    else:
        metric = None

    # --- output / sort ---
    if orch._has(text, "top"):
        output, sort_by = "top_list", ("max" if ("peak" in text or "tepe" in text) else "avg")
    elif orch._has(text, "overview"):
        output, sort_by = "summary", "avg"
    else:
        output, sort_by = ("latest" if entity in ("vm", "host") else "summary"), "latest"

    source = "db" if orch._has(text, "explicit_db") else "auto"
    if metric == "memory" and entity == "cluster":
        profile = "memory_usage"
    elif metric == "cpu" and entity in ("vm", "host"):
        profile = "cpu_usage"
    else:
        profile = "generic"

    initial = [{"tool": s.tool, "args": s.args} for s in orch.select_tools(message, ctx)]

    return IntentPlan(
        entity_type=entity,
        metric=metric,
        calculation=output,
        analysis_profile=profile,
        dc_code=dc_code,
        customer_name=customer,
        days=orch._extract_days(text),
        requested_source=source,
        requested_output=output,
        limit=orch._extract_limit(text),
        sort_by=sort_by,
        needs_analysis=True,
        initial_tools=initial,
    )
