"""CRM entitlement vs infrastructure resource compliance panels."""
from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import html

from src.components.crm_sales_panel import format_crm_money


def filter_compliance_rows(
    payload: dict[str, Any] | None,
    gui_tab_prefix: str,
) -> list[dict[str, Any]]:
    rows = (payload or {}).get("rows") or []
    prefix = (gui_tab_prefix or "").strip().lower()
    if not prefix:
        return list(rows)
    return [
        r
        for r in rows
        if str(r.get("gui_tab_binding") or "").lower().startswith(prefix)
    ]


def _status_badge(status: str | None) -> dmc.Badge:
    s = (status or "unknown").lower()
    if s == "unsold_usage":
        return dmc.Badge("Unsold usage", color="red", variant="filled", size="sm")
    if s == "over":
        return dmc.Badge("Over-utilized", color="red", variant="light", size="sm")
    if s == "under":
        return dmc.Badge("Under-utilized", color="green", variant="light", size="sm")
    if s == "optimal":
        return dmc.Badge("Optimal", color="indigo", variant="light", size="sm")
    if s == "no_usage":
        return dmc.Badge("No usage", color="gray", variant="outline", size="sm")
    return dmc.Badge("N/A", color="gray", variant="outline", size="sm")


def build_resource_compliance_table(
    compliance_payload: dict[str, Any] | None,
    *,
    currency: str | None = "TL",
) -> html.Div:
    """Summary tab table: entitled vs used with overage loss."""
    rows = (compliance_payload or {}).get("rows") or []
    summary = (compliance_payload or {}).get("summary") or {}

    if not rows:
        return dmc.Alert(
            color="gray",
            variant="light",
            title="Resource Compliance",
            children="No virtualization compliance data for this customer.",
        )

    header_style = {
        "display": "grid",
        "gridTemplateColumns": "2fr 1fr 1fr 1fr 1fr 1fr 1fr",
        "padding": "8px 0",
        "borderBottom": "2px solid #4318FF",
        "fontSize": "0.75rem",
        "fontWeight": 700,
        "color": "#A3AED0",
    }
    row_style = {
        "display": "grid",
        "gridTemplateColumns": "2fr 1fr 1fr 1fr 1fr 1fr 1fr",
        "padding": "10px 0",
        "borderBottom": "1px solid #F4F7FE",
        "fontSize": "0.82rem",
        "alignItems": "center",
    }

    def _qty(value: float | int | None, unit: str) -> str:
        try:
            return f"{float(value or 0):,.2f} {unit}".strip()
        except (TypeError, ValueError):
            return f"- {unit}".strip()

    body_rows = []
    for row in rows:
        unit = str(row.get("resource_unit") or "")
        body_rows.append(
            html.Div(
                style=row_style,
                children=[
                    html.Span(
                        str(row.get("category_label") or row.get("category_code") or "-"),
                        style={"color": "#2B3674", "fontWeight": 600},
                    ),
                    html.Span(_qty(row.get("entitled_qty"), unit)),
                    html.Span(_qty(row.get("used_qty"), unit), style={"color": "#4318FF"}),
                    html.Span(
                        _qty(row.get("overage_qty"), unit),
                        style={"color": "#E03131" if float(row.get("overage_qty") or 0) > 0 else "#2B3674"},
                    ),
                    html.Span(format_crm_money(row.get("unit_price_tl"), currency)),
                    html.Span(
                        format_crm_money(row.get("overage_loss_tl"), currency),
                        style={"color": "#E03131" if float(row.get("overage_loss_tl") or 0) > 0 else "#2B3674"},
                    ),
                    _status_badge(str(row.get("status"))),
                ],
            )
        )

    total_loss = float(summary.get("total_overage_loss_tl") or 0)
    has_overuse = bool(summary.get("has_overuse"))

    footer = dmc.Group(
        justify="space-between",
        mt="md",
        children=[
            dmc.Text(
                f"Estimated total overage loss: {format_crm_money(total_loss, currency)}",
                fw=700,
                size="sm",
                c="#E03131" if has_overuse else "#2B3674",
            ),
            dmc.Badge(
                "Resource overage detected" if has_overuse else "Within limits",
                color="red" if has_overuse else "teal",
                variant="light",
            ),
        ],
    )

    return html.Div(
        children=[
            html.Div(
                style=header_style,
                children=[
                    html.Span("Category"),
                    html.Span("Entitled"),
                    html.Span("Used"),
                    html.Span("Overage"),
                    html.Span("Unit Price"),
                    html.Span("Est. Loss"),
                    html.Span("Status"),
                ],
            ),
            *body_rows,
            footer,
        ],
    )
