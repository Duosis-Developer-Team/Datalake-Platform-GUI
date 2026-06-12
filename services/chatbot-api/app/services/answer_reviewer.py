"""Post-process LLM answers — optional markdown table extraction into blocks.

Does NOT replace LLM text with deterministic templates. The user-facing answer
always comes from the synthesis LLM (or llm_client error message when LLM fails).
"""

from __future__ import annotations

import re
from typing import Optional

from app.models.schemas import ResponseBlock

_TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|\s*$")


def _parse_markdown_tables(answer: str) -> list[ResponseBlock]:
    """Extract markdown tables from LLM answer into native table blocks."""
    if not answer or "|" not in answer:
        return []
    lines = answer.splitlines()
    blocks: list[ResponseBlock] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not _TABLE_ROW_RE.match(line.strip()):
            i += 1
            continue
        header_cells = [c.strip() for c in line.strip().strip("|").split("|")]
        i += 1
        if i >= len(lines) or not _TABLE_SEP_RE.match(lines[i].strip()):
            continue
        i += 1
        rows: list[list[str]] = []
        while i < len(lines) and _TABLE_ROW_RE.match(lines[i].strip()):
            if _TABLE_SEP_RE.match(lines[i].strip()):
                i += 1
                continue
            cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            rows.append(cells)
            i += 1
        if header_cells and rows:
            blocks.append(
                ResponseBlock(type="table", columns=header_cells, rows=rows)
            )
    return blocks


def review(
    answer: str,
    outcome=None,
    *,
    llm_failed: bool = False,
    user_message: str = "",
) -> tuple[str, list[ResponseBlock], dict]:
    """Return LLM answer unchanged plus optional parsed table blocks."""
    _ = outcome, user_message  # reserved for future metadata-only hooks
    blocks = [] if llm_failed else _parse_markdown_tables(answer or "")
    meta = {
        "llm_failed": llm_failed,
        "blocks_parsed": len(blocks),
        "answer_source": "llm_error_message" if llm_failed else "llm",
    }
    return answer, blocks, meta
