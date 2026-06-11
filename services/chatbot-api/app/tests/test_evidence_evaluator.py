"""Tests for evidence evaluator fallback exhaustion."""

from __future__ import annotations

from app.services.evidence_evaluator import evaluate
from app.services.planner import IntentPlan
from app.services.tool_registry import ToolResult


def test_aggregate_only_triggers_fallback_not_early_enough():
    plan = IntentPlan(
        entity_type="datacenter",
        metric_key="dc_capacity",
        dc_code="DC13",
        days=7,
        limit=5,
        fallback_tools=[{"tool": "get_dc_compute_classic", "args": {"dc_code": "DC13"}}],
    )
    results = [
        ToolResult("get_dashboard_overview", "success", "api", summary={"x": 1}, rows=0),
    ]
    ev = evaluate(plan, results)
    assert ev.enough_for_answer is False
    assert ev.recommended_followup_tools
    assert ev.recommended_followup_tools[0].tool == "get_dc_compute_classic"


def test_no_rows_marks_enough_when_budget_exhausted():
    plan = IntentPlan(entity_type="datacenter", dc_code="DC13")
    results = [ToolResult("get_datacenter_detail", "success", "api", summary={}, rows=0)]
    ev = evaluate(plan, results, tool_budget_exhausted=True)
    assert ev.enough_for_answer is True
    assert ev.confidence in ("low", "medium")
