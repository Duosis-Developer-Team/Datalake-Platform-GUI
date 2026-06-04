"""Agentic analysis loop.

Deterministic multi-step orchestration: plan -> execute (allowlisted tools) ->
evaluate evidence -> (maybe) follow-up -> synthesize analysis. No LLM runs inside
the loop and tools are only ever invoked through ``tool_registry.execute_tool``,
so the allowlist and all DB guards are preserved. Early-stops as soon as the
evidence is sufficient; hard-capped by iterations / per-iteration / per-turn.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings
from app.models.schemas import FrontendContext
from app.services import (
    analysis_synthesizer,
    evidence_evaluator,
    planner,
    tool_registry,
)
from app.services.analysis_synthesizer import AnalysisSummary
from app.services.evidence_evaluator import EvidenceEvaluation
from app.services.planner import IntentPlan
from app.services.tool_registry import ToolResult

logger = logging.getLogger("chatbot-api.agent")


@dataclass
class AgentOutcome:
    plan: IntentPlan
    results: list[ToolResult] = field(default_factory=list)
    evaluation: Optional[EvidenceEvaluation] = None
    analysis: Optional[AnalysisSummary] = None
    iterations: int = 0


def _tool_args(req: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(req, dict):
        return req.get("tool"), dict(req.get("args") or {})
    return req.tool, dict(req.args or {})


def _dedupe_key(tool: str, args: dict[str, Any]) -> tuple:
    return (tool, args.get("dc_code"), args.get("days"), args.get("limit"))


def run(message: str, ctx: Optional[FrontendContext], auth_header: Optional[str]) -> AgentOutcome:
    plan = planner.make_plan(message, ctx)
    outcome = AgentOutcome(plan=plan)

    max_iter = max(1, settings.chatbot_max_tool_iterations)
    per_iter = max(1, settings.chatbot_max_tool_calls_per_iteration)
    per_turn = max(1, settings.chatbot_max_tool_calls_per_turn)

    executed: set[tuple] = set()
    total = 0
    requests: list[Any] = list(plan.initial_tools)
    evaluation: Optional[EvidenceEvaluation] = None

    for i in range(max_iter):
        outcome.iterations = i + 1
        if not requests:
            break
        for req in requests[:per_iter]:
            if total >= per_turn:
                break
            tool, args = _tool_args(req)
            if not tool:
                continue
            key = _dedupe_key(tool, args)
            if key in executed:  # never run the same tool+params twice
                continue
            executed.add(key)
            try:
                res = tool_registry.execute_tool(tool, args, auth_header)
            except Exception as exc:  # pragma: no cover - executor already guards
                logger.warning("agent tool %s failed: %s", tool, exc)
                res = ToolResult(tool, "error", tool, error="tool_exception")
            outcome.results.append(res)
            total += 1

        evaluation = evidence_evaluator.evaluate(plan, outcome.results)
        if evaluation.enough_for_answer or total >= per_turn:
            break
        # Next iteration: only the recommended (allowlisted) follow-ups.
        requests = list(evaluation.recommended_followup_tools)

    if evaluation is None:
        evaluation = evidence_evaluator.evaluate(plan, outcome.results)
    outcome.evaluation = evaluation
    outcome.analysis = analysis_synthesizer.synthesize(plan, outcome.results, evaluation)
    return outcome
