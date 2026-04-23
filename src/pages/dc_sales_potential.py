"""
DC Sales Potential page.

Shows datacenter-level sales intelligence:
- YTD billed revenue and open pipeline from customers present in this DC
- Standard catalog prices from CRM discovery
- Estimated idle capacity valuation

Route: /dc-sales-potential/{dc_code}
"""
from __future__ import annotations

import dash
from dash import dcc, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from src.services import api_client as api
from src.utils.time_range import default_time_range

dash.register_page(
    __name__,
    path_template="/dc-sales-potential/<dc_code>",
    title="DC Sales Potential",
)


def _kpi(label: str, value: str, icon: str, color: str = "indigo"):
    return html.Div(
        className="nexus-card",
        style={"padding": "20px"},
        children=dmc.Group(gap="md", align="flex-start", children=[
            dmc.ThemeIcon(
                size="xl", variant="light", color=color, radius="md",
                children=DashIconify(icon=icon, width=28),
            ),
            dmc.Stack(gap=2, children=[
                dmc.Text(label, size="sm", c="dimmed"),
                dmc.Text(value, size="xl", fw=700, c="#2B3674"),
            ]),
        ]),
    )


def _catalog_table(rows: list[dict]):
    if not rows:
        return dmc.Alert(color="yellow", title="No catalog data", children="CRM catalog not yet seeded.")

    def _row(r):
        return html.Tr([
            html.Td(r.get("product_name") or "-"),
            html.Td(r.get("unit") or "-"),
            html.Td(f"{float(r['unit_price_tl']):,.2f} TL" if r.get("unit_price_tl") is not None else "-"),
            html.Td(r.get("price_list") or "-"),
        ])

    return dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=True,
        children=[
            html.Thead(html.Tr([
                html.Th("Product"), html.Th("Unit"), html.Th("Unit Price (TL)"), html.Th("Price List"),
            ])),
            html.Tbody([_row(r) for r in rows]),
        ],
    )


def layout(dc_code: str = ""):
    if not dc_code:
        return dmc.Alert(color="red", title="No DC specified", children="Provide a DC code in the URL.")

    data = api.get_dc_sales_potential(dc_code)
    summary = data.get("summary") or {}
    catalog = data.get("catalog_detail") or []

    currency = "TL"
    ytd = summary.get("total_billed_ytd") or 0
    inv_cnt = summary.get("invoice_count") or 0
    pipeline = summary.get("total_pipeline_value") or 0
    opp_cnt = summary.get("open_opportunity_count") or 0
    cust_cnt = summary.get("customer_count") or 0

    header = dmc.Group(
        justify="space-between",
        style={"padding": "24px 30px 0 30px"},
        children=[
            dmc.Group(gap="sm", children=[
                dmc.ThemeIcon(
                    size="xl", variant="light", color="violet", radius="md",
                    children=DashIconify(icon="solar:buildings-3-bold-duotone", width=30),
                ),
                dmc.Stack(gap=0, children=[
                    dmc.Text(f"DC Sales Potential — {dc_code}", fw=700, size="xl", c="#2B3674"),
                    dmc.Text("CRM-derived billing and catalog valuation for this datacenter", size="sm", c="#A3AED0"),
                ]),
            ]),
            dmc.Anchor("← Back to Datacenter", href=f"/dc-view/{dc_code}", size="sm", c="indigo"),
        ],
    )

    kpis = dmc.SimpleGrid(
        cols=5, spacing="lg",
        style={"padding": "24px 30px"},
        children=[
            _kpi("Customers in DC",   str(cust_cnt),                      "solar:users-group-two-rounded-bold-duotone", "teal"),
            _kpi("YTD Revenue",       f"{ytd:,.2f} {currency}",           "solar:money-bag-bold-duotone",               "green"),
            _kpi("Invoices (YTD)",    str(inv_cnt),                       "solar:document-bold-duotone",                 "blue"),
            _kpi("Open Pipeline",     f"{pipeline:,.2f} {currency}",      "solar:target-bold-duotone",                   "indigo"),
            _kpi("Open Opportunities",str(opp_cnt),                       "solar:star-bold-duotone",                     "orange"),
        ],
    )

    catalog_section = html.Div(
        style={"padding": "0 30px 30px 30px"},
        children=[
            dmc.Text("Standard Catalog Prices (TL)", fw=600, size="lg", mb="sm", c="#2B3674"),
            dmc.Text(
                "Unit prices from the active TL price list. Multiply by idle capacity to estimate potential revenue.",
                size="sm", c="#A3AED0", mb="md",
            ),
            _catalog_table(catalog),
        ],
    )

    return html.Div(children=[
        header,
        kpis,
        catalog_section,
    ])
