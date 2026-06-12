"""Tests for the LLM ReAct investigation loop."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.services import llm_react_loop, tool_registry
from app.services.llm_client import LLMResultWithTools, ToolCallRequest
from app.services.planner import IntentPlan
from app.services.tool_registry import ToolResult


def _plan() -> IntentPlan:
    return IntentPlan(
        entity_type="datacenter",
        dc_code="DC13",
        days=7,
        limit=5,
        initial_tools=[{"tool": "get_datacenter_detail", "args": {"dc_code": "DC13"}}],
    )


def test_react_loop_executes_tool_calls(monkeypatch):
    calls = []

    def fake_exec(name, args, auth):
        calls.append((name, args.get("dc_code")))
        return ToolResult(name, "success", f"api:{name}", summary={"ok": True}, rows=1)

    monkeypatch.setattr(tool_registry, "execute_tool", fake_exec)
    monkeypatch.setattr(settings, "chatbot_llm_react_mode", True)
    monkeypatch.setattr(settings, "chatbot_max_llm_rounds", 5)
    monkeypatch.setattr(settings, "chatbot_max_tool_calls_per_turn", 10)

    llm = MagicMock()
    llm.is_configured = True
    llm.probe_tools_support.return_value = True
    llm.complete_with_tools.side_effect = [
        LLMResultWithTools(
            content=None,
            model="test",
            tool_calls=[
                ToolCallRequest(id="c1", name="get_datacenters_summary", arguments="{}"),
            ],
        ),
        LLMResultWithTools(
            content="**Analiz:**\n- checked\n\n**Sonuç:**\n- done",
            model="test",
            tool_calls=[],
        ),
    ]
    monkeypatch.setattr(llm_react_loop, "get_llm_client", lambda: llm)

    seed = [ToolResult("get_datacenter_detail", "success", "api", summary={}, rows=0)]
    out = llm_react_loop.run("özet", _plan(), seed, None)

    assert out.react_used is True
    assert out.llm_rounds == 2
    assert not hasattr(out, "draft_answer") or getattr(out, "draft_answer", None) is None
    assert any(c[0] == "get_datacenters_summary" for c in calls)


def test_react_loop_respects_tool_cap(monkeypatch):
    monkeypatch.setattr(
        tool_registry,
        "execute_tool",
        lambda n, a, auth: ToolResult(n, "success", n, summary={}, rows=0),
    )
    monkeypatch.setattr(settings, "chatbot_llm_react_mode", True)
    monkeypatch.setattr(settings, "chatbot_max_llm_rounds", 20)
    monkeypatch.setattr(settings, "chatbot_max_tool_calls_per_turn", 2)

    llm = MagicMock()
    llm.is_configured = True
    llm.probe_tools_support.return_value = True

    def always_tool(*_a, **_k):
        return LLMResultWithTools(
            content=None,
            model="test",
            tool_calls=[ToolCallRequest(id="x", name="get_dashboard_overview", arguments="{}")],
        )

    llm.complete_with_tools.side_effect = always_tool
    monkeypatch.setattr(llm_react_loop, "get_llm_client", lambda: llm)

    out = llm_react_loop.run("test", _plan(), [], None)
    assert out.tool_call_count <= 2


def test_build_openai_tools_from_registry():
    from app.services.llm_tool_schemas import build_openai_tools

    tools = build_openai_tools(["get_dashboard_overview"])
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "get_dashboard_overview"


def test_investigation_trace_summary():
    from app.services.investigation_trace import InvestigationTrace

    t = InvestigationTrace()
    t.record(ToolResult("a", "success", "s", rows=3))
    t.record(ToolResult("b", "error", "s", error="x"))
    assert "2 source" in t.summary_line()
