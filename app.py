import logging
import dash
from dash import Dash, html, dcc, _dash_renderer
import dash_mantine_components as dmc
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from src.components.sidebar import create_sidebar_nav
from src.services import api_client as api
from src.utils.time_range import default_time_range, preset_to_range
from src.components.s3_panel import build_dc_s3_panel, build_customer_s3_panel

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

from src.pages import home, datacenters, dc_view, customer_view, query_explorer, global_view
from src.pages.dc_view import _build_compute_tab

_default_tr = default_time_range()
_customers = api.get_customer_list()
_default_customer = _customers[0] if _customers else "Boyner"
_customer_options = [{"value": c, "label": c} for c in _customers] if _customers else [{"value": "Boyner", "label": "Boyner"}]

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
        dcc.Store(id="app-time-range", data=_default_tr),
        html.Div(
            [
                _sidebar,
                html.Div(
                    html.Div(id="main-content", children=[]),
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
    name = customer_name or "Boyner"
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
    from src.components.backup_panel import build_netbackup_panel

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
    from src.components.backup_panel import build_zerto_panel

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
    from src.components.backup_panel import build_veeam_panel

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
    from src.pages.home import _phys_inv_bar_figure

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
    dash.Input("net-filters-store", "data"),
)
def update_net_role_device_options(manufacturer, net_filters):
    net_filters = net_filters or {}
    roles_by_manu = net_filters.get("roles_by_manufacturer") or {}
    devices_by_manu_role = net_filters.get("devices_by_manufacturer_role") or {}

    if not roles_by_manu:
        return [], None, [], None

    if manufacturer:
        roles = roles_by_manu.get(manufacturer) or []
        roles = sorted(roles)
        # All devices within this manufacturer (regardless of role selection)
        devs_set = set()
        for r in roles:
            devs_set.update(devices_by_manu_role.get(manufacturer, {}).get(r, []) or [])
        devices = sorted(devs_set)
    else:
        # Default: all manufacturers => all roles and all devices
        roles = sorted({r for roles in roles_by_manu.values() for r in (roles or [])})
        devices = sorted(
            {
                d
                for roles_map in devices_by_manu_role.values()
                for devs in roles_map.values()
                for d in (devs or [])
            }
        )

    role_data = [{"label": r, "value": r} for r in roles]
    device_data = [{"label": d, "value": d} for d in devices]
    # Reset downstream selections
    return role_data, None, device_data, None


@app.callback(
    dash.Output("net-device-selector", "data"),
    dash.Output("net-device-selector", "value"),
    dash.Input("net-role-selector", "value"),
    dash.Input("net-manufacturer-selector", "value"),
    dash.Input("net-filters-store", "data"),
)
def update_net_device_options(role, manufacturer, net_filters):
    net_filters = net_filters or {}
    roles_by_manu = net_filters.get("roles_by_manufacturer") or {}
    devices_by_manu_role = net_filters.get("devices_by_manufacturer_role") or {}

    if not devices_by_manu_role:
        return [], None

    if manufacturer and role:
        devices = devices_by_manu_role.get(manufacturer, {}).get(role, []) or []
    elif manufacturer and not role:
        # manufacturer selected, role cleared => all devices under manufacturer
        devices = []
        for r in roles_by_manu.get(manufacturer, []) or []:
            devices.extend(devices_by_manu_role.get(manufacturer, {}).get(r, []) or [])
    elif not manufacturer and role:
        # role selected, manufacturer cleared => union across manufacturers
        devs = set()
        for manu, roles_map in devices_by_manu_role.items():
            devs.update((roles_map.get(role, []) or []))
        devices = sorted(devs)
    else:
        # both cleared => all devices
        devices = sorted(
            {
                d
                for roles_map in devices_by_manu_role.values()
                for devs in roles_map.values()
                for d in (devs or [])
            }
        )

    device_data = [{"label": d, "value": d} for d in sorted(devices or [])]
    # Reset device selection whenever options change
    return device_data, None


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

    from src.components.charts import create_horizontal_bar_chart, create_usage_donut_chart
    from src.utils.format_units import pct_float
    from src.pages.dc_view import _bps_to_gbps  # reuse conversion helper

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


if __name__ == "__main__":
    app.run(debug=True, port=8050, use_reloader=False)
