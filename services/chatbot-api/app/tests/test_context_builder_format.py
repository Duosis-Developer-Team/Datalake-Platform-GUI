"""Tests for executive analysis-first prompt and formatter."""

from __future__ import annotations

from app.services import context_builder


def test_agentic_format_puts_analysis_before_result():
    assert "1. **Analiz**" in context_builder._AGENTIC_FORMAT
    assert "2. **Sonuç**" in context_builder._AGENTIC_FORMAT
    assert context_builder._AGENTIC_FORMAT.index("Analiz") < context_builder._AGENTIC_FORMAT.index("Sonuç")


def test_system_prompt_targets_executives():
    assert "executives" in context_builder.SYSTEM_PROMPT.lower()
    assert "analysis" in context_builder.SYSTEM_PROMPT.lower()
