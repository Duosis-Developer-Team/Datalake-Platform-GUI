"""Tests for customer overview evidence evaluation."""

from app.services.evidence_evaluator import evaluate
from app.services.planner import IntentPlan
from app.services.tool_registry import ToolResult


def test_customer_overview_enough_when_crm_data_present_despite_resources_timeout():
    plan = IntentPlan(
        entity_type="customer",
        metric_key="customer_overview",
        analysis_profile="customer_overview",
        customer_name="Boyner",
    )
    results = [
        ToolResult(
            "get_customer_sales_summary",
            "success",
            "customer-api:/sales/summary",
            summary={"ytd_revenue": 1000},
            rows=1,
        ),
        ToolResult(
            "get_customer_resources",
            "error",
            "customer-api:/resources",
            error="ReadTimeout",
        ),
    ]
    ev = evaluate(plan, results)
    assert ev.enough_for_answer
    assert any("timed out" in w.lower() for w in ev.data_quality_warnings)
