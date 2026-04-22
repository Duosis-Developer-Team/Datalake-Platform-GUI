from __future__ import annotations
import json
import logging
import os
import threading
import time as time_module
from urllib.parse import parse_qs

import dash
import plotly.graph_objects as go
from dash import Dash, html, dcc, _dash_renderer, ALL
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from dotenv import load_dotenv
from flask import request

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from src.telemetry.dash_instrumentation import trace_dash_callback
from src.telemetry.setup import instrument_flask_server, setup_telemetry_sdk

setup_telemetry_sdk()

from src.components.sidebar import create_sidebar_nav
from src.components.backup_panel import build_netbackup_panel, build_zerto_panel, build_veeam_panel
from src.components.charts import (
    create_capacity_area_chart,
    create_horizontal_bar_chart,
    create_premium_gauge_chart,
)
from src.services import api_client as api
from src.services.db_service import DEFAULT_CUSTOMER_NAME, WARMED_CUSTOMERS
from src.utils.time_range import (
    PRESET_CUSTOM,
    cache_time_ranges,
    default_time_range,
    preset_to_range,
    time_range_to_bounds,
)
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

from src.auth.config import SECRET_KEY

server.secret_key = SECRET_KEY

try:
    from src.auth.migration import run_migrations
    from src.auth.seed import seed_all

    run_migrations()
    seed_all()
except Exception as _auth_exc:
    logging.getLogger(__name__).warning("Auth DB bootstrap failed: %s", _auth_exc)

from src.auth.routes import auth_bp
from src.auth.middleware import register_middleware

server.register_blueprint(auth_bp)
register_middleware(server)
instrument_flask_server(server)

APP_BUILD_ID = (os.environ.get("APP_BUILD_ID") or "dev").strip()


@server.after_request
def _prevent_stale_dash_cache(response):
    """Cache policy: no-store for Dash shell/HTML; long-lived cache for fingerprinted static assets."""
    try:
        path = request.path
        ct = (response.content_type or "").lower()
        if path.startswith("/_dash") or "text/html" in ct:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        elif path.startswith("/assets/") and ("text/css" in ct or "javascript" in ct or "application/javascript" in ct):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    except Exception:
        pass
    return response


_log = logging.getLogger(__name__)
_log.info("APP_BUILD_ID=%s", APP_BUILD_ID)

from src.pages import home, datacenters, dc_view, customer_view, query_explorer, global_view, region_drilldown, dc_detail
from src.pages import login as login_page_mod
from src.pages.settings import shell as settings_shell
from src.components.access_denied import build_access_denied
from src.pages.dc_view import _bps_to_gbps, _build_compute_tab, _DC_ICONS
from src.pages.settings.iam import roles_callbacks  # noqa: F401 — registers role matrix callback
from src.pages.settings.iam import teams_callbacks  # noqa: F401 — IAM teams panel / members
from src.pages.settings.iam import users_callbacks  # noqa: F401 — IAM users AD import / edit
from src.pages.settings.integrations import ldap_callbacks  # noqa: F401 — LDAP test connection / mapping role sync

_default_tr = default_time_range()
_custom_st, _custom_en = time_range_to_bounds(_default_tr)
_custom_picker_start = _custom_st.strftime("%Y-%m-%dT%H:%M:%S")
_custom_picker_end = _custom_en.strftime("%Y-%m-%dT%H:%M:%S")
try:
    _customers = api.get_customer_list()
except Exception as exc:
    logging.getLogger(__name__).warning("get_customer_list failed at startup (using defaults): %s", exc)
    _customers = []
if not _customers:
    _customers = list(WARMED_CUSTOMERS)
_default_customer = _customers[0] if _customers else DEFAULT_CUSTOMER_NAME
_customer_options = [{"value": c, "label": c} for c in _customers]


def _warm_worker_local_customer_availability_cache() -> None:
    """
    Warm per-worker in-memory AuraNotify cache so the first customer page render
    does not depend on a cold external HTTP call.
    """
    for tr in cache_time_ranges():
        for customer_name in _customers:
            try:
                api.get_customer_availability_bundle(customer_name, tr, force_refresh=True)
            except Exception as exc:
                _log.warning(
                    "Availability startup warm failed for customer=%s preset=%s: %s",
                    customer_name,
                    tr.get("preset", ""),
                    exc,
                )


threading.Thread(target=_warm_worker_local_customer_availability_cache, daemon=True).start()

_sidebar = html.Div(
    id="sidebar-shell",
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
                        {"label": "1H", "value": "1h"},
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
                        dmc.Stack(
                            gap="xs",
                            children=[
                                dmc.Text("Start", size="xs", c="dimmed", fw=500),
                                dmc.DateTimePicker(
                                    id="time-range-start-datetime",
                                    value=_custom_picker_start,
                                    valueFormat="DD/MM/YYYY HH:mm",
                                    placeholder="Start",
                                    radius="md",
                                    size="sm",
                                    w="100%",
                                    popoverProps={"withinPortal": True, "zIndex": 9999},
                                ),
                                dmc.Text("End", size="xs", c="dimmed", fw=500),
                                dmc.DateTimePicker(
                                    id="time-range-end-datetime",
                                    value=_custom_picker_end,
                                    valueFormat="DD/MM/YYYY HH:mm",
                                    placeholder="End",
                                    radius="md",
                                    size="sm",
                                    w="100%",
                                    popoverProps={"withinPortal": True, "zIndex": 9999},
                                ),
                            ],
                        ),
                    ],
                    style={"position": "relative", "display": "none"},
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
                    placeholder="Select customer",
                    clearable=True,
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
        dcc.Store(id="auth-user-store", data=None),
        dcc.Store(id="auth-permissions-store", data=None),
        html.Div(id="export-pdf-clientside-dummy", style={"display": "none"}),
        html.Div(
            [
                _sidebar,
                html.Div(
                    id="main-shell",
                    children=[
                        dcc.Loading(
                            id="main-content-loading",
                            type="circle",
                            color="#4318FF",
                            delay_show=250,
                            overlay_style={
                                "visibility": "visible",
                                "backgroundColor": "rgba(244, 247, 254, 0.72)",
                            },
                            target_components={"main-content": "children"},
                            children=html.Div(id="main-content", children=[]),
                            style={"minHeight": "240px"},
                        ),
                    ],
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


app.clientside_callback(
    """
    function(homePdf, dcListPdf, dcPdf, globalPdf, customerPdf, qePdf) {
        const triggered = dash_clientside.callback_context.triggered;
        if (!triggered || !triggered.length || !triggered[0]) {
            return window.dash_clientside.no_update;
        }
        const propId = triggered[0].prop_id || "";
        const id = propId.split(".")[0];
        const map = {
            "home-export-pdf": "home_overview",
            "datacenters-export-pdf": "datacenters",
            "dc-export-pdf": "dc_detail",
            "global-export-pdf": "global_view",
            "customer-export-pdf": "customer_view",
            "qe-export-pdf": "query_explorer"
        };
        const prefix = map[id];
        if (!prefix) {
            return window.dash_clientside.no_update;
        }
        const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
        if (typeof window.triggerPagePDF === "function") {
            window.triggerPagePDF("main-content", prefix + "_" + ts + ".pdf");
        }
        return window.dash_clientside.no_update;
    }
    """,
    dash.Output("export-pdf-clientside-dummy", "children"),
    dash.Input("home-export-pdf", "n_clicks"),
    dash.Input("datacenters-export-pdf", "n_clicks"),
    dash.Input("dc-export-pdf", "n_clicks"),
    dash.Input("global-export-pdf", "n_clicks"),
    dash.Input("customer-export-pdf", "n_clicks"),
    dash.Input("qe-export-pdf", "n_clicks"),
    prevent_initial_call=True,
)


@app.callback(
    dash.Output("sidebar-nav", "children"),
    dash.Input("url", "pathname"),
)
def update_sidebar_nav(pathname):
    from flask import g, has_request_context

    from src.auth.permission_service import user_effective_map

    pmap = None
    uname = ""
    if has_request_context():
        uid = getattr(g, "auth_user_id", None)
        u = getattr(g, "auth_user", None) or {}
        uname = str(u.get("username") or "")
        if uid:
            pmap = user_effective_map(int(uid))
    return create_sidebar_nav(pathname or "/", pmap, uname)


@app.callback(
    dash.Output("sidebar-shell", "style"),
    dash.Output("main-shell", "style"),
    dash.Input("url", "pathname"),
)
def layout_shell(pathname):
    pathname = pathname or "/"
    base_sidebar = {
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
    }
    base_main = {
        "marginLeft": "292px",
        "padding": "30px",
        "minHeight": "100vh",
        "width": "calc(100% - 292px)",
        "backgroundColor": "#F4F7FE",
    }
    if pathname == "/login":
        return {**base_sidebar, "display": "none"}, {
            **base_main,
            "marginLeft": "0",
            "width": "100%",
        }
    return base_sidebar, base_main


@app.callback(
    dash.Output("auth-user-store", "data"),
    dash.Output("auth-permissions-store", "data"),
    dash.Input("url", "pathname"),
)
def sync_auth_stores(pathname):
    from flask import g, has_request_context

    from src.auth.permission_service import user_effective_map

    if not has_request_context():
        return dash.no_update, dash.no_update
    uid = getattr(g, "auth_user_id", None)
    if not uid:
        return None, None
    pmap = user_effective_map(int(uid))
    u = getattr(g, "auth_user", None) or {}
    return {"id": int(uid), "username": u.get("username")}, pmap


@app.callback(
    dash.Output("customer-section", "style"),
    dash.Input("url", "pathname"),
)
def toggle_customer_section(pathname):
    base = {"marginTop": "16px", "paddingTop": "12px", "borderTop": "1px solid #E9ECEF"}
    if (pathname or "/") == "/customer-view":
        return {**base, "display": "block"}
    return {**base, "display": "none"}


def _normalize_custom_iso(v: str | None) -> str | None:
    if not v:
        return None
    s = str(v).strip()
    if s.endswith("Z"):
        return s
    if "+" in s[-6:] or s.endswith("UTC"):
        return s
    if "T" in s:
        return s + "Z"
    return s


@app.callback(
    dash.Output("time-range-custom-container", "style"),
    dash.Input("time-range-preset", "value"),
)
def toggle_custom_time_container(preset):
    base = {"position": "relative"}
    if preset == PRESET_CUSTOM:
        return {**base, "display": "block"}
    return {**base, "display": "none"}


@app.callback(
    dash.Output("time-range-start-datetime", "value"),
    dash.Output("time-range-end-datetime", "value"),
    dash.Input("time-range-preset", "value"),
    dash.State("app-time-range", "data"),
)
def sync_custom_datetime_pickers(preset, store):
    if preset != PRESET_CUSTOM:
        return dash.no_update, dash.no_update
    tr = store or default_time_range()
    st, en = time_range_to_bounds(tr)
    return st.strftime("%Y-%m-%dT%H:%M:%S"), en.strftime("%Y-%m-%dT%H:%M:%S")


@app.callback(
    dash.Output("app-time-range", "data"),
    dash.Input("time-range-preset", "value"),
    dash.Input("time-range-start-datetime", "value"),
    dash.Input("time-range-end-datetime", "value"),
    dash.State("app-time-range", "data"),
)
def update_time_range_store(preset, start_dt, end_dt, current):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    tid = ctx.triggered[0]["prop_id"].split(".")[0]
    if tid == "time-range-preset":
        if preset == PRESET_CUSTOM:
            cur = current or default_time_range()
            st, en = time_range_to_bounds(cur)
            return {
                "start": st.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                "end": en.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                "preset": PRESET_CUSTOM,
            }
        return preset_to_range(preset)
    if tid in ("time-range-start-datetime", "time-range-end-datetime"):
        if (current or {}).get("preset") != PRESET_CUSTOM:
            return dash.no_update
        s = start_dt or (current or {}).get("start")
        e = end_dt or (current or {}).get("end")
        s = _normalize_custom_iso(s) if isinstance(s, str) else s
        e = _normalize_custom_iso(e) if isinstance(e, str) else e
        if s and e:
            return {"start": s, "end": e, "preset": PRESET_CUSTOM}
        return dash.no_update
    return dash.no_update


@app.callback(
    dash.Output("main-content", "children"),
    dash.Input("url", "pathname"),
    dash.Input("app-time-range", "data"),
    dash.Input("customer-select", "value"),
    dash.Input("url", "search"),
)
@trace_dash_callback("render_main_content")
def render_main_content(pathname, time_range, selected_customer, search):
    from flask import g, has_request_context, request as flask_request

    from src.auth.config import AUTH_DISABLED
    from src.auth.permission_service import can_view, get_visible_sections, resolve_pathname_to_page_code

    pathname = pathname or "/"
    tr = time_range or default_time_range()

    if pathname == "/login":
        nxt, err = login_page_mod.parse_login_search(search)
        return login_page_mod.build_login_layout(nxt, error=err)

    uid = getattr(g, "auth_user_id", None) if has_request_context() else None
    if not AUTH_DISABLED and uid is None:
        _log.warning(
            "main-content: missing auth user; rendering empty layout pathname=%s "
            "flask_path=%s has_request_context=%s",
            pathname,
            getattr(flask_request, "path", None),
            has_request_context(),
        )
        return html.Div()

    page_code = resolve_pathname_to_page_code(pathname)
    vis = (
        get_visible_sections(int(uid), page_code)
        if uid and page_code and not str(pathname).startswith("/settings")
        else None
    )

    if (
        page_code
        and uid
        and not str(pathname).startswith("/settings")
        and not can_view(int(uid), page_code)
    ):
        return build_access_denied()

    if pathname in ("/", ""):
        return home.build_overview(tr, visible_sections=vis)
    if pathname == "/datacenters":
        return datacenters.build_datacenters(tr, visible_sections=vis)
    if pathname and pathname.startswith("/datacenter/"):
        dc_id = pathname.replace("/datacenter/", "").strip("/")
        return dc_view.build_dc_view(dc_id, tr, visible_sections=vis)
    if pathname == "/global-view":
        return global_view.build_global_view(tr, visible_sections=vis)
    if pathname == "/customer-view":
        return customer_view.build_customer_layout(tr, selected_customer, visible_sections=vis)
    if pathname == "/query-explorer":
        return query_explorer.layout(visible_sections=vis)
    if pathname and pathname.startswith("/dc-detail/"):
        dc_id = pathname.replace("/dc-detail/", "").strip("/")
        return dc_detail.build_dc_detail(dc_id, tr, visible_sections=vis)
    if pathname == "/region-drilldown":
        from urllib.parse import parse_qs

        params = parse_qs((search or "").lstrip("?"))
        region = params.get("region", [""])[0]
        return region_drilldown.build_region_drilldown(region, tr)
    if pathname.startswith("/settings"):
        return settings_shell.build_settings_page(pathname, int(uid), search)
    return home.build_overview(tr, visible_sections=vis)


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
    name = (customer_name or "").strip()
    if not name:
        return html.Div()
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
    dash.Output("global-detail-panel", "children"),
    dash.Output("last-clicked-dc-id", "data"),
    dash.Output("current-view-mode", "data", allow_duplicate=True),
    dash.Output("selected-building-dc-store", "data"),
    dash.Input("global-map-graph", "clickedPoint"),
    dash.State("last-clicked-dc-id", "data"),
    dash.State("app-time-range", "data"),
    prevent_initial_call=True,
)
def handle_globe_pin_click(clicked_point, last_dc_id, time_range):
    if not clicked_point:
        return [], None, dash.no_update, dash.no_update
    dc_id = clicked_point.get("dc_id")
    site_name = clicked_point.get("site_name", "")
    if not dc_id:
        return [], None, dash.no_update, dash.no_update

    if dc_id == last_dc_id:
        return dash.no_update, dc_id, "building", {"dc_id": dc_id, "dc_name": dc_id}

    from src.utils.time_range import default_time_range
    tr = time_range or default_time_range()
    from src.pages.global_view import build_dc_info_card
    panel = build_dc_info_card(dc_id, tr, site_name=site_name)
    return panel, dc_id, dash.no_update, dash.no_update


@app.callback(
    dash.Output("global-3d-modal-container", "children"),
    dash.Output("global-3d-modal-container", "style"),
    dash.Input({"type": "open-3d-hologram-btn", "index": ALL}, "n_clicks"),
    dash.State("global-3d-modal-container", "style"),
    prevent_initial_call=True,
)
def open_3d_hologram_modal(btn_clicks, current_style):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update
    if all(x is None for x in btn_clicks):
        return dash.no_update, dash.no_update

    trig = ctx.triggered[0]["prop_id"].split(".")[0]
    try:
        trig_dict = json.loads(trig)
    except Exception:
        return dash.no_update, dash.no_update

    dc_id = trig_dict.get("index")
    if not dc_id:
        return dash.no_update, dash.no_update

    from src.services import api_client as api
    from src.pages.global_view import build_3d_rack_overlay

    info = api.get_dc_details(dc_id, default_time_range())
    dc_name = info.get("meta", {}).get("name", dc_id)

    racks_resp = api.get_dc_racks(dc_id)
    racks = racks_resp.get("racks", [])

    if racks:
        content = build_3d_rack_overlay(dc_id, dc_name, racks)
        new_style = current_style.copy() if current_style else {}
        new_style["display"] = "flex"
        new_style["pointerEvents"] = "auto"
        return content, new_style

    return [], current_style


@app.callback(
    dash.Output("global-3d-modal-container", "style", allow_duplicate=True),
    dash.Input("close-3d-overlay-btn", "n_clicks"),
    dash.State("global-3d-modal-container", "style"),
    prevent_initial_call=True,
)
def close_3d_hologram_modal(n_clicks, current_style):
    if not n_clicks:
        return dash.no_update
    new_style = current_style.copy() if current_style else {}
    new_style["display"] = "none"
    new_style["pointerEvents"] = "none"
    return new_style



@app.callback(
    dash.Output("globe-layer", "style"),
    dash.Output("building-reveal-layer", "style"),
    dash.Output("floor-map-layer", "style"),
    dash.Output("building-reveal-timer", "disabled"),
    dash.Output("building-reveal-timer", "n_intervals"),
    dash.Output("building-reveal-dc-name", "children"),
    dash.Input("current-view-mode", "data"),
    dash.State("selected-building-dc-store", "data"),
)
def view_controller(mode, dc_store):
    shown = {"display": "block"}
    hidden = {"display": "none"}
    reveal_shown = {"display": "flex"}
    dc_label = (dc_store or {}).get("dc_name", "")
    if mode == "building":
        # Reset n_intervals to 0 so the timer fires fresh every time
        return hidden, reveal_shown, hidden, False, 0, dc_label
    if mode == "floor_map":
        return hidden, hidden, shown, True, dash.no_update, dc_label
    return shown, hidden, hidden, True, dash.no_update, dc_label


@app.callback(
    dash.Output("current-view-mode", "data", allow_duplicate=True),
    dash.Output("floor-map-layer", "children"),
    dash.Input("building-reveal-timer", "n_intervals"),
    dash.State("selected-building-dc-store", "data"),
    dash.State("current-view-mode", "data"),
    prevent_initial_call=True,
)
def advance_to_floor_map(n_intervals, dc_store, current_mode):
    if not n_intervals or current_mode != "building" or not dc_store:
        return dash.no_update, dash.no_update
    dc_id = dc_store.get("dc_id", "")
    dc_name = dc_store.get("dc_name", dc_id)
    racks_resp = api.get_dc_racks(dc_id)
    racks = racks_resp.get("racks", [])
    from src.pages.floor_map import build_floor_map_layout
    return "floor_map", build_floor_map_layout(dc_id, dc_name, racks)


@app.callback(
    dash.Output("current-view-mode", "data", allow_duplicate=True),
    dash.Output("last-clicked-dc-id", "data", allow_duplicate=True),
    dash.Input("back-to-global-btn", "n_clicks"),
    prevent_initial_call=True,
)
def back_to_globe(n_clicks):
    if not n_clicks:
        return dash.no_update, dash.no_update
    return "globe", None


def _build_rack_unit_diagram(rack_name, u_height, devices, fill, dark):
    """Render a CSS-based rack unit diagram showing installed devices."""
    # Build a map: slot -> device (position is bottom U of device)
    slot_map = {}
    for d in devices:
        pos = d.get("position")
        if pos is not None:
            slot_map[int(pos)] = d

    # Device type → visual style
    DEVICE_STYLES = {
        "patch panel":   {"bg": "#EFF8FF", "border": "#B2DDFF", "color": "#175CD3", "icon": "solar:gamepad-bold-duotone"},
        "server":        {"bg": "#ECFDF3", "border": "#A9EFC5", "color": "#027A48", "icon": "solar:server-bold-duotone"},
        "switch":        {"bg": "#FDF4FF", "border": "#E9D7FE", "color": "#6941C6", "icon": "solar:routing-bold-duotone"},
        "storage":       {"bg": "#FFF6ED", "border": "#FDD49A", "color": "#B54708", "icon": "solar:hard-drive-bold-duotone"},
        "router":        {"bg": "#F0F9FF", "border": "#B9E6FE", "color": "#026AA2", "icon": "solar:routing-bold-duotone"},
        "pdu":           {"bg": "#FEF3F2", "border": "#FECDCA", "color": "#B42318", "icon": "solar:bolt-bold-duotone"},
        "ups":           {"bg": "#FFFAEB", "border": "#FEDF89", "color": "#B54708", "icon": "solar:battery-charge-bold-duotone"},
    }

    def _style_for(device_type):
        dt = (device_type or "").lower()
        for key, val in DEVICE_STYLES.items():
            if key in dt:
                return val
        return {"bg": "#F9FAFB", "border": "#EAECF0", "color": "#344054", "icon": "solar:cpu-bold-duotone"}

    total_u = max(u_height or 47, max((int(d.get("position") or 0) for d in devices), default=0) + 1)
    # Show top-down: slot total_u → 1
    rows = []
    u = total_u
    while u >= 1:
        device = slot_map.get(u)
        u_label = html.Div(
            str(u),
            style={"width": "22px", "flexShrink": "0", "textAlign": "right",
                   "color": "#B0B7C3", "fontSize": "9px", "fontFamily": "DM Mono, monospace",
                   "paddingRight": "6px", "lineHeight": "22px"},
        )
        if device:
            s = _style_for(device.get("device_type") or device.get("role") or "")
            dev_name = str(device.get("name") or "")
            # Truncate long names
            display_name = dev_name if len(dev_name) <= 28 else dev_name[:25] + "…"
            dtype = str(device.get("device_type") or device.get("role") or "Device")
            row_content = html.Div(
                style={
                    "flex": "1", "height": "22px",
                    "background": s["bg"],
                    "border": f"1px solid {s['border']}",
                    "borderRadius": "4px",
                    "display": "flex", "alignItems": "center",
                    "gap": "5px", "padding": "0 6px",
                    "cursor": "default",
                },
                title=f"{dev_name} — {dtype}",
                children=[
                    DashIconify(icon=s["icon"], width=11, color=s["color"]),
                    html.Span(display_name, style={
                        "fontSize": "9px", "color": s["color"],
                        "fontWeight": "600", "overflow": "hidden",
                        "whiteSpace": "nowrap", "textOverflow": "ellipsis",
                        "fontFamily": "DM Sans, sans-serif",
                    }),
                ],
            )
        else:
            row_content = html.Div(style={
                "flex": "1", "height": "22px",
                "background": "rgba(0,0,0,0)",
                "borderRadius": "4px",
            })

        rows.append(html.Div(
            style={"display": "flex", "alignItems": "center", "gap": "2px",
                   "borderBottom": "1px solid rgba(234,236,240,0.5)"},
            children=[u_label, row_content],
        ))
        u -= 1

    occupied = len([d for d in devices if d.get("position") is not None])

    return html.Div(children=[
        # Header
        html.Div(
            style={"display": "flex", "alignItems": "center", "justifyContent": "space-between",
                   "marginBottom": "8px"},
            children=[
                dmc.Text("Rack Units", size="xs", fw=700, c="#344054"),
                dmc.Group(gap=6, align="center", children=[
                    html.Div(style={"width": "8px", "height": "8px", "borderRadius": "2px",
                                    "background": fill, "flexShrink": "0"}),
                    dmc.Text(f"{occupied} / {total_u}U occupied",
                             size="xs", c="#667085"),
                ]),
            ],
        ),
        # Rack cabinet
        html.Div(
            className="rack-unit-cabinet",
            children=[
                # Left rail
                html.Div(className="rack-rail rack-rail-left"),
                # Right rail
                html.Div(className="rack-rail rack-rail-right"),
                # Units
                html.Div(
                    style={"flex": "1", "display": "flex", "flexDirection": "column",
                           "padding": "4px 8px"},
                    children=rows,
                ),
            ],
        ),
        # Legend
        dmc.Group(gap="md", mt="xs", children=[
            *[dmc.Group(gap=4, align="center", children=[
                html.Div(style={"width": "8px", "height": "8px", "borderRadius": "2px",
                                "background": v["bg"], "border": f"1px solid {v['border']}"}),
                dmc.Text(k.title(), size="xs", c="#667085"),
            ]) for k, v in list(DEVICE_STYLES.items())[:4]],
        ]),
    ])


def _detail_row(icon, label, value):
    return html.Div(
        style={"display": "flex", "alignItems": "center", "gap": "10px",
               "padding": "10px 14px"},
        children=[
            DashIconify(icon=icon, width=15, color="#98A2B3"),
            dmc.Text(label, size="xs", c="#667085", fw=600,
                     style={"width": "52px", "flexShrink": "0"}),
            dmc.Text(value, size="xs", c="#344054", fw=500),
        ],
    )


@app.callback(
    dash.Output("floor-map-rack-detail", "children"),
    dash.Input("floor-map-graph", "clickData"),
    dash.State("selected-building-dc-store", "data"),
    prevent_initial_call=True,
)
def show_rack_detail(click_data, dc_store):
    if not click_data or not click_data.get("points"):
        return dash.no_update
    point = click_data["points"][0]
    cd = point.get("customdata")
    if not cd:
        return dash.no_update
    rack_id, name, status, u_height, power, hall, rack_type, serial = (
        list(cd) + [None] * 8
    )[:8]
    # dc_id always comes from the store — never trust Plotly customdata for this
    dc_id = (dc_store or {}).get("dc_id", "")

    status_meta = {
        "active":   ("#17B26A", "#ECFDF3", "#027A48", "green"),
        "planned":  ("#2E90FA", "#EFF8FF", "#175CD3", "blue"),
        "inactive": ("#F04438", "#FEF3F2", "#B42318", "red"),
    }
    fill, bg, dark, badge_color = status_meta.get(
        status, ("#98A2B3", "#F9FAFB", "#667085", "gray")
    )

    # Fetch devices for rack unit diagram
    devices_resp = api.get_rack_devices(dc_id or "", name or "")
    devices = devices_resp.get("devices", [])

    return html.Div(
        children=[
            # ── Status color bar at top
            html.Div(style={
                "height": "4px",
                "background": f"linear-gradient(90deg, {fill}, {fill}88)",
                "borderRadius": "12px 12px 0 0",
                "margin": "-16px -16px 16px -16px",
            }),

            # ── Rack identity header
            html.Div(
                style={"display": "flex", "justifyContent": "space-between",
                       "alignItems": "flex-start", "marginBottom": "14px"},
                children=[
                    html.Div(
                        style={"display": "flex", "gap": "12px", "alignItems": "center"},
                        children=[
                            html.Div(
                                style={
                                    "width": "40px", "height": "40px",
                                    "borderRadius": "10px",
                                    "background": bg,
                                    "border": f"1.5px solid {fill}44",
                                    "display": "flex", "alignItems": "center",
                                    "justifyContent": "center", "flexShrink": "0",
                                },
                                children=[DashIconify(
                                    icon="solar:server-square-bold-duotone",
                                    width=22, color=fill,
                                )],
                            ),
                            html.Div(children=[
                                dmc.Text(name, fw=700, size="md", c="#101828",
                                         style={"lineHeight": "1.3"}),
                                dmc.Text(hall, size="xs", c="#667085", fw=500),
                            ]),
                        ],
                    ),
                    dmc.Badge(status.title(), color=badge_color,
                              variant="light", size="sm"),
                ],
            ),

            # ── Quick stats row
            dmc.SimpleGrid(cols=2, spacing="sm", mb="md", children=[
                html.Div(
                    style={"background": "#F9FAFB", "border": "1px solid #EAECF0",
                           "borderRadius": "10px", "padding": "10px 12px"},
                    children=[
                        dmc.Group(gap=5, align="center", mb=2, children=[
                            DashIconify(icon="solar:ruler-bold-duotone",
                                        width=13, color="#667085"),
                            dmc.Text("U Height", size="xs", c="#667085", fw=600),
                        ]),
                        dmc.Text(f"{u_height}U", fw=800, size="lg", c="#101828"),
                    ],
                ),
                html.Div(
                    style={"background": "#F9FAFB", "border": "1px solid #EAECF0",
                           "borderRadius": "10px", "padding": "10px 12px"},
                    children=[
                        dmc.Group(gap=5, align="center", mb=2, children=[
                            DashIconify(icon="solar:bolt-circle-bold-duotone",
                                        width=13, color="#667085"),
                            dmc.Text("Power", size="xs", c="#667085", fw=600),
                        ]),
                        dmc.Text(str(power or "—"), fw=800, size="lg", c="#101828"),
                    ],
                ),
            ]),

            # ── Rack unit diagram
            _build_rack_unit_diagram(name, u_height or 47, devices, fill, dark),
        ],
    )


@app.callback(
    dash.Output("global-detail-panel", "children", allow_duplicate=True),
    dash.Output("global-map-graph", "focusRegion", allow_duplicate=True),
    dash.Input("global-map-reset-btn", "n_clicks"),
    prevent_initial_call=True,
)
def reset_global_detail(n_clicks):
    if not n_clicks:
        return dash.no_update, dash.no_update
    return [], {"lat": 38.0, "lng": 30.0, "zoom": 3}




@app.callback(
    dash.Output("selected-region-store", "data"),
    dash.Input({"type": "region-nav", "region": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def update_region_store(n_clicks_list):
    import time as _time
    import json
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    triggered = ctx.triggered[0]
    if not triggered.get("value"):
        return dash.no_update
    prop_id = json.loads(triggered["prop_id"].rsplit(".", 1)[0])
    region = prop_id.get("region", "")
    from src.pages.global_view import REGION_ZOOM_TARGETS
    target = REGION_ZOOM_TARGETS.get(region, {})
    if not target:
        return dash.no_update
    return {
        "region": region,
        "lon": target["lon"],
        "lat": target["lat"],
        "scale": target["scale"],
        "ts": _time.time(),
    }




@app.callback(
    dash.Output("global-map-graph", "focusRegion"),
    dash.Input("selected-region-store", "data"),
    prevent_initial_call=True,
)
def update_globe_camera(region):
    if not region:
        return dash.no_update
    lat = region.get("lat")
    lng = region.get("lon")
    scale = region.get("scale", 6.0)
    # Istanbul (scale=40): tight zoom to show all Istanbul DCs
    # Ankara/Izmir (scale=15): moderate zoom to show the city
    # International (scale<10): continent-level zoom
    if scale >= 35:
        zoom = 10
    elif scale >= 10:
        zoom = 8
    else:
        zoom = 5
    if lat is not None and lng is not None:
        return {"lat": float(lat), "lng": float(lng), "zoom": zoom}
    return dash.no_update


@app.callback(
    dash.Output("global-detail-panel", "children", allow_duplicate=True),
    dash.Input("selected-region-store", "data"),
    dash.State("app-time-range", "data"),
    prevent_initial_call=True,
)
def update_global_detail_from_menu(store_data, time_range):
    if not store_data or not store_data.get("region"):
        return dash.no_update
    region = store_data["region"]
    tr = time_range or default_time_range()
    from src.pages.global_view import build_region_detail_panel
    return build_region_detail_panel(region, tr)


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
            dc_view._kpi("Total Devices", f"{device_count:,}", _DC_ICONS["total_devices"], color="indigo"),
            dc_view._kpi("Active Ports", f"{active_ports:,}", _DC_ICONS["active_ports"], color="indigo"),
            dc_view._kpi("Total Ports", f"{total_ports:,}", _DC_ICONS["total_ports"], color="indigo"),
            dc_view._kpi("Port Availability", f"{port_availability_pct:.1f}%", _DC_ICONS["port_availability"], color="indigo"),
        ],
    )

    donut_active = create_premium_gauge_chart(port_availability_pct, "Port Availability", color="#FFB547")
    donut_util = create_premium_gauge_chart(overall_util_pct, "Port Utilization", color="#05CD99")
    donut_icmp = create_premium_gauge_chart(icmp_availability_pct, "ICMP Availability", color="#4318FF")

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

    donut_total = create_premium_gauge_chart(100.0, f"Total {smart_storage(total_gb)}", color="#FFB547")
    donut_used = create_premium_gauge_chart(used_pct, "Used Capacity", color="#4318FF")
    donut_free = create_premium_gauge_chart(free_pct, "Free Capacity", color="#05CD99")

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
