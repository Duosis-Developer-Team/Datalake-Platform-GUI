"""Unit tests for scripts/analyze_chatbot_logs.py."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import analyze_chatbot_logs as analyzer  # noqa: E402


def test_analyze_turns_counts_customer_and_bad_answers():
    turns = [
        {
            "request_id": "a1",
            "status": "success",
            "response_type": "answer",
            "user_message": "Boyner aktif siparişleri",
            "assistant_answer": "Sonuç: 3 aktif sipariş",
            "tools": [{"name": "get_customer_sales_active_orders", "status": "success"}],
            "latency_ms": 1000,
            "tool_call_count": 1,
            "llm_rounds": 2,
        },
        {
            "request_id": "a2",
            "status": "success",
            "response_type": "answer",
            "user_message": "test",
            "assistant_answer": "Şu anki veri eksikliği nedeniyle belirleyemiyoruz.",
            "tools": [],
        },
    ]
    report = analyzer.analyze_turns(turns, source="fixture", days=30, focus=["all"])
    assert report.total_turns == 2
    assert report.customer_related_messages == 1
    assert report.customer_tool_turns == 1
    assert report.bad_answer_count == 1
    assert report.zero_tool_success_count == 1


def test_render_markdown_contains_summary():
    report = analyzer.AnalysisReport(
        source="fixture",
        generated_at="2026-06-15T12:00:00+00:00",
        days=7,
        focus=["customer"],
        total_turns=1,
        status_counts={"success": 1},
    )
    md = analyzer.render_markdown(report)
    assert "Turns analyzed" in md
    assert "fixture" in md
