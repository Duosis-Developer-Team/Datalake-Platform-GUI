"""Tests for ambiguous ranking clarification policy."""

from __future__ import annotations

from app.models.schemas import ChatMessage
from app.services import clarification_policy, query_planner


def test_ambiguous_ranking_asks_clarification():
    plan = query_planner.plan("En yoğun datacenter hangisi?", None, [])
    assert plan.clarification is not None
    assert plan.clarification_block is not None
    assert len(plan.clarification_block.choices) == 4
    assert any(c.id == "cpu" for c in plan.clarification_block.choices)
    assert plan.ranking_metric is None


def test_build_ranking_clarification_structure():
    block = clarification_policy.build_ranking_clarification()
    assert block.prompt
    assert len(block.choices) == 4
    assert block.choices[0].value


def test_explicit_cpu_skips_clarification():
    plan = query_planner.plan("CPU kullanımına göre en yoğun datacenter hangisi?", None, [])
    assert plan.clarification is None
    assert plan.ranking_metric == "cpu"
    assert plan.analysis_profile == "datacenter_ranking"


def test_resolve_metric_from_conversation_reply():
    conv = [
        ChatMessage(role="user", content="En yoğun datacenter hangisi?"),
        ChatMessage(role="assistant", content=clarification_policy.RANKING_METRIC_CLARIFICATION),
        ChatMessage(role="user", content="2"),
    ]
    plan = query_planner.plan("tamam", None, conv)
    assert plan.ranking_metric == "memory"
    assert plan.clarification is None


def test_detect_ranking_metric_composite():
    assert clarification_policy.detect_ranking_metric("hepsini birlikte değerlendir") == "composite"
