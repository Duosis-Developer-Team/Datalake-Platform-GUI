from __future__ import annotations

from dash import Input, Output, State, ALL, callback, ctx, dcc, html, no_update
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objects as go

from src.services import api_client as api
from src.utils.customers_list_ui import (
    badge_color_for_mapping_status,
    filter_catalog_rows,
    format_revenue,
    overuse_badge_props,
    page_count,
    paginate_rows,
)
from src.utils.time_range import default_time_range
from src.utils.ui_tokens import card_style, kpi_card

_PAGE_SIZE = 12
_SECTION_KEYS = ("vip", "mapped", "unmapped")


def _load_page_data() -> dict:
    try:
        catalog = api.get_customer_catalog() or {}
        overview = api.get_customer_overview() or {}
    except Exception:
        catalog = {}
        overview = {}
    customers = catalog.get("customers") if isinstance(catalog.get("customers"), list) else []
    groups = catalog.get("groups") if isinstance(catalog.get("groups"), dict) else {}
    if not groups and customers:
        groups = {"vip": [], "mapped": [], "unmapped": []}
        for row in customers:
            group = str(row.get("list_group") or "unmapped")
            groups.setdefault(group, []).append(row)
    return {
        "customers": customers,
        "groups": groups,
        "overview": overview if isinstance(overview, dict) else {},
    }


def _can_manage_vip(permissions: dict | None) -> bool:
    if permissions is None:
        return True
    row = (permissions or {}).get("action:customer_view:vip_manage") or {}
    return bool(row.get("edit") or row.get("view"))


def _status_badges(row: dict, *, show_unmapped_on_vip: bool = False) -> list:
    badges: list = []
    if row.get("is_vip"):
        badges.append(dmc.Badge("VIP", color="yellow", variant="filled", size="xs"))
    if show_unmapped_on_vip and row.get("is_vip") and not row.get("mapped"):
        badges.append(dmc.Badge("Unmapped", color="gray", variant="light", size="xs"))
    mapping_status = str(row.get("mapping_status") or "empty")
    if row.get("mapped"):
        badges.append(
            dmc.Badge(
                "Mapped",
                color=badge_color_for_mapping_status(mapping_status),
                variant="light",
                size="xs",
            )
        )
    elif not row.get("is_vip"):
        badges.append(dmc.Badge("CRM only", color="gray", variant="light", size="xs"))
    if row.get("mapped"):
        cache_label = "Cached" if row.get("real_data_cached") else "Cache cold"
        cache_color = "teal" if row.get("real_data_cached") else "orange"
        badges.append(dmc.Badge(cache_label, color=cache_color, variant="outline", size="xs"))
    overuse_label, overuse_color = overuse_badge_props(str(row.get("overuse_status") or ""))
    if row.get("mapped") or row.get("is_vip"):
        badges.append(dmc.Badge(overuse_label, color=overuse_color, variant="outline", size="xs"))
    return badges


def _compact_customer_card(row: dict, *, allow_vip_toggle: bool):
    name = str(row.get("display_name") or row.get("crm_account_name") or "-")
    account_id = str(row.get("crm_accountid") or "")
    revenue = format_revenue(row.get("ytd_revenue"), row.get("currency"))
    star = None
    if allow_vip_toggle:
        star = dmc.ActionIcon(
            DashIconify(
                icon="tabler:star-filled" if row.get("is_vip") else "tabler:star",
                width=18,
            ),
            id={"type": "customer-vip-toggle", "account": account_id},
            variant="subtle" if row.get("is_vip") else "transparent",
            color="yellow" if row.get("is_vip") else "gray",
            size="sm",
            style={"opacity": 0.85},
            n_clicks=0,
        )

    header = dmc.Group(
        justify="space-between",
        align="flex-start",
        wrap="nowrap",
        children=[
            dmc.Stack(
                gap=2,
                style={"minWidth": 0, "flex": 1},
                children=[
                    dmc.Text(name, fw=700, size="sm", c="#2B3674", lineClamp=2),
                    dmc.Text(f"YTD {revenue}", size="xs", c="#A3AED0"),
                    dmc.Group(gap=4, wrap="wrap", children=_status_badges(row, show_unmapped_on_vip=True)),
                ],
            ),
            dmc.Stack(
                gap=4,
                align="flex-end",
                children=[
                    star,
                    dmc.Anchor(
                        "Open",
                        href=f"/customer-view?customer={name}",
                        size="xs",
                        c="#4318FF",
                        underline="never",
                    ),
                ],
            ),
        ],
    )

    return dmc.Paper(
        className="nexus-card customer-list-card customer-list-card--compact",
        radius="md",
        p="sm",
        withBorder=True,
        style={"minHeight": "96px"},
        children=header,
    )


def _service_sales_chart(service_sales: list[dict]):
    rows = service_sales or []
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


def _overview_strip(overview: dict):
    ov = overview or {}
    return dmc.SimpleGrid(
        cols={"base": 2, "sm": 3, "lg": 6},
        spacing="md",
        children=[
            kpi_card("CRM Customers", int(ov.get("total_customers") or 0), icon="solar:users-group-rounded-bold-duotone", color="indigo"),
            kpi_card("Mapped", int(ov.get("mapped_count") or 0), icon="solar:link-circle-bold-duotone", color="teal"),
            kpi_card("Unmapped", int(ov.get("unmapped_count") or 0), icon="solar:unlink-circle-bold-duotone", color="gray"),
            kpi_card("VIP", int(ov.get("vip_count") or 0), icon="solar:star-bold-duotone", color="yellow"),
            kpi_card(
                "Realized Sales",
                format_revenue(ov.get("total_revenue"), ov.get("currency")),
                icon="solar:wallet-money-bold-duotone",
                color="violet",
            ),
            kpi_card(
                "Overuse (pending)",
                int(ov.get("overuse_customer_count") or 0),
                icon="solar:danger-triangle-bold-duotone",
                color="orange",
            ),
        ],
    )


def _render_section_cards(rows: list[dict], *, allow_vip_toggle: bool):
    if not rows:
        return dmc.Alert(
            color="gray",
            variant="light",
            title="No customers",
            children="No customers match the current filter in this section.",
        )
    return dmc.SimpleGrid(
        cols={"base": 1, "sm": 2, "lg": 3},
        spacing="sm",
        children=[_compact_customer_card(row, allow_vip_toggle=allow_vip_toggle) for row in rows],
    )


def _section_panel(section_key: str, rows: list[dict], page: int, *, allow_vip_toggle: bool):
    total = len(rows)
    pages = page_count(total, _PAGE_SIZE)
    page = min(max(int(page or 0), 0), pages - 1)
    page_rows = paginate_rows(rows, page, _PAGE_SIZE)
    return html.Div(
        children=[
            _render_section_cards(page_rows, allow_vip_toggle=allow_vip_toggle),
            dmc.Group(
                justify="space-between",
                mt="sm",
                children=[
                    dmc.Text(f"{total} customer(s)", size="xs", c="dimmed"),
                    dmc.Pagination(
                        id={"type": "customer-section-page", "section": section_key},
                        total=pages,
                        value=page + 1,
                        size="sm",
                    ),
                ],
            ),
        ]
    )


def _build_accordion(store_data: dict, query: str, pages: dict[str, int], *, allow_vip_toggle: bool):
    groups = store_data.get("groups") if isinstance(store_data.get("groups"), dict) else {}
    filtered_groups = {
        key: filter_catalog_rows(groups.get(key) or [], query)
        for key in _SECTION_KEYS
    }
    labels = {
        "vip": "VIP Customers",
        "mapped": "Mapped Customers",
        "unmapped": "Unmapped CRM Customers",
    }
    descriptions = {
        "vip": "Pinned customers with continuous cache warm-up.",
        "mapped": "CRM customers linked to infrastructure source mappings.",
        "unmapped": "CRM-only customers without enabled source mappings.",
    }
    items = []
    for key in _SECTION_KEYS:
        count = len(filtered_groups.get(key) or [])
        items.append(
            dmc.AccordionItem(
                value=key,
                children=[
                    dmc.AccordionControl(
                        dmc.Group(
                            gap="xs",
                            children=[
                                dmc.Text(labels[key], fw=600, size="sm"),
                                dmc.Badge(str(count), color="indigo", variant="light", size="sm"),
                                dmc.Text(descriptions[key], size="xs", c="dimmed"),
                            ],
                        )
                    ),
                    dmc.AccordionPanel(
                        _section_panel(
                            key,
                            filtered_groups.get(key) or [],
                            pages.get(key, 0),
                            allow_vip_toggle=allow_vip_toggle,
                        )
                    ),
                ],
            )
        )
    return dmc.Accordion(
        id="customer-section-accordion",
        multiple=True,
        value=["mapped"],
        children=items,
    )


def build_customers_list(time_range=None, visible_sections=None):
    _ = visible_sections
    tr = time_range or default_time_range()
    store_data = _load_page_data()
    overview = store_data.get("overview") or {}

    return html.Div(
        className="customer-page-enter",
        children=[
            dcc.Store(id="customer-catalog-store", data=store_data),
            dcc.Store(id="customer-section-pages", data={"vip": 0, "mapped": 0, "unmapped": 0}),
            dmc.Stack(
                gap="lg",
                style={"padding": "8px 0 24px"},
                children=[
                    dmc.Paper(
                        className="nexus-card",
                        radius="xl",
                        p="lg",
                        mx=32,
                        style=card_style(),
                        children=dmc.Stack(
                            gap="md",
                            children=[
                                dmc.Group(
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
                                                            "CRM project customers grouped by mapping and VIP status",
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
                                            leftSection=DashIconify(
                                                icon="solar:magnifer-linear",
                                                width=16,
                                                color="#A3AED0",
                                            ),
                                            radius="md",
                                            size="sm",
                                            style={"width": "280px"},
                                        ),
                                    ],
                                ),
                                _overview_strip(overview),
                                dmc.SimpleGrid(
                                    cols={"base": 1, "lg": 2},
                                    spacing="md",
                                    children=[
                                        dmc.Paper(
                                            withBorder=True,
                                            radius="md",
                                            p="md",
                                            children=[
                                                dmc.Text("Service sales mix", fw=700, size="sm", mb="sm"),
                                                _service_sales_chart(overview.get("service_sales") or []),
                                            ],
                                        ),
                                        dmc.Paper(
                                            withBorder=True,
                                            radius="md",
                                            p="md",
                                            children=dmc.Stack(
                                                gap="xs",
                                                children=[
                                                    dmc.Text("Catalog notes", fw=700, size="sm"),
                                                    dmc.Text(
                                                        "Mapped customers combine CRM billing with infrastructure data. "
                                                        "Unmapped rows are CRM-only until source mappings are configured in Settings.",
                                                        size="sm",
                                                        c="dimmed",
                                                    ),
                                                    dmc.Text(
                                                        "CRM vs infrastructure overuse comparison is pending; badges show draft status only.",
                                                        size="sm",
                                                        c="dimmed",
                                                    ),
                                                ],
                                            ),
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ),
                    html.Div(
                        id="customer-section-accordion-wrap",
                        style={"padding": "0 32px"},
                        children=_build_accordion(
                            store_data,
                            "",
                            {"vip": 0, "mapped": 0, "unmapped": 0},
                            allow_vip_toggle=False,
                        ),
                    ),
                ],
            ),
        ],
    )


@callback(
    Output("customer-section-accordion-wrap", "children"),
    Input("customer-search-input", "value"),
    Input({"type": "customer-section-page", "section": ALL}, "value"),
    State("customer-catalog-store", "data"),
    State("customer-section-pages", "data"),
    State("auth-permissions-store", "data"),
)
def refresh_customer_sections(query, _page_values, store_data, page_store, permissions):
    pages = dict(page_store or {"vip": 0, "mapped": 0, "unmapped": 0})
    trig = ctx.triggered_id
    if isinstance(trig, dict) and trig.get("type") == "customer-section-page":
        section = str(trig.get("section") or "")
        idx = next(
            (i for i, key in enumerate(_SECTION_KEYS) if key == section),
            None,
        )
        if idx is not None and _page_values and idx < len(_page_values):
            pages[section] = max(int(_page_values[idx] or 1) - 1, 0)
    allow_vip = _can_manage_vip(permissions)
    if isinstance(store_data, dict):
        return _build_accordion(store_data, query or "", pages, allow_vip_toggle=allow_vip)
    return _build_accordion({"groups": {}}, query or "", pages, allow_vip_toggle=allow_vip)


@callback(
    Output("customer-catalog-store", "data"),
    Input({"type": "customer-vip-toggle", "account": ALL}, "n_clicks"),
    State({"type": "customer-vip-toggle", "account": ALL}, "id"),
    State("customer-catalog-store", "data"),
    State("auth-permissions-store", "data"),
    prevent_initial_call=True,
)
def toggle_customer_vip(_clicks, ids, store_data, permissions):
    if not _can_manage_vip(permissions):
        return no_update
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "customer-vip-toggle":
        return no_update
    account_id = str(trig.get("account") or "")
    if not account_id:
        return no_update
    customers = (store_data or {}).get("customers") if isinstance(store_data, dict) else []
    current = next((c for c in customers if str(c.get("crm_accountid")) == account_id), None)
    if not current:
        return no_update
    new_vip = not bool(current.get("is_vip"))
    try:
        api.set_customer_vip(account_id, is_vip=new_vip)
    except Exception:
        return no_update
    return _load_page_data()
