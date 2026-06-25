"""Shared layout helpers for CRM dashboard pages."""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

BRAND_PURPLE = "#552cf8"
BRAND_PURPLE_LIGHT = "#a092ff"
BRAND_GREEN = "#00b888"
BRAND_ORANGE = "#f59f00"
BRAND_GREY = "#A3AED0"
BRAND_RED = "#E03131"


def fmt_tl(value: float | int | None) -> str:
    try:
        return f"{float(value or 0):,.0f} TL"
    except (TypeError, ValueError):
        return "0 TL"


def fmt_unit(value: float | int | None, unit: str) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.0f} {unit}".strip()
    except (TypeError, ValueError):
        return f"— {unit}".strip()


def kpi_card(
    title: str,
    value: str,
    subtitle: str | None = None,
    *,
    color: str = BRAND_PURPLE,
    icon: str | None = None,
) -> dmc.Card:
    return dmc.Card(
        withBorder=True,
        radius="md",
        padding="md",
        children=[
            dmc.Group(
                gap="sm",
                wrap="nowrap",
                children=[
                    DashIconify(icon=icon or "solar:chart-square-bold-duotone", width=28, color=color),
                    dmc.Stack(gap=2, children=[
                        dmc.Text(title, size="xs", c="dimmed", tt="uppercase", fw=600),
                        dmc.Text(value, size="xl", fw=800, c=color),
                        dmc.Text(subtitle or "", size="xs", c="dimmed"),
                    ]),
                ],
            ),
        ],
    )


_STATUS_COLORS = {
    "ok": "green",
    "under": "yellow",
    "over": "red",
    "unsold_usage": "orange",
    "crm_only": "grape",
    "no_usage": "gray",
}


def status_badge(status: str | None) -> dmc.Badge:
    key = (status or "no_usage").lower()
    return dmc.Badge(key, color=_STATUS_COLORS.get(key, "gray"), variant="light", size="sm")


def capacity_bar(total: float, crm_sold: float, used: float, sellable: float, color: str = BRAND_PURPLE) -> html.Div:
    cap = max(float(total or 0), 1e-9)
    crm_pct = min(100.0, 100.0 * float(crm_sold or 0) / cap)
    used_pct = min(100.0, 100.0 * float(used or 0) / cap)
    sell_pct = min(100.0, 100.0 * float(sellable or 0) / cap)
    return html.Div(style={"marginTop": "8px"}, children=[
        html.Div(style={
            "position": "relative", "height": "12px", "borderRadius": "6px",
            "background": "#E9EDF7", "overflow": "hidden",
        }, children=[
            html.Div(style={
                "position": "absolute", "left": 0, "top": 0, "bottom": 0,
                "width": f"{used_pct}%",
                "background": f"linear-gradient(90deg, {color}55, {color})",
            }),
            html.Div(style={
                "position": "absolute", "left": 0, "top": 0, "bottom": 0,
                "width": f"{crm_pct}%",
                "borderRight": "2px solid #FFB547",
            }),
            html.Div(style={
                "position": "absolute", "right": 0, "top": 0, "bottom": 0,
                "width": f"{sell_pct}%",
                "background": "rgba(0, 184, 136, 0.35)",
            }),
        ]),
        dmc.Group(gap="md", mt=6, children=[
            dmc.Text(f"Total: {total:,.0f}", size="xs", c="dimmed"),
            dmc.Text(f"CRM sold: {crm_sold:,.0f}", size="xs", c="dimmed"),
            dmc.Text(f"Used: {used:,.0f}", size="xs", c="dimmed"),
            dmc.Text(f"Sellable: {sellable:,.0f}", size="xs", c="teal", fw=600),
        ]),
    ])
