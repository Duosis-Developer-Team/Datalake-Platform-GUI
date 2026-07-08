"""CRM sales panels for Customer View context card and Billing tab."""
from __future__ import annotations

from dash import dcc, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objects as go

from src.utils.visibility import is_meaningful_value, visible_kv_rows


def format_crm_money(value, currency: str | None = None) -> str:
    cur = (currency or "TL").strip() or "TL"
    if value is None:
        return "-"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{amount:,.2f} {cur}"


def crm_has_sales_data(
    sales_summary: dict | None,
    active_items: list[dict] | None = None,
) -> bool:
    summary = sales_summary or {}
    return bool(
        float(summary.get("ytd_revenue_total") or 0) > 0
        or float(summary.get("lifetime_revenue_total") or 0) > 0
        or int(summary.get("invoice_count") or 0) > 0
        or int(summary.get("lifetime_order_count") or 0) > 0
        or int(summary.get("active_order_count") or 0) > 0
        or float(summary.get("active_order_value") or 0) > 0
        or len(active_items or []) > 0
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
    active_items: list[dict] | None = None,
):
    summary = sales_summary or {}
    currency = summary.get("currency")
    service_count = len(service_breakdown or [])
    line_count = len(sales_items or [])
    active_line_count = len(active_items or [])

    candidate_rows = [
        ("Customer reference", customer_name or None),
        ("YTD realized revenue", summary.get("ytd_revenue_total")),
        ("Lifetime realized revenue", summary.get("lifetime_revenue_total")),
        ("YTD orders (fulfilled)", int(summary.get("invoice_count") or 0)),
        ("Lifetime orders", int(summary.get("lifetime_order_count") or 0)),
        ("Active orders (open)", int(summary.get("active_order_count") or 0)),
        ("Active order value", summary.get("active_order_value")),
        ("Service categories sold", service_count),
        ("Invoiced line items", line_count),
        ("Active line items", active_line_count),
        ("Currency", currency),
    ]
    rows = []
    for label, raw in visible_kv_rows(candidate_rows):
        if label == "Customer reference":
            display = str(raw)
        elif label == "Currency":
            display = str(raw)
        elif label in ("YTD orders (fulfilled)", "Lifetime orders", "Active orders (open)", "Service categories sold", "Invoiced line items", "Active line items"):
            display = f"{int(raw):,}"
        else:
            display = format_crm_money(raw, currency)
        rows.append(_kv_row(label, display))
    if not rows:
        return dmc.Text("No CRM sales metrics for this customer.", size="sm", c="dimmed")
    return html.Div(children=rows)


def build_crm_intro_kpi_strip(sales_summary: dict | None, service_breakdown: list[dict] | None):
    summary = sales_summary or {}
    currency = summary.get("currency")
    service_count = len(service_breakdown or [])
    candidates = [
        ("YTD Revenue", summary.get("ytd_revenue_total"), format_crm_money(summary.get("ytd_revenue_total"), currency), "green"),
        ("Lifetime Revenue", summary.get("lifetime_revenue_total"), format_crm_money(summary.get("lifetime_revenue_total"), currency), "teal"),
        ("YTD Orders", int(summary.get("invoice_count") or 0), f"{int(summary.get('invoice_count') or 0):,}", "cyan"),
        ("Active Orders", int(summary.get("active_order_count") or 0), f"{int(summary.get('active_order_count') or 0):,}", "orange"),
        ("Active Order Value", summary.get("active_order_value"), format_crm_money(summary.get("active_order_value"), currency), "grape"),
        ("Service categories", service_count, f"{service_count:,}", "violet"),
    ]
    tiles = [_intro_kpi(t, display, color) for t, raw, display, color in candidates if is_meaningful_value(raw)]
    if not tiles:
        return dmc.Text("No realized or active CRM sales in scope.", size="sm", c="dimmed")
    return dmc.SimpleGrid(
        cols={"base": 2, "md": min(3, len(tiles)), "lg": min(6, len(tiles))},
        spacing="md",
        children=tiles,
    )


def _intro_kpi(title: str, value: str, color: str):
    del color
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


def _line_items_table_body(items: list[dict], *, include_order_ref: bool = True):
    body = []
    for item in items:
        qty = item.get("quantity")
        qty_display = f"{float(qty):,.2f}" if qty is not None else "-"
        product = str(item.get("product_name") or item.get("productdescription") or "-")
        cells = [
            html.Td(product),
            html.Td(qty_display, style={"textAlign": "right"}),
            html.Td(format_crm_money(item.get("line_total"), item.get("currency"))),
        ]
        if include_order_ref:
            cells.extend(
                [
                    html.Td(str(item.get("reference_number") or "-")),
                    html.Td(str(item.get("status") or "-")),
                ]
            )
        body.append(html.Tr(cells))
    return body


def build_crm_line_items_table(sales_items: list[dict] | None, limit: int = 25):
    items = list(sales_items or [])[:limit]
    if not items:
        return dmc.Text("No invoiced sales line items.", size="sm", c="dimmed")

    table = dmc.Table(
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
            html.Tbody(_line_items_table_body(items)),
        ],
    )
    return html.Div(
        style={"overflowX": "auto", "width": "100%", "minWidth": 0, "maxWidth": "100%"},
        children=table,
    )


def _order_header_cards(headers: list[dict] | None):
    rows = headers or []
    if not rows:
        return None
    cards = []
    for header in rows:
        currency = header.get("currency")
        cards.append(
            html.Div(
                style={
                    "display": "grid",
                    "gridTemplateColumns": "1.2fr 1fr 1fr 1fr",
                    "gap": "8px",
                    "padding": "10px 12px",
                    "borderRadius": "10px",
                    "background": "#F4F7FE",
                    "marginBottom": "8px",
                    "fontSize": "0.8rem",
                },
                children=[
                    html.Div(
                        [
                            html.Div("Order ref", style={"color": "#A3AED0", "fontWeight": 600}),
                            html.Div(
                                str(header.get("reference_number") or "-"),
                                style={"color": "#2B3674", "fontWeight": 700},
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Div("Date", style={"color": "#A3AED0", "fontWeight": 600}),
                            html.Div(str(header.get("date") or "-"), style={"color": "#2B3674", "fontWeight": 600}),
                        ]
                    ),
                    html.Div(
                        [
                            html.Div("Status", style={"color": "#A3AED0", "fontWeight": 600}),
                            html.Div(str(header.get("status") or "-"), style={"color": "#2B3674", "fontWeight": 600}),
                        ]
                    ),
                    html.Div(
                        [
                            html.Div("Order total", style={"color": "#A3AED0", "fontWeight": 600}),
                            html.Div(
                                format_crm_money(header.get("order_total"), currency),
                                style={"color": "#2B3674", "fontWeight": 700},
                            ),
                        ]
                    ),
                ],
            )
        )
    return html.Div(children=cards)


def build_crm_active_orders_section(
    active_orders: list[dict] | None,
    active_items: list[dict] | None,
    limit: int = 50,
):
    headers = active_orders or []
    items = list(active_items or [])[:limit]
    if not headers and not items:
        return dmc.Alert(
            color="gray",
            variant="light",
            title="No active orders",
            children="No open CRM sales orders were returned for this customer.",
        )

    header_cards = _order_header_cards(headers)
    table = dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=True,
        children=[
            html.Thead(
                html.Tr(
                    [
                        html.Th("Order ref"),
                        html.Th("Date"),
                        html.Th("Status"),
                        html.Th("Product"),
                        html.Th("Quantity", style={"textAlign": "right"}),
                        html.Th("Unit price", style={"textAlign": "right"}),
                        html.Th("Line total"),
                    ]
                )
            ),
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td(str(item.get("reference_number") or "-")),
                            html.Td(str(item.get("date") or "-")),
                            html.Td(str(item.get("status") or "-")),
                            html.Td(str(item.get("product_name") or item.get("productdescription") or "-")),
                            html.Td(
                                f"{float(item.get('quantity')):,.2f}"
                                if item.get("quantity") is not None
                                else "-",
                                style={"textAlign": "right"},
                            ),
                            html.Td(
                                format_crm_money(item.get("unit_price"), item.get("currency")),
                                style={"textAlign": "right"},
                            ),
                            html.Td(format_crm_money(item.get("line_total"), item.get("currency"))),
                        ]
                    )
                    for item in items
                ]
                if items
                else [html.Tr(html.Td("No line items", colSpan=7))]
            ),
        ],
    )

    children = []
    if header_cards is not None:
        children.append(header_cards)
    # Wide line-item table: horizontal scroll so QUANTITY/price columns stay reachable.
    # minWidth:0 defeats the flex-item min-content floor so overflowX actually engages.
    children.append(
        html.Div(
            style={"overflowX": "auto", "width": "100%", "minWidth": 0, "maxWidth": "100%"},
            children=table,
        )
    )
    return dmc.Stack(gap="md", children=children)


def build_crm_invoiced_orders_section(
    service_breakdown: list[dict] | None,
    efficiency_rows: list[dict] | None,
    sales_items: list[dict] | None,
):
    if not (service_breakdown or sales_items):
        return dmc.Alert(
            color="blue",
            variant="light",
            title="No invoiced orders yet",
            children="No fulfilled or invoiced CRM sales were returned for this customer.",
        )
    return dmc.Stack(
        gap="lg",
        children=[
            build_crm_service_sales_chart(service_breakdown),
            build_crm_category_table(efficiency_rows, service_breakdown),
            html.Div(
                children=[
                    dmc.Text("Invoiced line items", fw=700, size="sm", c="#2B3674", mb="xs"),
                    build_crm_line_items_table(sales_items),
                ]
            ),
        ],
    )


def build_crm_sold_services_panel(
    service_breakdown: list[dict] | None,
    efficiency_rows: list[dict] | None,
    sales_items: list[dict] | None,
):
    """Backward-compatible wrapper for invoiced orders panel."""
    return build_crm_invoiced_orders_section(service_breakdown, efficiency_rows, sales_items)


def build_crm_context_card(
    customer_name: str,
    sales_summary: dict | None,
    compliance_payload: dict | None = None,
):
    """Single header context card — identity, risk badge, primary commercial signal."""
    summary = sales_summary or {}
    currency = summary.get("currency")
    compliance_summary = (compliance_payload or {}).get("summary") or {}
    has_overuse = bool(compliance_summary.get("has_overuse"))
    active_value = summary.get("active_order_value")

    stack_children: list = [
        dmc.Group(
            gap="xs",
            align="center",
            children=[
                dmc.Text(customer_name, fw=700, size="lg", c="#2B3674"),
                dmc.Badge("Resource overage", color="red", variant="filled", size="sm") if has_overuse else None,
            ],
        ),
        dmc.Text(
            "Customer overview — use Summary for signals, Billing for commercial detail.",
            size="sm",
            c="#A3AED0",
            fw=500,
        ),
    ]
    if is_meaningful_value(active_value):
        stack_children.append(
            dmc.Text(
                f"Active order value: {format_crm_money(active_value, currency)}",
                size="sm",
                c="#4318FF",
                fw=700,
            )
        )
    if has_overuse and is_meaningful_value(compliance_summary.get("total_overage_loss_tl")):
        stack_children.append(
            dmc.Text(
                f"Est. overage loss: {format_crm_money(compliance_summary.get('total_overage_loss_tl'), currency)}",
                size="sm",
                c="#E03131",
                fw=700,
            )
        )

    return html.Div(
        className="nexus-card",
        style={"padding": "24px", "margin": "0 30px 24px"},
        children=[
            dmc.Group(
                gap="sm",
                children=[
                    dmc.ThemeIcon(
                        size="xl",
                        variant="light",
                        color="indigo",
                        radius="md",
                        children=DashIconify(icon="solar:users-group-two-rounded-bold-duotone", width=30),
                    ),
                    dmc.Stack(gap=4, children=stack_children),
                ],
            ),
        ],
    )


def build_crm_intro_card(
    customer_name: str,
    sales_summary: dict | None,
    service_breakdown: list[dict] | None,
    compliance_payload: dict | None = None,
):
    """Backward-compatible wrapper — delegates to single context card."""
    del service_breakdown
    return build_crm_context_card(customer_name, sales_summary, compliance_payload=compliance_payload)
