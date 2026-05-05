"""Annual Availability report: single DC + calendar year (AuraNotify + product catalog)."""

from __future__ import annotations

from datetime import datetime, timezone

import dash_mantine_components as dmc
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from src.components.dc_availability_panel import build_dc_availability_panel
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
    """Shell: overview bar charts (all DCs) + compact filters on the right; detail via callback."""

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
    year_options = [{"value": str(y), "label": str(y)} for y in range(MIN_REPORT_YEAR, current_year + 1)]
    dc_options: list[dict] = []
    default_dc_id: str | None = None
    for dc in datacenters:
        cid = dc.get("id")
        if cid is None:
            continue
        sid = str(cid)
        label = format_dc_display_name(dc.get("name"), dc.get("description")) or str(dc.get("name") or sid)
        dc_options.append({"value": sid, "label": label})
        if default_dc_id is None:
            default_dc_id = sid

    if not dc_options:
        return html.Div(
            dmc.Alert("No data centers available for this environment.", color="gray", variant="light"),
            style={"padding": "24px 32px"},
        )

    header = html.Div(
        style={"padding": "0 32px 16px"},
        children=[
            dmc.Text("Annual Availability", fw=700, size="xl", c="#2B3674", mb="md"),
            dmc.Group(
                grow=True,
                align="flex-start",
                justify="space-between",
                wrap="wrap",
                gap="lg",
                styles={"root": {"alignItems": "flex-start"}},
                children=[
                    html.Div(
                        style={
                            "flex": "1 1 280px",
                            "minWidth": "min(100%, 280px)",
                            "maxWidth": "100%",
                        },
                        children=[
                            dmc.Text(
                                "All data centers — overall availability",
                                size="sm",
                                fw=600,
                                c="#344054",
                                mb="xs",
                            ),
                            dmc.Text(
                                "Compared for the selected report year (AuraNotify match).",
                                size="xs",
                                c="dimmed",
                                mb="sm",
                            ),
                            html.Div(
                                id="availability-annual-overview",
                                style={
                                    "maxHeight": "340px",
                                    "overflowY": "auto",
                                    "paddingRight": "6px",
                                },
                            ),
                        ],
                    ),
                    dmc.Stack(
                        gap="sm",
                        w=260,
                        maw=280,
                        miw=200,
                        style={"flexShrink": 0},
                        children=[
                            dmc.Select(
                                label="Year",
                                id="availability-annual-year",
                                data=year_options,
                                value=str(current_year),
                                w="100%",
                                searchable=False,
                                clearable=False,
                            ),
                            dmc.Select(
                                label="Data center",
                                id="availability-annual-dc",
                                data=dc_options,
                                value=default_dc_id,
                                searchable=True,
                                clearable=False,
                                nothingFoundMessage="No DCs",
                                w="100%",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )

    body = html.Div(id="availability-annual-body")
    return html.Div([header, body])


@callback(
    Output("availability-annual-overview", "children"),
    Output("availability-annual-body", "children"),
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

    tr_list = default_time_range()
    all_dcs = api.get_all_datacenters_summary(tr_list)
    rows = [r for r in all_dcs if r.get("id") is not None]
    items_map = api.get_dc_availability_sla_items_for_dcs(rows, tr) if rows else {}

    # --- Overview: small bar chart per DC (sorted by display name)
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
        short = _truncate_label(display, 24)
        pct = _overall_availability_pct(items_map.get(sid))
        highlighted = bool(sel and sid == sel)
        overview_cards.append(
            dmc.Paper(
                withBorder=True,
                p="xs",
                radius="sm",
                style={
                    "borderWidth": "2px",
                    "borderColor": "#4318FF" if highlighted else "#e9ecef",
                },
                children=[
                    dmc.Stack(
                        gap=2,
                        style={"minWidth": 0},
                        children=[
                            dmc.Text(short, size="xs", fw=600, c="#2B3674", lineClamp=2),
                            dmc.Text(f"{pct:.4f} %", size="xs", c="dimmed"),
                        ],
                    ),
                    dcc.Graph(
                        figure=_mini_horizontal_bar_figure(pct),
                        config={"displayModeBar": False},
                        style={"height": "44px"},
                    ),
                ],
            )
        )

    overview_content = (
        dmc.SimpleGrid(cols=3, spacing="sm", verticalSpacing="sm", children=overview_cards)
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
        return overview_content, body

    row_by_id = {str(r.get("id")): r for r in all_dcs if r.get("id") is not None}
    row = row_by_id.get(sel)
    if not row:
        body = html.Div(
            style={"padding": "0 32px"},
            children=[dmc.Alert("No matching data center found.", color="orange", variant="light")],
        )
        return overview_content, body

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
    return overview_content, body
