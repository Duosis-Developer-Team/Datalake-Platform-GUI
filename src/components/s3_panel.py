from __future__ import annotations
from typing import Iterable

from dash import html
import dash_mantine_components as dmc
from dash_iconify import DashIconify

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
                children=[
                    _kpi_card("Total usable capacity", smart_bytes(total_usable), "solar:database-bold-duotone"),
                    _kpi_card("Total used", smart_bytes(total_used), "solar:pie-chart-2-bold-duotone"),
                    _kpi_card("Free space", smart_bytes(max(total_usable - total_used, 0)), "solar:folder-with-files-bold-duotone"),
                    _kpi_card(f"Utilisation ({len(aggregates['pools'])} pool)", f"{utilisation_pct:.1f}%", "solar:chart-square-bold-duotone"),
                ],
            ),
            html.Div(style={"height": "20px"}),
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
                    dmc.MultiSelect(
                        id="s3-customer-vault-selector",
                        data=[{"label": v, "value": v} for v in vaults],
                        value=selector_value,
                        clearable=True,
                        searchable=True,
                        nothingFoundMessage="No S3 vaults",
                        placeholder="Select S3 vaults",
                        size="sm",
                        style={"minWidth": "260px"},
                    ),
                ],
            ),
            dmc.SimpleGrid(
                cols=4,
                spacing="lg",
                children=[
                    _kpi_card("Total hard limit", smart_bytes(total_limit), "solar:database-bold-duotone"),
                    _kpi_card("Total used (logical)", smart_bytes(total_used), "solar:pie-chart-2-bold-duotone"),
                    _kpi_card("Free capacity", smart_bytes(max(total_limit - total_used, 0)), "solar:folder-with-files-bold-duotone"),
                    _kpi_card(f"Utilisation ({len(aggregates['vaults'])} vault)", f"{utilisation_pct:.1f}%", "solar:chart-square-bold-duotone"),
                ],
            ),
            html.Div(style={"height": "20px"}),
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

