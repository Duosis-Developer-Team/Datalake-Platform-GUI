"""Instant loading skeleton for CRM Inventory overview (Phase A).

Design standard: docs/LOADING_UX_DESIGN.md — mirrors DC View / Customer View two-phase load.
"""
from __future__ import annotations

from dash import html
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from src.pages import crm_shared as shared

LOADING_STAGE_MESSAGES = (
    "Loading global inventory overview…",
    "Aggregating capacity across data centers…",
    "Merging CRM entitled sales with infra panels…",
    "Computing sellable potential…",
)


def _kpi_skeleton() -> html.Div:
    return html.Div(
        className="dc-load-shimmer customer-load-shimmer",
        style={
            "background": "#fff",
            "borderRadius": "16px",
            "padding": "18px",
            "border": "1px solid #eef1f4",
            "minHeight": "110px",
        },
        children=[
            dmc.Skeleton(height=12, width="50%", mb="sm", radius="sm"),
            dmc.Skeleton(height=24, width="70%", mb="xs", radius="sm"),
            dmc.Skeleton(height=10, width="85%", radius="sm"),
        ],
    )


def _table_skeleton() -> html.Div:
    return html.Div(
        className="dc-load-shimmer customer-load-shimmer",
        style={
            "background": "#fff",
            "borderRadius": "16px",
            "padding": "24px",
            "border": "1px solid #eef1f4",
            "minHeight": "280px",
        },
        children=[
            dmc.Skeleton(height=16, width="30%", mb="md", radius="sm"),
            dmc.Skeleton(height=12, width="100%", mb="sm", radius="sm"),
            dmc.Skeleton(height=12, width="96%", mb="sm", radius="sm"),
            dmc.Skeleton(height=12, width="92%", mb="sm", radius="sm"),
            dmc.Skeleton(height=12, width="88%", radius="sm"),
        ],
    )


def build_crm_inventory_loading_shell() -> html.Div:
    """Phase A skeleton — shown instantly while inventory API loads."""
    return html.Div(
        id="crm-inventory-loading-layer",
        className="customer-loading-layer",
        style={"maxWidth": "1480px", "margin": "0 auto", "padding": "12px 16px 32px"},
        children=[
            dmc.Paper(
                p="md",
                radius="lg",
                mb="md",
                children=[
                    dmc.Group(gap="sm", wrap="nowrap", mb="md", children=[
                        DashIconify(icon="solar:chart-2-bold-duotone", width=28, color=shared.BRAND_PURPLE),
                        dmc.Stack(gap=4, children=[
                            dmc.Text("CRM › Inventory", size="xs", fw=700, c="dimmed"),
                            dmc.Title("Capacity & Sales Inventory", order=3, style={"margin": 0}),
                        ]),
                    ]),
                    dmc.SimpleGrid(cols={"base": 2, "sm": 4}, spacing="sm", mb="sm", children=[
                        _kpi_skeleton(),
                        _kpi_skeleton(),
                        _kpi_skeleton(),
                        _kpi_skeleton(),
                    ]),
                    dmc.SimpleGrid(cols={"base": 1, "sm": 2}, spacing="sm", mb="md", children=[
                        _kpi_skeleton(),
                        _kpi_skeleton(),
                    ]),
                    dmc.Group(gap="sm", wrap="wrap", children=[
                        dmc.Skeleton(height=36, width=320, radius="md"),
                        dmc.Skeleton(height=36, width=280, radius="md"),
                    ]),
                ],
            ),
            dmc.Text(
                LOADING_STAGE_MESSAGES[0],
                size="sm",
                c="dimmed",
                ta="center",
                mb="md",
            ),
            _table_skeleton(),
            _table_skeleton(),
        ],
    )
