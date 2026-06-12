"""Tests for context builder table-bias stripping and intent hints."""

from __future__ import annotations

import json

from app.services.context_builder import (
    _intent_format_hint,
    strip_table_bias_from_messages,
)


def test_intent_format_hint_for_explain():
    hint = _intent_format_hint("En yoğun dc neden DC17? Açıklar mısın?")
    assert "Explanatory mode" in hint
    assert "tablo" in hint.lower() or "table" in hint.lower()


def test_intent_format_hint_empty_for_generic():
    assert _intent_format_hint("Genel kapasite durumunu özetle") == ""


def test_strip_table_bias_from_messages():
    analysis = {
        "extra": {
            "datacenter_ranking": {
                "winner": {"id": "DC17"},
                "ranking_table": [{"id": "DC17", "rank": 1}],
                "narrative_summary": {"winner_id": "DC17"},
            }
        }
    }
    prefix = "Derived analysis (deterministic — use ONLY these numbers/verdicts, do not invent):\n"
    content = prefix + json.dumps(analysis, ensure_ascii=False) + "\n\nTail"
    messages = [{"role": "developer", "content": content}]
    stripped = strip_table_bias_from_messages(messages)
    data = json.loads(stripped[0]["content"].split(prefix, 1)[1].split("\n\n", 1)[0])
    dr = data["extra"]["datacenter_ranking"]
    assert "ranking_table" not in dr
    assert dr["narrative_summary"]["winner_id"] == "DC17"
