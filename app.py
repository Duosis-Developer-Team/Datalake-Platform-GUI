import json
import logging
import os
import time as time_module
from urllib.parse import parse_qs

import dash
import plotly.graph_objects as go
from dash import Dash, html, dcc, _dash_renderer
import dash_mantine_components as dmc
from dotenv import load_dotenv
from flask import request

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from src.components.sidebar import create_sidebar_nav
from src.components.backup_panel import build_netbackup_panel, build_zerto_panel, build_veeam_panel
from src.components.charts import (
    create_capacity_area_chart,
    create_horizontal_bar_chart,
    create_usage_donut_chart,
)
from src.services import api_client as api
from src.services.db_service import DEFAULT_CUSTOMER_NAME, WARMED_CUSTOMERS
from src.utils.time_range import default_time_range, preset_to_range
from src.utils.format_units import pct_float, smart_storage
from src.components.s3_panel import build_dc_s3_panel, build_customer_s3_panel
from src.pages.home import _phys_inv_bar_figure

_dash_renderer._set_react_version("18.2.0")

stylesheets = [
    "https://unpkg.com/@mantine/core@7.10.0/styles.css",
    "https://unpkg.com/@mantine/dates@7.10.0/styles.css",
    "https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap",
]

app = Dash(
    __name__,
    use_pages=False,
    external_stylesheets=stylesheets,
    suppress_callback_exceptions=True,
    title="Bulutistan Dashboard",
)
server = app.server

APP_BUILD_ID = (os.environ.get("APP_BUILD_ID") or "dev").strip()


@server.after_request
def _prevent_stale_dash_cache(response):
    """Avoid browsers/CDNs serving an old Dash shell after a new image is deployed."""
    try:
        path = request.path
        ct = (response.content_type or "").lower()
        if path.startswith("/_dash") or "text/html" in ct:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
    except Exception:
        pass
    return response


_log = logging.getLogger(__name__)
_log.info("APP_BUILD_ID=%s", APP_BUILD_ID)

from src.pages import home, datacenters, dc_view, customer_view, query_explorer, global_view
from src.pages.dc_view import _bps_to_gbps, _build_compute_tab

_default_tr = default_time_range()
try:
    _customers = api.get_customer_list()
except Exception as exc:
    logging.getLogger(__name__).warning("get_customer_list failed at startup (using defaults): %s", exc)
    _customers = []
if not _customers:
    _customers = list(WARMED_CUSTOMERS)
_default_customer = _customers[0] if _customers else DEFAULT_CUSTOMER_NAME
_customer_options = [{"value": c, "label": c} for c in _customers]

_sidebar = html.Div(
    style={
        "width": "260px",
        "position": "fixed",
        "top": "16px",
        "left": "16px",
        "height": "calc(100vh - 32px)",
        "zIndex": 999,
        "padding": "24px",
        "backgroundColor": "#FFFFFF",
        "overflowY": "auto",
        "overflowX": "hidden",
        "borderRadius": "16px",
        "boxShadow": "0 10px 30px rgba(0, 0, 0, 0.08), 0 4px 12px rgba(0, 0, 0, 0.04)",
        "display": "flex",
        "flexDirection": "column",
    },
    children=[
        html.Div(id="sidebar-nav"),

        dmc.Stack(
            [
                dmc.Divider(mt="xl", style={"marginBottom": "4px"}),
                dmc.Text(
                    "REPORT PERIOD",
                    size="xs",
                    fw=600,
                    c="dimmed",
                    style={"letterSpacing": "0.06em"},
                ),
                dmc.SegmentedControl(
                    id="time-range-preset",
                    value=_default_tr.get("preset", "7d"),
                    data=[
                        {"label": "1D", "value": "1d"},
                        {"label": "7D", "value": "7d"},
                        {"label": "30D", "value": "30d"},
                        {"label": "Cstm", "value": "custom"},
                    ],
                    size="sm",
                    fullWidth=True,
                ),
                html.Div(
                    id="time-range-custom-container",
                    children=[
                        dmc.DatePicker(
                            id="time-range-picker",
                            type="range",
                            value=[_default_tr["start"], _default_tr["end"]],
                            valueFormat="DD/MM/YY",
                            placeholder="Select date range",
                            radius="md",
                            size="sm",
                            w="100%",
                            numberOfColumns=2,
                            styles={
                                "day": {
                                    "borderRadius": "50%",
                                    "fontWeight": "500",
                                    "transition": "background-color 0.15s ease, color 0.15s ease",
                                },
                            },
                            popoverProps={
                                "withinPortal": True,
                                "zIndex": 9999,
                                "position": "right-start",
                                "radius": "xl",
                                "styles": {
                                    "dropdown": {
                                        "border": "1px solid rgba(67, 24, 255, 0.08)",
                                        "boxShadow": "0 10px 40px rgba(67, 24, 255, 0.12), 0 4px 16px rgba(0, 0, 0, 0.06)",
                                        "borderRadius": "16px",
                                    }
                                },
                            },
                        ),
                    ],
                    style={"position": "relative"},
                ),
            ],
            gap="xs",
            px="md",
            mt="auto",
        ),

        html.Div(
            id="customer-section",
            children=[
                dmc.Text("Customer", size="xs", fw=600, c="#A3AED0", style={"marginBottom": "6px"}),
                dmc.Select(
                    id="customer-select",
                    data=_customer_options,
                    value=_default_customer,
                    radius="md",
                    variant="default",
                    size="sm",
                    style={"width": "100%"},
                ),
            ],
            style={
                "marginTop": "16px",
                "paddingTop": "12px",
                "borderTop": "1px solid #E9ECEF",
                "display": "none",
            },
        ),
    ],
)

app.layout = dmc.MantineProvider(
    theme={
        "fontFamily": "'DM Sans', sans-serif",
        "headings": {"fontFamily": "'DM Sans', sans-serif"},
        "primaryColor": "indigo",
    },
    children=[
        dcc.Location(id="url", refresh=False),
        html.Div(
            APP_BUILD_ID,
            id="app-deploy-revision",
            title="Deploy revision (env APP_BUILD_ID)",
            style={
                "position": "fixed",
                "bottom": "2px",
                "right": "8px",
                "fontSize": "10px",
                "color": "#ADB5BD",
                "zIndex": 9998,
                "pointerEvents": "none",
                "userSelect": "none",
            },
        ),
        dcc.Store(id="app-time-range", data=_default_tr),
        html.Div(
            [
                _sidebar,
                html.Div(
                    dcc.Loading(
                        id="main-content-loading",
                        type="circle",
                        color="#4318FF",
                        children=html.Div(id="main-content", children=[]),
                        style={"minHeight": "240px"},
                    ),
                    style={
                        "marginLeft": "292px",
                        "padding": "30px",
                        "minHeight": "100vh",
                        "width": "calc(100% - 292px)",
                        "backgroundColor": "#F4F7FE",
                    },
                ),
            ],
            style={"display": "flex", "backgroundColor": "#F4F7FE", "minHeight": "100vh"},
        ),
    ],
)


@app.callback(
    dash.Output("sidebar-nav", "children"),
    dash.Input("url", "pathname"),
)
def update_sidebar_nav(pathname):
    return create_sidebar_nav(pathname or "/")


@app.callback(
    dash.Output("customer-section", "style"),
    dash.Input("url", "pathname"),
)
def toggle_customer_section(pathname):
    base = {"marginTop": "16px", "paddingTop": "12px", "borderTop": "1px solid #E9ECEF"}
    if (pathname or "/") == "/customer-view":
        return {**base, "display": "block"}
    return {**base, "display": "none"}


@app.callback(
    dash.Output("app-time-range", "data"),
    dash.Input("time-range-preset", "value"),
    dash.Input("time-range-picker", "value"),
    dash.State("app-time-range", "data"),
)
def update_time_range_store(preset, date_value, current):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    tid = ctx.triggered[0]["prop_id"]
    if "time-range-preset" in tid and preset != "custom":
        return preset_to_range(preset)
    if "time-range-picker" in tid and date_value:
        if isinstance(date_value, (list, tuple)) and len(date_value) == 2:
            start, end = date_value
        else:
            start = (current or {}).get("start")
            end = date_value if isinstance(date_value, str) else None
        if start and end:
            return {"start": start, "end": end, "preset": "custom"}
        return dash.no_update
    return dash.no_update


@app.callback(
    dash.Output("main-content", "children"),
    dash.Input("url", "pathname"),
    dash.Input("app-time-range", "data"),
    dash.Input("customer-select", "value"),
)
def render_main_content(pathname, time_range, selected_customer):
    pathname = pathname or "/"
    tr = time_range or default_time_range()
    if pathname in ("/", ""):
        return home.build_overview(tr)
    if pathname == "/datacenters":
        return datacenters.build_datacenters(tr)
    if pathname and pathname.startswith("/datacenter/"):
        dc_id = pathname.replace("/datacenter/", "").strip("/")
        return dc_view.build_dc_view(dc_id, tr)
    if pathname == "/global-view":
        return global_view.build_global_view(tr)
    if pathname == "/customer-view":
        return customer_view.build_customer_layout(tr, selected_customer)
    if pathname == "/query-explorer":
        return query_explorer.layout()
    return home.build_overview(tr)


@app.callback(
    dash.Output("s3-dc-metrics-panel", "children"),
    dash.Input("s3-dc-pool-selector", "value"),
    dash.Input("app-time-range", "data"),
    dash.State("url", "pathname"),
)
def update_s3_dc_panel(selected_pools, time_range, pathname):
    if not pathname or not pathname.startswith("/datacenter/"):
        return dash.no_update
    dc_id = pathname.replace("/datacenter/", "").strip("/")
    tr = time_range or default_time_range()
    s3_data = api.get_dc_s3_pools(dc_id, tr)
    if not s3_data.get("pools"):
        return html.Div()
    pools = s3_data.get("pools") or []
    if not selected_pools:
        selected = pools
    else:
        selected = [p for p in selected_pools if p in pools] or pools
    return build_dc_s3_panel(dc_id, s3_data, tr, selected)


@app.callback(
    dash.Output("s3-customer-metrics-panel", "children"),
    dash.Input("s3-customer-vault-selector", "value"),
    dash.Input("app-time-range", "data"),
    dash.State("customer-select", "value"),
)
def update_s3_customer_panel(selected_vaults, time_range, customer_name):
    name = customer_name or DEFAULT_CUSTOMER_NAME
    tr = time_range or default_time_range()
    s3_data = api.get_customer_s3_vaults(name, tr)
    if not s3_data.get("vaults"):
        return html.Div()
    vaults = s3_data.get("vaults") or []
    if not selected_vaults:
        selected = vaults
    else:
        selected = [v for v in selected_vaults if v in vaults] or vaults
    return build_customer_s3_panel(name, s3_data, tr, selected)


@app.callback(
    dash.Output("classic-virt-panel", "children"),
    dash.Input("virt-classic-cluster-selector", "value"),
    dash.Input("app-time-range", "data"),
    dash.State("url", "pathname"),
)
def update_classic_virt_panel(selected_clusters, time_range, pathname):
    if not pathname or not pathname.startswith("/datacenter/"):
        return dash.no_update
    dc_id = pathname.replace("/datacenter/", "").strip("/")
    tr = time_range or default_time_range()
    classic = api.get_classic_metrics_filtered(dc_id, selected_clusters, tr)
    return _build_compute_tab(classic, "Classic Compute", color="blue")


@app.callback(
    dash.Output("hyperconv-virt-panel", "children"),
    dash.Input("virt-hyperconv-cluster-selector", "value"),
    dash.Input("app-time-range", "data"),
    dash.State("url", "pathname"),
)
def update_hyperconv_virt_panel(selected_clusters, time_range, pathname):
    if not pathname or not pathname.startswith("/datacenter/"):
        return dash.no_update
    dc_id = pathname.replace("/datacenter/", "").strip("/")
    tr = time_range or default_time_range()
    hyperconv = api.get_hyperconv_metrics_filtered(dc_id, selected_clusters, tr)
    return _build_compute_tab(hyperconv, "Hyperconverged Compute", color="teal")


@app.callback(
    dash.Output("backup-netbackup-panel", "children"),
    dash.Input("backup-nb-pool-selector", "value"),
    dash.Input("app-time-range", "data"),
    dash.State("url", "pathname"),
)
def update_backup_netbackup_panel(selected_pools, time_range, pathname):
    if not pathname or not pathname.startswith("/datacenter/"):
        return dash.no_update
    dc_id = pathname.replace("/datacenter/", "").strip("/")
    tr = time_range or default_time_range()
    data = api.get_dc_netbackup_pools(dc_id, tr)
    pools = data.get("pools") or []
    if not pools:
        return html.Div()
    if not selected_pools:
        selected = pools
    else:
        selected = [p for p in selected_pools if p in pools] or pools
    return build_netbackup_panel(data, selected)


@app.callback(
    dash.Output("backup-zerto-panel", "children"),
    dash.Input("backup-zerto-site-selector", "value"),
    dash.Input("app-time-range", "data"),
    dash.State("url", "pathname"),
)
def update_backup_zerto_panel(selected_sites, time_range, pathname):
    if not pathname or not pathname.startswith("/datacenter/"):
        return dash.no_update
    dc_id = pathname.replace("/datacenter/", "").strip("/")
    tr = time_range or default_time_range()
    data = api.get_dc_zerto_sites(dc_id, tr)
    sites = data.get("sites") or []
    if not sites:
        return html.Div()
    if not selected_sites:
        selected = sites
    else:
        selected = [s for s in selected_sites if s in sites] or sites
    return build_zerto_panel(data, selected)


@app.callback(
    dash.Output("backup-veeam-panel", "children"),
    dash.Input("backup-veeam-repo-selector", "value"),
    dash.Input("app-time-range", "data"),
    dash.State("url", "pathname"),
)
def update_backup_veeam_panel(selected_repos, time_range, pathname):
    if not pathname or not pathname.startswith("/datacenter/"):
        return dash.no_update
    dc_id = pathname.replace("/datacenter/", "").strip("/")
    tr = time_range or default_time_range()
    data = api.get_dc_veeam_repos(dc_id, tr)
    repos = data.get("repos") or []
    if not repos:
        return html.Div()
    if not selected_repos:
        selected = repos
    else:
        selected = [r for r in selected_repos if r in repos] or repos
    return build_veeam_panel(data, selected)


@app.callback(
    dash.Output("phys-inv-overview-chart", "figure"),
    dash.Output("phys-inv-overview-chart", "style"),
    dash.Output("phys-inv-drill-state", "data"),
    dash.Output("phys-inv-reset-btn", "style"),
    dash.Input("phys-inv-overview-chart", "clickData"),
    dash.Input("phys-inv-reset-btn", "n_clicks"),
    dash.State("phys-inv-drill-state", "data"),
    prevent_initial_call=True,
)
def update_phys_inv_chart(click_data, reset_clicks, state):
    state = state or {"level": 0, "role": None, "manufacturer": None}
    level = state.get("level", 0)
    role = state.get("role")
    manufacturer = state.get("manufacturer")

    def chart_height(n):
        return max(260, min(520, n * 32))

    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    trigger_id = ctx.triggered[0]["prop_id"]
    triggered_by_reset = "phys-inv-reset-btn" in trigger_id

    if triggered_by_reset:
        data = api.get_physical_inventory_overview_by_role()
        labels = [r["role"] for r in data]
        counts = [r["count"] for r in data]
        h = chart_height(len(labels))
        fig = _phys_inv_bar_figure(labels, counts, height=h)
        new_state = {"level": 0, "role": None, "manufacturer": None}
        return fig, {"height": f"{h}px"}, new_state, {"display": "none"}

    if not click_data or "points" not in click_data or not click_data["points"]:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    clicked_label = click_data["points"][0].get("y")
    if clicked_label is None:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    if level == 0:
        data = api.get_physical_inventory_overview_manufacturer(clicked_label)
        labels = [r["manufacturer"] for r in data]
        counts = [r["count"] for r in data]
        h = chart_height(len(labels))
        fig = _phys_inv_bar_figure(labels, counts, height=h)
        new_state = {"level": 1, "role": clicked_label, "manufacturer": None}
        return fig, {"height": f"{h}px"}, new_state, {"display": "inline-block"}
    if level == 1:
        data = api.get_physical_inventory_overview_location(role or "", clicked_label)
        labels = [r["location"] for r in data]
        counts = [r["count"] for r in data]
        h = chart_height(len(labels))
        fig = _phys_inv_bar_figure(labels, counts, height=h)
        new_state = {"level": 2, "role": role, "manufacturer": clicked_label}
        return fig, {"height": f"{h}px"}, new_state, {"display": "inline-block"}
    return dash.no_update, dash.no_update, dash.no_update, dash.no_update


@app.callback(
    dash.Output("global-dc-info-card", "children"),
    dash.Input("global-map-graph", "clickData"),
    dash.State("app-time-range", "data"),
    prevent_initial_call=True,
)
def update_global_info_card(click_data, time_range):
    if not click_data or "points" not in click_data or not click_data["points"]:
        return []
    point = click_data["points"][0]
    custom = point.get("customdata")
    if not custom or not custom[0]:
        return []
    dc_id = custom[0]
    tr = time_range or default_time_range()
    from src.pages.global_view import build_dc_info_card

    return build_dc_info_card(dc_id, tr)


# ---------------------------------------------------------------------------
# Network Dashboard (Zabbix) callbacks
# ---------------------------------------------------------------------------


@app.callback(
    dash.Output("net-role-selector", "data"),
    dash.Output("net-role-selector", "value"),
    dash.Output("net-device-selector", "data"),
    dash.Output("net-device-selector", "value"),
    dash.Input("net-manufacturer-selector", "value"),
    dash.Input("net-role-selector", "value"),
    dash.Input("net-filters-store", "data"),
)
def update_net_selectors(manufacturer, role, net_filters):
    """Single callback for role + device dropdowns (avoids duplicate Output writers)."""
    net_filters = net_filters or {}
    roles_by_manu = net_filters.get("roles_by_manufacturer") or {}
    devices_by_manu_role = net_filters.get("devices_by_manufacturer_role") or {}

    if not roles_by_manu:
        return [], None, [], None

    if manufacturer:
        roles = sorted(roles_by_manu.get(manufacturer) or [])
        devs_set: set = set()
        for r in roles:
            devs_set.update(devices_by_manu_role.get(manufacturer, {}).get(r, []) or [])
        devices_all = sorted(devs_set)
    else:
        roles = sorted({r for rs in roles_by_manu.values() for r in (rs or [])})
        devices_all = sorted(
            d
            for rm in devices_by_manu_role.values()
            for devs in rm.values()
            for d in (devs or [])
        )

    role_data = [{"label": r, "value": r} for r in roles]
    ctx = dash.callback_context
    triggered_id = getattr(ctx, "triggered_id", None)
    if triggered_id is None and ctx.triggered:
        triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if triggered_id == "net-role-selector":
        if manufacturer and role:
            devices = devices_by_manu_role.get(manufacturer, {}).get(role, []) or []
        elif manufacturer and not role:
            devices = []
            for r in roles_by_manu.get(manufacturer, []) or []:
                devices.extend(devices_by_manu_role.get(manufacturer, {}).get(r, []) or [])
        elif not manufacturer and role:
            devs = set()
            for roles_map in devices_by_manu_role.values():
                devs.update(roles_map.get(role, []) or [])
            devices = sorted(devs)
        else:
            devices = devices_all
        device_data = [{"label": d, "value": d} for d in sorted(devices or [])]
        return role_data, dash.no_update, device_data, None

    device_data = [{"label": d, "value": d} for d in devices_all]
    return role_data, None, device_data, None


@app.callback(
    dash.Output("net-kpi-container", "children"),
    dash.Output("net-donut-active-ports", "figure"),
    dash.Output("net-donut-utilization", "figure"),
    dash.Output("net-donut-icmp", "figure"),
    dash.Output("net-top-interfaces-bar", "figure"),
    dash.Input("net-manufacturer-selector", "value"),
    dash.Input("net-role-selector", "value"),
    dash.Input("net-device-selector", "value"),
    dash.Input("app-time-range", "data"),
    dash.State("url", "pathname"),
)
def update_net_kpis_and_charts(manufacturer, device_role, device_name, time_range, pathname):
    if not pathname or not pathname.startswith("/datacenter/"):
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    dc_id = pathname.replace("/datacenter/", "").strip("/")
    tr = time_range or default_time_range()

    port_summary = api.get_dc_network_port_summary(
        dc_id,
        tr,
        manufacturer=manufacturer,
        device_role=device_role,
        device_name=device_name,
    )
    percentile_data = api.get_dc_network_95th_percentile(
        dc_id,
        tr,
        top_n=20,
        manufacturer=manufacturer,
        device_role=device_role,
        device_name=device_name,
    )

    device_count = int(port_summary.get("device_count", 0) or 0)
    total_ports = int(port_summary.get("total_ports", 0) or 0)
    active_ports = int(port_summary.get("active_ports", 0) or 0)
    avg_icmp_loss_pct = float(port_summary.get("avg_icmp_loss_pct", 0) or 0)

    port_availability_pct = pct_float(active_ports, total_ports)
    icmp_availability_pct = max(0.0, min(100.0, 100.0 - avg_icmp_loss_pct))
    overall_util_pct = float(percentile_data.get("overall_port_utilization_pct", 0) or 0)

    kpis = dmc.SimpleGrid(
        cols=4,
        spacing="lg",
        children=[
            dc_view._kpi("Total Devices", f"{device_count:,}", "solar:server-bold-duotone", color="indigo"),
            dc_view._kpi("Active Ports", f"{active_ports:,}", "solar:signal-bold-duotone", color="indigo"),
            dc_view._kpi("Total Ports", f"{total_ports:,}", "solar:port-bold-duotone", color="indigo"),
            dc_view._kpi("Port Availability", f"{port_availability_pct:.1f}%", "solar:graph-bold-duotone", color="indigo"),
        ],
    )

    donut_active = create_usage_donut_chart(port_availability_pct, "Port Availability", color="#FFB547")
    donut_util = create_usage_donut_chart(overall_util_pct, "Port Utilization", color="#05CD99")
    donut_icmp = create_usage_donut_chart(icmp_availability_pct, "ICMP Availability", color="#4318FF")

    top_interfaces = percentile_data.get("top_interfaces") or []
    bar_labels = [(t.get("interface_name") or "").strip() or "Unknown" for t in top_interfaces]
    bar_values = [_bps_to_gbps(t.get("p95_total_bps")) for t in top_interfaces]
    bar_fig = create_horizontal_bar_chart(
        labels=bar_labels,
        values=bar_values,
        title="Top 95th Percentile Interfaces (Gbps)",
        color="#4318FF",
        height=320,
    )

    return kpis, donut_active, donut_util, donut_icmp, bar_fig


@app.callback(
    dash.Output("net-interface-table", "data"),
    dash.Input("net-manufacturer-selector", "value"),
    dash.Input("net-role-selector", "value"),
    dash.Input("net-device-selector", "value"),
    dash.Input("net-interface-search", "value"),
    dash.Input("net-interface-table", "page_current"),
    dash.Input("net-interface-table", "page_size"),
    dash.Input("app-time-range", "data"),
    dash.State("url", "pathname"),
)
def update_net_interface_table(manufacturer, device_role, device_name, search_value, page_current, page_size, time_range, pathname):
    if not pathname or not pathname.startswith("/datacenter/"):
        return []

    dc_id = pathname.replace("/datacenter/", "").strip("/")
    tr = time_range or default_time_range()

    page_current_safe = int(page_current or 0)
    page_size_safe = int(page_size or 50)
    page_backend = page_current_safe + 1  # backend is 1-based

    interface_data = api.get_dc_network_interface_table(
        dc_id,
        tr,
        page=page_backend,
        page_size=page_size_safe,
        search=search_value or "",
        manufacturer=manufacturer,
        device_role=device_role,
        device_name=device_name,
    )

    items = interface_data.get("items") or []
    rows = []
    for it in items:
        speed_gbps = (float(it.get("speed_bps") or 0) / 1e9) if it.get("speed_bps") is not None else 0.0
        total_gbps = (float(it.get("p95_total_bps") or 0) / 1e9) if it.get("p95_total_bps") is not None else 0.0
        rows.append(
            {
                "interface_name": it.get("interface_name") or "",
                "interface_alias": it.get("interface_alias") or "",
                "p95_total_gbps": round(total_gbps, 3),
                "speed_gbps": round(speed_gbps, 3),
                "utilization_pct": round(float(it.get("utilization_pct") or 0), 2),
            }
        )

    return rows


@app.callback(
    dash.Output("intel-donut-total", "figure"),
    dash.Output("intel-donut-used", "figure"),
    dash.Output("intel-donut-free", "figure"),
    dash.Output("intel-capacity-trend-chart", "figure"),
    dash.Input("intel-storage-device-selector", "value"),
    dash.Input("app-time-range", "data"),
    dash.State("url", "pathname"),
)
def update_intel_storage_charts(host, time_range, pathname):
    if not pathname or not pathname.startswith("/datacenter/"):
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    dc_id = pathname.replace("/datacenter/", "").strip("/")
    tr = time_range or default_time_range()

    cap = api.get_dc_zabbix_storage_capacity(dc_id, tr, host=host)
    trend = api.get_dc_zabbix_storage_trend(dc_id, tr, host=host)

    total_bytes = float(cap.get("total_capacity_bytes", 0) or 0)
    used_bytes = float(cap.get("used_capacity_bytes", 0) or 0)
    free_bytes = float(cap.get("free_capacity_bytes", 0) or 0)

    # Zabbix bytes -> GB for smart_storage labels.
    bytes_to_gb = lambda b: (float(b) / (1024.0**3)) if b else 0.0
    total_gb = bytes_to_gb(total_bytes)
    used_gb = bytes_to_gb(used_bytes)
    free_gb = bytes_to_gb(free_bytes)

    used_pct = pct_float(used_gb, total_gb)
    free_pct = max(0.0, 100.0 - used_pct)

    donut_total = create_usage_donut_chart(100.0, f"Total {smart_storage(total_gb)}", color="#FFB547")
    donut_used = create_usage_donut_chart(used_pct, "Used Capacity", color="#4318FF")
    donut_free = create_usage_donut_chart(free_pct, "Free Capacity", color="#05CD99")

    series = trend.get("series") or []
    timestamps = [p.get("ts") for p in series if p.get("ts") is not None]
    used_series = [p.get("used_capacity_bytes") for p in series]
    total_series = [p.get("total_capacity_bytes") for p in series]

    trend_fig = create_capacity_area_chart(
        timestamps=timestamps,
        used=used_series,
        total=total_series,
        title="Capacity Utilization Trend",
        height=260,
    )

    return donut_total, donut_used, donut_free, trend_fig


@app.callback(
    dash.Output("intel-disk-container", "children"),
    dash.Input("intel-storage-device-selector", "value"),
    dash.Input("app-time-range", "data"),
    dash.State("url", "pathname"),
)
def update_intel_disk_container(host, time_range, pathname):
    if not pathname or not pathname.startswith("/datacenter/"):
        return dash.no_update

    dc_id = pathname.replace("/datacenter/", "").strip("/")
    tr = time_range or default_time_range()

    if host is None:
        return [
            dmc.Text("Select a device to load disks.", size="sm", c="#A3AED0"),
            html.Div(id="intel-disk-trend-container"),
        ]

    disk_data = api.get_dc_zabbix_disk_list(dc_id, tr, host=host)
    disks = disk_data.get("items") or []
    disk_options = [{"label": d, "value": d} for d in disks]

    disk_selector = dmc.Select(
        id="intel-storage-disk-selector",
        data=disk_options,
        value=None,
        clearable=True,
        searchable=True,
        placeholder="Select disk",
        nothingFoundMessage="No disks",
        style={"minWidth": "260px"},
    )

    return [
        disk_selector,
        html.Div(id="intel-disk-trend-container"),
    ]


@app.callback(
    dash.Output("intel-disk-trend-container", "children"),
    dash.Input("intel-storage-disk-selector", "value"),
    dash.Input("intel-storage-device-selector", "value"),
    dash.Input("app-time-range", "data"),
    dash.State("url", "pathname"),
)
def update_intel_disk_trend(disk_name, host, time_range, pathname):
    if not pathname or not pathname.startswith("/datacenter/"):
        return dash.no_update

    if host is None or disk_name is None:
        return html.Div()

    dc_id = pathname.replace("/datacenter/", "").strip("/")
    tr = time_range or default_time_range()

    trend = api.get_dc_zabbix_disk_trend(dc_id, tr, host=host, disk_name=disk_name)
    series = trend.get("series") or []

    timestamps = [p.get("ts") for p in series if p.get("ts") is not None]
    iops_series = [float(p.get("avg_iops") or 0) for p in series]
    latency_series = [float(p.get("avg_latency_ms") or 0) for p in series]

    total_bytes_series = [float(p.get("total_capacity_bytes") or 0) for p in series]
    free_bytes_series = [float(p.get("free_capacity_bytes") or 0) for p in series]
    used_bytes_series = [t - f for t, f in zip(total_bytes_series, free_bytes_series)]

    capacity_fig = create_capacity_area_chart(
        timestamps=timestamps,
        used=used_bytes_series,
        total=total_bytes_series,
        title=f"Disk Capacity Utilization - {disk_name}",
        height=260,
    )

    iops_fig = go.Figure(data=[go.Scatter(x=timestamps, y=iops_series, mode="lines+markers", name="Avg IOPS")])
    iops_fig.update_layout(height=240, margin=dict(l=30, r=10, t=30, b=20))

    latency_fig = go.Figure(
        data=[go.Scatter(x=timestamps, y=latency_series, mode="lines+markers", name="Avg Latency (ms)")]
    )
    latency_fig.update_layout(height=240, margin=dict(l=30, r=10, t=30, b=20))

    return dmc.Stack(
        gap="lg",
        children=[
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    dc_view._section_title("Disk Capacity Utilization", "Latest daily utilization trend"),
                    dc_view._chart_card(
                        dcc.Graph(
                            figure=capacity_fig,
                            config={"displayModeBar": False},
                            style={"height": "260px"},
                        )
                    ),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    dc_view._section_title("Disk Performance", "Avg IOPS and latency over time"),
                    dmc.SimpleGrid(
                        cols=2,
                        spacing="lg",
                        children=[
                            dc_view._chart_card(dcc.Graph(figure=iops_fig, config={"displayModeBar": False})),
                            dc_view._chart_card(dcc.Graph(figure=latency_fig, config={"displayModeBar": False})),
                        ],
                    ),
                ],
            ),
        ],
    )


if __name__ == "__main__":
    app.run(debug=True, port=8050, use_reloader=False)
