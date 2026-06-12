"""Annual Availability report: single DC + calendar year (AuraNotify + product catalog)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update

from src.components.dc_availability_panel import AvailabilityDataState, build_dc_availability_panel
from src.components.header import create_detail_header
from src.services import api_client as api
from src.utils.dc_display import format_dc_display_name
from src.utils.time_range import MIN_REPORT_YEAR, calendar_year_range, default_time_range

_MAX_SLA_RETRIES = 3
_SLA_POLL_INTERVAL_MS = 2000


def _overall_availability_pct(item: dict | None) -> Optional[float]:
    if not item:
        return None
    try:
        return float(item.get("availability_pct") or 0.0)
    except (TypeError, ValueError):
        return None


def _bar_color_for_pct(pct: float) -> str:
    if pct >= 99.999:
        return "#12B76A"
    if pct >= 99.9:
        return "#F79009"
    return "#F04438"


def _sla_tier(pct: float) -> tuple[str, str, str, str]:
    """Returns (accent_color, text_color, bg_color, bar_gradient)."""
    if pct >= 99.999:
        return "#12B76A", "#027A48", "rgba(18,183,106,0.07)", "linear-gradient(90deg,#6CE9A6,#12B76A)"
    if pct >= 99.9:
        return "#F79009", "#B54708", "rgba(247,144,9,0.07)", "linear-gradient(90deg,#FEC84B,#F79009)"
    return "#F04438", "#B42318", "rgba(240,68,56,0.07)", "linear-gradient(90deg,#FDA29B,#F04438)"


def _truncate_label(text: str, max_len: int = 22) -> str:
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _overview_loading_skeleton() -> html.Div:
    return dmc.SimpleGrid(
        cols={"base": 2, "md": 3, "lg": 4},
        spacing="sm",
        verticalSpacing="sm",
        children=[dmc.Skeleton(height=88, radius="md") for _ in range(8)],
    )


def _build_overview_cards(
    rows: list[dict],
    items_map: dict[str, dict | None],
    sel: str,
    *,
    sla_pending: bool,
) -> html.Div:
    overview_cards: list = []
    sorted_rows = sorted(
        rows,
        key=lambda r: (
            format_dc_display_name(r.get("name"), r.get("description"))
            or str(r.get("name") or str(r.get("id")))
        ).lower(),
    )
    for row in sorted_rows:
        sid = str(row.get("id"))
        display = format_dc_display_name(row.get("name"), row.get("description")) or str(
            row.get("name") or sid
        )
        short = _truncate_label(display, 26)
        pct_val = _overall_availability_pct(items_map.get(sid))
        highlighted = bool(sel and sid == sel)

        if sla_pending or pct_val is None:
            pct_label = "—"
            bar_width = "0%"
            accent_color, text_color, bar_gradient = "#A3AED0", "#A3AED0", "linear-gradient(90deg,#E4E7EC,#CBD5E1)"
        else:
            pct = pct_val
            pct_label = f"{pct:.4f}%"
            bar_width = f"{max(0.0, min(100.0, pct)):.4f}%"
            accent_color, text_color, _bg_color, bar_gradient = _sla_tier(pct)

        overview_cards.append(
            html.Div(
                id={"type": "availability-annual-card", "dc": sid},
                n_clicks=0,
                style={"cursor": "pointer"},
                children=dmc.Paper(
                    withBorder=False,
                    p="md",
                    radius="md",
                    style={
                        "border": "1.5px solid rgba(67,24,255,0.12)",
                        "borderLeft": f"4px solid {accent_color}",
                        "background": "rgba(237,233,254,0.45)" if highlighted else "rgba(255,255,255,0.95)",
                        "boxShadow": (
                            "0 0 0 2px #4318FF, 0 4px 16px rgba(67,24,255,0.13)"
                            if highlighted
                            else "0 1px 4px rgba(0,0,0,0.04)"
                        ),
                        "cursor": "pointer",
                        "transition": "box-shadow 0.2s ease",
                    },
                    children=[
                        dmc.Group(
                            justify="space-between",
                            align="flex-start",
                            mb=8,
                            children=[
                                dmc.Text(
                                    short,
                                    size="xs",
                                    fw=700,
                                    c="#2B3674",
                                    lineClamp=1,
                                    style={"flex": 1, "minWidth": 0},
                                ),
                                dmc.Text(
                                    pct_label,
                                    size="sm",
                                    fw=900,
                                    c=text_color,
                                    style={
                                        "fontVariantNumeric": "tabular-nums",
                                        "letterSpacing": "-0.02em",
                                        "flexShrink": 0,
                                        "marginLeft": "8px",
                                    },
                                ),
                            ],
                        ),
                        html.Div(
                            style={
                                "height": "7px",
                                "background": "rgba(67,24,255,0.07)",
                                "borderRadius": "99px",
                                "overflow": "hidden",
                            },
                            children=[
                                html.Div(
                                    style={
                                        "height": "100%",
                                        "width": bar_width,
                                        "background": bar_gradient,
                                        "borderRadius": "99px",
                                    }
                                )
                            ],
                        ),
                    ],
                ),
            )
        )

    return dmc.SimpleGrid(
        cols={"base": 2, "md": 3, "lg": 4},
        spacing="sm",
        verticalSpacing="sm",
        children=overview_cards,
    )


def _resolve_panel_state(
    sla_status: str,
    item: dict | None,
    raw_count: int,
) -> AvailabilityDataState:
    if sla_status in ("error", "empty") and raw_count == 0:
        return "fetch_failed"
    if item:
        return "ok"
    if raw_count > 0:
        return "no_match"
    return "fetch_failed"


def build_availability_annual_layout(visible_sections: set[str] | None = None) -> html.Div:
    """Annual Availability: non-blocking shell; data loaded via callbacks."""

    def _sec(code: str) -> bool:
        if visible_sections is None:
            return True
        return code in visible_sections

    if not _sec("sec:availability_annual:report"):
        return html.Div(
            dmc.Alert(
                "You do not have permission to view this report.",
                color="red",
                variant="light",
            ),
            style={"padding": "24px"},
        )

    current_year = datetime.now(timezone.utc).year
    year_options = [
        {"value": str(y), "label": str(y)}
        for y in range(MIN_REPORT_YEAR, current_year + 1)
    ]

    year_select_inline = dmc.Select(
        id="availability-annual-year",
        data=year_options,
        value=str(current_year),
        w=110,
        size="sm",
        searchable=False,
        clearable=False,
        styles={"input": {"fontWeight": 700, "color": "#4318FF"}},
    )

    page_header = create_detail_header(
        title="Annual Availability",
        back_href="/",
        back_label="Overview",
        subtitle_badge="Loading data centers…",
        subtitle_color="indigo",
        icon="solar:calendar-bold-duotone",
        time_range=None,
        tabs=None,
        right_extra=[
            html.Div(id="availability-annual-date-badge"),
            year_select_inline,
        ],
    )

    overview_section = html.Div(
        style={"padding": "0 32px", "marginBottom": "16px"},
        children=[
            dmc.Text(
                "All data centers — overall availability",
                size="sm",
                fw=600,
                c="#344054",
                mb=4,
            ),
            dmc.Text(
                "Compared for the selected report year (AuraNotify match).",
                size="xs",
                c="dimmed",
                mb="sm",
            ),
            dcc.Loading(
                id="availability-annual-overview-loading",
                type="circle",
                color="#4318FF",
                delay_show=200,
                children=html.Div(id="availability-annual-overview"),
            ),
        ],
    )

    filter_row = html.Div(
        style={"display": "none"},
        children=[
            dmc.Select(
                id="availability-annual-dc",
                data=[],
                value=None,
                clearable=False,
            ),
        ],
    )

    return html.Div([
        page_header,
        overview_section,
        filter_row,
        dcc.Store(id="availability-annual-sla-retry-store", data={"attempts": 0, "year": str(current_year)}),
        dcc.Interval(
            id="availability-annual-sla-poll",
            interval=_SLA_POLL_INTERVAL_MS,
            n_intervals=0,
            disabled=True,
        ),
        dcc.Loading(
            id="availability-annual-body-loading",
            type="circle",
            color="#4318FF",
            delay_show=200,
            children=html.Div(id="availability-annual-body"),
        ),
    ])


@callback(
    Output("availability-annual-overview", "children"),
    Output("availability-annual-body", "children"),
    Output("availability-annual-date-badge", "children"),
    Output("availability-annual-dc", "data"),
    Output("availability-annual-dc", "value"),
    Output("availability-annual-sla-poll", "disabled"),
    Output("availability-annual-sla-retry-store", "data"),
    Input("availability-annual-year", "value"),
    Input("availability-annual-dc", "value"),
    Input("availability-annual-sla-poll", "n_intervals"),
    State("availability-annual-sla-retry-store", "data"),
)
def _render_availability_annual(year, dc_id, _poll_n, retry_store):
    current_year = datetime.now(timezone.utc).year
    try:
        y = int(year) if year is not None and str(year).strip() != "" else current_year
    except (TypeError, ValueError):
        y = current_year

    tr = calendar_year_range(y)
    year_key = str(y)
    sel = str(dc_id).strip() if dc_id not in (None, "") else ""

    retry_data = retry_store if isinstance(retry_store, dict) else {}
    attempts = int(retry_data.get("attempts") or 0)
    if retry_data.get("year") != year_key:
        attempts = 0

    triggered = ctx.triggered_id
    force_refresh = triggered == "availability-annual-sla-poll"

    date_badge = dmc.Badge(
        children=dmc.Group(
            gap=6,
            align="center",
            children=[
                dmc.Text(f"{tr['start']} – {tr['end']}", size="xs"),
            ],
        ),
        variant="light",
        color="indigo",
        radius="xl",
        size="md",
        style={"textTransform": "none", "fontWeight": 500, "letterSpacing": 0},
    )

    tr_list = default_time_range()
    all_dcs = api.get_all_datacenters_summary(tr_list)
    rows = [r for r in all_dcs if r.get("id") is not None]

    dc_options: list[dict] = []
    first_dc_id: str | None = None
    for dc in rows:
        sid = str(dc.get("id"))
        label = format_dc_display_name(dc.get("name"), dc.get("description")) or str(dc.get("name") or sid)
        dc_options.append({"value": sid, "label": label})
        if first_dc_id is None:
            first_dc_id = sid

    dc_value_out = no_update
    if not sel and first_dc_id:
        sel = first_dc_id
        dc_value_out = first_dc_id

    if not rows:
        empty_alert = dmc.Alert("No data centers available for this environment.", color="gray", variant="light")
        return (
            empty_alert,
            html.Div(style={"padding": "0 32px"}, children=[empty_alert]),
            date_badge,
            [],
            None,
            True,
            {"attempts": 0, "year": year_key},
        )

    sla_batch = api.get_dc_availability_sla_items_for_dcs(rows, tr, force_refresh=force_refresh)
    sla_status = sla_batch.get("status", "error")
    items_map = sla_batch.get("items_map") or {}
    raw_count = int(sla_batch.get("raw_count") or 0)

    sla_pending = sla_status in ("error", "empty") and raw_count == 0
    should_retry = sla_pending and attempts < _MAX_SLA_RETRIES
    poll_disabled = not should_retry
    if not sla_pending:
        next_attempts = 0
    elif triggered == "availability-annual-sla-poll":
        next_attempts = attempts + 1
    else:
        next_attempts = attempts
    retry_out = {"attempts": next_attempts, "year": year_key}

    if sla_pending:
        overview_content = _overview_loading_skeleton()
    else:
        overview_content = _build_overview_cards(rows, items_map, sel, sla_pending=False)

    if not sel:
        body = html.Div(
            style={"padding": "0 32px"},
            children=[dmc.Alert("Select a data center.", color="gray", variant="light")],
        )
        return overview_content, body, date_badge, dc_options, dc_value_out, poll_disabled, retry_out

    row_by_id = {str(r.get("id")): r for r in rows}
    row = row_by_id.get(sel)
    if not row:
        body = html.Div(
            style={"padding": "0 32px"},
            children=[dmc.Alert("No matching data center found.", color="orange", variant="light")],
        )
        return overview_content, body, date_badge, dc_options, dc_value_out, poll_disabled, retry_out

    intro = dmc.Text(
        f"Report period (UTC): {tr['start']} — {tr['end']}",
        size="sm",
        c="dimmed",
        mb="md",
    )

    sid = str(row.get("id"))
    display = format_dc_display_name(row.get("name"), row.get("description")) or str(row.get("name") or sid)
    item = items_map.get(sid)
    panel_state: AvailabilityDataState = "loading" if sla_pending else _resolve_panel_state(sla_status, item, raw_count)

    body = html.Div(
        style={"padding": "0 32px 32px"},
        children=[
            intro,
            html.Div(
                className="nexus-card",
                style={"padding": "8px 0 24px"},
                children=[build_dc_availability_panel(item, display, data_state=panel_state)],
            ),
        ],
    )
    return overview_content, body, date_badge, dc_options, dc_value_out, poll_disabled, retry_out


@callback(
    Output("availability-annual-dc", "value", allow_duplicate=True),
    Input({"type": "availability-annual-card", "dc": ALL}, "n_clicks"),
    State("availability-annual-dc", "value"),
    prevent_initial_call=True,
)
def _select_dc_from_card(_clicks, current):
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        return no_update
    new_dc = str(triggered.get("dc") or "")
    if not new_dc or new_dc == str(current or ""):
        return no_update
    return new_dc
