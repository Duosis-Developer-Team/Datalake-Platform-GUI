"""ReAct allowlist for customer/CRM metrics."""

from app.services.llm_react_loop import _allowed_tools_for_plan
from app.services.planner import IntentPlan


def test_customer_overview_react_allowlist():
    plan = IntentPlan(metric_key="customer_overview", entity_type="customer")
    allowed = _allowed_tools_for_plan(plan)
    assert allowed is not None
    assert "get_customer_catalog" in allowed
    assert "get_customer_backup_summary" not in allowed


def test_crm_sellable_react_allowlist():
    plan = IntentPlan(metric_key="crm_sellable", entity_type="crm", dc_code="DC13")
    allowed = _allowed_tools_for_plan(plan)
    assert allowed == frozenset({
        "get_sellable_summary",
        "get_sellable_by_panel",
        "get_sellable_by_family",
    })


def test_react_blocks_disallowed_tool():
    from app.services import llm_react_loop
    from app.services.investigation_trace import InvestigationTrace
    from app.services.tool_registry import ToolResult

    plan = IntentPlan(metric_key="customer_overview", entity_type="customer")
    allowed = _allowed_tools_for_plan(plan)
    results: list[ToolResult] = []
    trace = InvestigationTrace()
    executed: set[tuple] = set()
    ran = llm_react_loop._execute_tool(
        "get_customer_backup_summary",
        {"customer_name": "Boyner"},
        None,
        executed,
        trace,
        results,
        allowed_tools=allowed,
    )
    assert ran
    assert results[-1].error == "tool_not_in_plan"
