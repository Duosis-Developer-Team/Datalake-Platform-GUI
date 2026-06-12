"""Golden and adversarial chatbot test harness (deterministic, mock LLM)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from app.core.security import classify_intent
from app.models.schemas import ChatMessage, FrontendContext
from app.services import agent_loop, query_planner, scope_guard
from app.services.planner import IntentPlan
from app.services.tool_registry import ToolResult

GOLDEN_DIR = Path(__file__).parent / "golden"


def _load_cases(name: str) -> list[dict[str, Any]]:
    path = GOLDEN_DIR / name
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def _run_plan(message: str, conversation: list[ChatMessage] | None = None) -> IntentPlan:
    return query_planner.plan(message, FrontendContext(), conversation)


def _mock_agent(message: str, conversation: list[ChatMessage] | None = None):
    return agent_loop.run(message, FrontendContext(), None, conversation=conversation or [])


@pytest.mark.parametrize("case", _load_cases("chatbot_golden_cases.yaml"), ids=lambda c: c["id"])
def test_golden_cases(case: dict[str, Any]) -> None:
    message = case["user_message"]
    conversation = [
        ChatMessage(**m) for m in (case.get("conversation") or [])
    ]
    expect = case.get("expect") or {}

    if "plan_profile" in expect or "plan_tools_contain" in expect:
        plan = _run_plan(message, conversation or None)
        if "plan_profile" in expect:
            assert plan.analysis_profile == expect["plan_profile"]
        for tool in expect.get("plan_tools_contain") or []:
            names = {t.get("tool") if isinstance(t, dict) else t.tool for t in plan.initial_tools}
            names.update(t.get("tool") if isinstance(t, dict) else t.tool for t in plan.fallback_tools)
            assert tool in names

    if expect.get("response_type") == "clarification":
        plan = _run_plan(message, conversation or None)
        assert plan.clarification or plan.clarification_block

    if expect.get("write_intent"):
        flags = classify_intent(message)
        assert flags.wants_write

    if expect.get("forbidden_intent"):
        flags = classify_intent(message)
        assert flags.wants_secret or flags.injection

    if "answer_contains" in expect and not expect.get("write_intent") and not expect.get("forbidden_intent"):
        with patch("app.services.agent_loop.tool_registry.execute_tool") as mock_exec:
            mock_exec.return_value = ToolResult("get_datacenters_summary", "success", "api", summary={"_count": 1}, rows=1)
            outcome = _mock_agent(message, conversation)
        answer = ""
        if outcome.plan.clarification:
            answer = outcome.plan.clarification
        elif outcome.analysis:
            from app.services.context_builder import format_from_analysis

            answer = format_from_analysis(outcome)
        for fragment in expect["answer_contains"]:
            assert fragment.lower() in answer.lower()

    if expect.get("response_type") == "answer" and "answer_contains" in expect:
        pass


@pytest.mark.parametrize("case", _load_cases("chatbot_adversarial_cases.yaml"), ids=lambda c: c["id"])
def test_adversarial_cases(case: dict[str, Any]) -> None:
    test_golden_cases(case)


def test_tool_registry_snapshot_size():
    from app.services.tool_registry import list_tool_names

    names = list_tool_names()
    assert len(names) >= 25
