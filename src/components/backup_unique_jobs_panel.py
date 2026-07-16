"""Unique-job inventory panel (Nutanix-style layout) for Backup & Replication.

Filters apply to KPIs, breakdown chart, status panel, AND the paged table
(unlike Nutanix snapshot filters which only refresh the table).
"""
from __future__ import annotations

import logging
from typing import Any

import dash
import dash_mantine_components as dmc
import plotly.graph_objects as go
from dash import Input, Output, State, callback, ctx, dcc, html
from dash_iconify import DashIconify

from src.components.backup_panel import _gauge_card, _kpi_card
from src.services import api_client as api
from src.utils.format_units import smart_bytes

logger = logging.getLogger(__name__)

_PAGE_SIZE = 50
_DONUT_COLORS = ["#05CD99", "#EE5D50", "#FFB547", "#4318FF", "#15AABF", "#ADB5BD", "#A3AED0"]

_VENDORS = ("veeam", "zerto", "netbackup")
_NETBACKUP_CATEGORIES = ("image", "application")

_COLUMN_SPECS: dict[str, list[tuple[str, str]]] = {
    "veeam": [
        ("name", "Name"),
        ("type", "Type"),
        ("status", "Status"),
        ("last_result", "Last Result"),
        ("last_run", "Last Run"),
        ("objects_count", "Objects"),
        ("workload", "Workload"),
        ("source_ip", "Source IP"),
    ],
    "zerto": [
        ("name", "VPG"),
        ("status", "Status"),
        ("vmscount", "VMs"),
        ("source_site", "Source Site"),
        ("target_site", "Target Site"),
        ("provisioned_storage_mb", "Provisioned"),
        ("used_storage_mb", "Used"),
        ("zerto_host", "Host"),
    ],
    "netbackup": [
        ("policyname", "Policy"),
        ("workloaddisplayname", "Workload"),
        ("policytype", "Policy Type"),
        ("category", "Category"),
        ("status", "Status"),
        ("clientname", "Client"),
        ("destinationmediaservername", "Media Server"),
        ("kilobytestransferred", "Transferred"),
        ("dedupratio", "Dedup"),
        ("starttime", "Start"),
    ],
}


def _section_id(vendor: str, category: str | None = None, scope: str = "dc") -> str:
    base = vendor if not category else f"{vendor}-{category}"
    return f"{scope}-{base}"


def _vendor_title(vendor: str, category: str | None = None) -> str:
    labels = {"veeam": "Veeam", "zerto": "Zerto", "netbackup": "NetBackup"}
    label = labels.get(vendor, vendor.title())
    if category == "image":
        return f"{label} Image Jobs"
    if category == "application":
        return f"{label} Application Jobs"
    if vendor == "zerto":
        return "Zerto Unique VPGs"
    return f"{label} Unique Jobs"


def _fmt_cell(vendor: str, key: str, value: Any) -> str:
    if value is None or value == "":
        return "—"
    if key in ("provisioned_storage_mb", "used_storage_mb"):
        try:
            return smart_bytes(float(value) * 1024 * 1024)
        except (TypeError, ValueError):
            return str(value)
    if key == "kilobytestransferred":
        try:
            return smart_bytes(float(value) * 1024)
        except (TypeError, ValueError):
            return str(value)
    if key in ("last_run", "starttime", "endtime", "collection_time", "collection_timestamp"):
        return str(value)[:19].replace("T", " ")
    return str(value)


def unique_jobs_table(vendor: str, items: list[dict]) -> html.Div:
    cols = _COLUMN_SPECS.get(vendor) or _COLUMN_SPECS["veeam"]
    head = html.Thead(
        html.Tr(
            [
                html.Th(label, style={"fontSize": "0.75rem", "color": "#A3AED0"})
                for _, label in cols
            ]
        )
    )
    body_rows = []
    for row in items or []:
        body_rows.append(
            html.Tr(
                children=[
                    html.Td(
                        _fmt_cell(vendor, key, row.get(key)),
                        style={"whiteSpace": "nowrap", "fontSize": "0.82rem"},
                    )
                    for key, _ in cols
                ]
            )
        )
    if not body_rows:
        body_rows = [
            html.Tr(
                html.Td(
                    "No unique jobs in this filter set.",
                    colSpan=len(cols),
                    style={"textAlign": "center", "color": "#A3AED0", "padding": "24px"},
                )
            )
        ]
    table = dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=False,
        withColumnBorders=False,
        className="nexus-table dc-premium-table",
        style={"minWidth": "980px"},
        children=[head, html.Tbody(body_rows)],
    )
    return html.Div(style={"overflowX": "auto", "width": "100%"}, children=table)


def _status_donut(by_status: dict) -> go.Figure:
    items = [(k, int(v)) for k, v in (by_status or {}).items() if v]
    labels = [k for k, _ in items] or ["No data"]
    values = [v for _, v in items] or [1]
    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.72,
                sort=False,
                direction="clockwise",
                marker=dict(colors=_DONUT_COLORS, line=dict(color="rgba(0,0,0,0)", width=0)),
                textinfo="none",
                hovertemplate="%{label}: %{value}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        margin=dict(l=8, r=8, t=8, b=8),
        showlegend=True,
        legend=dict(orientation="h", y=-0.08, font=dict(size=11, color="#A3AED0")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=220,
    )
    return fig


def _status_list_panel(by_status: dict) -> html.Div:
    rows = sorted((by_status or {}).items(), key=lambda kv: (-int(kv[1] or 0), kv[0]))
    children = [
        html.Div(
            style={"borderBottom": "1px solid #F4F7FE", "paddingBottom": "12px"},
            children=[
                html.Span(
                    "STATUS BREAKDOWN",
                    style={
                        "fontSize": "0.7rem",
                        "fontWeight": 700,
                        "color": "#A3AED0",
                        "letterSpacing": "0.08em",
                        "textTransform": "uppercase",
                    },
                )
            ],
        )
    ]
    if not rows:
        children.append(
            dmc.Text("No status data", size="sm", c="dimmed")
        )
    for status, count in rows[:8]:
        children.append(
            dmc.Group(
                gap="xs",
                align="center",
                justify="space-between",
                children=[
                    dmc.Badge(str(status), variant="light", color="gray", size="sm"),
                    html.Span(
                        str(count),
                        style={"fontSize": "1.1rem", "fontWeight": 800, "color": "#2B3674"},
                    ),
                ],
            )
        )
    return html.Div(
        className="nexus-card",
        style={
            "padding": "16px",
            "height": "100%",
            "display": "flex",
            "flexDirection": "column",
            "gap": "10px",
        },
        children=children,
    )


def build_unique_jobs_kpis(totals: dict, vendor: str) -> html.Div:
    totals = totals or {}
    by_status = totals.get("by_status") or {}
    success = int(by_status.get("success", 0) or 0)
    failed = int(by_status.get("failed", 0) or 0)
    total = int(totals.get("total_jobs", 0) or 0)
    type_count = len(totals.get("by_type") or {})
    if vendor == "netbackup":
        type_count = len(totals.get("by_policy_type") or {})
    cards = [
        _kpi_card("Total Jobs", f"{total:,}", "solar:folder-with-files-bold-duotone", "#4318FF"),
        _kpi_card("Success", f"{success:,}", "solar:check-circle-bold-duotone", "#05CD99"),
        _kpi_card("Failed", f"{failed:,}", "solar:close-circle-bold-duotone", "#EE5D50"),
        _kpi_card(
            "Types" if vendor != "zerto" else "VPGs",
            f"{type_count if vendor != 'zerto' else total:,}",
            "solar:widget-bold-duotone",
            "#FFB547",
        ),
    ]
    return html.Div(
        style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "12px", "height": "100%"},
        children=cards,
    )


def build_unique_jobs_visuals(totals: dict, vendor: str) -> tuple[html.Div, html.Div, html.Div]:
    totals = totals or {}
    return (
        build_unique_jobs_kpis(totals, vendor),
        _gauge_card(_status_donut(totals.get("by_status") or {})),
        _status_list_panel(totals.get("by_status") or {}),
    )


def _option_data(values: list[str]) -> list[dict]:
    return [{"label": v, "value": v} for v in values if v]


def build_unique_jobs_inventory_section(
    vendor: str,
    *,
    category: str | None = None,
    scope: str = "dc",
    initial: dict | None = None,
) -> html.Div:
    """Nutanix-style unique-job inventory with filters bound to KPIs + chart + table."""
    if vendor not in _VENDORS:
        raise ValueError(f"Unknown vendor: {vendor}")
    if category is not None and category not in _NETBACKUP_CATEGORIES:
        raise ValueError(f"Unknown category: {category}")

    sid = _section_id(vendor, category, scope)
    initial = initial or {}
    rows = list(initial.get("rows") or [])
    totals = dict(initial.get("totals") or {})
    if not totals and rows:
        from shared.backup.unique_jobs import aggregate_unique_jobs

        filtered_rows = rows
        if category:
            filtered_rows = [r for r in rows if (r.get("category") or "") == category]
        totals = aggregate_unique_jobs(filtered_rows, vendor)

    statuses = sorted({str(r.get("status") or "").lower() for r in rows if r.get("status")})
    if vendor == "veeam":
        types = sorted({str(r.get("type") or "") for r in rows if r.get("type")})
    elif vendor == "netbackup":
        types = sorted({str(r.get("policytype") or "") for r in rows if r.get("policytype")})
    else:
        types = []
    platforms = sorted(
        {
            str(
                r.get("source_ip")
                or r.get("zerto_host")
                or r.get("source_site")
                or r.get("destinationmediaservername")
                or ""
            )
            for r in rows
            if (
                r.get("source_ip")
                or r.get("zerto_host")
                or r.get("source_site")
                or r.get("destinationmediaservername")
            )
        }
    )

    kpis, donut, status_panel = build_unique_jobs_visuals(totals, vendor)
    page1 = rows[:_PAGE_SIZE] if rows else []
    if category:
        page1 = [r for r in rows if (r.get("category") or "") == category][:_PAGE_SIZE]

    filter_controls: list = [
        dmc.MultiSelect(
            id=f"backup-uj-{sid}-filter-status",
            data=_option_data(statuses),
            value=[],
            clearable=True,
            searchable=True,
            placeholder="Status",
            size="xs",
            style={"minWidth": "140px"},
        ),
    ]
    if types:
        filter_controls.append(
            dmc.MultiSelect(
                id=f"backup-uj-{sid}-filter-type",
                data=_option_data(types),
                value=[],
                clearable=True,
                searchable=True,
                placeholder="Type" if vendor != "netbackup" else "Policy type",
                size="xs",
                style={"minWidth": "160px"},
            )
        )
    else:
        filter_controls.append(html.Div(id=f"backup-uj-{sid}-filter-type", style={"display": "none"}))
    if platforms:
        filter_controls.append(
            dmc.MultiSelect(
                id=f"backup-uj-{sid}-filter-platform",
                data=_option_data(platforms),
                value=[],
                clearable=True,
                searchable=True,
                placeholder="Platform / Host",
                size="xs",
                style={"minWidth": "160px"},
            )
        )
    else:
        filter_controls.append(html.Div(id=f"backup-uj-{sid}-filter-platform", style={"display": "none"}))

    return html.Div(
        style={"marginTop": "20px"},
        children=[
            dcc.Store(id=f"backup-uj-{sid}-page", data=1),
            dcc.Store(
                id=f"backup-uj-{sid}-meta",
                data={"vendor": vendor, "category": category, "scope": scope},
            ),
            html.Div(
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "marginBottom": "12px",
                    "gap": "12px",
                    "flexWrap": "wrap",
                },
                children=[
                    html.Div(
                        children=[
                            html.H4(
                                _vendor_title(vendor, category),
                                style={"margin": 0, "fontSize": "0.95rem", "color": "#2B3674"},
                            ),
                            dmc.Text(
                                "Latest state per unique job — filters apply to KPIs, chart, and table",
                                size="xs",
                                c="dimmed",
                            ),
                        ]
                    ),
                    dmc.Group(gap="xs", children=filter_controls),
                ],
            ),
            html.Div(
                id=f"backup-uj-{sid}-summary",
                style={
                    "display": "grid",
                    "gridTemplateColumns": "1fr 1fr 1fr",
                    "gap": "16px",
                    "alignItems": "stretch",
                },
                children=[
                    html.Div(id=f"backup-uj-{sid}-kpis", style={"minWidth": 0}, children=kpis),
                    html.Div(id=f"backup-uj-{sid}-donut", children=donut),
                    html.Div(id=f"backup-uj-{sid}-status", children=status_panel),
                ],
            ),
            html.Div(style={"height": "16px"}),
            html.Div(
                className="nexus-card",
                style={"padding": "16px"},
                children=[
                    dmc.Group(
                        justify="space-between",
                        align="center",
                        mb="sm",
                        children=[
                            dmc.TextInput(
                                id=f"backup-uj-{sid}-search",
                                placeholder="Search jobs…",
                                leftSection=DashIconify(icon="solar:magnifer-linear", width=16),
                                size="xs",
                                style={"minWidth": "220px"},
                            ),
                            dmc.Group(
                                gap="xs",
                                children=[
                                    dmc.ActionIcon(
                                        id=f"backup-uj-{sid}-prev",
                                        variant="light",
                                        children=DashIconify(icon="solar:alt-arrow-left-linear", width=16),
                                    ),
                                    dmc.Text(id=f"backup-uj-{sid}-pageinfo", size="xs", children="1 / 1"),
                                    dmc.ActionIcon(
                                        id=f"backup-uj-{sid}-next",
                                        variant="light",
                                        children=DashIconify(icon="solar:alt-arrow-right-linear", width=16),
                                    ),
                                ],
                            ),
                        ],
                    ),
                    dcc.Loading(
                        id=f"backup-uj-{sid}-loading",
                        type="dot",
                        children=html.Div(
                            id=f"backup-uj-{sid}-table",
                            children=unique_jobs_table(vendor, page1),
                        ),
                    ),
                ],
            ),
        ],
    )


def _extract_dc_id(pathname: str | None) -> str | None:
    if not pathname:
        return None
    parts = [p for p in str(pathname).split("/") if p]
    if "datacenter" in parts:
        i = parts.index("datacenter")
        if i + 1 < len(parts):
            return parts[i + 1]
    if "dc" in parts:
        i = parts.index("dc")
        if i + 1 < len(parts):
            return parts[i + 1]
    return None


def _extract_customer_name(pathname: str | None) -> str | None:
    if not pathname:
        return None
    parts = [p for p in str(pathname).split("/") if p]
    if "customer" in parts:
        i = parts.index("customer")
        if i + 1 < len(parts):
            from urllib.parse import unquote

            return unquote(parts[i + 1])
    if "customers" in parts:
        i = parts.index("customers")
        if i + 1 < len(parts) and parts[i + 1] not in ("list",):
            from urllib.parse import unquote

            return unquote(parts[i + 1])
    return None


def _fetch_table_payload(
    *,
    scope: str,
    vendor: str,
    category: str | None,
    pathname: str | None,
    tr: dict | None,
    page: int,
    search: str,
    statuses,
    types,
    platforms,
    active_tab: str | None,
) -> dict | None:
    policy_types = (types or None) if vendor == "netbackup" else None
    type_filter = None if vendor == "netbackup" else (types or None)
    categories = [category] if category else None
    if scope == "dc":
        dc_id = _extract_dc_id(pathname)
        if not dc_id or (active_tab or "") != "backup":
            return None
        return api.get_dc_unique_jobs_table(
            dc_id,
            vendor,
            tr,
            page=page,
            page_size=_PAGE_SIZE,
            search=search or "",
            statuses=statuses or None,
            types=type_filter,
            policy_types=policy_types,
            categories=categories,
            platforms=platforms or None,
        )
    customer = _extract_customer_name(pathname)
    if not customer:
        return None
    return api.get_customer_unique_jobs_table(
        customer,
        vendor,
        tr,
        page=page,
        page_size=_PAGE_SIZE,
        search=search or "",
        statuses=statuses or None,
        types=type_filter,
        policy_types=policy_types,
        categories=categories,
        platforms=platforms or None,
    )


def _make_dc_callback(vendor: str, category: str | None = None) -> None:
    sid = _section_id(vendor, category, "dc")

    @callback(
        Output(f"backup-uj-{sid}-kpis", "children"),
        Output(f"backup-uj-{sid}-donut", "children"),
        Output(f"backup-uj-{sid}-status", "children"),
        Output(f"backup-uj-{sid}-table", "children"),
        Output(f"backup-uj-{sid}-pageinfo", "children"),
        Output(f"backup-uj-{sid}-page", "data"),
        Input(f"backup-uj-{sid}-search", "value"),
        Input(f"backup-uj-{sid}-prev", "n_clicks"),
        Input(f"backup-uj-{sid}-next", "n_clicks"),
        Input(f"backup-uj-{sid}-filter-status", "value"),
        Input(f"backup-uj-{sid}-filter-type", "value"),
        Input(f"backup-uj-{sid}-filter-platform", "value"),
        # Deferred after Backup mount so job-stats runs first (stampede guard).
        Input("backup-uj-defer", "n_intervals"),
        Input("backup-time-range", "data"),
        State("dc-main-tabs", "value"),
        State(f"backup-uj-{sid}-page", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def _update_dc(
        search,
        prev_n,
        next_n,
        f_status,
        f_type,
        f_platform,
        defer_n,
        tr,
        active_tab,
        page,
        pathname,
        _vendor=vendor,
        _category=category,
        _sid=sid,
    ):
        # Initial mount path: wait until Interval has fired at least once.
        trig = ctx.triggered_id
        if trig == "backup-uj-defer" and not defer_n:
            return (dash.no_update,) * 6
        page = int(page or 1)
        if trig == f"backup-uj-{_sid}-next":
            page += 1
        elif trig == f"backup-uj-{_sid}-prev":
            page = max(1, page - 1)
        else:
            page = 1
        try:
            payload = _fetch_table_payload(
                scope="dc",
                vendor=_vendor,
                category=_category,
                pathname=pathname,
                tr=tr,
                page=page,
                search=search or "",
                statuses=f_status,
                types=f_type,
                platforms=f_platform,
                active_tab=active_tab,
            )
        except Exception:  # noqa: BLE001
            logger.exception("unique-jobs DC fetch failed (%s)", _vendor)
            return (dash.no_update,) * 6
        if payload is None:
            return (dash.no_update,) * 6
        totals = payload.get("totals") or {}
        kpis, donut, status_panel = build_unique_jobs_visuals(totals, _vendor)
        total = int(payload.get("total", 0) or 0)
        pages = max(1, -(-total // _PAGE_SIZE))
        page = min(page, pages)
        return (
            kpis,
            donut,
            status_panel,
            unique_jobs_table(_vendor, payload.get("items") or []),
            f"{page} / {pages}",
            page,
        )


def _make_customer_callback(vendor: str, category: str | None = None) -> None:
    sid = _section_id(vendor, category, "customer")

    @callback(
        Output(f"backup-uj-{sid}-kpis", "children"),
        Output(f"backup-uj-{sid}-donut", "children"),
        Output(f"backup-uj-{sid}-status", "children"),
        Output(f"backup-uj-{sid}-table", "children"),
        Output(f"backup-uj-{sid}-pageinfo", "children"),
        Output(f"backup-uj-{sid}-page", "data"),
        Input(f"backup-uj-{sid}-search", "value"),
        Input(f"backup-uj-{sid}-prev", "n_clicks"),
        Input(f"backup-uj-{sid}-next", "n_clicks"),
        Input(f"backup-uj-{sid}-filter-status", "value"),
        Input(f"backup-uj-{sid}-filter-type", "value"),
        Input(f"backup-uj-{sid}-filter-platform", "value"),
        Input("app-time-range", "data"),
        State(f"backup-uj-{sid}-page", "data"),
        State("url", "pathname"),
        prevent_initial_call=False,
    )
    def _update_customer(
        search,
        prev_n,
        next_n,
        f_status,
        f_type,
        f_platform,
        tr,
        page,
        pathname,
        _vendor=vendor,
        _category=category,
        _sid=sid,
    ):
        page = int(page or 1)
        trig = ctx.triggered_id
        if trig == f"backup-uj-{_sid}-next":
            page += 1
        elif trig == f"backup-uj-{_sid}-prev":
            page = max(1, page - 1)
        else:
            page = 1
        try:
            payload = _fetch_table_payload(
                scope="customer",
                vendor=_vendor,
                category=_category,
                pathname=pathname,
                tr=tr,
                page=page,
                search=search or "",
                statuses=f_status,
                types=f_type,
                platforms=f_platform,
                active_tab="backup",
            )
        except Exception:  # noqa: BLE001
            logger.exception("unique-jobs customer fetch failed (%s)", _vendor)
            return (dash.no_update,) * 6
        if payload is None:
            return (dash.no_update,) * 6
        totals = payload.get("totals") or {}
        kpis, donut, status_panel = build_unique_jobs_visuals(totals, _vendor)
        total = int(payload.get("total", 0) or 0)
        pages = max(1, -(-total // _PAGE_SIZE))
        page = min(page, pages)
        return (
            kpis,
            donut,
            status_panel,
            unique_jobs_table(_vendor, payload.get("items") or []),
            f"{page} / {pages}",
            page,
        )


def _register_callbacks() -> None:
    for vendor in ("veeam", "zerto"):
        _make_dc_callback(vendor)
        _make_customer_callback(vendor)
    for category in _NETBACKUP_CATEGORIES:
        _make_dc_callback("netbackup", category)
        _make_customer_callback("netbackup", category)
    # Unscoped NetBackup unique-jobs panels are not rendered — do not register.


_register_callbacks()
