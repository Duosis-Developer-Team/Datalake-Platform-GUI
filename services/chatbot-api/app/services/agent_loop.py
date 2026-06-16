"""Agentic analysis loop.

Hybrid orchestration: deterministic plan + seed tools -> optional LLM ReAct ->
deterministic evidence follow-ups -> synthesize analysis. Tools only run through
``tool_registry.execute_tool`` so the allowlist and DB guards are preserved.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings
from app.models.schemas import ChatMessage, FrontendContext
from app.services import (
    analysis_synthesizer,
    customer_resolver,
    evidence_evaluator,
    investigation_coordinator,
    llm_react_loop,
    query_planner,
    tool_registry,
)
from app.services.analysis_synthesizer import AnalysisSummary
from app.services.evidence_evaluator import EvidenceEvaluation
from app.services.investigation_trace import InvestigationTrace
from app.services.planner import IntentPlan
from app.services.tool_registry import ToolResult

logger = logging.getLogger("chatbot-api.agent")

_CUSTOMER_NAME_TOOLS = frozenset({
    "get_customer_resources",
    "get_customer_s3_vaults",
    "get_customer_itsm_summary",
    "get_customer_itsm_extremes",
    "get_customer_itsm_tickets",
    "get_customer_sales_summary",
    "get_customer_sales_active_orders",
    "get_customer_efficiency_by_category",
    "get_customer_resource_compliance",
    "list_customers",
})


@dataclass
class AgentOutcome:
    plan: IntentPlan
    results: list[ToolResult] = field(default_factory=list)
    evaluation: Optional[EvidenceEvaluation] = None
    analysis: Optional[AnalysisSummary] = None
    iterations: int = 0
    llm_rounds: int = 0
    tool_call_count: int = 0
    investigation_trace: InvestigationTrace = field(default_factory=InvestigationTrace)
    react_mode_used: bool = False


def _tool_args(req: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(req, dict):
        return req.get("tool"), dict(req.get("args") or {})
    return req.tool, dict(req.args or {})


def _dedupe_key(tool: str, args: dict[str, Any]) -> tuple:
    customer = args.get("customer_name")
    if isinstance(customer, str):
        customer = customer.casefold()
    return (
        tool,
        args.get("dc_code"),
        customer,
        args.get("days"),
        args.get("limit"),
    )


def _dc_from_result(result: ToolResult) -> Optional[str]:
    source = result.source or ""
    if "/datacenters/" in source:
        part = source.rsplit("/datacenters/", 1)[-1].split("?")[0].strip("/")
        return part.upper() if part else None
    return None


def _catalog_payload_from_results(results: list[ToolResult]) -> Any:
    for res in results:
        if res.name == "get_customer_catalog" and res.status == "success":
            return res.summary
    return None


def _rewrite_plan_customer_tools(plan: IntentPlan, resolved_name: str) -> IntentPlan:
    """Apply canonical CRM display name to all customer-scoped tool args."""
    if not resolved_name:
        return plan
    for bucket in (plan.initial_tools, plan.fallback_tools):
        for req in bucket:
            tool, args = _tool_args(req)
            if tool in _CUSTOMER_NAME_TOOLS:
                normalized = customer_resolver.normalize_customer_tool_args(args, resolved_name)
                if isinstance(req, dict):
                    req["args"] = normalized
                else:
                    req.args = normalized
    plan.customer_name = resolved_name
    return plan


def _conversation_user_messages(conversation: Optional[list[ChatMessage]]) -> list[str]:
    return [msg.content or "" for msg in (conversation or []) if msg.role == "user"]


def _fetch_catalog_payload(auth_header: Optional[str]) -> Any:
    result = tool_registry.execute_tool("get_customer_catalog", {}, auth_header)
    if result.status == "success":
        return result.summary
    return None


def _resolve_customer_from_catalog(
    message: str,
    ctx: Optional[FrontendContext],
    conversation: Optional[list[ChatMessage]],
    catalog_payload: Any,
    *,
    hint: Optional[str] = None,
) -> Optional[str]:
    return customer_resolver.resolve_customer_name(
        message,
        selected_customer=hint or (ctx.selected_customer if ctx else None),
        conversation_messages=_conversation_user_messages(conversation),
        catalog_payload=catalog_payload,
    )


def _try_catalog_customer_resolution(
    plan: IntentPlan,
    message: str,
    ctx: Optional[FrontendContext],
    conversation: Optional[list[ChatMessage]],
    auth_header: Optional[str],
) -> IntentPlan:
    if plan.metric_key == "customer_overview" and plan.customer_name:
        return plan

    needs_catalog = (
        plan.metric_key == "customer_overview"
        or "customer_name" in (plan.missing_required_params or [])
        or (
            plan.entity_type == "customer"
            and plan.customer_name
            and plan.metric_key != "customer_overview"
        )
    )
    if not needs_catalog:
        return plan

    catalog_payload = _fetch_catalog_payload(auth_header)
    if not catalog_payload:
        return plan

    resolved = _resolve_customer_from_catalog(
        message, ctx, conversation, catalog_payload, hint=plan.customer_name,
    )
    if not resolved:
        return plan

    if plan.metric_key == "customer_overview":
        plan = query_planner.plan(message, ctx, conversation, forced_customer=resolved)
        return _rewrite_plan_customer_tools(plan, resolved)

    if plan.customer_name or "customer_name" not in (plan.missing_required_params or []):
        return _rewrite_plan_customer_tools(plan, resolved)

    replanned = query_planner.plan(message, ctx, conversation, forced_customer=resolved)
    return _rewrite_plan_customer_tools(replanned, resolved)


def _run_tool(
    tool: str,
    args: dict[str, Any],
    auth_header: Optional[str],
    executed: set[tuple],
    trace: InvestigationTrace,
    results: list[ToolResult],
) -> bool:
    if not tool:
        return False
    key = _dedupe_key(tool, args)
    if key in executed:
        return False
    executed.add(key)
    try:
        res = tool_registry.execute_tool(tool, args, auth_header)
    except Exception as exc:  # pragma: no cover
        logger.warning("agent tool %s failed: %s", tool, exc)
        res = ToolResult(tool, "error", tool, error="tool_exception")
    results.append(res)
    trace.record(res)
    return True


def _execute_requests(
    requests: list[Any],
    auth_header: Optional[str],
    executed: set[tuple],
    trace: InvestigationTrace,
    results: list[ToolResult],
    per_batch: int,
    total_cap: int,
    current_total: int,
) -> int:
    total = current_total
    for req in requests[:per_batch]:
        if total >= total_cap:
            break
        tool, args = _tool_args(req)
        if _run_tool(tool, args, auth_header, executed, trace, results):
            total += 1
    return total


def _execute_overview_seed(
    plan: IntentPlan,
    message: str,
    ctx: Optional[FrontendContext],
    conversation: Optional[list[ChatMessage]],
    auth_header: Optional[str],
    executed: set[tuple],
    trace: InvestigationTrace,
    results: list[ToolResult],
    per_turn: int,
) -> int:
    """Customer overview: catalog first, normalize name, CRM tools, resources last."""
    total = 0
    catalog_reqs = [r for r in plan.initial_tools if _tool_args(r)[0] == "get_customer_catalog"]
    other_initial = [r for r in plan.initial_tools if _tool_args(r)[0] != "get_customer_catalog"]
    fallbacks = list(plan.fallback_tools)

    total = _execute_requests(
        catalog_reqs, auth_header, executed, trace, results, per_turn, per_turn, total,
    )
    catalog_payload = _catalog_payload_from_results(results)
    if catalog_payload:
        resolved = _resolve_customer_from_catalog(
            message, ctx, conversation, catalog_payload, hint=plan.customer_name,
        )
        if resolved:
            _rewrite_plan_customer_tools(plan, resolved)
            other_initial = [r for r in plan.initial_tools if _tool_args(r)[0] != "get_customer_catalog"]
            fallbacks = list(plan.fallback_tools)

    crm_reqs = [
        r for r in other_initial
        if _tool_args(r)[0] != "get_customer_resources"
    ]
    infra_reqs = [
        r for r in other_initial
        if _tool_args(r)[0] == "get_customer_resources"
    ] + [
        r for r in fallbacks
        if _tool_args(r)[0] == "get_customer_resources"
    ]
    non_infra_fallbacks = [
        r for r in fallbacks
        if _tool_args(r)[0] != "get_customer_resources"
    ]

    total = _execute_requests(
        crm_reqs + non_infra_fallbacks, auth_header, executed, trace, results,
        per_turn, per_turn, total,
    )
    total = _execute_requests(
        infra_reqs, auth_header, executed, trace, results, per_turn, per_turn, total,
    )
    return total


def run(
    message: str,
    ctx: Optional[FrontendContext],
    auth_header: Optional[str],
    conversation: Optional[list[ChatMessage]] = None,
    *,
    run_tools: bool = True,
) -> AgentOutcome:
    plan = query_planner.plan(message, ctx, conversation)
    plan = _try_catalog_customer_resolution(plan, message, ctx, conversation, auth_header)
    outcome = AgentOutcome(plan=plan)

    if plan.clarification or plan.clarification_block:
        outcome.evaluation = evidence_evaluator.evaluate(plan, [])
        outcome.analysis = analysis_synthesizer.synthesize(plan, [], outcome.evaluation)
        return outcome

    max_iter = max(1, settings.chatbot_max_tool_iterations)
    per_iter = max(1, settings.chatbot_max_tool_calls_per_iteration)
    per_turn = max(1, settings.chatbot_max_tool_calls_per_turn)

    executed: set[tuple] = set()
    trace = outcome.investigation_trace
    total = 0

    # --- Seed: initial + catalog fallback tools --------------------------------
    if run_tools:
        if plan.metric_key == "customer_overview":
            total = _execute_overview_seed(
                plan, message, ctx, conversation, auth_header,
                executed, trace, outcome.results, per_turn,
            )
        else:
            seed_requests = list(plan.initial_tools) + list(plan.fallback_tools)
            total = _execute_requests(
                seed_requests, auth_header, executed, trace, outcome.results, per_turn, per_turn, total,
            )
        outcome.tool_call_count = total

        # --- Map-reduce coordinator (full-coverage global comparisons) ---------------
        if plan.analysis_profile in investigation_coordinator.COVERAGE_PROFILES:
            coord = investigation_coordinator.run(
                plan, outcome.results, auth_header, trace
            )
            if coord.extra_results:
                outcome.results.extend(coord.extra_results)
                for r in coord.extra_results:
                    executed.add(_dedupe_key(r.name, {"dc_code": _dc_from_result(r)}))
                total = len(trace.entries)
                outcome.tool_call_count = total

        # --- LLM ReAct tool rounds (optional) ----------------------------------------
        react = llm_react_loop.run(message, plan, list(outcome.results), auth_header)
        if react.react_used:
            outcome.react_mode_used = True
            outcome.llm_rounds = react.llm_rounds
            if len(react.results) >= len(outcome.results):
                outcome.results = react.results
            trace = react.investigation_trace
            outcome.investigation_trace = trace
            for r in outcome.results:
                dc = _dc_from_result(r)
                cust_args: dict[str, Any] = {"dc_code": dc} if dc else {}
                if r.name in _CUSTOMER_NAME_TOOLS and plan.customer_name:
                    cust_args["customer_name"] = plan.customer_name
                executed.add(_dedupe_key(r.name, cust_args))
            total = len(trace.entries)

        # --- Deterministic follow-up loop ------------------------------------------
        requests: list[Any] = []
        evaluation: Optional[EvidenceEvaluation] = None

        for i in range(max_iter):
            outcome.iterations = i + 1
            evaluation = evidence_evaluator.evaluate(plan, outcome.results, tool_budget_exhausted=total >= per_turn)
            if evaluation.enough_for_answer or total >= per_turn:
                break
            requests = list(evaluation.recommended_followup_tools)
            if not requests:
                break
            batch_start = total
            total = _execute_requests(
                requests, auth_header, executed, trace, outcome.results, per_iter, per_turn, total
            )
            if total == batch_start:
                break
    else:
        evaluation = None

    if evaluation is None:
        evaluation = evidence_evaluator.evaluate(
            plan, outcome.results, tool_budget_exhausted=not run_tools or total >= per_turn
        )
    outcome.evaluation = evaluation
    outcome.tool_call_count = len(trace.entries)
    outcome.analysis = analysis_synthesizer.synthesize(plan, outcome.results, evaluation)
    if outcome.analysis:
        outcome.analysis.extra = dict(outcome.analysis.extra or {})
        outcome.analysis.extra["investigation_trace"] = trace.as_context()
        outcome.analysis.extra["investigation_summary"] = trace.summary_line()
    return outcome
