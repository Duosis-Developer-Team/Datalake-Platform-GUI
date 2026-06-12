"""Bulutistan AI Assistant — floating chatbot widget for the Dash WebUI.

Self-contained, non-invasive add-on (CTO pack 04):
* ``build_chatbot_shell()`` returns the floating button + panel (added once to
  ``app.layout``).
* ``register_chatbot_callbacks(app)`` wires the callbacks: toggle panel, sync
  page context, and a two-phase send (instant user bubble + typing indicator,
  then the real answer) so the conversation stays visible while the model works.
* All network calls go server-side through ``src.services.chatbot_client`` to the
  internal chatbot-api — the browser never sees the LLM token.

Required component ids: chatbot-fab, chatbot-panel, chatbot-close-button,
chatbot-messages, chatbot-input, chatbot-send-button, chatbot-status. Stores
(chatbot-open-store / -history-store / -context-store / -pending-store) live in
``app.layout``. Auto-scroll + Enter-to-send are handled by ``assets/chatbot.js``.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

import dash_mantine_components as dmc
from dash import Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from dash_iconify import DashIconify

from src.services.chatbot_client import send_chat_message

logger = logging.getLogger(__name__)

_ERR_MSG = (
    "Şu an cevabı getiremedim (AI servisine ulaşılamadı). "
    "Lütfen birkaç saniye sonra tekrar dene."
)
_ASSISTANT_ICON = "solar:chat-round-line-duotone"

# Datacenter code in the path, e.g. /datacenter/DC13, /dc-detail/AZ2, /dc/ICT1.
_DC_PATH = re.compile(r"/(?:datacenter|dc-detail|dc)/([A-Za-z]{2,4}\d+)", re.IGNORECASE)

_PAGE_LABELS = {
    "/": "Genel Bakış",
    "/datacenters": "Datacenter'lar",
    "/global-view": "Global Görünüm",
    "/customers": "Müşteri Listesi",
    "/customer-view": "Müşteri Görünümü",
    "/availability-annual": "Yıllık Erişilebilirlik",
    "/query-explorer": "Query Explorer",
    "/crm/sellable-potential": "Satılabilir Potansiyel",
    "/region-drilldown": "Bölge Detayı",
}

_SUGGESTIONS = {
    "/": ["Genel kapasite durumunu özetle", "En yoğun datacenter hangisi?"],
    "/datacenters": ["En yoğun datacenter hangisi?", "Datacenter'ları karşılaştır"],
    "/global-view": ["Global kapasite dağılımını özetle", "Hangi bölge en yoğun?"],
    "/customers": ["En büyük müşterileri listele", "Müşteri kaynak kullanımını özetle"],
    "/customer-view": ["Seçili müşterinin kaynak kullanımını özetle", "SLA durumunu açıkla"],
    "/availability-annual": ["Yıllık erişilebilirlik trendini özetle", "En düşük SLA hangi müşteride?"],
    "/crm/sellable-potential": ["Öne çıkan satılabilir fırsatlar neler?", "Hangi panel riskli?"],
    "/query-explorer": ["Bu query sonuçlarını nasıl yorumlamalıyım?"],
    "/region-drilldown": ["Bu bölgedeki kapasiteyi özetle", "Hangi datacenter en yoğun?"],
}
_DEFAULT_SUGGESTIONS = [
    "Genel kapasite durumunu özetle",
    "En yoğun datacenter hangisi?",
]


# --------------------------------------------------------------------------- #
# Pure context helpers (unit-tested)
# --------------------------------------------------------------------------- #


def extract_datacenter(pathname: Optional[str]) -> Optional[str]:
    """Return the DC code embedded in the path, or None."""
    if not pathname:
        return None
    m = _DC_PATH.search(pathname)
    return m.group(1).upper() if m else None


def _is_administration_path(pathname: Optional[str]) -> bool:
    p = str(pathname or "")
    return p.startswith("/administration") or p.startswith("/settings")


def _page_label(pathname: Optional[str]) -> str:
    p = (pathname or "/").rstrip("/") or "/"
    if p in _PAGE_LABELS:
        return _PAGE_LABELS[p]
    if _is_administration_path(p):
        return "Yönetim / Ayarlar"
    dc = extract_datacenter(p)
    if dc:
        return f"Datacenter {dc}"
    return "Bulutistan Datalake"


def _suggestions_for(pathname: Optional[str]) -> list[str]:
    p = (pathname or "/").rstrip("/") or "/"
    if p in _SUGGESTIONS:
        return _SUGGESTIONS[p]
    if _is_administration_path(p):
        return ["Bu ayar ekranını özetle", "Entegrasyon durumunu açıkla"]
    if extract_datacenter(p):
        return ["Bu datacenter'ı özetle", "Riskli kaynakları yorumla"]
    return _DEFAULT_SUGGESTIONS


def extract_context(
    pathname: Optional[str],
    search: Optional[str],
    time_range: Optional[dict],
    selected_customer: Optional[str],
) -> dict[str, Any]:
    """Build the frontend_context payload sent with each message."""
    return {
        "pathname": pathname or "/",
        "search": search or "",
        "time_range": time_range or {},
        "selected_customer": (selected_customer or None),
        "selected_datacenter": extract_datacenter(pathname),
        "page_title": _page_label(pathname),
        "visible_sections": None,
    }


# --------------------------------------------------------------------------- #
# Rendering (ChatGPT-style rows: avatar + bubble)
# --------------------------------------------------------------------------- #


def _suggestion_chip(text: str) -> Any:
    return html.Div(text, className="chatbot-suggestion", **{"data-suggestion": text})


def _empty_state(pathname: Optional[str] = None) -> Any:
    return html.Div(
        className="chatbot-empty",
        children=[
            html.Div(
                DashIconify(icon=_ASSISTANT_ICON, width=30, color="#FFFFFF"),
                className="chatbot-empty-badge",
            ),
            html.Div("Bulutistan AI Assistant", className="chatbot-empty-title"),
            html.Div(
                "Datacenter, müşteri, SLA, backup, S3 ve CRM metrikleri hakkında "
                "soru sorabilirsin.",
                className="chatbot-empty-text",
            ),
            html.Div(
                [_suggestion_chip(s) for s in _suggestions_for(pathname)],
                className="chatbot-suggestions",
            ),
        ],
    )


def _avatar() -> Any:
    return html.Div(
        DashIconify(icon=_ASSISTANT_ICON, width=16, color="#FFFFFF"),
        className="chatbot-avatar",
    )


def _choice_button(choice: dict) -> Any:
    return html.Button(
        choice.get("label", "?"),
        className="chatbot-choice",
        type="button",
        **{"data-choice-value": str(choice.get("value") or choice.get("id") or "")},
    )


def _render_block(block: dict) -> Any:
    btype = str(block.get("type") or "markdown")
    if btype == "table":
        cols = block.get("columns") or []
        rows = block.get("rows") or []
        header = html.Tr([html.Th(c) for c in cols]) if cols else None
        body = [
            html.Tr([html.Td(cell) for cell in row])
            for row in rows
            if isinstance(row, (list, tuple))
        ]
        table = html.Table(
            [header, *body] if header else body,
            className="chatbot-data-table",
        )
        return html.Div(table, className="chatbot-table-scroll")
    return dcc.Markdown(str(block.get("content") or ""), className="chatbot-markdown", link_target="_blank")


def _render_debug_panel(debug: dict) -> Any:
    if not isinstance(debug, dict):
        return None
    stages = debug.get("pipeline_stages") or []
    tools = debug.get("tools") or []
    llm_calls = debug.get("llm_calls") or []
    post = debug.get("post_process") or {}
    summary = (
        f"{debug.get('tool_call_count', 0)} tools · "
        f"{debug.get('llm_rounds', 0)} LLM · "
        f"{debug.get('latency_ms', 0)} ms · "
        f"{post.get('answer_source', 'llm')}"
    )
    stage_lines = [
        html.Li(f"{s.get('name')}: {s.get('duration_ms', 0)} ms")
        for s in stages
        if isinstance(s, dict)
    ]
    tool_rows = [
        html.Tr(
            children=[
                html.Td(str(t.get("name") or "")),
                html.Td(str(t.get("status") or "")),
                html.Td(str(t.get("rows") or "—")),
            ]
        )
        for t in tools
        if isinstance(t, dict)
    ]
    llm_lines = [
        html.Li(
            f"{c.get('phase')}: {c.get('model') or '—'} "
            f"({c.get('prompt_tokens', '—')}/{c.get('completion_tokens', '—')} tok)"
        )
        for c in llm_calls
        if isinstance(c, dict)
    ]
    return html.Details(
        [
            html.Summary(f"Investigation — {summary}", className="chatbot-debug-summary"),
            html.Ul(stage_lines, className="chatbot-debug-stages") if stage_lines else None,
            html.Table(
                [
                    html.Tr([html.Th("Tool"), html.Th("Status"), html.Th("Rows")]),
                    *tool_rows,
                ],
                className="chatbot-debug-tools",
            )
            if tool_rows
            else None,
            html.Ul(llm_lines, className="chatbot-debug-llm") if llm_lines else None,
        ],
        className="chatbot-debug-panel",
        open=False,
    )


def _bubble(
    role: str,
    content: str,
    used_tools: Optional[list] = None,
    error: bool = False,
    clarification: Optional[dict] = None,
    response_type: Optional[str] = None,
    blocks: Optional[list] = None,
    debug: Optional[dict] = None,
) -> Any:
    if role == "user":
        return html.Div(
            html.Div(content, className="chatbot-bubble-user"),
            className="chatbot-row chatbot-row-user",
        )
    cls = "chatbot-bubble-assistant" + (" chatbot-bubble-error" if error else "")
    inner: list[Any] = []
    if blocks:
        inner.extend(_render_block(b) for b in blocks if isinstance(b, dict))
    elif content:
        inner.append(dcc.Markdown(content, className="chatbot-markdown", link_target="_blank"))
    if response_type == "clarification" and isinstance(clarification, dict):
        choices = clarification.get("choices") or []
        choice_nodes = [
            _choice_button(c) for c in choices if isinstance(c, dict) and c.get("label")
        ]
        if choice_nodes:
            inner.append(html.Div(choice_nodes, className="chatbot-choice-row"))
    if used_tools:
        names = ", ".join(
            t.get("name", "") for t in used_tools if isinstance(t, dict) and t.get("name")
        )
        if names:
            inner.append(html.Div(f"Kaynak: {names}", className="chatbot-sources"))
    debug_panel = _render_debug_panel(debug) if debug else None
    if debug_panel is not None:
        inner.append(debug_panel)
    return html.Div(
        [_avatar(), html.Div(inner, className=cls)],
        className="chatbot-row chatbot-row-assistant",
    )


def _typing_bubble() -> Any:
    return html.Div(
        [
            _avatar(),
            html.Div(
                [
                    html.Div([html.Span(), html.Span(), html.Span()], className="chatbot-loading-dots"),
                    html.Div("Veri kaynakları analiz ediliyor…", className="chatbot-typing-label"),
                ],
                className="chatbot-bubble-assistant chatbot-typing",
            ),
        ],
        className="chatbot-row chatbot-row-assistant",
    )


def reset_chatbot_session(pathname: Optional[str] = None) -> dict[str, Any]:
    """Clear conversation state when the user closes the panel via X."""
    return {
        "history": [],
        "messages": _empty_state(pathname),
        "pending": None,
        "status": "",
        "input": "",
    }


def _render_messages(history: Optional[list], pathname: Optional[str] = None) -> Any:
    history = history or []
    if not history:
        return _empty_state(pathname)
    return [
        _bubble(
            m.get("role", "assistant"),
            m.get("content", ""),
            m.get("used_tools"),
            bool(m.get("error")),
            m.get("clarification"),
            m.get("response_type"),
            m.get("blocks"),
            m.get("debug"),
        )
        for m in history
    ]


# --------------------------------------------------------------------------- #
# Shell
# --------------------------------------------------------------------------- #


def build_chatbot_shell() -> Any:
    """Floating button + slide-in panel. Add once to ``app.layout``."""
    return html.Div(
        className="chatbot-root",
        children=[
            html.Button(
                DashIconify(icon=_ASSISTANT_ICON, width=26, color="#FFFFFF"),
                id="chatbot-fab",
                className="chatbot-fab",
                n_clicks=0,
                title="Bulutistan AI Assistant",
                **{"aria-label": "Bulutistan AI Assistant sohbetini aç"},
            ),
            html.Div(
                id="chatbot-panel",
                className="chatbot-panel",
                children=[
                    html.Div(
                        className="chatbot-header",
                        children=[
                            html.Div(
                                className="chatbot-header-left",
                                children=[
                                    html.Div(
                                        DashIconify(icon=_ASSISTANT_ICON, width=20, color="#FFFFFF"),
                                        className="chatbot-header-badge",
                                    ),
                                    html.Div(
                                        [
                                            html.Div("Bulutistan AI Assistant", className="chatbot-title"),
                                            html.Div(id="chatbot-subtitle", className="chatbot-subtitle"),
                                        ]
                                    ),
                                ],
                            ),
                            html.Button(
                                DashIconify(icon="mdi:arrow-expand", width=20),
                                id="chatbot-expand-button",
                                className="chatbot-expand-button",
                                n_clicks=0,
                                title="Genişlet",
                                **{"aria-label": "Sohbet panelini genişlet"},
                            ),
                            html.Button(
                                DashIconify(icon="mdi:close", width=20),
                                id="chatbot-close-button",
                                className="chatbot-close-button",
                                n_clicks=0,
                                **{"aria-label": "Sohbeti kapat"},
                            ),
                        ],
                    ),
                    # Messages — a direct flex child (no Loading overlay) so the
                    # conversation stays visible and the area scrolls.
                    html.Div(
                        id="chatbot-messages",
                        className="chatbot-messages",
                        children=_empty_state(),
                    ),
                    html.Div(id="chatbot-status", className="chatbot-status"),
                    html.Div(
                        className="chatbot-input-row",
                        children=[
                            dmc.Textarea(
                                id="chatbot-input",
                                placeholder="Bir soru sor…",
                                autosize=True,
                                minRows=1,
                                maxRows=4,
                                className="chatbot-input",
                                style={"flex": 1},
                            ),
                            html.Button(
                                DashIconify(icon="solar:plain-2-bold", width=20, color="#FFFFFF"),
                                id="chatbot-send-button",
                                className="chatbot-send-button",
                                n_clicks=0,
                                **{"aria-label": "Gönder"},
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


# --------------------------------------------------------------------------- #
# Callbacks
# --------------------------------------------------------------------------- #


def register_chatbot_callbacks(app) -> None:
    """Register the chatbot callbacks on ``app``. Idempotent per process."""

    @app.callback(
        Output("chatbot-open-store", "data"),
        Output("chatbot-panel", "className"),
        Output("chatbot-fab", "className"),
        Output("chatbot-expanded-store", "data", allow_duplicate=True),
        Output("chatbot-history-store", "data", allow_duplicate=True),
        Output("chatbot-messages", "children", allow_duplicate=True),
        Output("chatbot-pending-store", "data", allow_duplicate=True),
        Output("chatbot-status", "children", allow_duplicate=True),
        Output("chatbot-input", "value", allow_duplicate=True),
        Input("chatbot-fab", "n_clicks"),
        Input("chatbot-close-button", "n_clicks"),
        State("chatbot-open-store", "data"),
        State("chatbot-context-store", "data"),
        prevent_initial_call=True,
    )
    def _toggle_panel(_fab, _close, is_open, context):
        trigger = ctx.triggered_id
        pathname = (context or {}).get("pathname")
        if trigger == "chatbot-close-button":
            open_ = False
            panel_cls = "chatbot-panel"
            fab_cls = "chatbot-fab"
            cleared = reset_chatbot_session(pathname)
            return (
                open_,
                panel_cls,
                fab_cls,
                False,
                cleared["history"],
                cleared["messages"],
                cleared["pending"],
                cleared["status"],
                cleared["input"],
            )
        if trigger == "chatbot-fab":
            open_ = not bool(is_open)
        else:  # pragma: no cover - defensive
            raise PreventUpdate
        panel_cls = "chatbot-panel open" if open_ else "chatbot-panel"
        fab_cls = "chatbot-fab active" if open_ else "chatbot-fab"
        return open_, panel_cls, fab_cls, no_update, no_update, no_update, no_update, no_update, no_update

    @app.callback(
        Output("chatbot-expanded-store", "data"),
        Output("chatbot-panel", "className", allow_duplicate=True),
        Input("chatbot-expand-button", "n_clicks"),
        State("chatbot-expanded-store", "data"),
        State("chatbot-open-store", "data"),
        prevent_initial_call=True,
    )
    def _toggle_expand(_n, expanded, is_open):
        expanded = not bool(expanded)
        base = "chatbot-panel open" if is_open else "chatbot-panel"
        if expanded and is_open:
            base += " chatbot-panel-expanded"
        return expanded, base

    @app.callback(
        Output("chatbot-context-store", "data"),
        Output("chatbot-subtitle", "children"),
        Input("url", "pathname"),
        Input("url", "search"),
        Input("app-time-range", "data"),
        Input("customer-select", "value"),
    )
    def _sync_context(pathname, search, time_range, customer):
        try:
            context = extract_context(pathname, search, time_range, customer)
            return context, context.get("page_title", "")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("chatbot context sync failed: %s", exc)
            return {}, ""

    # Phase 1 — instant: echo the user bubble + a typing indicator, then hand off
    # to phase 2 via the pending store. No HTTP here, so it returns immediately.
    @app.callback(
        Output("chatbot-history-store", "data", allow_duplicate=True),
        Output("chatbot-messages", "children", allow_duplicate=True),
        Output("chatbot-input", "value"),
        Output("chatbot-status", "children", allow_duplicate=True),
        Output("chatbot-pending-store", "data"),
        Input("chatbot-send-button", "n_clicks"),
        State("chatbot-input", "value"),
        State("chatbot-history-store", "data"),
        State("chatbot-context-store", "data"),
        prevent_initial_call=True,
    )
    def _on_send(_n_clicks, value, history, context):
        message = (value or "").strip()
        history = history or []
        if not message:
            raise PreventUpdate
        new_history = history + [{"role": "user", "content": message}]
        pathname = (context or {}).get("pathname")
        rendered = _render_messages(new_history, pathname) + [_typing_bubble()]
        pending = {"message": message, "history": history, "context": context or {}}
        return new_history, rendered, "", "", pending

    # Phase 2 — the actual server-side request; replaces the typing indicator with
    # the assistant's answer (or a friendly error bubble).
    @app.callback(
        Output("chatbot-history-store", "data", allow_duplicate=True),
        Output("chatbot-messages", "children", allow_duplicate=True),
        Output("chatbot-status", "children", allow_duplicate=True),
        Output("chatbot-pending-store", "data", allow_duplicate=True),
        Input("chatbot-pending-store", "data"),
        State("auth-permissions-store", "data"),
        prevent_initial_call=True,
    )
    def _on_pending(pending, permissions):
        if not pending:
            raise PreventUpdate
        message = pending.get("message", "")
        history = pending.get("history") or []
        context = pending.get("context") or {}
        new_history = history + [{"role": "user", "content": message}]
        status = ""
        include_debug = False
        if permissions is None:
            include_debug = True
        elif isinstance(permissions, dict):
            perm = permissions.get("action:chatbot:audit:read") or {}
            include_debug = bool(perm.get("view"))
        try:
            resp = send_chat_message(message, history, context, include_debug=include_debug)
            answer = (resp.get("answer") or "").strip() or "(boş cevap döndü)"
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": answer,
                "used_tools": resp.get("used_tools") or [],
            }
            if resp.get("response_type") == "clarification":
                assistant_msg["response_type"] = "clarification"
                if resp.get("clarification"):
                    assistant_msg["clarification"] = resp.get("clarification")
            if resp.get("blocks"):
                assistant_msg["blocks"] = resp.get("blocks")
            if resp.get("debug"):
                assistant_msg["debug"] = resp.get("debug")
            new_history = new_history + [assistant_msg]
        except Exception as exc:
            logger.warning("chatbot send failed: %s", exc)
            new_history = new_history + [{"role": "assistant", "content": _ERR_MSG, "error": True}]
            status = "Bağlantı hatası — tekrar deneyebilirsin."
        rendered = _render_messages(new_history, context.get("pathname"))
        return new_history, rendered, status, None
