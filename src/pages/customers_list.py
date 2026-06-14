from __future__ import annotations

from urllib.parse import quote

from dash import Input, Output, State, ALL, callback, ctx, dcc, html, no_update
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objects as go

from src.services import api_client as api
from src.utils.customers_list_ui import (
    apply_vip_toggle_local,
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
_SECTION_LABELS = {
    "vip": "VIP Customers",
    "mapped": "Mapped Customers",
    "unmapped": "Unmapped CRM Customers",
}
_SECTION_DESCRIPTIONS = {
    "vip": "Pinned customers with continuous cache warm-up.",
    "mapped": "CRM customers linked to infrastructure source mappings.",
    "unmapped": "CRM-only customers without enabled source mappings.",
}
_CARDS_TRANSITION_STYLE = {
    "transition": "opacity 0.18s ease-in-out",
    "minHeight": "120px",
}


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


def _pending_account_id(pending_data: dict | str | None) -> str | None:
    if isinstance(pending_data, dict):
        account_id = str(pending_data.get("account_id") or "").strip()
        return account_id or None
    if pending_data:
        return str(pending_data)
    return None


def _build_vip_pending_request(
    triggered_id: dict | str | None,
    store_data: dict | None,
    *,
    click_count: int,
) -> dict | None:
    if not click_count:
        return None
    if not isinstance(triggered_id, dict) or triggered_id.get("type") != "customer-vip-toggle":
        return None
    account_id = str(triggered_id.get("account") or "")
    if not account_id or not isinstance(store_data, dict):
        return None
    customers = store_data.get("customers") if isinstance(store_data.get("customers"), list) else []
    current = next((c for c in customers if str(c.get("crm_accountid")) == account_id), None)
    if not current:
        return None
    return {"account_id": account_id, "is_vip": not bool(current.get("is_vip"))}


def _complete_vip_pending_request(
    pending_data: dict | None,
    store_data: dict | None,
) -> tuple[dict | None, str | None, bool | None]:
    if not isinstance(pending_data, dict):
        return None, None, None
    account_id = str(pending_data.get("account_id") or "")
    if "is_vip" not in pending_data:
        return None, None, None
    new_vip = bool(pending_data.get("is_vip"))
    if not account_id or not isinstance(store_data, dict):
        return None, None, None
    customers = store_data.get("customers") if isinstance(store_data.get("customers"), list) else []
    current = next((c for c in customers if str(c.get("crm_accountid")) == account_id), None)
    if not current:
        return None, None, None
    name = str(current.get("display_name") or current.get("crm_account_name") or account_id)
    return current, name, new_vip


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


def _compact_customer_card(
    row: dict,
    *,
    allow_vip_toggle: bool,
    pending_account_id: str | None = None,
):
    name = str(row.get("display_name") or row.get("crm_account_name") or "-")
    account_id = str(row.get("crm_accountid") or "")
    revenue = format_revenue(row.get("ytd_revenue"), row.get("currency"))
    active_value = format_revenue(row.get("active_order_value"), row.get("currency"))
    is_pending = bool(pending_account_id and account_id == pending_account_id)
    customer_href = f"/customer-view?customer={quote(name, safe='')}"

    star_overlay = None
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
            disabled=is_pending,
            loading=is_pending,
        )
        star_overlay = html.Div(
            className="customer-list-card__vip-toggle",
            style={
                "position": "absolute",
                "top": "8px",
                "right": "8px",
                "zIndex": 2,
            },
            children=star,
        )

    link_body = dcc.Link(
        href=customer_href,
        style={
            "textDecoration": "none",
            "color": "inherit",
            "display": "block",
            "paddingRight": "28px" if star_overlay else "0",
        },
        children=dmc.Stack(
            gap=2,
            style={"minWidth": 0},
            children=[
                dmc.Text(name, fw=700, size="sm", c="#2B3674", lineClamp=2),
                dmc.Text(f"YTD {revenue}", size="xs", c="#A3AED0"),
                dmc.Text(f"Active {active_value}", size="xs", c="#4318FF", fw=600),
                dmc.Group(gap=4, wrap="wrap", children=_status_badges(row, show_unmapped_on_vip=True)),
            ],
        ),
    )

    children: list = [link_body]
    if star_overlay is not None:
        children.append(star_overlay)

    return dmc.Paper(
        className="nexus-card customer-list-card customer-list-card--compact customer-list-card--clickable",
        radius="md",
        p="sm",
        withBorder=True,
        style={"minHeight": "96px", "position": "relative"},
        children=children,
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
    active_count = int(ov.get("total_active_order_count") or 0)
    active_trend = f"{active_count} open order{'s' if active_count != 1 else ''}"
    return dmc.SimpleGrid(
        cols={"base": 2, "sm": 3, "lg": 4, "xl": 7},
        spacing="md",
        children=[
            kpi_card("CRM Customers", int(ov.get("total_customers") or 0), icon="solar:users-group-rounded-bold-duotone", color="indigo"),
            kpi_card("Mapped", int(ov.get("mapped_count") or 0), icon="solar:link-circle-bold-duotone", color="teal"),
            kpi_card("Unmapped", int(ov.get("unmapped_count") or 0), icon="solar:unlink-circle-bold-duotone", color="gray"),
            kpi_card("VIP", int(ov.get("vip_count") or 0), icon="solar:star-bold-duotone", color="yellow"),
            kpi_card(
                "Active Orders",
                format_revenue(ov.get("total_active_order_value"), ov.get("currency")),
                icon="solar:cart-check-bold-duotone",
                color="indigo",
                trend=active_trend,
            ),
            kpi_card(
                "Realized Sales",
                format_revenue(ov.get("total_revenue"), ov.get("currency")),
                icon="solar:wallet-money-bold-duotone",
                color="violet",
            ),
            kpi_card(
                "Overuse detected",
                int(ov.get("overuse_customer_count") or 0),
                icon="solar:danger-triangle-bold-duotone",
                color="red" if int(ov.get("overuse_customer_count") or 0) > 0 else "teal",
            ),
        ],
    )


def _render_section_cards(
    rows: list[dict],
    *,
    allow_vip_toggle: bool,
    pending_account_id: str | None = None,
):
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
        children=[
            _compact_customer_card(
                row,
                allow_vip_toggle=allow_vip_toggle,
                pending_account_id=pending_account_id,
            )
            for row in rows
        ],
    )


def _filtered_groups(store_data: dict, query: str) -> dict[str, list[dict]]:
    groups = store_data.get("groups") if isinstance(store_data.get("groups"), dict) else {}
    return {
        key: filter_catalog_rows(groups.get(key) or [], query)
        for key in _SECTION_KEYS
    }


def _section_refresh_outputs(
    store_data: dict,
    query: str,
    pages: dict[str, int],
    *,
    allow_vip_toggle: bool,
    pending_account_id: str | None = None,
):
    filtered = _filtered_groups(store_data, query)
    cards_out: list = []
    page_totals: list[int] = []
    page_values: list[int] = []
    count_badges: list[str] = []
    total_labels: list[str] = []
    page_store = dict(pages or {"vip": 0, "mapped": 0, "unmapped": 0})

    for key in _SECTION_KEYS:
        rows = filtered.get(key) or []
        total = len(rows)
        pages_n = page_count(total, _PAGE_SIZE)
        safe_page = min(max(int(page_store.get(key, 0) or 0), 0), pages_n - 1)
        page_store[key] = safe_page
        page_rows = paginate_rows(rows, safe_page, _PAGE_SIZE)
        cards_out.append(
            _render_section_cards(
                page_rows,
                allow_vip_toggle=allow_vip_toggle,
                pending_account_id=pending_account_id,
            )
        )
        page_totals.append(pages_n)
        page_values.append(safe_page + 1)
        count_badges.append(str(total))
        total_labels.append(f"{total} customer(s)")

    overview = store_data.get("overview") if isinstance(store_data.get("overview"), dict) else {}
    return (
        cards_out,
        page_totals,
        page_values,
        count_badges,
        total_labels,
        page_store,
        _overview_strip(overview),
    )


def _build_static_accordion_shell(
    store_data: dict,
    query: str,
    pages: dict[str, int],
    *,
    allow_vip_toggle: bool,
):
    initial = _section_refresh_outputs(
        store_data,
        query,
        pages,
        allow_vip_toggle=allow_vip_toggle,
    )
    cards, page_totals, page_values, count_badges, total_labels, _, _ = initial
    items = []
    for idx, key in enumerate(_SECTION_KEYS):
        items.append(
            dmc.AccordionItem(
                value=key,
                children=[
                    dmc.AccordionControl(
                        dmc.Group(
                            gap="xs",
                            children=[
                                dmc.Text(_SECTION_LABELS[key], fw=600, size="sm"),
                                dmc.Badge(
                                    id={"type": "customer-section-count", "section": key},
                                    children=count_badges[idx],
                                    color="indigo",
                                    variant="light",
                                    size="sm",
                                ),
                                dmc.Text(_SECTION_DESCRIPTIONS[key], size="xs", c="dimmed"),
                            ],
                        )
                    ),
                    dmc.AccordionPanel(
                        html.Div(
                            children=[
                                html.Div(
                                    id={"type": "customer-section-cards", "section": key},
                                    style=_CARDS_TRANSITION_STYLE,
                                    children=cards[idx],
                                ),
                                dmc.Group(
                                    justify="space-between",
                                    mt="sm",
                                    children=[
                                        dmc.Text(
                                            id={"type": "customer-section-total", "section": key},
                                            children=total_labels[idx],
                                            size="xs",
                                            c="dimmed",
                                        ),
                                        dmc.Pagination(
                                            id={"type": "customer-section-page", "section": key},
                                            total=page_totals[idx],
                                            value=page_values[idx],
                                            size="sm",
                                        ),
                                    ],
                                ),
                            ]
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


def build_customers_list_shell(visible_sections=None):
    """Phase A: instant skeleton shell; `_fill_customers_list_content` builds the real
    content off the render path so a cold backend never leaves the page blank."""
    return html.Div([
        dcc.Store(
            id="customers-list-visible-sections",
            data=list(visible_sections) if visible_sections else None,
        ),
        dcc.Loading(
            id="customers-list-content-loading",
            type="circle", color="#4318FF", delay_show=150,
            children=html.Div(id="customers-list-page-root", style={"minHeight": "60vh", "padding": "0 8px"}),
        ),
    ])


@callback(
    Output("customers-list-page-root", "children"),
    Input("url", "pathname"),
    Input("app-time-range", "data"),
    State("customers-list-visible-sections", "data"),
)
def _fill_customers_list_content(pathname, time_range, visible_sections):
    """Phase B: build the real Customers list content off the initial render path."""
    if pathname != "/customers":
        return no_update
    tr = time_range or default_time_range()
    return build_customers_list(tr, visible_sections=visible_sections)


def build_customers_list(time_range=None, visible_sections=None):
    _ = visible_sections
    tr = time_range or default_time_range()
    store_data = _load_page_data()
    overview = store_data.get("overview") or {}
    initial_pages = {"vip": 0, "mapped": 0, "unmapped": 0}

    return html.Div(
        className="customer-page-enter",
        children=[
            dcc.Store(id="customer-catalog-store", data=store_data),
            dcc.Store(id="customer-section-pages", data=initial_pages),
            dcc.Store(id="customer-accordion-open", data=["mapped"]),
            dcc.Store(id="customer-vip-pending", data=None),
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
                                html.Div(id="customer-vip-alert"),
                                html.Div(id="customer-overview-strip", children=_overview_strip(overview)),
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
                                                        "Overuse badges compare CRM entitlement (active + invoiced) "
                                                        "with cached infrastructure usage for mapped customers.",
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
                    dcc.Loading(
                        id="customer-section-loading",
                        type="circle",
                        color="#4318FF",
                        children=html.Div(
                            id="customer-section-accordion-wrap",
                            style={"padding": "0 32px"},
                            children=_build_static_accordion_shell(
                                store_data,
                                "",
                                initial_pages,
                                allow_vip_toggle=False,
                            ),
                        ),
                    ),
                ],
            ),
        ],
    )


@callback(
    Output({"type": "customer-section-cards", "section": ALL}, "children"),
    Output({"type": "customer-section-page", "section": ALL}, "total"),
    Output({"type": "customer-section-page", "section": ALL}, "value"),
    Output({"type": "customer-section-count", "section": ALL}, "children"),
    Output({"type": "customer-section-total", "section": ALL}, "children"),
    Output("customer-section-pages", "data"),
    Output("customer-overview-strip", "children"),
    Input("customer-search-input", "value"),
    Input({"type": "customer-section-page", "section": ALL}, "value"),
    Input("customer-catalog-store", "data"),
    Input("auth-permissions-store", "data"),
    Input("customer-vip-pending", "data"),
    State("customer-section-pages", "data"),
)
def refresh_customer_sections(
    query,
    _page_values,
    store_data,
    permissions,
    pending_data,
    page_store,
):
    pages = dict(page_store or {"vip": 0, "mapped": 0, "unmapped": 0})
    trig = ctx.triggered_id
    if trig == "customer-search-input":
        pages = {"vip": 0, "mapped": 0, "unmapped": 0}
    elif isinstance(trig, dict) and trig.get("type") == "customer-section-page":
        section = str(trig.get("section") or "")
        idx = next((i for i, key in enumerate(_SECTION_KEYS) if key == section), None)
        if idx is not None and _page_values and idx < len(_page_values):
            pages[section] = max(int(_page_values[idx] or 1) - 1, 0)

    allow_vip = _can_manage_vip(permissions)
    data = store_data if isinstance(store_data, dict) else {"groups": {}, "overview": {}}
    return _section_refresh_outputs(
        data,
        query or "",
        pages,
        allow_vip_toggle=allow_vip,
        pending_account_id=_pending_account_id(pending_data),
    )


@callback(
    Output("customer-accordion-open", "data"),
    Input("customer-section-accordion", "value"),
    prevent_initial_call=True,
)
def persist_accordion_open(value):
    return value if isinstance(value, list) else ["mapped"]


@callback(
    Output("customer-vip-pending", "data"),
    Input({"type": "customer-vip-toggle", "account": ALL}, "n_clicks"),
    State("customer-catalog-store", "data"),
    State("auth-permissions-store", "data"),
    prevent_initial_call=True,
)
def queue_customer_vip_toggle(_clicks, store_data, permissions):
    if not _can_manage_vip(permissions):
        return no_update
    trigger = ctx.triggered[0] if ctx.triggered else None
    click_count = int(trigger.get("value") or 0) if trigger else 0
    pending = _build_vip_pending_request(ctx.triggered_id, store_data, click_count=click_count)
    if not pending:
        return no_update
    return pending


@callback(
    Output("customer-catalog-store", "data"),
    Output("customer-vip-alert", "children"),
    Output("customer-vip-pending", "data", allow_duplicate=True),
    Input("customer-vip-pending", "data"),
    State("customer-catalog-store", "data"),
    prevent_initial_call=True,
)
def complete_customer_vip_toggle(pending_data, store_data):
    _current, name, new_vip = _complete_vip_pending_request(pending_data, store_data)
    if _current is None or name is None or new_vip is None:
        return no_update, no_update, None
    account_id = str(pending_data.get("account_id") or "")
    try:
        api.set_customer_vip(account_id, is_vip=new_vip)
    except Exception as exc:
        action = "add to VIP" if new_vip else "remove from VIP"
        alert = dmc.Alert(
            color="red",
            title="VIP update failed",
            children=f"Could not {action} for {name}: {exc}",
        )
        return no_update, alert, None
    updated = apply_vip_toggle_local(store_data, account_id, new_vip)
    action_label = "added to VIP" if new_vip else "removed from VIP"
    alert = dmc.Alert(
        color="green",
        title="VIP updated",
        children=f"{name} {action_label}.",
    )
    return updated, alert, None
