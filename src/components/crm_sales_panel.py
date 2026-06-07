"""CRM realized sales panels for the customer detail Summary tab and intro card."""
from __future__ import annotations

from dash import dcc, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objects as go


def format_crm_money(value, currency: str | None = None) -> str:
    cur = (currency or "TL").strip() or "TL"
    if value is None:
        return "-"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{amount:,.2f} {cur}"


def crm_has_sales_data(sales_summary: dict | None) -> bool:
    summary = sales_summary or {}
    return bool(
        float(summary.get("ytd_revenue_total") or 0) > 0
        or float(summary.get("lifetime_revenue_total") or 0) > 0
        or int(summary.get("invoice_count") or 0) > 0
        or int(summary.get("lifetime_order_count") or 0) > 0
    )


def build_crm_service_sales_chart(service_breakdown: list[dict]):
    rows = service_breakdown or []
    if not rows:
        return dmc.Text("No service sales data available.", size="sm", c="dimmed")
    top = rows[:8]
    labels = [str(r.get("service_label") or r.get("service_code") or "-") for r in top]
    values = [float(r.get("amount_tl") or 0.0) for r in top]
    fig = go.Figure(
        data=[
            go.Bar(
                x=values,
                y=labels,
                orientation="h",
                marker_color="#4318FF",
                hovertemplate="%{y}<br>%{x:,.0f} TL<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        margin=dict(l=8, r=8, t=8, b=8),
        height=max(180, len(top) * 34),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=True, gridcolor="#E9EDF7"),
        yaxis=dict(autorange="reversed"),
        font=dict(family="Inter, system-ui, sans-serif", size=11, color="#2B3674"),
    )
    return dcc.Graph(figure=fig, config={"displayModeBar": False}, style={"width": "100%"})


def _kv_row(label: str, value: str):
    return html.Div(
        style={
            "display": "grid",
            "gridTemplateColumns": "1fr 1fr",
            "padding": "8px 0",
            "borderBottom": "1px solid #F4F7FE",
            "fontSize": "0.82rem",
        },
        children=[
            html.Span(label, style={"color": "#A3AED0", "fontWeight": 600}),
            html.Span(value, style={"color": "#2B3674", "fontWeight": 700, "textAlign": "right"}),
        ],
    )


def build_crm_summary_kv_panel(
    customer_name: str,
    sales_summary: dict | None,
    service_breakdown: list[dict] | None,
    sales_items: list[dict] | None,
):
    summary = sales_summary or {}
    currency = summary.get("currency")
    service_count = len(service_breakdown or [])
    line_count = len(sales_items or [])

    rows = [
        _kv_row("Customer reference", customer_name or "-"),
        _kv_row("YTD realized revenue", format_crm_money(summary.get("ytd_revenue_total"), currency)),
        _kv_row("Lifetime realized revenue", format_crm_money(summary.get("lifetime_revenue_total"), currency)),
        _kv_row("YTD orders (fulfilled)", f"{int(summary.get('invoice_count') or 0):,}"),
        _kv_row("Lifetime orders", f"{int(summary.get('lifetime_order_count') or 0):,}"),
        _kv_row("Active orders (open)", f"{int(summary.get('active_order_count') or 0):,}"),
        _kv_row("Service categories sold", f"{service_count:,}"),
        _kv_row("Sold line items", f"{line_count:,}"),
        _kv_row("Currency", str(currency or "-")),
    ]
    return html.Div(children=rows)


def build_crm_intro_kpi_strip(sales_summary: dict | None, service_breakdown: list[dict] | None):
    summary = sales_summary or {}
    currency = summary.get("currency")
    service_count = len(service_breakdown or [])
    return dmc.SimpleGrid(
        cols=4,
        spacing="md",
        children=[
            _intro_kpi("YTD Revenue", format_crm_money(summary.get("ytd_revenue_total"), currency), "green"),
            _intro_kpi("Lifetime Revenue", format_crm_money(summary.get("lifetime_revenue_total"), currency), "teal"),
            _intro_kpi("YTD Orders", f"{int(summary.get('invoice_count') or 0):,}", "cyan"),
            _intro_kpi("Service categories", f"{service_count:,}", "violet"),
        ],
    )


def _intro_kpi(title: str, value: str, color: str):
    return html.Div(
        style={
            "padding": "14px 12px",
            "borderRadius": "12px",
            "background": "#F4F7FE",
            "textAlign": "center",
        },
        children=[
            html.Div(title, style={"color": "#A3AED0", "fontSize": "0.7rem", "fontWeight": 600}),
            html.Div(value, style={"color": "#2B3674", "fontSize": "1rem", "fontWeight": 800, "marginTop": "4px"}),
        ],
    )


def build_crm_category_table(efficiency_rows: list[dict] | None, service_breakdown: list[dict] | None):
    eff_map = {
        str(r.get("category_label") or r.get("category_code") or ""): r
        for r in (efficiency_rows or [])
    }
    rows = service_breakdown or []
    if not rows:
        return dmc.Text("No sold service categories.", size="sm", c="dimmed")

    body = []
    for row in rows:
        label = str(row.get("service_label") or row.get("service_code") or "-")
        eff = eff_map.get(label) or {}
        sold_qty = eff.get("sold_qty")
        qty_display = f"{float(sold_qty):,.2f}" if sold_qty is not None else "-"
        body.append(
            html.Tr(
                [
                    html.Td(label),
                    html.Td(format_crm_money(row.get("amount_tl"))),
                    html.Td(qty_display, style={"textAlign": "right"}),
                ]
            )
        )
    return dmc.Table(
        striped=True,
        highlightOnHover=True,
        children=[
            html.Thead(
                html.Tr(
                    [
                        html.Th("Service category"),
                        html.Th("Amount (TL)"),
                        html.Th("Sold quantity", style={"textAlign": "right"}),
                    ]
                )
            ),
            html.Tbody(body),
        ],
    )


def build_crm_line_items_table(sales_items: list[dict] | None, limit: int = 25):
    items = list(sales_items or [])[:limit]
    if not items:
        return dmc.Text("No realized sales line items.", size="sm", c="dimmed")

    body = []
    for item in items:
        qty = item.get("quantity")
        qty_display = f"{float(qty):,.2f}" if qty is not None else "-"
        body.append(
            html.Tr(
                [
                    html.Td(str(item.get("product_name") or "-")),
                    html.Td(qty_display, style={"textAlign": "right"}),
                    html.Td(format_crm_money(item.get("line_total"), item.get("currency"))),
                    html.Td(str(item.get("reference_number") or "-")),
                    html.Td(str(item.get("status") or "-")),
                ]
            )
        )
    return dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=True,
        children=[
            html.Thead(
                html.Tr(
                    [
                        html.Th("Product"),
                        html.Th("Quantity", style={"textAlign": "right"}),
                        html.Th("Line total"),
                        html.Th("Order ref"),
                        html.Th("Status"),
                    ]
                )
            ),
            html.Tbody(body),
        ],
    )


def build_crm_sold_services_panel(
    service_breakdown: list[dict] | None,
    efficiency_rows: list[dict] | None,
    sales_items: list[dict] | None,
):
    if not (service_breakdown or sales_items):
        return dmc.Alert(
            color="gray",
            variant="light",
            title="No realized sales",
            children="No fulfilled or invoiced CRM sales were returned for this customer.",
        )
    return dmc.Stack(
        gap="lg",
        children=[
            build_crm_service_sales_chart(service_breakdown),
            build_crm_category_table(efficiency_rows, service_breakdown),
            html.Div(
                children=[
                    dmc.Text("Sold line items", fw=700, size="sm", c="#2B3674", mb="xs"),
                    build_crm_line_items_table(sales_items),
                ]
            ),
        ],
    )


def build_crm_intro_card(customer_name: str, sales_summary: dict | None, service_breakdown: list[dict] | None):
    return dmc.SimpleGrid(
        cols={"base": 1, "md": 2},
        spacing="lg",
        style={"padding": "0 30px", "marginBottom": "24px"},
        children=[
            html.Div(
                className="nexus-card",
                style={"padding": "24px"},
                children=[
                    dmc.Group(
                        gap="sm",
                        mb="md",
                        children=[
                            dmc.ThemeIcon(
                                size="xl",
                                variant="light",
                                color="indigo",
                                radius="md",
                                children=DashIconify(icon="solar:users-group-two-rounded-bold-duotone", width=30),
                            ),
                            dmc.Stack(
                                gap=0,
                                children=[
                                    dmc.Text(customer_name, fw=700, size="lg", c="#2B3674"),
                                    dmc.Text(
                                        "CRM sales · Infrastructure assets",
                                        size="sm",
                                        c="#A3AED0",
                                        fw=500,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    dmc.Text(
                        "Realized CRM sales (YTD and lifetime) plus infrastructure billing assets for this customer.",
                        size="sm",
                        c="#A3AED0",
                    ),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    dmc.Text("CRM Sales", fw=700, size="sm", c="#2B3674", mb="sm"),
                    build_crm_intro_kpi_strip(sales_summary, service_breakdown),
                ],
            ),
        ],
    )
