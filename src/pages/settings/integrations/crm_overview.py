"""Integrations — CRM Dynamics 365 overview (discovery counts + navigation helpers)."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from src.services import api_client as api


def build_layout(search: str | None = None) -> html.Div:
    rows = api.get_crm_discovery_counts()

    table_rows = []
    for r in rows:
        table_rows.append(
            html.Tr(
                [
                    html.Td(str(r.get("table_name") or "")),
                    html.Td(str(r.get("row_count") or 0)),
                    html.Td(str(r.get("last_collected") or "-")),
                ]
            )
        )

    cards = dmc.SimpleGrid(
        cols={"base": 1, "sm": 2},
        spacing="md",
        children=[
            _nav_card(
                "/settings/integrations/crm/service-mapping",
                "CRM service mapping",
                "Map CRM catalog SKUs to GUI billing panels.",
                "solar:bookmark-bold-duotone",
            ),
            _nav_card(
                "/settings/integrations/crm/aliases",
                "Customer aliases",
                "Resolve CRM accounts ↔ NetBox tenant identifiers.",
                "solar:users-group-rounded-bold-duotone",
            ),
            _nav_card(
                "/settings/integrations/crm/thresholds",
                "Capacity thresholds",
                "Sellable ceilings per resource type / DC.",
                "solar:chart-square-bold-duotone",
            ),
            _nav_card(
                "/settings/integrations/crm/price-overrides",
                "Price overrides",
                "Manual catalog unit prices when Dynamics price lists are empty.",
                "solar:wallet-money-bold-duotone",
            ),
            _nav_card(
                "/settings/integrations/crm/calc-config",
                "Calculation variables",
                "Efficiency bands, allocator caps and cache TTL knobs.",
                "solar:slider-vertical-bold-duotone",
            ),
        ],
    )

    return html.Div(
        [
            dmc.Stack(
                gap="xs",
                mb="md",
                children=[
                    dmc.Title("CRM Dynamics 365", order=3),
                    dmc.Text(
                        "Raw CRM orders stay in the datalake DB. Operator-managed mappings and calculation knobs "
                        "live in the separate WebUI App DB (`bulutwebui`). Use this overview to verify ingestion "
                        "volume before adjusting mappings.",
                        size="sm",
                        c="dimmed",
                    ),
                ],
            ),
            cards,
            dmc.Paper(
                p="md",
                mt="lg",
                radius="md",
                withBorder=True,
                children=[
                    dmc.Title("discovery_crm_* row counts", order=5, mb="sm"),
                    html.Table(
                        className="table table-sm",
                        style={"width": "100%", "borderCollapse": "collapse"},
                        children=[
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("Table"),
                                        html.Th("Rows"),
                                        html.Th("Last collection"),
                                    ]
                                )
                            ),
                            html.Tbody(table_rows or [html.Tr([html.Td(colSpan=3, children="No data")])]),
                        ],
                    ),
                ],
            ),
        ]
    )


def _nav_card(href: str, title: str, desc: str, icon: str) -> dmc.Card:
    return dmc.Card(
        withBorder=True,
        radius="md",
        padding="md",
        children=[
            dmc.Anchor(
                [
                    dmc.Group(
                        gap="sm",
                        wrap="nowrap",
                        children=[
                            DashIconify(icon=icon, width=22, color="#552cf8"),
                            dmc.Stack(gap=2, children=[dmc.Text(title, fw=700), dmc.Text(desc, size="xs", c="dimmed")]),
                        ],
                    )
                ],
                href=href,
                underline=False,
            )
        ],
    )
