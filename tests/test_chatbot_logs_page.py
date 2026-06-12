"""Smoke tests for AI Assistant log viewer page."""

from __future__ import annotations

from src.pages.settings.integrations.chatbot_logs import (
    build_detail_content,
    build_layout,
    build_table_rows,
    pagination_label,
)


def test_build_layout_contains_core_ids():
    layout = build_layout()
    text = str(layout)
    assert "chatbot-logs-table-body" in text
    assert "chatbot-logs-detail-modal" in text


def test_build_table_rows_empty():
    rows = build_table_rows([])
    assert len(rows) == 1
    assert "No turn logs" in str(rows[0])


def test_build_table_rows_with_item():
    rows = build_table_rows(
        [
            {
                "request_id": "r1",
                "status": "success",
                "created_at": "2026-06-12T10:00:00+00:00",
                "username": "admin",
                "user_message": "hello world",
                "response_type": "answer",
            }
        ]
    )
    assert len(rows) == 1
    assert "r1" in str(rows[0])


def test_build_detail_content():
    content = build_detail_content(
        {
            "request_id": "r1",
            "user_message": "q",
            "assistant_answer": "a",
            "clarification": {"prompt": "pick", "choices": [{"label": "CPU", "value": "cpu"}]},
            "tools": [{"name": "get_datacenters_summary", "status": "ok", "rows": 5}],
        }
    )
    assert len(content) >= 3


def test_pagination_label():
    assert "1–10 of 25" in pagination_label(0, 10, 25)
    assert pagination_label(0, 10, 0) == "No records"
