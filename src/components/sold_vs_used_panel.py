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
from src.components.crm_sales_panel import format_crm_money
from src.components.status_badges import compliance_status_badge
from src.utils.visibility import filter_efficiency_rows_for_display, filter_overusage_rows


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

    detected = r.get("detected")
    has_detected = detected is not None
    detected_val = float(detected or 0) if has_detected else 0.0

    # The gauge is a used/sold ratio, so it means nothing when nothing was sold:
    # the denominator is zero and efficiency_pct comes back None. Rendering that
    # as a literal 0% put "0%" next to an OVER-UTILIZED badge and a 74-unit
    # overage — it reads as "barely used" when the truth is the exact opposite.
    # Undefined is not zero, so the ratio is replaced with the plain statement.
    if eff is None and used > 0 and sold <= 0:
        gauge = html.Div(
            style={
                "width": "100%",
                "maxWidth": "360px",
                "margin": "0 auto",
                "display": "flex",
                "flexDirection": "column",
                "alignItems": "center",
                "justifyContent": "center",
                "minHeight": "200px",
                "textAlign": "center",
            },
            children=[
                dmc.Text(f"{used:,.0f} {unit}".strip(), fw=700, size="xl", c="#E03131"),
                dmc.Text("in use, nothing sold", size="sm", c="#A3AED0"),
                dmc.Text(
                    "Used/sold ratio cannot be computed when there are no sales.",
                    size="xs", c="#A3AED0", mt="xs",
                ),
            ],
        )
    else:
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

    bar_series = {"Sold": [sold], "Used": [used]}
    if has_detected:
        bar_series["Detected"] = [detected_val]

    bar = dcc.Graph(
        figure=create_grouped_bar_chart(
            [title[:40]],
            bar_series,
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
    else:
        headroom = float(r.get("headroom_qty") or 0)
        headroom_tl = r.get("headroom_tl")
        if headroom > 0:
            pot = f"{float(headroom_tl or 0):,.2f} TL" if headroom_tl is not None else "-"
            overage_line = dmc.Text(
                f"Headroom: {headroom:,.2f} {unit} · Potential: {pot}",
                size="xs",
                c="#12B886",
                fw=600,
            )

    detected_line = None
    if has_detected:
        detected_line = dmc.Text(
            f"Detected: {detected_val:,.2f} {unit}".strip(),
            size="xs",
            c="#4318FF",
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
            detected_line,
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


def _compliance_qty(row: dict[str, Any], key: str) -> float:
    if key == "sold":
        return float(
            row.get("entitled_qty")
            if row.get("entitled_qty") is not None
            else row.get("sold_qty") or 0
        )
    if key == "used":
        return float(row.get("used_qty") or 0)
    return float(row.get(key) or 0)


def build_compliance_issue_table(
    rows: list[dict[str, Any]] | None,
    *,
    currency: str | None = "TL",
) -> html.Div:
    """Compact table for summary overusage issues (no gauges or charts)."""
    visible = filter_overusage_rows(rows)
    if not visible:
        return html.Div()

    cols = ["Category", "Sold", "Used", "Overage / Headroom", "Est. loss / Potential", "Status"]

    def _row(r: dict[str, Any]) -> html.Tr:
        unit = str(r.get("resource_unit") or "")
        sold = _compliance_qty(r, "sold")
        used = _compliance_qty(r, "used")
        overage = _compliance_qty(r, "overage_qty")
        headroom = float(r.get("headroom_qty") or 0)
        loss = r.get("overage_loss_tl")
        headroom_tl = r.get("headroom_tl")
        label = str(r.get("category_label") or r.get("category_code") or "Category")

        def _qty(v: float) -> str:
            return f"{v:,.2f} {unit}".strip() if unit else f"{v:,.2f}"

        if overage > 0:
            gap_cell = _qty(overage)
            money_cell = format_crm_money(loss, currency) if loss is not None else "-"
        elif headroom > 0:
            gap_cell = f"Headroom {_qty(headroom)}"
            money_cell = (
                format_crm_money(headroom_tl, currency) if headroom_tl is not None else "-"
            )
        else:
            gap_cell = _qty(0)
            money_cell = "-"

        return html.Tr(
            [
                html.Td(label),
                html.Td(_qty(sold)),
                html.Td(_qty(used)),
                html.Td(gap_cell),
                html.Td(money_cell),
                html.Td(compliance_status_badge(str(r.get("status")))),
            ]
        )

    return html.Div(
        style={"overflowX": "auto"},
        children=[
            dmc.Table(
                striped=True,
                highlightOnHover=True,
                withColumnBorders=True,
                children=[
                    html.Thead(html.Tr([html.Th(c) for c in cols])),
                    html.Tbody([_row(r) for r in visible]),
                ],
            )
        ],
    )
