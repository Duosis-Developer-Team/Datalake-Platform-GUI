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
from src.components.status_badges import compliance_status_badge
from src.utils.visibility import filter_efficiency_rows_for_display


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


def _one_row_card(r: dict[str, Any]) -> html.Div:
    title = str(r.get("category_label") or r.get("category_code") or "Category")
    unit = str(r.get("resource_unit") or "")
    sold = float(
        r.get("entitled_qty") if r.get("entitled_qty") is not None else r.get("sold_qty") or 0
    )
    used = float(r.get("used_qty") or 0)
    overage = float(r.get("overage_qty") or 0)
    overage_loss = r.get("overage_loss_tl")
    eff = r.get("efficiency_pct")
    note = r.get("usage_note")
    gauge_pct = min(float(eff or 0), 100.0) if eff is not None else 0.0

    gauge = html.Div(
        style={
            "width": "100%",
            "aspectRatio": "16 / 11",
            "maxWidth": "360px",
            "margin": "0 auto",
        },
        children=dcc.Graph(
            figure=create_premium_gauge_chart(
                gauge_pct,
                f"Used / sold ({eff:.0f}%)" if eff is not None else "Used / sold",
                color="#4318FF",
                height=200,
                show_threshold=False,
            ),
            config={"displayModeBar": False, "responsive": True},
            style={"height": "100%", "width": "100%"},
        ),
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
    overage_line = None
    if overage > 0 or overage_loss is not None:
        loss_txt = f"{float(overage_loss or 0):,.2f} TL" if overage_loss is not None else "-"
        overage_line = dmc.Text(
            f"Overage: {overage:,.2f} {unit} · Est. loss: {loss_txt}",
            size="xs",
            c="#E03131",
            fw=600,
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
                    compliance_status_badge(str(r.get("status"))),
                ],
            ),
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 2},
                spacing="md",
                children=[gauge, bar],
            ),
            alloc_line,
            overage_line,
            dmc.Text(note, size="xs", c="orange", mt="xs") if note else None,
        ],
    )


def build_compliance_stack(compliance_payload: dict[str, Any] | None, gui_tab_prefix: str) -> html.Div:
    """Compliance cards filtered by virtualization tab prefix."""
    rows = filter_efficiency_rows((compliance_payload or {}).get("rows") or [], gui_tab_prefix)
    if not rows:
        rows = [
            r
            for r in ((compliance_payload or {}).get("rows") or [])
            if str(r.get("gui_tab_binding") or "").lower().startswith(gui_tab_prefix.lower())
        ]
    return build_sold_vs_used_stack(rows)


def build_sold_vs_used_stack(rows: list[dict[str, Any]] | None) -> html.Div:
    """Vertical stack of cards; omit section when no meaningful categories."""
    visible = filter_efficiency_rows_for_display(rows)
    if not visible:
        return html.Div()
    return html.Div(children=[_one_row_card(r) for r in visible])
