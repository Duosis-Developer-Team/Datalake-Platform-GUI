"""Sticky command bar for CRM Inventory overview — header, KPIs, toolbar."""
from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from src.pages import crm_shared as shared

_GLASS_STYLE = {
    "background": "rgba(255, 255, 255, 0.92)",
    "backdropFilter": "blur(14px)",
    "WebkitBackdropFilter": "blur(14px)",
    "boxShadow": "0 4px 24px rgba(67, 24, 255, 0.08), 0 1px 6px rgba(0, 0, 0, 0.05)",
    "border": "1px solid rgba(67, 24, 255, 0.08)",
    "position": "sticky",
    "top": 0,
    "zIndex": 100,
    "marginBottom": "16px",
}

_FILTER_OPTIONS = [
    {"value": "all", "label": "All"},
    {"value": "infra", "label": "With infra"},
    {"value": "crm_only", "label": "CRM only"},
    {"value": "issues", "label": "Issues"},
]

_VIEW_OPTIONS = [
    {"value": "grouped", "label": "Grouped"},
    {"value": "flat", "label": "Flat table"},
]


def _kpi_button(
    title: str,
    value: str,
    subtitle: str,
    *,
    filter_value: str,
    color: str,
    icon: str,
    size: str = "md",
) -> dmc.UnstyledButton:
    return dmc.UnstyledButton(
        id={"type": "crm-inv-kpi", "filter": filter_value},
        n_clicks=0,
        style={"width": "100%"},
        children=dmc.Card(
            withBorder=True,
            radius="md",
            padding="sm" if size == "sm" else "md",
            style={"cursor": "pointer", "transition": "box-shadow 0.15s ease"},
            children=[
                dmc.Group(
                    gap="sm",
                    wrap="nowrap",
                    children=[
                        DashIconify(icon=icon, width=24 if size == "md" else 20, color=color),
                        dmc.Stack(gap=0, style={"flex": 1}, children=[
                            dmc.Text(title, size="xs", c="dimmed", tt="uppercase", fw=600),
                            dmc.Text(value, size="lg" if size == "md" else "md", fw=800, c=color),
                            dmc.Text(subtitle, size="xs", c="dimmed"),
                        ]),
                    ],
                ),
            ],
        ),
    )


def build_inventory_shell(summary: dict[str, Any], unmapped: list[dict[str, Any]] | None = None) -> html.Div:
    """Glass sticky header + KPI strip + search/filter toolbar."""
    unmapped = unmapped or []
    issue_count = int(summary.get("overage_panel_count") or 0) + int(summary.get("unsold_usage_count") or 0)
    catalog_unmapped = int(summary.get("unmapped_product_count") or 0)

    header = dmc.Paper(
        p="md",
        radius="lg",
        style=_GLASS_STYLE,
        children=[
            dmc.Group(justify="space-between", align="flex-start", wrap="wrap", gap="md", children=[
                dmc.Group(gap="sm", wrap="nowrap", children=[
                    DashIconify(icon="solar:chart-2-bold-duotone", width=28, color=shared.BRAND_PURPLE),
                    dmc.Stack(gap=2, children=[
                        dmc.Text("CRM › Inventory", size="xs", fw=700, c="dimmed"),
                        dmc.Title("Capacity & Sales Inventory", order=3, style={"margin": 0}),
                        dmc.Group(gap="xs", children=[
                            dmc.Badge("Global", color="indigo", variant="light", size="sm"),
                            dmc.Badge("All DCs aggregated", color="gray", variant="outline", size="sm"),
                        ]),
                    ]),
                ]),
                dmc.Button(
                    "Export Excel",
                    id="crm-inventory-export-btn",
                    leftSection=DashIconify(icon="solar:download-square-bold-duotone", width=16),
                    color="indigo",
                    variant="light",
                    size="sm",
                ),
            ]),
            dmc.Divider(my="md", color="gray.2"),
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 2, "lg": 4},
                spacing="sm",
                mb="sm",
                children=[
                    _kpi_button(
                        "Infra services",
                        f"{int(summary.get('infra_panel_count') or 0):,}",
                        f"of {int(summary.get('panel_count') or 0):,} mapped",
                        filter_value="infra",
                        color=shared.BRAND_PURPLE,
                        icon="solar:server-bold-duotone",
                    ),
                    _kpi_button(
                        "CRM entitled",
                        shared.fmt_tl(summary.get("crm_entitled_tl")),
                        "Active + invoiced lines",
                        filter_value="all",
                        color=shared.BRAND_GREEN,
                        icon="solar:hand-money-bold-duotone",
                    ),
                    _kpi_button(
                        "Sellable potential",
                        shared.fmt_tl(summary.get("total_potential_tl")),
                        "All mapped infra panels · constrained × unit price",
                        filter_value="all",
                        color=shared.BRAND_PURPLE_LIGHT,
                        icon="solar:wallet-money-bold-duotone",
                    ),
                    _kpi_button(
                        "Issues",
                        f"{issue_count:,}",
                        "Overage + unsold usage",
                        filter_value="issues",
                        color=shared.BRAND_RED if issue_count else shared.BRAND_GREY,
                        icon="solar:shield-warning-bold-duotone",
                    ),
                ],
            ),
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 2},
                spacing="sm",
                mb="md",
                children=[
                    _kpi_button(
                        "CRM-only",
                        f"{int(summary.get('crm_only_count') or 0):,}",
                        "No infra binding",
                        filter_value="crm_only",
                        color=shared.BRAND_GREY,
                        icon="solar:cloud-bold-duotone",
                        size="sm",
                    ),
                    _kpi_button(
                        "Unmapped SKUs",
                        f"{catalog_unmapped:,}",
                        f"{int(summary.get('unmapped_entitled_count') or 0):,} entitled lines",
                        filter_value="all",
                        color=shared.BRAND_ORANGE if catalog_unmapped else shared.BRAND_GREY,
                        icon="solar:question-circle-bold-duotone",
                        size="sm",
                    ),
                ],
            ),
            dmc.Group(
                justify="space-between",
                align="flex-end",
                wrap="wrap",
                gap="sm",
                children=[
                    dmc.TextInput(
                        id="crm-inventory-search",
                        placeholder="Search service, family, or CRM product…",
                        leftSection=DashIconify(icon="solar:magnifer-linear", width=16, color="#A3AED0"),
                        style={"flex": 1, "minWidth": "220px", "maxWidth": "420px"},
                        size="sm",
                        radius="md",
                    ),
                    dmc.Group(gap="sm", wrap="wrap", children=[
                        dmc.SegmentedControl(
                            id="crm-inventory-filter",
                            value="all",
                            data=_FILTER_OPTIONS,
                            size="sm",
                        ),
                        dmc.SegmentedControl(
                            id="crm-inventory-view-mode",
                            value="grouped",
                            data=_VIEW_OPTIONS,
                            size="sm",
                        ),
                    ]),
                ],
            ),
        ],
    )

    return html.Div([header])
