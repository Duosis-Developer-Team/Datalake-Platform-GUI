"""Administration — AI Assistant turn log viewer (MongoDB via chatbot-log-api)."""

from __future__ import annotations

import json
from typing import Any, Optional

import dash_mantine_components as dmc
from dash import dcc, html

from src.utils.ui_tokens import ON_SURFACE, relative_time, section_header, settings_page_shell

PAGE_LIMIT = 50

STATUS_OPTIONS = [
    {"label": "All statuses", "value": ""},
    {"label": "success", "value": "success"},
    {"label": "clarification", "value": "clarification"},
    {"label": "refused", "value": "refused"},
    {"label": "fallback", "value": "fallback"},
    {"label": "error", "value": "error"},
]

TYPE_OPTIONS = [
    {"label": "All types", "value": ""},
    {"label": "answer", "value": "answer"},
    {"label": "clarification", "value": "clarification"},
]


def _status_color(status: str) -> str:
    s = (status or "").lower()
    if s == "success":
        return "green"
    if s == "clarification":
        return "blue"
    if s == "refused":
        return "orange"
    if s in ("error", "fallback"):
        return "red"
    return "indigo"


def _preview(text: str, limit: int = 80) -> str:
    t = (text or "").replace("\n", " ").strip()
    if len(t) <= limit:
        return t or "—"
    return t[: limit - 1] + "…"


def build_table_rows(items: list[dict[str, Any]]) -> list[html.Tr]:
    rows: list[html.Tr] = []
    for item in items:
        rid = str(item.get("request_id") or "")
        status = str(item.get("status") or "")
        created = str(item.get("created_at") or "")[:19]
        rows.append(
            html.Tr(
                id={"type": "chatbot-log-row", "request_id": rid},
                n_clicks=0,
                style={"borderBottom": "1px solid #eef1f4", "cursor": "pointer"},
                children=[
                    html.Td(
                        dmc.Stack(
                            gap=0,
                            children=[
                                dmc.Text(created or "—", size="sm", fw=500),
                                dmc.Text(relative_time(item.get("created_at")), size="xs", c="dimmed"),
                            ],
                        )
                    ),
                    html.Td(str(item.get("username") or item.get("user_id") or "—")),
                    html.Td(
                        dmc.Badge(status or "—", variant="light", color=_status_color(status), size="sm")
                    ),
                    html.Td(str(item.get("response_type") or "—")),
                    html.Td(_preview(str(item.get("user_message") or "")), style={"fontSize": "13px", "maxWidth": "280px"}),
                    html.Td(str(item.get("latency_ms") or "—"), style={"fontSize": "12px"}),
                    html.Td(str(item.get("tool_call_count") or "—"), style={"fontSize": "12px"}),
                    html.Td(str(item.get("model") or "—")[:24], style={"fontSize": "12px"}),
                ],
            )
        )
    if not rows:
        rows.append(
            html.Tr(
                children=[
                    html.Td(
                        "No turn logs found.",
                        colSpan=8,
                        style={"padding": "24px", "textAlign": "center", "color": "#A3AED0"},
                    )
                ]
            )
        )
    return rows


def build_detail_content(turn: dict[str, Any]) -> list:
    if not turn:
        return [dmc.Text("Turn not found.", c="dimmed")]

    usage = turn.get("usage") or {}
    usage_text = ""
    if usage:
        usage_text = f"prompt={usage.get('prompt_tokens', '—')}, completion={usage.get('completion_tokens', '—')}"

    meta = dmc.SimpleGrid(
        cols=3,
        spacing="sm",
        mb="md",
        children=[
            dmc.Text(f"Request ID: {turn.get('request_id', '—')}", size="xs"),
            dmc.Text(f"Session: {turn.get('session_id') or '—'}", size="xs"),
            dmc.Text(f"Model: {turn.get('model') or '—'}", size="xs"),
            dmc.Text(f"Latency: {turn.get('latency_ms') or '—'} ms", size="xs"),
            dmc.Text(f"LLM rounds: {turn.get('llm_rounds') or '—'}", size="xs"),
            dmc.Text(f"Tools: {turn.get('tool_call_count') or '—'}", size="xs"),
            dmc.Text(
                f"Answer source: {(turn.get('post_process') or {}).get('answer_source', '—')}",
                size="xs",
            ),
            dmc.Text(f"Tokens: {usage_text or '—'}", size="xs", span=3),
        ],
    )

    sections: list = [
        meta,
        dmc.Text("User message", fw=600, size="sm", mb=4),
        dmc.Paper(
            p="sm",
            withBorder=True,
            radius="sm",
            mb="md",
            children=dmc.Text(str(turn.get("user_message") or "—"), size="sm", style={"whiteSpace": "pre-wrap"}),
        ),
        dmc.Text("Assistant answer", fw=600, size="sm", mb=4),
        dmc.Paper(
            p="sm",
            withBorder=True,
            radius="sm",
            mb="md",
            children=dmc.Text(str(turn.get("assistant_answer") or "—"), size="sm", style={"whiteSpace": "pre-wrap"}),
        ),
    ]

    clarification = turn.get("clarification")
    if clarification:
        choices = clarification.get("choices") or []
        choice_lines = [f"• {c.get('label', '')} → {c.get('value', '')}" for c in choices]
        sections.extend(
            [
                dmc.Text("Clarification", fw=600, size="sm", mb=4),
                dmc.Paper(
                    p="sm",
                    withBorder=True,
                    radius="sm",
                    mb="md",
                    children=[
                        dmc.Text(str(clarification.get("prompt") or ""), size="sm", mb="xs"),
                        *[dmc.Text(line, size="xs", c="dimmed") for line in choice_lines],
                    ],
                ),
            ]
        )

    fc = turn.get("frontend_context")
    if fc:
        sections.extend(
            [
                dmc.Text("Frontend context", fw=600, size="sm", mb=4),
                dmc.Code(json.dumps(fc, ensure_ascii=False, indent=2), block=True),
            ]
        )

    tools = turn.get("tools") or []
    if tools:
        tool_rows = [
            html.Tr(
                children=[
                    html.Td(str(t.get("name") or "")),
                    html.Td(str(t.get("status") or "")),
                    html.Td(str(t.get("rows") or "—")),
                    html.Td(str(t.get("source") or "—")),
                ]
            )
            for t in tools
        ]
        sections.extend(
            [
                dmc.Text("Tools", fw=600, size="sm", mb=4, mt="md"),
                html.Table(
                    [
                        html.Tr([html.Th("Name"), html.Th("Status"), html.Th("Rows"), html.Th("Source")]),
                        *tool_rows,
                    ],
                    style={"width": "100%", "fontSize": "12px"},
                ),
            ]
        )

    summary = turn.get("investigation_summary")
    if summary:
        sections.extend(
            [
                dmc.Text("Investigation summary", fw=600, size="sm", mb=4, mt="md"),
                dmc.Text(str(summary), size="sm"),
            ]
        )

    trace = turn.get("investigation_trace") or []
    if trace:
        sections.extend(
            [
                dmc.Text("Investigation trace", fw=600, size="sm", mb=4, mt="md"),
                dmc.Code(json.dumps(trace, ensure_ascii=False, indent=2), block=True),
            ]
        )

    stages = turn.get("pipeline_stages") or []
    if stages:
        stage_rows = [
            html.Tr(
                children=[
                    html.Td(str(s.get("name") or "")),
                    html.Td(str(s.get("duration_ms") or "—")),
                    html.Td(json.dumps(s.get("detail") or {}, ensure_ascii=False)[:120]),
                ]
            )
            for s in stages
        ]
        sections.extend(
            [
                dmc.Text("Pipeline stages", fw=600, size="sm", mb=4, mt="md"),
                html.Table(
                    [
                        html.Tr([html.Th("Stage"), html.Th("ms"), html.Th("Detail")]),
                        *stage_rows,
                    ],
                    style={"width": "100%", "fontSize": "12px"},
                ),
            ]
        )

    tool_execs = turn.get("tool_executions") or []
    if tool_execs:
        for t in tool_execs:
            sections.extend(
                [
                    dmc.Text(f"Tool output: {t.get('name')}", fw=600, size="sm", mb=4, mt="md"),
                    dmc.Code(
                        json.dumps(t.get("summary") or {}, ensure_ascii=False, indent=2)[:12000],
                        block=True,
                    ),
                ]
            )

    llm_calls = turn.get("llm_calls") or []
    if llm_calls:
        sections.extend(
            [
                dmc.Text("LLM calls", fw=600, size="sm", mb=4, mt="md"),
                dmc.Code(json.dumps(llm_calls, ensure_ascii=False, indent=2), block=True),
            ]
        )

    post = turn.get("post_process")
    if post:
        sections.extend(
            [
                dmc.Text("Post-process", fw=600, size="sm", mb=4, mt="md"),
                dmc.Code(json.dumps(post, ensure_ascii=False, indent=2), block=True),
            ]
        )

    scope = turn.get("scope_decision")
    if scope:
        sections.extend(
            [
                dmc.Text("Scope decision", fw=600, size="sm", mb=4, mt="md"),
                dmc.Code(json.dumps(scope, ensure_ascii=False, indent=2), block=True),
            ]
        )

    return sections


def pagination_label(skip: int, limit: int, total: int) -> str:
    if total <= 0:
        return "No records"
    start = skip + 1
    end = min(skip + limit, total)
    return f"Showing {start}–{end} of {total}"


def build_layout(search: str | None = None) -> html.Div:
    del search  # filters are client-side via callbacks
    filters = dmc.Paper(
        p="md",
        withBorder=True,
        radius="md",
        mb="md",
        children=[
            dmc.Group(
                grow=True,
                align="flex-end",
                children=[
                    dmc.Select(
                        id="chatbot-logs-status-filter",
                        label="Status",
                        data=STATUS_OPTIONS,
                        value="",
                        clearable=False,
                    ),
                    dmc.Select(
                        id="chatbot-logs-type-filter",
                        label="Response type",
                        data=TYPE_OPTIONS,
                        value="",
                        clearable=False,
                    ),
                    dmc.TextInput(id="chatbot-logs-username-filter", label="Username contains"),
                    dmc.TextInput(id="chatbot-logs-date-from", label="Date from (YYYY-MM-DD)"),
                    dmc.TextInput(id="chatbot-logs-date-to", label="Date to (YYYY-MM-DD)"),
                    dmc.Button("Refresh", id="chatbot-logs-refresh-btn", variant="light", color="indigo"),
                ],
            ),
        ],
    )

    table = dmc.Paper(
        p=0,
        radius="md",
        withBorder=True,
        children=[
            html.Div(
                style={"padding": "16px 20px", "borderBottom": "1px solid #eef1f4"},
                children=[
                    dmc.Group(
                        justify="space-between",
                        children=[
                            dmc.Text("Turn logs", fw=700, c=ON_SURFACE),
                            dmc.Text(id="chatbot-logs-pagination-text", children="Loading…", size="xs", c="dimmed"),
                        ],
                    )
                ],
            ),
            html.Div(
                style={"overflowX": "auto"},
                children=[
                    html.Table(
                        [
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("Time", style=_th()),
                                        html.Th("User", style=_th()),
                                        html.Th("Status", style=_th()),
                                        html.Th("Type", style=_th()),
                                        html.Th("User message", style=_th()),
                                        html.Th("Latency", style=_th()),
                                        html.Th("Tools", style=_th()),
                                        html.Th("Model", style=_th()),
                                    ]
                                )
                            ),
                            html.Tbody(id="chatbot-logs-table-body"),
                        ],
                        style={"width": "100%", "fontSize": "13px", "borderCollapse": "collapse"},
                    )
                ],
            ),
            html.Div(
                style={"padding": "12px 20px", "borderTop": "1px solid #eef1f4"},
                children=[
                    dmc.Group(
                        gap="sm",
                        children=[
                            dmc.Button("Previous", id="chatbot-logs-prev-btn", variant="default", size="xs"),
                            dmc.Button("Next", id="chatbot-logs-next-btn", variant="default", size="xs"),
                        ],
                    )
                ],
            ),
        ],
    )

    return html.Div(
        [
            dcc.Store(id="chatbot-logs-skip-store", data=0),
            dcc.Store(id="chatbot-logs-total-store", data=0),
            dmc.Modal(
                id="chatbot-logs-detail-modal",
                title="Turn detail",
                opened=False,
                size="xl",
                children=html.Div(id="chatbot-logs-detail-content"),
            ),
            settings_page_shell(
                [
                    section_header(
                        "AI Assistant logs",
                        "Redacted chatbot conversation turns stored in MongoDB.",
                        icon="solar:chat-round-dots-bold-duotone",
                    ),
                    filters,
                    table,
                ]
            ),
        ]
    )


def _th():
    return {
        "textAlign": "left",
        "padding": "12px 16px",
        "borderBottom": "1px solid #e9ecef",
        "color": "#2B3674",
        "fontSize": "11px",
        "textTransform": "uppercase",
    }
