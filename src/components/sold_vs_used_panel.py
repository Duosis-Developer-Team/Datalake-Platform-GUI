"""
Reusable "Sold vs Used" CRM efficiency panel (gauge + grouped bar + status badge).

Used on customer_view category tabs. UI labels may be Turkish; code/comments in English.
"""
from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import dcc, html
import plotly.graph_objects as go

from src.components.charts import create_grouped_bar_chart, create_premium_gauge_chart


def filter_efficiency_rows(rows: list[dict[str, Any]] | None, gui_tab_prefix: str) -> list[dict[str, Any]]:
    """Keep rows whose gui_tab_binding starts with prefix (e.g. virtualization.classic)."""
    if not rows:
        return []
    p = (gui_tab_prefix or "").strip().lower()
    out: list[dict[str, Any]] = []
    for r in rows:
        g = str(r.get("gui_tab_binding") or "").lower()
        if g.startswith(p):
            out.append(r)
    return out


def _status_badge(status: str | None) -> dmc.Badge:
    s = (status or "unknown").lower()
    if s == "under":
        return dmc.Badge("Under-utilized", color="green", variant="light", size="sm")
    if s == "optimal":
        return dmc.Badge("Optimal", color="indigo", variant="light", size="sm")
    if s == "over":
        return dmc.Badge("Over-utilized", color="red", variant="light", size="sm")
    if s == "no_sales":
        return dmc.Badge("No CRM sales", color="gray", variant="light", size="sm")
    return dmc.Badge("N/A", color="gray", variant="outline", size="sm")


def _one_row_card(r: dict[str, Any]) -> html.Div:
    title = str(r.get("category_label") or r.get("category_code") or "Category")
    unit = str(r.get("resource_unit") or "")
    sold = float(r.get("sold_qty") or 0)
    used = float(r.get("used_qty") or 0)
    eff = r.get("efficiency_pct")
    note = r.get("usage_note")
    gauge_pct = min(float(eff or 0), 100.0) if eff is not None else 0.0

    gauge = dcc.Graph(
        figure=create_premium_gauge_chart(
            gauge_pct,
            f"Used / sold ({eff:.0f}%)" if eff is not None else "Used / sold",
            color="#4318FF",
            height=200,
            show_threshold=False,
        ),
        config={"displayModeBar": False},
        style={"height": "220px"},
    )

    bar = dcc.Graph(
        figure=create_grouped_bar_chart(
            [title[:40]],
            {"Sold": [sold], "Used": [used]},
            f"Quantities ({unit})" if unit else "Quantities",
            height=220,
        ),
        config={"displayModeBar": False},
        style={"height": "240px"},
    )

    alloc = r.get("allocated_vs_sold_pct")
    alloc_line = (
        dmc.Text(
            f"Allocated vs sold (usage intensity): {float(alloc):.1f}%",
            size="xs",
            c="#A3AED0",
        )
        if alloc is not None
        else None
    )

    return html.Div(
        className="nexus-card",
        style={"padding": "16px", "marginBottom": "12px"},
        children=[
            dmc.Group(
                justify="space-between",
                align="flex-start",
                mb="sm",
                children=[
                    dmc.Stack(
                        gap=2,
                        children=[
                            dmc.Text(title, fw=700, size="sm", c="#2B3674"),
                            dmc.Text(f"Unit: {unit}" if unit else "", size="xs", c="#A3AED0"),
                        ],
                    ),
                    _status_badge(str(r.get("status"))),
                ],
            ),
            dmc.SimpleGrid(
                cols=2,
                spacing="md",
                breakpoints=[{"maxWidth": 900, "cols": 1}],
                children=[gauge, bar],
            ),
            alloc_line,
            dmc.Text(note, size="xs", c="orange", mt="xs") if note else None,
        ],
    )


def build_sold_vs_used_stack(rows: list[dict[str, Any]] | None) -> html.Div:
    """Vertical stack of cards; empty state when no matching categories."""
    if not rows:
        return html.Div(
            dmc.Alert(
                color="gray",
                variant="light",
                title="Sold vs Used",
                children="No CRM category sales mapped to this tab for the selected customer.",
            )
        )
    return html.Div(children=[_one_row_card(r) for r in rows])
