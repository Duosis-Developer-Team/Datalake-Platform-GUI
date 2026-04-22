from __future__ import annotations

from dash import Input, Output, State, callback, dcc, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from src.services import api_client as api
from src.services.db_service import DISABLED_CUSTOMERS, WARMED_CUSTOMERS
from src.utils.time_range import default_time_range


def _load_customers() -> dict[str, list[str]]:
    try:
        fetched = api.get_customer_list()
    except Exception:
        fetched = []
    warmed = set(WARMED_CUSTOMERS)
    active = [name for name in fetched if name in warmed] or list(WARMED_CUSTOMERS)
    return {"active": active, "disabled": list(DISABLED_CUSTOMERS)}


def _matches_query(name: str, query: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return True
    return q in (name or "").lower()


def _customer_card(name: str):
    return dcc.Link(
        href=f"/customer-view?customer={name}",
        style={"textDecoration": "none", "color": "inherit", "display": "block", "height": "100%"},
        children=dmc.Paper(
            className="nexus-card customer-list-card",
            radius="lg",
            p="lg",
            withBorder=True,
            style={"height": "100%", "minHeight": "190px"},
            children=dmc.Stack(
                gap="md",
                justify="space-between",
                style={"height": "100%"},
                children=[
                    dmc.Group(
                        justify="space-between",
                        align="flex-start",
                        children=[
                            dmc.Group(
                                gap="sm",
                                align="center",
                                children=[
                                    dmc.ThemeIcon(
                                        size=42,
                                        radius="xl",
                                        variant="light",
                                        color="indigo",
                                        children=DashIconify(
                                            icon="solar:users-group-two-rounded-bold-duotone",
                                            width=22,
                                        ),
                                    ),
                                    dmc.Stack(
                                        gap=2,
                                        children=[
                                            dmc.Text(name, fw=700, size="lg", c="#2B3674"),
                                            dmc.Text("Customer Profile", size="xs", c="#A3AED0"),
                                        ],
                                    ),
                                ],
                            ),
                            dmc.Badge("Pilot", variant="light", color="teal", radius="xl"),
                        ],
                    ),
                    dmc.Divider(color="#E9EDF7"),
                    dmc.Group(
                        justify="space-between",
                        align="center",
                        children=[
                            dmc.Text("Open customer details", size="sm", c="#A3AED0", fw=500),
                            dmc.Group(
                                gap=6,
                                align="center",
                                children=[
                                    dmc.Text("Open", size="sm", fw=700, c="#4318FF"),
                                    DashIconify(icon="solar:arrow-right-line-duotone", width=16, color="#4318FF"),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ),
    )


def _disabled_customer_card(name: str):
    return html.Div(
        style={"display": "block", "height": "100%"},
        children=dmc.Paper(
            className="nexus-card customer-list-card customer-list-card--disabled",
            radius="lg",
            p="lg",
            withBorder=True,
            style={
                "height": "100%",
                "minHeight": "190px",
                "opacity": 0.45,
                "pointerEvents": "none",
            },
            children=dmc.Stack(
                gap="md",
                justify="space-between",
                style={"height": "100%"},
                children=[
                    dmc.Group(
                        justify="space-between",
                        align="flex-start",
                        children=[
                            dmc.Group(
                                gap="sm",
                                align="center",
                                children=[
                                    dmc.ThemeIcon(
                                        size=42,
                                        radius="xl",
                                        variant="light",
                                        color="gray",
                                        children=DashIconify(
                                            icon="solar:users-group-two-rounded-bold-duotone",
                                            width=22,
                                        ),
                                    ),
                                    dmc.Stack(
                                        gap=2,
                                        children=[
                                            dmc.Text(name, fw=700, size="lg", c="#2B3674"),
                                            dmc.Text("Customer Profile", size="xs", c="#A3AED0"),
                                        ],
                                    ),
                                ],
                            ),
                            dmc.Badge("Disabled", variant="light", color="gray", radius="xl"),
                        ],
                    ),
                    dmc.Divider(color="#E9EDF7"),
                    dmc.Text("Currently unavailable", size="sm", c="#A3AED0", fw=500),
                ],
            ),
        ),
    )


def _build_customer_cards(store_data: dict, query: str):
    active = store_data.get("active", []) if isinstance(store_data, dict) else []
    disabled = store_data.get("disabled", []) if isinstance(store_data, dict) else []
    active_filtered = [name for name in active if _matches_query(name, query)]
    disabled_filtered = [name for name in disabled if _matches_query(name, query)]

    grid_children: list = []
    idx = 0
    for name in active_filtered:
        grid_children.append(
            html.Div(
                className=f"dc-card-enter dc-card-n{min(idx + 1, 12)}",
                style={"height": "100%"},
                children=_customer_card(name),
            )
        )
        idx += 1
    for name in disabled_filtered:
        grid_children.append(
            html.Div(
                className=f"dc-card-enter dc-card-n{min(idx + 1, 12)}",
                style={"height": "100%"},
                children=_disabled_customer_card(name),
            )
        )
        idx += 1

    if not grid_children:
        return dmc.Alert(
            title="No customer found",
            color="yellow",
            children="No customer card matches the current search query.",
        )

    return dmc.SimpleGrid(
        cols=3,
        spacing="lg",
        style={"padding": "0 32px"},
        children=grid_children,
    )


def build_customers_list(time_range=None, visible_sections=None):
    _ = visible_sections
    tr = time_range or default_time_range()
    store_data = _load_customers()
    active_count = len(store_data.get("active", []))

    return html.Div(
        className="customer-page-enter",
        children=[
            dcc.Store(id="customer-cards-store", data=store_data),
            dmc.Stack(
                gap="xl",
                style={"padding": "8px 0 24px"},
                children=[
                    dmc.Paper(
                        className="nexus-card",
                        radius="xl",
                        p="lg",
                        mx=32,
                        children=dmc.Group(
                            justify="space-between",
                            align="center",
                            children=[
                                dmc.Group(
                                    gap="md",
                                    children=[
                                        dmc.ThemeIcon(
                                            size=44,
                                            radius="xl",
                                            variant="light",
                                            color="indigo",
                                            children=DashIconify(
                                                icon="solar:users-group-two-rounded-bold-duotone",
                                                width=22,
                                            ),
                                        ),
                                        dmc.Stack(
                                            gap=2,
                                            children=[
                                                dmc.Text("Customer View", fw=800, size="xl", c="#2B3674"),
                                                dmc.Text(
                                                    f"{active_count} customer card(s) available",
                                                    size="sm",
                                                    c="#A3AED0",
                                                ),
                                                dmc.Text(
                                                    f"Time preset: {tr.get('preset', '')}",
                                                    size="xs",
                                                    c="#A3AED0",
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                                dmc.TextInput(
                                    id="customer-search-input",
                                    placeholder="Search customer...",
                                    leftSection=DashIconify(icon="solar:magnifer-linear", width=16, color="#A3AED0"),
                                    radius="md",
                                    size="sm",
                                    style={"width": "280px"},
                                ),
                            ],
                        ),
                    ),
                    html.Div(
                        id="customer-cards-grid",
                        children=_build_customer_cards(store_data, ""),
                    ),
                ],
            ),
        ],
    )


@callback(
    Output("customer-cards-grid", "children"),
    Input("customer-search-input", "value"),
    State("customer-cards-store", "data"),
)
def filter_customer_cards(query, store_data):
    if isinstance(store_data, dict):
        return _build_customer_cards(store_data, query or "")
    # Backward compatibility if store still holds a flat list
    if isinstance(store_data, list):
        warmed = set(WARMED_CUSTOMERS)
        names = [str(n) for n in store_data if str(n).strip()]
        active = [n for n in names if n in warmed] or list(WARMED_CUSTOMERS)
        return _build_customer_cards({"active": active, "disabled": list(DISABLED_CUSTOMERS)}, query or "")
    return _build_customer_cards({"active": [], "disabled": list(DISABLED_CUSTOMERS)}, query or "")
