"""Lightweight answer critique pass — catches numeric denial when tools returned data."""

from __future__ import annotations

from typing import Any, Optional

from app.models.schemas import ResponseBlock
from app.services import context_builder
from app.services.tool_registry import ToolResult

_DENY_PHRASES = (
    "erişemiyorum",
    "erişimim yok",
    "veri yok",
    "veri bulunmuyor",
    "veriye ulaşamıyorum",
    "sağlayamıyorum",
    "elimde veri yok",
    "bilgiye sahip değilim",
)


def _has_rows(results: list[ToolResult]) -> bool:
    return any(r.status == "success" and (r.rows or 0) > 0 for r in results)


def _denies_data(answer: str) -> bool:
    text = answer or ""
    if "|" in text and "---" in text:
        return False
    low = text.lower()
    return any(p in low for p in _DENY_PHRASES)


def _dashboard_tool_used(results: list[ToolResult]) -> bool:
    return any(r.name == "get_dashboard_overview" and r.status == "success" for r in results)


def review(
    answer: str,
    outcome,
    *,
    llm_failed: bool = False,
) -> tuple[str, list[ResponseBlock]]:
    """Return possibly revised answer and structured blocks."""
    blocks: list[ResponseBlock] = []
    if outcome is None:
        return answer, blocks

    tool_results = outcome.results or []
    inv_summary = None
    if outcome.analysis and outcome.analysis.extra:
        inv_summary = outcome.analysis.extra.get("investigation_summary")

    needs_fallback = (
        (_has_rows(tool_results) and (llm_failed or _denies_data(answer)))
        or (inv_summary and _denies_data(answer) and not _has_rows(tool_results))
    )
    if needs_fallback:
        answer = context_builder.format_from_analysis(outcome)

    if _dashboard_tool_used(tool_results):
        formatted = context_builder.format_dashboard_overview(outcome)
        if formatted:
            answer = formatted.get("answer") or answer
            for block in formatted.get("blocks") or []:
                blocks.append(ResponseBlock(**block))

    return answer, blocks
