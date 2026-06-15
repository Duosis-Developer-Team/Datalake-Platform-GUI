"""Tests for executive analysis-first prompt and formatter."""

from __future__ import annotations

from app.services import context_builder


def test_agentic_format_puts_analysis_before_result():
    assert "1. **Analiz**" in context_builder._AGENTIC_FORMAT
    assert "2. **Sonuç**" in context_builder._AGENTIC_FORMAT
    assert context_builder._AGENTIC_FORMAT.index("Analiz") < context_builder._AGENTIC_FORMAT.index("Sonuç")
    assert "Forbidden" in context_builder._AGENTIC_FORMAT
    assert "table-only" in context_builder._AGENTIC_FORMAT.lower() or "Tablo" in context_builder._AGENTIC_FORMAT


def test_system_prompt_targets_executives():
    assert "executives" in context_builder.SYSTEM_PROMPT.lower()
    assert "prose" in context_builder.SYSTEM_PROMPT.lower() or "advisor" in context_builder.SYSTEM_PROMPT.lower()


def test_output_format_hint_top_list():
    hint = context_builder._output_format_hint("top_list")
    assert "prose" in hint.lower() or "summary" in hint.lower()
    assert "markdown table" in hint.lower() or "tablo" in hint.lower()


def test_output_format_hint_summary_no_table():
    hint = context_builder._output_format_hint("summary")
    assert "prose" in hint.lower()
    assert "no markdown table" in hint.lower() or "Prose only" in hint
