"""Map-reduce investigation coordinator for full-coverage global comparisons."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings
from app.services import investigation_workers
from app.services.investigation_trace import InvestigationTrace
from app.services.planner import IntentPlan
from app.services.tool_registry import ToolResult

logger = logging.getLogger("chatbot-api.coordinator")

COVERAGE_PROFILES = frozenset({"datacenter_ranking"})


@dataclass
class CoordinatorOutcome:
    extra_results: list[ToolResult] = field(default_factory=list)
    findings: list[investigation_workers.WorkerFinding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _base_tool_args(plan: IntentPlan) -> dict[str, Any]:
    return {
        "dc_code": plan.dc_code,
        "days": plan.days,
        "limit": plan.limit,
    }


def run(
    plan: IntentPlan,
    results: list[ToolResult],
    auth_header: Optional[str],
    trace: InvestigationTrace,
) -> CoordinatorOutcome:
    """Run map-reduce workers when global comparison needs fuller coverage."""
    if not settings.chatbot_map_reduce_enabled:
        return CoordinatorOutcome()
    if plan.analysis_profile not in COVERAGE_PROFILES:
        return CoordinatorOutcome()
    if plan.clarification:
        return CoordinatorOutcome()

    outcome = CoordinatorOutcome(
        findings=investigation_workers.summary_ranking_findings(results),
    )
    expected, analyzed, missing_metrics = investigation_workers.coverage_status(results)

    if missing_metrics:
        batch_size = max(1, settings.chatbot_max_tool_calls_per_iteration)
        remaining = list(missing_metrics)
        while remaining and len(outcome.extra_results) < settings.chatbot_max_tool_calls_per_turn:
            batch = investigation_workers.run_detail_workers(
                remaining[:batch_size],
                _base_tool_args(plan),
                auth_header,
            )
            outcome.extra_results.extend(batch.extra_results)
            outcome.findings.extend(batch.findings)
            outcome.warnings.extend(batch.warnings)
            for res in batch.extra_results:
                trace.record(res)
            remaining = remaining[batch_size:]
            if not batch.extra_results:
                break

    if expected and analyzed < expected:
        outcome.warnings.append(f"coverage gap: {analyzed}/{expected} datacenters in summary")
        logger.info(
            "datacenter ranking partial coverage: %s/%s (profile=%s)",
            analyzed,
            expected,
            plan.analysis_profile,
        )

    return outcome
