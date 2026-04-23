"""
Settings — Customer Alias Management page.

Allows operators to view and correct CRM account → platform customer key mappings.
Rows with source='auto' are seeded automatically; editing them promotes them to source='manual'.

Route: /settings/customer-alias
"""
from __future__ import annotations

import dash
from dash import dcc, html, Input, Output, State, callback, ctx
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import httpx
import os

from src.services import api_client as api

dash.register_page(
    __name__,
    path="/settings/customer-alias",
    title="Customer Alias Management",
)

_CUSTOMER_API = os.getenv("CUSTOMER_API_URL", "http://customer-api:8001").rstrip("/")
_API_KEY = os.getenv("API_KEY", "")


def _row_form(alias: dict):
    aid = alias.get("crm_accountid", "")
    return html.Tr([
        html.Td(aid, style={"fontSize": "11px", "color": "#888", "maxWidth": "120px", "overflow": "hidden", "textOverflow": "ellipsis"}),
        html.Td(alias.get("crm_account_name") or "-"),
        html.Td(
            dmc.TextInput(
                id={"type": "alias-canonical", "index": aid},
                value=alias.get("canonical_customer_key") or "",
                size="xs",
                placeholder="canonical key",
                style={"minWidth": "160px"},
            )
        ),
        html.Td(
            dmc.TextInput(
                id={"type": "alias-netbox", "index": aid},
                value=alias.get("netbox_musteri_value") or "",
                size="xs",
                placeholder="NetBox musteri value",
                style={"minWidth": "160px"},
            )
        ),
        html.Td(
            dmc.TextInput(
                id={"type": "alias-notes", "index": aid},
                value=alias.get("notes") or "",
                size="xs",
                placeholder="notes",
            )
        ),
        html.Td(
            dmc.Badge(
                alias.get("source") or "auto",
                color="teal" if alias.get("source") == "manual" else "gray",
                size="sm",
            )
        ),
        html.Td(
            dmc.Button(
                "Save",
                id={"type": "alias-save-btn", "index": aid},
                size="xs",
                color="indigo",
                variant="light",
            )
        ),
    ])


def layout():
    aliases = api.get_crm_aliases()

    if not aliases:
        info = dmc.Alert(
            color="yellow",
            title="No alias data",
            children=[
                "Run the auto-seed SQL script first: ",
                dmc.Code("psql -d datalake -f SQL/CRM/seed_customer_alias_from_accounts.sql"),
            ],
        )
    else:
        info = None

    table = dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=True,
        children=[
            html.Thead(html.Tr([
                html.Th("CRM Account ID"),
                html.Th("CRM Account Name"),
                html.Th("Canonical Key"),
                html.Th("NetBox Musteri"),
                html.Th("Notes"),
                html.Th("Source"),
                html.Th(""),
            ])),
            html.Tbody([_row_form(a) for a in aliases] if aliases else [
                html.Tr([html.Td("No data", colSpan=7)])
            ]),
        ],
    ) if aliases else None

    return html.Div(
        style={"padding": "30px"},
        children=[
            dmc.Group(gap="sm", mb="lg", children=[
                dmc.ThemeIcon(
                    size="xl", variant="light", color="teal", radius="md",
                    children=DashIconify(icon="solar:link-circle-bold-duotone", width=28),
                ),
                dmc.Stack(gap=0, children=[
                    dmc.Text("Customer Alias Management", fw=700, size="xl", c="#2B3674"),
                    dmc.Text(
                        "Map CRM account IDs to platform canonical customer keys and NetBox musteri values.",
                        size="sm", c="#A3AED0",
                    ),
                ]),
            ]),
            dmc.Alert(
                color="blue",
                title="How it works",
                mb="lg",
                children=[
                    "Rows marked ",
                    dmc.Badge("auto", color="gray", size="sm"),
                    " are seeded automatically from CRM accounts. Editing a row promotes it to ",
                    dmc.Badge("manual", color="teal", size="sm"),
                    " — manual rows survive re-seeding without being overwritten.",
                ],
            ),
            info,
            html.Div(id="alias-save-feedback", style={"marginBottom": "12px"}),
            dcc.Store(id="alias-save-trigger"),
            html.Div(style={"overflowX": "auto"}, children=[table]) if table else html.Div(),
        ],
    )
