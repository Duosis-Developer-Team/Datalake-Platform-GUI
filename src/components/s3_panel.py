from datetime import datetime
from typing import Iterable

from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objects as go

from src.utils.format_units import smart_bytes, pct_float


def _compute_dc_aggregates(s3_data: dict, selected_pools: Iterable[str] | None) -> dict:
    """Aggregate S3 metrics for the selected pools."""
    pools = s3_data.get("pools") or []
    if not pools:
        return {"pools": [], "total_usable": 0, "total_used": 0, "growth": 0}

    chosen = set(selected_pools or pools)
    latest = s3_data.get("latest") or {}
    growth = s3_data.get("growth") or {}

    total_usable = 0
    total_used = 0
    total_growth = 0
    active_pools: list[str] = []

    for name in pools:
        if name not in chosen:
            continue
        latest_row = latest.get(name) or {}
        growth_row = growth.get(name) or {}
        usable = int(latest_row.get("usable_bytes", 0) or 0)
        used = int(latest_row.get("used_bytes", 0) or 0)
        delta = int(growth_row.get("delta_used_bytes", 0) or 0)
        total_usable += usable
        total_used += used
        total_growth += delta
        active_pools.append(name)

    return {
        "pools": active_pools,
        "total_usable": total_usable,
        "total_used": total_used,
        "growth": total_growth,
    }


def _build_trend_figure(trend_rows: list[dict], selected_items: Iterable[str] | None, is_dc: bool) -> go.Figure:
    """Build a simple area trend chart for utilisation percentage over time."""
    fig = go.Figure()
    if not trend_rows:
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=10, r=10, t=10, b=20),
            showlegend=False,
        )
        return fig

    key_name = "pool" if is_dc else "vault"
    chosen = set(selected_items) if selected_items else None

    # Group by pool/vault
    series: dict[str, list[tuple[datetime, float]]] = {}
    for row in trend_rows:
        name = row.get(key_name)
        if not name:
            continue
        if chosen and name not in chosen:
            continue
        bucket = row.get("bucket")
        if not isinstance(bucket, datetime):
            continue
        used = float(row.get("used_bytes", 0) or 0)
        cap = float(row.get("hard_quota_bytes" if not is_dc else "usable_bytes", 0) or 0)
        pct = pct_float(used, cap) if cap else 0.0
        series.setdefault(name, []).append((bucket, pct))

    for name, points in series.items():
        points_sorted = sorted(points, key=lambda x: x[0])
        xs = [p[0] for p in points_sorted]
        ys = [p[1] for p in points_sorted]
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                name=name,
                line=dict(width=2),
                hovertemplate="<b>%{x}</b><br>%{y:.1f}%<extra></extra>",
            )
        )

    fig.update_layout(
        title=dict(
            text="Utilisation trend",
            font=dict(size=14, color="#2B3674", family="DM Sans"),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=40, b=30),
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(showgrid=False, zeroline=False, title="Utilisation %"),
    )
    return fig


def build_dc_s3_panel(dc_name: str, s3_data: dict, time_range: dict | None, selected_pools: Iterable[str] | None):
    """Build S3 panel for a single datacenter."""
    pools = s3_data.get("pools") or []
    if not pools:
        # Panel should not be rendered at all if there is no data;
        # caller is responsible for hiding the entire S3 tab.
        return html.Div()

    aggregates = _compute_dc_aggregates(s3_data, selected_pools)
    total_usable = aggregates["total_usable"]
    total_used = aggregates["total_used"]
    total_growth = aggregates["growth"]
    utilisation_pct = pct_float(total_used, total_usable) if total_usable else 0.0

    trend_rows = s3_data.get("trend") or []
    fig = _build_trend_figure(trend_rows, aggregates["pools"], is_dc=True)

    selector_value = list(selected_pools) if selected_pools else list(pools)

    return html.Div(
        children=[
            html.Div(
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "16px"},
                children=[
                    dmc.Group(
                        gap="md",
                        children=[
                            DashIconify(icon="solar:cloud-storage-bold-duotone", width=28, style={"color": "#4318FF"}),
                            html.Div(
                                children=[
                                    html.H3(
                                        f"S3 Object Storage — {dc_name}",
                                        style={"margin": 0, "fontSize": "1rem", "color": "#2B3674"},
                                    ),
                                    html.P(
                                        "Pool-level capacity and utilisation over selected period.",
                                        style={"margin": "2px 0 0 0", "fontSize": "0.8rem", "color": "#A3AED0"},
                                    ),
                                ]
                            ),
                        ],
                    ),
                    dmc.MultiSelect(
                        id="s3-dc-pool-selector",
                        data=[{"label": p, "value": p} for p in pools],
                        value=selector_value,
                        clearable=True,
                        searchable=True,
                        nothingFoundMessage="No S3 pools",
                        placeholder="Select S3 pools",
                        size="sm",
                        style={"minWidth": "260px"},
                    ),
                ],
            ),
            dmc.SimpleGrid(
                cols=4,
                spacing="lg",
                breakpoints=[{"maxWidth": "md", "cols": 2}, {"maxWidth": "sm", "cols": 1}],
                children=[
                    _kpi_card("Total usable capacity", smart_bytes(total_usable), "solar:database-bold-duotone"),
                    _kpi_card("Total used", smart_bytes(total_used), "solar:pie-chart-2-bold-duotone"),
                    _kpi_card("Free space", smart_bytes(max(total_usable - total_used, 0)), "solar:folder-with-files-bold-duotone"),
                    _kpi_card(f"Utilisation ({len(aggregates['pools'])} pool)", f"{utilisation_pct:.1f}%", "solar:chart-square-bold-duotone"),
                ],
            ),
            html.Div(style={"height": "20px"}),
            dmc.Grid(
                gutter="lg",
                children=[
                    dmc.GridCol(
                        span=12,
                        children=dmc.Paper(
                            className="nexus-card",
                            shadow="sm",
                            radius="md",
                            withBorder=False,
                            style={"padding": "16px"},
                            children=dcc.Graph(
                                id="s3-dc-trend-graph",
                                figure=fig,
                                config={"displayModeBar": False},
                            ),
                        ),
                    ),
                ],
            ),
            html.Div(style={"marginTop": "16px"}, children=[
                html.Span(
                    f"Total growth over period: {smart_bytes(total_growth)}",
                    style={"fontSize": "0.8rem", "color": "#A3AED0"},
                )
            ]),
        ]
    )


def _compute_customer_aggregates(s3_data: dict, selected_vaults: Iterable[str] | None) -> dict:
    """Aggregate S3 metrics for the selected customer vaults."""
    vaults = s3_data.get("vaults") or []
    if not vaults:
        return {"vaults": [], "limit_bytes": 0, "used_bytes": 0, "growth": 0}

    chosen = set(selected_vaults or vaults)
    latest = s3_data.get("latest") or {}
    growth = s3_data.get("growth") or {}

    total_limit = 0
    total_used = 0
    total_growth = 0
    active_vaults: list[str] = []

    for name in vaults:
        if name not in chosen:
            continue
        latest_row = latest.get(name) or {}
        growth_row = growth.get(name) or {}
        limit_b = int(latest_row.get("hard_quota_bytes", 0) or 0)
        used_b = int(latest_row.get("used_bytes", 0) or 0)
        delta_b = int(growth_row.get("delta_used_bytes", 0) or 0)
        total_limit += limit_b
        total_used += used_b
        total_growth += delta_b
        active_vaults.append(name)

    return {
        "vaults": active_vaults,
        "limit_bytes": total_limit,
        "used_bytes": total_used,
        "growth": total_growth,
    }


def build_customer_s3_panel(customer_name: str, s3_data: dict, time_range: dict | None, selected_vaults: Iterable[str] | None):
    """Build S3 panel for a single customer."""
    vaults = s3_data.get("vaults") or []
    if not vaults:
        # Panel should not be rendered when there is no S3 data for the customer.
        return html.Div()

    aggregates = _compute_customer_aggregates(s3_data, selected_vaults)
    total_limit = aggregates["limit_bytes"]
    total_used = aggregates["used_bytes"]
    total_growth = aggregates["growth"]
    utilisation_pct = pct_float(total_used, total_limit) if total_limit else 0.0

    trend_rows = s3_data.get("trend") or []
    fig = _build_trend_figure(trend_rows, aggregates["vaults"], is_dc=False)

    selector_value = list(selected_vaults) if selected_vaults else list(vaults)

    return html.Div(
        children=[
            html.Div(
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "16px"},
                children=[
                    dmc.Group(
                        gap="md",
                        children=[
                            DashIconify(icon="solar:user-folder-bold-duotone", width=28, style={"color": "#4318FF"}),
                            html.Div(
                                children=[
                                    html.H3(
                                        f"S3 Object Storage — {customer_name}",
                                        style={"margin": 0, "fontSize": "1rem", "color": "#2B3674"},
                                    ),
                                    html.P(
                                        "Vault-level limit and utilisation over selected period.",
                                        style={"margin": "2px 0 0 0", "fontSize": "0.8rem", "color": "#A3AED0"},
                                    ),
                                ]
                            ),
                        ],
                    ),
                    dmc.ChipGroup(
                        id="s3-customer-vault-selector",
                        value=selector_value,
                        multiple=True,
                        spacing="xs",
                        children=[
                            dmc.Chip(
                                value=v,
                                children=v,
                                size="sm",
                                variant="outline",
                                radius="md",
                            )
                            for v in vaults
                        ],
                    ),
                ],
            ),
            dmc.SimpleGrid(
                cols=4,
                spacing="lg",
                breakpoints=[{"maxWidth": "md", "cols": 2}, {"maxWidth": "sm", "cols": 1}],
                children=[
                    _kpi_card("Total hard limit", smart_bytes(total_limit), "solar:database-bold-duotone"),
                    _kpi_card("Total used (logical)", smart_bytes(total_used), "solar:pie-chart-2-bold-duotone"),
                    _kpi_card("Free capacity", smart_bytes(max(total_limit - total_used, 0)), "solar:folder-with-files-bold-duotone"),
                    _kpi_card(f"Utilisation ({len(aggregates['vaults'])} vault)", f"{utilisation_pct:.1f}%", "solar:chart-square-bold-duotone"),
                ],
            ),
            html.Div(style={"height": "20px"}),
            dmc.Grid(
                gutter="lg",
                children=[
                    dmc.GridCol(
                        span=12,
                        children=dmc.Paper(
                            className="nexus-card",
                            shadow="sm",
                            radius="md",
                            withBorder=False,
                            style={"padding": "16px"},
                            children=dcc.Graph(
                                id="s3-customer-trend-graph",
                                figure=fig,
                                config={"displayModeBar": False},
                            ),
                        ),
                    ),
                ],
            ),
            html.Div(style={"marginTop": "16px"}, children=[
                html.Span(
                    f"Total growth over period: {smart_bytes(total_growth)}",
                    style={"fontSize": "0.8rem", "color": "#A3AED0"},
                )
            ]),
        ]
    )


def _kpi_card(title: str, value: str, icon: str):
    """Shared KPI card for S3 panels."""
    return dmc.Paper(
        className="nexus-card",
        shadow="sm",
        radius="md",
        withBorder=False,
        style={"padding": "16px"},
        children=[
            dmc.Group(
                gap="sm",
                align="center",
                children=[
                    dmc.ThemeIcon(
                        size="lg",
                        radius="md",
                        variant="light",
                        color="indigo",
                        children=DashIconify(icon=icon, width=22),
                    ),
                    html.Div(
                        children=[
                            html.Div(
                                title,
                                style={"fontSize": "0.8rem", "color": "#A3AED0", "marginBottom": "2px"},
                            ),
                            html.Div(
                                value,
                                style={"fontSize": "1.2rem", "color": "#2B3674", "fontWeight": 700},
                            ),
                        ]
                    ),
                ],
            ),
        ],
    )

