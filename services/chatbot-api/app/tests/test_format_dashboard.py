"""Tests for format_dashboard_overview and answer_reviewer post-process."""

from __future__ import annotations

from app.services.agent_loop import AgentOutcome
from app.services.answer_reviewer import review
from app.services.context_builder import format_dashboard_overview, is_dashboard_overview_intent
from app.services.planner import IntentPlan
from app.services.tool_registry import ToolResult


def _outcome_with_overview(platforms: dict) -> AgentOutcome:
    summary = {
        "overview": {"dc_count": 3, "total_hosts": 120, "total_vms": 800},
        "platforms": platforms,
        "classic_totals": {"cpu_used": 100, "cpu_cap": 200, "mem_used": 50, "mem_cap": 100},
    }
    result = ToolResult(
        "get_dashboard_overview",
        "success",
        "datacenter-api:/api/v1/dashboard/overview",
        summary=summary,
        rows=1,
    )
    return AgentOutcome(plan=IntentPlan(), results=[result])


def test_format_dashboard_overview_builds_table_block():
    outcome = _outcome_with_overview(
        {
            "nutanix": {"host_count": 40, "vm_count": 300, "cpu_used": 1200, "cpu_cap": 2000},
            "vmware": {"host_count": 50, "vm_count": 400, "cpu_used": 900, "cpu_cap": 1500},
        }
    )
    formatted = format_dashboard_overview(outcome)
    assert formatted is not None
    assert "Analiz" in formatted["answer"]
    table_blocks = [b for b in formatted["blocks"] if b.get("type") == "table"]
    assert len(table_blocks) == 1
    assert len(table_blocks[0]["rows"]) >= 1


def test_answer_reviewer_keeps_llm_answer_and_parses_table():
    llm_answer = (
        "**Analiz:**\nVeriler incelendi.\n\n"
        "| Platform | CPU |\n|---|---|\n| classic | 100 |\n"
    )
    reviewed, blocks, meta = review(llm_answer, _outcome_with_overview({}), user_message="test")
    assert reviewed == llm_answer
    assert meta["answer_source"] == "llm"
    assert any(b.type == "table" for b in blocks)


def test_answer_reviewer_llm_failed_source():
    reviewed, blocks, meta = review("", None, llm_failed=True)
    assert meta["answer_source"] == "llm_error_message"
    assert blocks == []


def test_is_dashboard_overview_intent_requires_keywords():
    outcome = AgentOutcome(plan=IntentPlan(), results=[])
    assert not is_dashboard_overview_intent(outcome, "test")
    assert is_dashboard_overview_intent(outcome, "platform bazlı dağılımı ver")
