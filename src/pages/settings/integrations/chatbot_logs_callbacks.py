"""Dash callbacks for AI Assistant log viewer."""

from __future__ import annotations

from dash import ALL, Input, Output, State, callback, ctx, no_update

from src.pages.settings.integrations.chatbot_logs import (
    PAGE_LIMIT,
    build_detail_content,
    build_table_rows,
    pagination_label,
)
from src.services import chatbot_log_client


def _list_kwargs(status, response_type, username, date_from, date_to, skip):
    return {
        "skip": skip,
        "limit": PAGE_LIMIT,
        "status": status or None,
        "response_type": response_type or None,
        "username": username or None,
        "date_from": date_from or None,
        "date_to": date_to or None,
    }


@callback(
    Output("chatbot-logs-table-body", "children"),
    Output("chatbot-logs-pagination-text", "children"),
    Output("chatbot-logs-skip-store", "data"),
    Output("chatbot-logs-total-store", "data"),
    Input("chatbot-logs-refresh-btn", "n_clicks"),
    Input("chatbot-logs-prev-btn", "n_clicks"),
    Input("chatbot-logs-next-btn", "n_clicks"),
    Input("chatbot-logs-status-filter", "value"),
    Input("chatbot-logs-type-filter", "value"),
    Input("chatbot-logs-username-filter", "value"),
    Input("chatbot-logs-date-from", "value"),
    Input("chatbot-logs-date-to", "value"),
    State("chatbot-logs-skip-store", "data"),
    State("chatbot-logs-total-store", "data"),
    prevent_initial_call=False,
)
def refresh_chatbot_logs(
    _refresh,
    _prev,
    _next,
    status,
    response_type,
    username,
    date_from,
    date_to,
    skip,
    total,
):
    skip = int(skip or 0)
    total = int(total or 0)
    triggered = ctx.triggered_id

    if triggered == "chatbot-logs-prev-btn":
        skip = max(0, skip - PAGE_LIMIT)
    elif triggered == "chatbot-logs-next-btn":
        if skip + PAGE_LIMIT < total:
            skip = skip + PAGE_LIMIT
    elif triggered in (
        "chatbot-logs-refresh-btn",
        "chatbot-logs-status-filter",
        "chatbot-logs-type-filter",
        "chatbot-logs-username-filter",
        "chatbot-logs-date-from",
        "chatbot-logs-date-to",
    ):
        skip = 0

    data = chatbot_log_client.list_turns(**_list_kwargs(status, response_type, username, date_from, date_to, skip))
    items = data.get("items") or []
    total = int(data.get("total") or 0)
    rows = build_table_rows(items)
    label = pagination_label(skip, PAGE_LIMIT, total)
    if data.get("error"):
        label = f"{label} (load error)"
    return rows, label, skip, total


@callback(
    Output("chatbot-logs-detail-modal", "opened"),
    Output("chatbot-logs-detail-content", "children"),
    Input({"type": "chatbot-log-row", "request_id": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def open_chatbot_log_detail(_n_clicks):
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict) or triggered.get("type") != "chatbot-log-row":
        return no_update, no_update
    if not ctx.triggered or not (ctx.triggered[0] or {}).get("value"):
        return no_update, no_update
    request_id = str(triggered.get("request_id") or "").strip()
    if not request_id:
        return no_update, no_update
    turn = chatbot_log_client.get_turn(request_id)
    return True, build_detail_content(turn or {})


@callback(
    Output("chatbot-logs-detail-modal", "opened", allow_duplicate=True),
    Input("chatbot-logs-detail-modal", "close"),
    prevent_initial_call=True,
)
def close_chatbot_log_modal(_):
    return False
