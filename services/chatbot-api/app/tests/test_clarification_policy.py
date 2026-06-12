"""Tests for ambiguous ranking clarification policy."""

from __future__ import annotations

from app.models.schemas import ChatMessage
from app.services import clarification_policy, query_planner


def test_ambiguous_ranking_asks_clarification():
    plan = query_planner.plan("En yoğun datacenter hangisi?", None, [])
    assert plan.clarification is not None
    assert "CPU" in plan.clarification or "cpu" in plan.clarification.lower()
    assert plan.ranking_metric is None


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
