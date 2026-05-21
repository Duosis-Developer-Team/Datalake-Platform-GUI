"""Annual Availability report: single DC + calendar year (AuraNotify + product catalog)."""

from __future__ import annotations

from datetime import datetime, timezone

import dash_mantine_components as dmc
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, callback, ctx, html, no_update

from src.components.dc_availability_panel import build_dc_availability_panel
from src.components.header import create_detail_header
from src.services import api_client as api
from src.utils.dc_display import format_dc_display_name
from src.utils.time_range import MIN_REPORT_YEAR, calendar_year_range, default_time_range


def _overall_availability_pct(item: dict | None) -> float:
    if not item:
        return 0.0
    try:
        return float(item.get("availability_pct") or 0.0)
    except (TypeError, ValueError):
        return 0.0


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


def _mini_horizontal_bar_figure(pct: float) -> go.Figure:
    pct = max(0.0, min(100.0, pct))
    color = _bar_color_for_pct(pct)
    fig = go.Figure(
        data=[
            go.Bar(
                x=[pct],
                y=[""],
                orientation="h",
                marker=dict(color=color),
                hovertemplate="%{x:.4f}%<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        height=40,
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(range=[0, 100], visible=False, fixedrange=True),
        yaxis=dict(visible=False, fixedrange=True),
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#EEF2F6",
        bargap=0.35,
    )
    return fig


def _truncate_label(text: str, max_len: int = 22) -> str:
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def build_availability_annual_layout(visible_sections: set[str] | None = None) -> html.Div:
    """Annual Availability sayfası: sticky header + tam genişlik DC grid + alt filtreler + detay."""

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

    tr_list = default_time_range()
    datacenters = api.get_all_datacenters_summary(tr_list)
    current_year = datetime.now(timezone.utc).year
    year_options = [
        {"value": str(y), "label": str(y)}
        for y in range(MIN_REPORT_YEAR, current_year + 1)
    ]
    dc_options: list[dict] = []
    default_dc_id: str | None = None
    for dc in datacenters:
        cid = dc.get("id")
        if cid is None:
            continue
        sid = str(cid)
        label = (
            format_dc_display_name(dc.get("name"), dc.get("description"))
            or str(dc.get("name") or sid)
        )
        dc_options.append({"value": sid, "label": label})
        if default_dc_id is None:
            default_dc_id = sid

    if not dc_options:
        return html.Div(
            dmc.Alert("No data centers available for this environment.", color="gray", variant="light"),
            style={"padding": "24px 32px"},
        )

    dc_count = len(dc_options)

    # ── Header: Year select sağ tarafa (right_extra), diğer sayfalarla uyumlu yükseklik ──
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
        subtitle_badge=f"{dc_count} Data Centers",
        subtitle_color="indigo",
        icon="solar:calendar-bold-duotone",
        time_range=None,
        tabs=None,
        right_extra=[
            html.Div(id="availability-annual-date-badge"),
            year_select_inline,
        ],
    )

    # ── Overview Grid ────────────────────────────────────────────────────
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
            html.Div(id="availability-annual-overview"),
        ],
    )

    # Hidden DC selector — driven by clicking overview cards.
    # Kept as a Select (instead of dcc.Store) so existing callbacks that read its
    # `.value` and write to it via the card-click callback keep working unchanged.
    filter_row = html.Div(
        style={"display": "none"},
        children=[
            dmc.Select(
                id="availability-annual-dc",
                data=dc_options,
                value=default_dc_id,
                clearable=False,
            ),
        ],
    )

    return html.Div([
        page_header,
        overview_section,
        filter_row,
        html.Div(id="availability-annual-body"),
    ])


@callback(
    Output("availability-annual-overview", "children"),
    Output("availability-annual-body", "children"),
    Output("availability-annual-date-badge", "children"),
    Input("availability-annual-year", "value"),
    Input("availability-annual-dc", "value"),
)
def _render_availability_annual(year, dc_id):
    current_year = datetime.now(timezone.utc).year
    try:
        y = int(year) if year is not None and str(year).strip() != "" else current_year
    except (TypeError, ValueError):
        y = current_year

    tr = calendar_year_range(y)
    sel = str(dc_id).strip() if dc_id not in (None, "") else ""

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
    items_map = api.get_dc_availability_sla_items_for_dcs(rows, tr) if rows else {}

    # --- Overview: premium kart per DC (sorted by display name)
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
        pct = _overall_availability_pct(items_map.get(sid))
        highlighted = bool(sel and sid == sel)
        accent_color, text_color, bg_color, bar_gradient = _sla_tier(pct)

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
                        "border": f"1.5px solid rgba(67,24,255,0.12)",
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
                        # İsim + büyük yüzde yan yana
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
                                    f"{pct:.4f}%",
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
                        # Premium CSS progress bar
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
                                        "width": f"{pct:.4f}%",
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

    overview_content = (
        dmc.SimpleGrid(
            cols={"base": 2, "md": 3, "lg": 4},
            spacing="sm",
            verticalSpacing="sm",
            children=overview_cards,
        )
        if overview_cards
        else dmc.Text("No data centers.", size="sm", c="dimmed")
    )

    if not sel:
        body = html.Div(
            style={"padding": "0 32px"},
            children=[
                dmc.Alert(
                    "Select a data center.",
                    color="gray",
                    variant="light",
                ),
            ],
        )
        return overview_content, body, date_badge

    row_by_id = {str(r.get("id")): r for r in all_dcs if r.get("id") is not None}
    row = row_by_id.get(sel)
    if not row:
        body = html.Div(
            style={"padding": "0 32px"},
            children=[dmc.Alert("No matching data center found.", color="orange", variant="light")],
        )
        return overview_content, body, date_badge

    intro = dmc.Text(
        f"Report period (UTC): {tr['start']} — {tr['end']}",
        size="sm",
        c="dimmed",
        mb="md",
    )

    sid = str(row.get("id"))
    display = format_dc_display_name(row.get("name"), row.get("description")) or str(row.get("name") or sid)
    item = items_map.get(sid)

    body = html.Div(
        style={"padding": "0 32px 32px"},
        children=[
            intro,
            html.Div(
                className="nexus-card",
                style={"padding": "8px 0 24px"},
                children=[build_dc_availability_panel(item, display)],
            ),
        ],
    )
    return overview_content, body, date_badge


@callback(
    Output("availability-annual-dc", "value"),
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
