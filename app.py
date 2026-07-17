from __future__ import annotations
import json
import math
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
from src.telemetry.faro_config import register_faro_routes
from src.telemetry.setup import instrument_flask_server, setup_telemetry_sdk

setup_telemetry_sdk()

from src.components.sidebar import create_sidebar_nav
from src.components.backup_panel import (
    build_netbackup_capacity_section,
    build_netbackup_panel,
    build_veeam_capacity_section,
    build_veeam_panel,
    build_zerto_capacity_section,
    build_zerto_panel,
)
from src.components.charts import (
    create_capacity_area_chart,
    create_horizontal_bar_chart,
    create_premium_gauge_chart,
)
from src.services import api_client as api
from src.services.db_service import WARMED_CUSTOMERS
from src.utils.time_range import (
    PRESET_CUSTOM,
    cache_time_ranges,
    default_time_range,
    preset_to_range,
    time_range_to_bounds,
)
from src.utils.format_units import pct_float, smart_storage
from src.utils.api_parallel import parallel_execute
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
register_faro_routes(server)
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
            response.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
    except Exception:
        pass
    return response


_log = logging.getLogger(__name__)
_log.info("APP_BUILD_ID=%s", APP_BUILD_ID)
from src.pages import home, datacenters, dc_view, customer_view, customers_list, query_explorer, global_view, region_drilldown, dc_detail
from src.pages import unmapped_resources
from src.pages import customer_view_callbacks  # noqa: F401 — async customer view load
from src.pages import dc_view_callbacks  # noqa: F401 — async DC view load + tab expand
from src.pages import availability_annual  # noqa: F401 — annual availability layout + callbacks
from src.pages import crm_sellable_potential
from src.pages import crm_inventory_overview
from src.pages import login as login_page_mod
from src.pages.settings import shell as settings_shell
from src.components.access_denied import build_access_denied
from src.components.virt_cluster_filter import normalize_virt_cluster_scope
from src.pages.dc_view import (
    _bps_to_gbps,
    _build_compute_tab,
    _build_hosts_panel_content,
    _hosts_panel_loader,
    _build_sellable_inline_kpi,
    _build_virt_subtab_stack,
    _build_virt_total_sellable_children,
    _sellable_card_children,
    merge_host_summary_into_compute,
    _DC_ICONS,
)
from src.pages.settings.iam import roles_callbacks  # noqa: F401 — registers role matrix callback
from src.pages.settings.iam import teams_callbacks  # noqa: F401 — IAM teams panel / members
from src.pages.settings.iam import users_callbacks  # noqa: F401 — IAM users AD import / edit
from src.pages.settings.integrations import ldap_callbacks  # noqa: F401 — LDAP test connection / mapping role sync
from src.pages.settings import crm_service_mapping  # noqa: F401 — CRM service mapping callbacks
from src.pages.settings.integrations import crm_aliases  # noqa: F401 — CRM customer aliases layout
from src.pages.settings.integrations import crm_aliases_callbacks  # noqa: F401 — CRM customer aliases callbacks
from src.pages.settings.integrations import crm_internal_aliases  # noqa: F401 — CRM internal aliases layout
from src.pages.settings.integrations import crm_internal_aliases_callbacks  # noqa: F401 — CRM internal aliases callbacks
from src.pages.settings.integrations import netbox_visualization_callbacks  # noqa: F401 — NetBox viz exclusions
from src.pages.settings.integrations import hmdl_callbacks  # noqa: F401 — HMDL sync health filters
from src.pages.settings.integrations import chatbot_logs_callbacks  # noqa: F401 — AI Assistant log viewer
from src.pages.settings import dashboard_callbacks  # noqa: F401 — Settings overview (cache refresh)
from src.pages.settings.admin_routes import to_administration_path
from src.components.chatbot import build_chatbot_shell, register_chatbot_callbacks

_default_tr = default_time_range()
_custom_st, _custom_en = time_range_to_bounds(_default_tr)
_custom_picker_start = _custom_st.strftime("%Y-%m-%dT%H:%M:%S")
_custom_picker_end = _custom_en.strftime("%Y-%m-%dT%H:%M:%S")


def _is_administration_path(pathname: str | None) -> bool:
    p = str(pathname or "")
    return p.startswith("/administration") or p.startswith("/settings")


def _warm_worker_local_customer_availability_cache() -> None:
    """Warm AuraNotify in-process cache for legacy pilot customers (resource cache is customer-api)."""
    for tr in cache_time_ranges():
        for customer_name in WARMED_CUSTOMERS:
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


def _periodic_common_warm() -> None:
    """User-independent periodic warm: keep the shared aggregate cache (overview,
    datacenters, availability SLA) hot even with no logged-in session, and pick up
    the daily time-window rollover. Runs in every worker; the shared cache dedupes
    the result."""
    from src.services.app_background_warm import warm_common

    interval = int(os.environ.get("APP_COMMON_WARM_INTERVAL_SECONDS", "240") or "240")
    while True:
        try:
            warm_common()
        except Exception as exc:  # never let the warm loop die
            _log.debug("periodic common warm failed: %s", exc)
        time_module.sleep(interval)


threading.Thread(target=_periodic_common_warm, daemon=True).start()

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
                html.Div(
                    style={
                        "overflowX": "auto",
                        "overflowY": "hidden",
                        "WebkitOverflowScrolling": "touch",
                        "scrollbarWidth": "thin",
                        "paddingBottom": "4px",
                    },
                    children=dmc.SegmentedControl(
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
                        style={"width": "max-content", "minWidth": "100%"},
                    ),
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
        # Periodic backend cache warm: keeps overview/summary hot so cold-load freezes
        # (build_overview 4 min cold vs ~20s warm) stay rare regardless of navigation.
        dcc.Interval(id="app-warm-interval", interval=300_000, n_intervals=0),
        dcc.Store(id="app-warm-tick"),
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
        dcc.Store(id="backup-time-range", data=_default_tr),
        dcc.Store(id="plot-resize-tick", data=0),
        dcc.Store(id="faro-view-tick", data=None),
        dcc.Store(id="anchor-latest-store", data=False, storage_type="local"),
        dcc.Store(id="auth-user-store", data=None),
        dcc.Store(id="auth-permissions-store", data=None),
        dcc.Store(id="chatbot-open-store", data=False, storage_type="session"),
        dcc.Store(id="chatbot-expanded-store", data=False, storage_type="session"),
        dcc.Store(id="chatbot-history-store", data=[], storage_type="session"),
        dcc.Store(id="chatbot-context-store", data={}, storage_type="session"),
        dcc.Store(id="chatbot-pending-store", data=None, storage_type="session"),
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
        build_chatbot_shell(),
    ],
)

# Chatbot widget callbacks (toggle panel, sync page context, send message).
register_chatbot_callbacks(app)


app.clientside_callback(
    """
    function(pathname) {
        if (!pathname) return window.dash_clientside.no_update;
        if (window.__datalakeFaro && typeof window.__datalakeFaro.setView === "function") {
            window.__datalakeFaro.setView(pathname);
            window.__datalakeFaro.pushEvent("view_changed", { pathname: String(pathname) }, "navigation");
        }
        return window.dash_clientside.no_update;
    }
    """,
    dash.Output("faro-view-tick", "data"),
    dash.Input("url", "pathname"),
    prevent_initial_call=False,
)


app.clientside_callback(
    """
    function(btn_clicks) {
        const triggered = dash_clientside.callback_context.triggered;
        if (!triggered || !triggered.length) return window.dash_clientside.no_update;
        const trigger = triggered[0];
        if (!trigger || !trigger.value || trigger.value < 1) return window.dash_clientside.no_update;

        const propId = trigger.prop_id || "";
        let index = "";
        try {
            const parsed = JSON.parse(propId.split(".")[0]);
            index = parsed.index || "";
        } catch(e) {
            return window.dash_clientside.no_update;
        }

        const map = {
            "home": "home_overview",
            "datacenters": "datacenters",
            "dc": "dc_detail",
            "global": "global_view",
            "qe": "query_explorer"
        };
        const prefix = map[index];
        if (!prefix) return window.dash_clientside.no_update;

        if (window.__datalakeFaro && typeof window.__datalakeFaro.pushEvent === "function") {
            window.__datalakeFaro.pushEvent("pdf_export", { page: prefix }, "ui");
        }

        const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
        if (typeof window.triggerPagePDF === "function") {
            const rootId = "main-content";
            window.triggerPagePDF(rootId, prefix + "_" + ts + ".pdf");
        }
        return window.dash_clientside.no_update;
    }
    """,
    dash.Output("export-pdf-clientside-dummy", "children"),
    dash.Input({"type": "pdf-export-btn", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)


app.clientside_callback(
    """
    function(tabValue) {
        // Plotly gauges inside inactive tabs render at 0x0 because the tab panel
        // is display:none on initial mount. When the user activates the tab,
        // Plotly does not detect the dimension change on its own — it only listens
        // for window.resize. We dispatch that event (twice, with a small delay)
        // to give the DOM a chance to settle before Plotly recalculates layout.
        if (!tabValue) return window.dash_clientside.no_update;
        if (window.__datalakeFaro && typeof window.__datalakeFaro.pushEvent === "function") {
            window.__datalakeFaro.pushEvent("dc_tab_changed", { tab: String(tabValue) }, "ui");
        }
        const fire = () => window.dispatchEvent(new Event("resize"));
        requestAnimationFrame(fire);
        setTimeout(fire, 120);
        return window.dash_clientside.no_update;
    }
    """,
    dash.Output("plot-resize-tick", "data"),
    dash.Input("dc-main-tabs", "value"),
    prevent_initial_call=True,
)


app.clientside_callback(
    """
    function(tabValue, loadedTabs) {
        if (!tabValue) return window.dash_clientside.no_update;
        const loaded = loadedTabs || [];
        if (loaded.includes(tabValue) || tabValue === 'summary') {
            return window.dash_clientside.no_update;
        }
        const root = document.getElementById('dc-tab-' + tabValue + '-root');
        if (root) {
            root.classList.add('dc-tab-loading-pending');
        }
        return window.dash_clientside.no_update;
    }
    """,
    dash.Output("export-pdf-clientside-dummy", "children", allow_duplicate=True),
    dash.Input("dc-main-tabs", "value"),
    dash.State("dc-view-loaded-tabs", "data"),
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
    try:
        from src.services.app_background_warm import set_active_route, trigger_rbac_warm
        from src.utils.time_range import default_time_range as _dtr

        set_active_route(pathname)
        if pathname and pathname != "/login":
            trigger_rbac_warm(int(uid), _dtr())
    except Exception:
        pass
    return {"id": int(uid), "username": u.get("username")}, pmap


@app.callback(
    dash.Output("app-warm-tick", "data"),
    dash.Input("app-warm-interval", "n_intervals"),
    prevent_initial_call=True,
)
def _periodic_backend_warm(n_intervals):
    """Re-warm the RBAC-scoped backend caches every ~5 min so overview/summary stay hot."""
    from flask import g, has_request_context

    if not has_request_context():
        return dash.no_update
    uid = getattr(g, "auth_user_id", None)
    if not uid:
        return dash.no_update
    try:
        from src.services.app_background_warm import trigger_rbac_warm
        from src.utils.time_range import default_time_range as _dtr

        trigger_rbac_warm(int(uid), _dtr())
    except Exception:
        pass
    return n_intervals


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


def _extract_dc_id(pathname: str | None) -> str | None:
    """`/datacenter/DC13` veya `/dc-detail/DC13` → 'DC13'. Eşleşmiyorsa None."""
    if not pathname:
        return None
    p = pathname.rstrip("/")
    for prefix in ("/datacenter/", "/dc-detail/"):
        if p.startswith(prefix):
            tail = p[len(prefix):].strip("/")
            return tail or None
    return None


@app.callback(
    dash.Output("backup-time-range", "data"),
    dash.Input("app-time-range", "data"),
)
def mirror_app_time_range_to_backup(app_tr):
    """Backup job metrics share the main time-range now — no separate selector."""
    return app_tr or dash.no_update


_BASE_PRESETS = [
    {"label": "1H", "value": "1h"},
    {"label": "1D", "value": "1d"},
    {"label": "7D", "value": "7d"},
    {"label": "30D", "value": "30d"},
    {"label": "Cstm", "value": "custom"},
]
_BACKUP_EXTRA_PRESETS = [
    {"label": "1M", "value": "1m"},
    {"label": "2M", "value": "2m"},
    {"label": "3M", "value": "3m"},
    {"label": "6M", "value": "6m"},
]


@app.callback(
    dash.Output("time-range-preset", "data"),
    dash.Output("time-range-preset", "value"),
    dash.Input("dc-main-tabs", "value"),
    dash.State("time-range-preset", "value"),
    prevent_initial_call=True,
)
def expand_periods_on_backup_tab(active_tab, current_preset):
    """On the DC Backup & Replication tab, append monthly presets (1M-6M).
    Off-tab, hide them and revert to the default 7D if a monthly preset was selected.
    """
    monthly_values = {p["value"] for p in _BACKUP_EXTRA_PRESETS}
    if active_tab == "backup":
        data = _BASE_PRESETS[:-1] + _BACKUP_EXTRA_PRESETS + _BASE_PRESETS[-1:]
        return data, dash.no_update
    fallback = "7d" if current_preset in monthly_values else dash.no_update
    return _BASE_PRESETS, fallback


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
    dash.Input("anchor-latest-store", "data"),
    dash.State("app-time-range", "data"),
)
def update_time_range_store(preset, start_dt, end_dt, anchor_latest, current):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    tid = ctx.triggered[0]["prop_id"].split(".")[0]

    def _with_anchor(tr: dict) -> dict:
        if anchor_latest:
            return {**tr, "anchor_latest": True}
        return {k: v for k, v in tr.items() if k != "anchor_latest"}

    if tid == "anchor-latest-store":
        # Toggle only — keep the existing dates/preset, just flip the flag.
        return _with_anchor(current or default_time_range())
    if tid == "time-range-preset":
        if not preset:
            return dash.no_update
        if preset == PRESET_CUSTOM:
            cur = current or default_time_range()
            st, en = time_range_to_bounds(cur)
            return _with_anchor({
                "start": st.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                "end": en.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                "preset": PRESET_CUSTOM,
            })
        return _with_anchor(preset_to_range(preset))
    if tid in ("time-range-start-datetime", "time-range-end-datetime"):
        if (current or {}).get("preset") != PRESET_CUSTOM:
            return dash.no_update
        s = start_dt or (current or {}).get("start")
        e = end_dt or (current or {}).get("end")
        s = _normalize_custom_iso(s) if isinstance(s, str) else s
        e = _normalize_custom_iso(e) if isinstance(e, str) else e
        if s and e:
            return _with_anchor({"start": s, "end": e, "preset": PRESET_CUSTOM})
        return dash.no_update
    return dash.no_update


@app.callback(
    dash.Output("url", "pathname", allow_duplicate=True),
    dash.Input("url", "pathname"),
    prevent_initial_call="initial_duplicate",
)
def redirect_legacy_settings_urls(pathname):
    if pathname and str(pathname).startswith("/settings"):
        return to_administration_path(str(pathname))
    return dash.no_update


@app.callback(
    dash.Output("main-content", "children"),
    dash.Input("url", "pathname"),
    dash.Input("app-time-range", "data"),
    dash.Input("url", "search"),
)
@trace_dash_callback("render_main_content")
def render_main_content(pathname, time_range, search):
    from flask import g, has_request_context, request as flask_request

    from src.auth.config import AUTH_DISABLED
    from src.auth.permission_service import can_view, get_visible_sections, resolve_pathname_to_page_code

    pathname = pathname or "/"
    tr = time_range or default_time_range()
    # Keep global prefetch phase-2 (rack device fan-out) paused unless user is
    # explicitly on /global-view. Otherwise it competes with datacenter routes.
    try:
        from src.services.global_view_prefetch import set_phase2_pause as _set_phase2_pause_for_route

        _set_phase2_pause(pathname != "/global-view")
    except Exception:
        pass

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
        if uid and page_code and not _is_administration_path(pathname)
        else None
    )

    if (
        page_code
        and uid
        and not _is_administration_path(pathname)
        and not can_view(int(uid), page_code)
    ):
        return build_access_denied()

    if pathname in ("/", ""):
        # Two-phase: instant skeleton shell; `_fill_overview_content` builds the real
        # content off the render path so a cold overview fetch never blanks the page.
        return home.build_overview_shell(visible_sections=vis)
    if pathname == "/datacenters":
        # Two-phase: return the skeleton shell instantly; `_fill_datacenters_content`
        # builds the real content off the render path so a cold backend never blanks the page.
        return datacenters.build_datacenters_shell(visible_sections=vis)
    if pathname and pathname.startswith("/datacenter/"):
        dc_id = pathname.replace("/datacenter/", "").strip("/")
        try:
            from src.services.app_background_warm import set_active_route

            set_active_route(pathname)
        except Exception:
            pass
        return dc_view.build_dc_view_layout_shell(dc_id, tr, visible_sections=vis)
    if pathname == "/global-view":
        return global_view.build_global_view(tr, visible_sections=vis)
    if pathname == "/availability-annual":
        return availability_annual.build_availability_annual_layout(visible_sections=vis)
    if pathname == "/customers":
        return customers_list.build_customers_list_shell(visible_sections=vis)
    if pathname == "/unmapped-resources":
        return unmapped_resources.build_layout(tr, visible_sections=vis)
    if pathname == "/customer-view":
        # Two-phase: static skeleton in page-root; load_customer_view_data is the sole filler.
        cust_params = parse_qs((search or "").lstrip("?"))
        chosen_customer = (cust_params.get("customer", [""])[0] or "").strip()
        return customer_view.build_customer_layout_shell(
            visible_sections=vis,
            selected_customer=chosen_customer,
            time_range=tr,
        )
    if pathname == "/query-explorer":
        return query_explorer.layout(visible_sections=vis)
    if pathname == "/crm/sellable-potential":
        return crm_sellable_potential.build_layout_shell(visible_sections=vis)
    if pathname == "/crm/inventory-overview":
        return crm_inventory_overview.build_layout_shell(visible_sections=vis)
    if pathname and pathname.startswith("/dc-detail/"):
        dc_id = pathname.replace("/dc-detail/", "").strip("/")
        return dc_detail.build_dc_detail(dc_id, tr, visible_sections=vis)
    if pathname == "/region-drilldown":
        params = parse_qs((search or "").lstrip("?"))
        region = params.get("region", [""])[0]
        return region_drilldown.build_region_drilldown(region, tr)
    if _is_administration_path(pathname):
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
    dash.State("url", "search"),
)
def update_s3_customer_panel(selected_vaults, time_range, search):
    params = parse_qs((search or "").lstrip("?"))
    name = (params.get("customer", [""])[0] or "").strip()
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


def _dc_id_from_pathname(pathname: str | None) -> str | None:
    if not pathname or not pathname.startswith("/datacenter/"):
        return None
    return pathname.replace("/datacenter/", "").strip("/") or None


@app.callback(
    dash.Output("virt-classic-cluster-debounce", "disabled"),
    dash.Input("virt-classic-cluster-selector", "value"),
    prevent_initial_call=True,
)
def enable_classic_cluster_debounce(_draft):
    return False


@app.callback(
    dash.Output("virt-hyperconv-cluster-debounce", "disabled"),
    dash.Input("virt-hyperconv-cluster-selector", "value"),
    prevent_initial_call=True,
)
def enable_hyperconv_cluster_debounce(_draft):
    return False


@app.callback(
    dash.Output("virt-classic-cluster-applied", "data"),
    dash.Input("virt-classic-cluster-debounce", "n_intervals"),
    dash.State("virt-classic-cluster-selector", "value"),
    dash.State("virt-classic-cluster-applied", "data"),
    prevent_initial_call=True,
)
def debounce_apply_classic_clusters(_n, draft, applied):
    if draft == applied:
        return dash.no_update
    return draft


@app.callback(
    dash.Output("virt-hyperconv-cluster-applied", "data"),
    dash.Input("virt-hyperconv-cluster-debounce", "n_intervals"),
    dash.State("virt-hyperconv-cluster-selector", "value"),
    dash.State("virt-hyperconv-cluster-applied", "data"),
    prevent_initial_call=True,
)
def debounce_apply_hyperconv_clusters(_n, draft, applied):
    if draft == applied:
        return dash.no_update
    return draft


@app.callback(
    dash.Output("virt-classic-cluster-applied", "data", allow_duplicate=True),
    dash.Output("virt-classic-cluster-debounce", "disabled", allow_duplicate=True),
    dash.Input("virt-classic-cluster-apply", "n_clicks"),
    dash.State("virt-classic-cluster-selector", "value"),
    prevent_initial_call=True,
)
def apply_classic_clusters(_n, draft):
    return draft, True


@app.callback(
    dash.Output("virt-hyperconv-cluster-applied", "data", allow_duplicate=True),
    dash.Output("virt-hyperconv-cluster-debounce", "disabled", allow_duplicate=True),
    dash.Input("virt-hyperconv-cluster-apply", "n_clicks"),
    dash.State("virt-hyperconv-cluster-selector", "value"),
    prevent_initial_call=True,
)
def apply_hyperconv_clusters(_n, draft):
    return draft, True


@app.callback(
    dash.Output("virt-classic-cluster-selector", "value"),
    dash.Output("virt-classic-cluster-debounce", "disabled", allow_duplicate=True),
    dash.Input("virt-classic-cluster-select-all", "n_clicks"),
    dash.State("virt-classic-cluster-all", "data"),
    prevent_initial_call=True,
)
def select_all_classic_clusters(_n, all_clusters):
    return list(all_clusters or []), False


@app.callback(
    dash.Output("virt-hyperconv-cluster-selector", "value"),
    dash.Output("virt-hyperconv-cluster-debounce", "disabled", allow_duplicate=True),
    dash.Input("virt-hyperconv-cluster-select-all", "n_clicks"),
    dash.State("virt-hyperconv-cluster-all", "data"),
    prevent_initial_call=True,
)
def select_all_hyperconv_clusters(_n, all_clusters):
    return list(all_clusters or []), False


@app.callback(
    dash.Output("virt-classic-cluster-selector", "value", allow_duplicate=True),
    dash.Output("virt-classic-cluster-debounce", "disabled", allow_duplicate=True),
    dash.Input("virt-classic-cluster-clear", "n_clicks"),
    prevent_initial_call=True,
)
def clear_classic_clusters(_n):
    return [], False


@app.callback(
    dash.Output("virt-hyperconv-cluster-selector", "value", allow_duplicate=True),
    dash.Output("virt-hyperconv-cluster-debounce", "disabled", allow_duplicate=True),
    dash.Input("virt-hyperconv-cluster-clear", "n_clicks"),
    prevent_initial_call=True,
)
def clear_hyperconv_clusters(_n):
    return [], False


@app.callback(
    dash.Output("classic-virt-panel", "children", allow_duplicate=True),
    dash.Output("sellable-classic-card", "children", allow_duplicate=True),
    dash.Output("hyperconv-virt-panel", "children", allow_duplicate=True),
    dash.Output("sellable-hyperconv-card", "children", allow_duplicate=True),
    dash.Input("virt-nested-tabs", "value"),
    dash.State("virt-classic-cluster-applied", "data"),
    dash.State("virt-hyperconv-cluster-applied", "data"),
    dash.State("app-time-range", "data"),
    dash.State("url", "pathname"),
    dash.State("classic-virt-panel", "children"),
    dash.State("hyperconv-virt-panel", "children"),
    prevent_initial_call=True,
)
def populate_virt_nested_tab(
    active,
    classic_applied,
    hyperconv_applied,
    time_range,
    pathname,
    classic_built,
    hyperconv_built,
):
    """Lazy-build Virt sub-tab heavy content on first tab switch (applied cluster scope)."""
    dc_id = _dc_id_from_pathname(pathname)
    if not dc_id:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    tr = time_range or default_time_range()
    no = dash.no_update
    if active == "classic" and not classic_built:
        scope = classic_applied or None
        batch = parallel_execute({
            "metrics": lambda: merge_host_summary_into_compute(
                api.get_classic_metrics_filtered(dc_id, scope, tr),
                api.get_classic_host_rows(dc_id, scope, tr),
            ),
            "card": lambda: _build_sellable_inline_kpi(
                dc_id, "virt_classic", "Klasik Mimari — Sellable Potential",
                color="blue", selected_clusters=scope, container_id="sellable-classic-card",
            ),
        })
        return (
            _build_compute_tab(batch["metrics"], "Classic Compute", color="blue"),
            _sellable_card_children(batch["card"]) or html.Div(id="sellable-classic-card"),
            no,
            no,
        )
    if active == "hyperconv" and not hyperconv_built:
        scope = hyperconv_applied or None
        batch = parallel_execute({
            "metrics": lambda: merge_host_summary_into_compute(
                api.get_hyperconv_metrics_filtered(dc_id, scope, tr),
                api.get_hyperconv_host_rows(dc_id, scope, tr),
                preserve_cluster_storage=True,
            ),
            "card": lambda: _build_sellable_inline_kpi(
                dc_id, "virt_hyperconverged", "Hyperconverged Mimari — Sellable Potential",
                color="teal", selected_clusters=scope, container_id="sellable-hyperconv-card",
            ),
        })
        return (
            no,
            no,
            _build_compute_tab(batch["metrics"], "Hyperconverged Compute", color="teal"),
            _sellable_card_children(batch["card"]) or html.Div(id="sellable-hyperconv-card"),
        )
    return no, no, no, no


def _virt_callback_trigger_id() -> str:
    ctx = dash.callback_context
    if not ctx.triggered:
        return ""
    return ctx.triggered[0]["prop_id"].split(".")[0]


@app.callback(
    dash.Output("classic-virt-panel", "children"),
    dash.Output("sellable-classic-card", "children"),
    dash.Input("virt-classic-cluster-applied", "data"),
    dash.Input("app-time-range", "data"),
    dash.State("url", "pathname"),
    dash.State("virt-classic-cluster-all", "data"),
    dash.State("classic-virt-panel", "children"),
    prevent_initial_call=True,
)
def update_classic_virt_block(applied_clusters, time_range, pathname, all_clusters, panel_children):
    dc_id = _dc_id_from_pathname(pathname)
    if not dc_id:
        return dash.no_update, dash.no_update
    tr = time_range or default_time_range()
    scope = normalize_virt_cluster_scope(applied_clusters, all_clusters)
    if (
        _virt_callback_trigger_id() == "virt-classic-cluster-applied"
        and scope is None
        and panel_children
    ):
        return dash.no_update, dash.no_update
    batch = parallel_execute({
        "metrics": lambda: merge_host_summary_into_compute(
            api.get_classic_metrics_filtered(dc_id, scope, tr),
            api.get_classic_host_rows(dc_id, scope, tr),
        ),
        "card": lambda: _build_sellable_inline_kpi(
            dc_id, "virt_classic", "Klasik Mimari — Sellable Potential",
            color="blue", selected_clusters=scope,
            container_id="sellable-classic-card",
        ),
    })
    panel = _build_compute_tab(batch["metrics"], "Classic Compute", color="blue")
    sellable = _sellable_card_children(batch["card"])
    if sellable is dash.no_update:
        sellable = html.Div(id="sellable-classic-card")
    return panel, sellable


@app.callback(
    dash.Output("hyperconv-virt-panel", "children"),
    dash.Output("sellable-hyperconv-card", "children"),
    dash.Input("virt-hyperconv-cluster-applied", "data"),
    dash.Input("app-time-range", "data"),
    dash.State("url", "pathname"),
    dash.State("virt-hyperconv-cluster-all", "data"),
    dash.State("hyperconv-virt-panel", "children"),
    prevent_initial_call=True,
)
def update_hyperconv_virt_block(applied_clusters, time_range, pathname, all_clusters, panel_children):
    dc_id = _dc_id_from_pathname(pathname)
    if not dc_id:
        return dash.no_update, dash.no_update
    tr = time_range or default_time_range()
    scope = normalize_virt_cluster_scope(applied_clusters, all_clusters)
    if (
        _virt_callback_trigger_id() == "virt-hyperconv-cluster-applied"
        and scope is None
        and panel_children
    ):
        return dash.no_update, dash.no_update
    batch = parallel_execute({
        "metrics": lambda: merge_host_summary_into_compute(
            api.get_hyperconv_metrics_filtered(dc_id, scope, tr),
            api.get_hyperconv_host_rows(dc_id, scope, tr),
            preserve_cluster_storage=True,
        ),
        "card": lambda: _build_sellable_inline_kpi(
            dc_id, "virt_hyperconverged", "Hyperconverged Mimari — Sellable Potential",
            color="teal", selected_clusters=scope,
            container_id="sellable-hyperconv-card",
        ),
    })
    panel = _build_compute_tab(batch["metrics"], "Hyperconverged Compute", color="teal")
    sellable = _sellable_card_children(batch["card"])
    if sellable is dash.no_update:
        sellable = html.Div(id="sellable-hyperconv-card")
    return panel, sellable


@app.callback(
    dash.Output("hosts-data-classic", "data"),
    dash.Output("hosts-count-classic", "children"),
    dash.Input("virt-classic-cluster-applied", "data"),
    dash.Input("app-time-range", "data"),
    dash.Input("virt-nested-tabs", "value"),
    dash.Input("hosts-collapse-classic", "in"),
    dash.State("url", "pathname"),
    dash.State("virt-classic-cluster-all", "data"),
    prevent_initial_call=True,
)
def prefetch_classic_hosts(applied_clusters, time_range, nested_tab, collapse_in, pathname, all_clusters):
    """Background host-row prefetch — updates Store + badge only (no card DOM rebuild)."""
    if nested_tab not in (None, "classic"):
        return dash.no_update, dash.no_update
    dc_id = _dc_id_from_pathname(pathname)
    if not dc_id:
        return dash.no_update, dash.no_update
    tr = time_range or default_time_range()
    scope = normalize_virt_cluster_scope(applied_clusters, all_clusters)
    trigger = _virt_callback_trigger_id()
    if trigger == "virt-classic-cluster-applied" and scope is None:
        return dash.no_update, dash.no_update
    if trigger == "hosts-collapse-classic" and not collapse_in:
        return dash.no_update, dash.no_update
    hosts_data = api.get_classic_host_rows(dc_id, scope, tr) or {}
    count = int(hosts_data.get("host_count") or 0)
    label = f"{count} host" if count else "—"
    return hosts_data, label


@app.callback(
    dash.Output("hosts-data-hyperconv", "data"),
    dash.Output("hosts-count-hyperconv", "children"),
    dash.Input("virt-hyperconv-cluster-applied", "data"),
    dash.Input("app-time-range", "data"),
    dash.Input("virt-nested-tabs", "value"),
    dash.Input("hosts-collapse-hyperconv", "in"),
    dash.State("url", "pathname"),
    dash.State("virt-hyperconv-cluster-all", "data"),
    prevent_initial_call=True,
)
def prefetch_hyperconv_hosts(applied_clusters, time_range, nested_tab, collapse_in, pathname, all_clusters):
    """Background host-row prefetch — updates Store + badge only (no card DOM rebuild)."""
    if nested_tab != "hyperconv":
        return dash.no_update, dash.no_update
    dc_id = _dc_id_from_pathname(pathname)
    if not dc_id:
        return dash.no_update, dash.no_update
    tr = time_range or default_time_range()
    scope = normalize_virt_cluster_scope(applied_clusters, all_clusters)
    trigger = _virt_callback_trigger_id()
    if trigger == "virt-hyperconv-cluster-applied" and scope is None:
        return dash.no_update, dash.no_update
    if trigger == "hosts-collapse-hyperconv" and not collapse_in:
        return dash.no_update, dash.no_update
    hosts_data = api.get_hyperconv_host_rows(dc_id, scope, tr) or {}
    count = int(hosts_data.get("host_count") or 0)
    label = f"{count} host" if count else "—"
    return hosts_data, label


@app.callback(
    dash.Output("hosts-panel-classic", "children"),
    dash.Input("hosts-collapse-classic", "in"),
    dash.Input("hosts-data-classic", "data"),
    prevent_initial_call=True,
)
def render_classic_hosts_panel(collapsed_in, hosts_data):
    """Render host cards only when the collapsible panel is open."""
    if not collapsed_in:
        return dash.no_update
    if not hosts_data:
        return _hosts_panel_loader("blue")
    return _build_hosts_panel_content(hosts_data, color="blue")


@app.callback(
    dash.Output("hosts-panel-hyperconv", "children"),
    dash.Input("hosts-collapse-hyperconv", "in"),
    dash.Input("hosts-data-hyperconv", "data"),
    prevent_initial_call=True,
)
def render_hyperconv_hosts_panel(collapsed_in, hosts_data):
    """Render host cards only when the collapsible panel is open."""
    if not collapsed_in:
        return dash.no_update
    if not hosts_data:
        return _hosts_panel_loader("teal")
    return _build_hosts_panel_content(hosts_data, color="teal")


# ---- Hosts panel toggle (DC view) --------------------------------------------


@app.callback(
    dash.Output("hosts-collapse-classic", "in"),
    dash.Output("hosts-toggle-classic", "children"),
    dash.Input("hosts-toggle-classic", "n_clicks"),
    dash.State("hosts-collapse-classic", "in"),
    prevent_initial_call=True,
)
def toggle_classic_hosts_panel(n_clicks, opened):
    now_open = not bool(opened)
    return now_open, ("Gizle" if now_open else "Göster")


@app.callback(
    dash.Output("hosts-collapse-hyperconv", "in"),
    dash.Output("hosts-toggle-hyperconv", "children"),
    dash.Input("hosts-toggle-hyperconv", "n_clicks"),
    dash.State("hosts-collapse-hyperconv", "in"),
    prevent_initial_call=True,
)
def toggle_hyperconv_hosts_panel(n_clicks, opened):
    now_open = not bool(opened)
    return now_open, ("Gizle" if now_open else "Göster")


# ---- Sellable Potential cards (DC view) --------------------------------------


@app.callback(
    dash.Output("sellable-power-card", "children"),
    dash.Input("app-time-range", "data"),
    dash.State("url", "pathname"),
)
def update_power_sellable_card(time_range, pathname):
    dc_id = _dc_id_from_pathname(pathname)
    if not dc_id:
        return dash.no_update
    card = _build_sellable_inline_kpi(
        dc_id,
        ["virt_power", "virt_power_hana"],
        "Power — Sellable Potential",
        color="grape",
        container_id="sellable-power-card",
    )
    if card is None:
        return html.Div(id="sellable-power-card")
    return card.children


@app.callback(
    dash.Output("sellable-virt-total-card", "children"),
    dash.Input("virt-classic-cluster-applied", "data"),
    dash.Input("virt-hyperconv-cluster-applied", "data"),
    dash.State("url", "pathname"),
    prevent_initial_call=True,
)
def update_virt_total_sellable_card(classic_clusters, hyperconv_clusters, pathname):
    dc_id = _dc_id_from_pathname(pathname)
    if not dc_id:
        return dash.no_update
    return _build_virt_total_sellable_children(dc_id, classic_clusters, hyperconv_clusters)


@app.callback(
    dash.Output("backup-nb-capacity-image", "children"),
    dash.Input("backup-nb-pool-selector-image", "value"),
    dash.Input("backup-time-range", "data"),
    dash.Input("backup-panels-ready", "data"),
    dash.State("url", "pathname"),
    prevent_initial_call=True,
)
def update_backup_netbackup_capacity_image(selected_pools, time_range, panels_ready, pathname):
    if not panels_ready:
        return dash.no_update
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

    return build_netbackup_capacity_section(data, selected, category="image")


@app.callback(
    dash.Output("backup-nb-capacity-application", "children"),
    dash.Input("backup-nb-pool-selector-application", "value"),
    dash.Input("backup-time-range", "data"),
    dash.Input("backup-panels-ready", "data"),
    dash.State("url", "pathname"),
    prevent_initial_call=True,
)
def update_backup_netbackup_capacity_application(selected_pools, time_range, panels_ready, pathname):
    if not panels_ready:
        return dash.no_update
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

    return build_netbackup_capacity_section(data, selected, category="application")


@app.callback(
    dash.Output("backup-zerto-capacity", "children"),
    dash.Input("backup-zerto-site-selector", "value"),
    dash.Input("backup-time-range", "data"),
    dash.Input("backup-panels-ready", "data"),
    dash.State("url", "pathname"),
    prevent_initial_call=True,
)
def update_backup_zerto_capacity(selected_sites, time_range, panels_ready, pathname):
    if not panels_ready:
        return dash.no_update
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
    return build_zerto_capacity_section(data, selected)


@app.callback(
    dash.Output("backup-veeam-capacity", "children"),
    dash.Input("backup-veeam-repo-selector", "value"),
    dash.Input("backup-time-range", "data"),
    dash.Input("backup-panels-ready", "data"),
    dash.State("url", "pathname"),
    prevent_initial_call=True,
)
def update_backup_veeam_capacity(selected_repos, time_range, panels_ready, pathname):
    if not panels_ready:
        return dash.no_update
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
    return build_veeam_capacity_section(data, selected)


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

    t0 = time_module.perf_counter()
    from src.services.global_view_prefetch import warm_dc_priority
    warm_dc_priority(dc_id)

    if dc_id == last_dc_id:
        elapsed_ms = round((time_module.perf_counter() - t0) * 1000, 1)
        _log.info("handle_globe_pin_click dc=%s same_dc=True elapsed_ms=%.1f", dc_id, elapsed_ms)
        return dash.no_update, dc_id, "building", {"dc_id": dc_id, "dc_name": site_name or dc_id}

    from src.utils.time_range import default_time_range
    tr = time_range or default_time_range()
    from src.pages.global_view import build_dc_info_card
    panel = build_dc_info_card(dc_id, tr, site_name=site_name)
    elapsed_ms = round((time_module.perf_counter() - t0) * 1000, 1)
    _log.info("handle_globe_pin_click dc=%s same_dc=False elapsed_ms=%.1f", dc_id, elapsed_ms)
    return panel, dc_id, dash.no_update, dash.no_update


@app.callback(
    dash.Output("global-3d-modal-container", "children"),
    dash.Output("global-3d-modal-container", "style"),
    dash.Input({"type": "open-3d-hologram-btn", "index": ALL}, "n_clicks"),
    dash.State("global-3d-modal-container", "style"),
    dash.State("app-time-range", "data"),
    prevent_initial_call=True,
)
def open_3d_hologram_modal(btn_clicks, current_style, time_range):
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
    from src.utils.dc_display import format_dc_display_name

    tr = time_range or default_time_range()
    info = api.get_dc_details(dc_id, tr)
    _meta = info.get("meta", {})
    dc_name = format_dc_display_name(_meta.get("name"), _meta.get("description")) or dc_id

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
    dash.Output("global-prefetch-trigger-store", "data"),
    dash.Input("global-prefetch-interval", "n_intervals"),
    dash.State("app-time-range", "data"),
    dash.State("url", "pathname"),
    prevent_initial_call=True,
)
def refresh_global_view_prefetch(n_intervals, time_range, pathname):
    from src.services.global_view_prefetch import trigger_background, set_phase2_pause
    from src.utils.time_range import default_time_range as _dtr
    # Run expensive global prefetch only while user is on Global View.
    # It was competing with datacenter-detail queries and causing long waits.
    if (pathname or "") != "/global-view":
        # Keep device prefetch paused off global-view routes.
        set_phase2_pause(True)
        _log.info(
            "refresh_global_view_prefetch skipped pathname=%s n_intervals=%s",
            pathname,
            n_intervals,
        )
        return dash.no_update
    trigger_background(time_range or _dtr())
    return n_intervals


@app.callback(
    dash.Output("globe-layer", "style"),
    dash.Output("building-reveal-layer", "style"),
    dash.Output("floor-map-layer", "style"),
    dash.Output("building-reveal-timer", "disabled"),
    dash.Output("building-reveal-timer", "n_intervals"),
    dash.Output("building-reveal-dc-name", "children"),
    dash.Input("current-view-mode", "data"),
    dash.State("selected-building-dc-store", "data"),
    dash.State("url", "pathname"),
)
def view_controller(mode, dc_store, pathname):
    from src.services.global_view_prefetch import set_phase2_pause
    on_global_view = (pathname == "/global-view")
    # Pause Phase-2 device fetches outside /global-view and while navigating
    # building/floor_map to avoid competing with detail-route rack calls.
    set_phase2_pause((not on_global_view) or (mode in {"building", "floor_map"}))

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
    dash.State("app-time-range", "data"),
    prevent_initial_call=True,
)
def advance_to_floor_map(n_intervals, dc_store, current_mode, time_range):
    if not n_intervals or current_mode != "building" or not dc_store:
        return dash.no_update, dash.no_update
    t0 = time_module.perf_counter()
    dc_id = dc_store.get("dc_id", "")
    from src.services.global_view_prefetch import is_warm
    from src.utils.time_range import default_time_range as _dtr
    from src.utils.dc_display import format_dc_display_name as _fmt_name
    tr = time_range or _dtr()
    warm = is_warm(tr)
    t_racks = time_module.perf_counter()
    racks_resp = api.get_dc_racks(dc_id)
    racks_ms = round((time_module.perf_counter() - t_racks) * 1000, 1)
    t_details = time_module.perf_counter()
    _info = api.get_dc_details(dc_id, tr)
    details_ms = round((time_module.perf_counter() - t_details) * 1000, 1)
    _meta = _info.get("meta", {})
    dc_name = _fmt_name(_meta.get("name"), _meta.get("description")) or dc_store.get("dc_name", dc_id)
    racks = racks_resp.get("racks", [])
    from src.pages.floor_map import build_floor_map_layout
    layout = build_floor_map_layout(dc_id, dc_name, racks)
    elapsed_ms = round((time_module.perf_counter() - t0) * 1000, 1)
    _log.info(
        "advance_to_floor_map dc=%s racks=%d is_warm=%s elapsed_ms=%.1f",
        dc_id, len(racks), warm, elapsed_ms,
    )
    return "floor_map", layout


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
    dash.Output("floor-map-graph", "figure"),
    dash.Input("floor-map-occupancy-interval", "n_intervals"),
    dash.State("selected-building-dc-store", "data"),
    prevent_initial_call=True,
)
def recolor_floor_map_by_fill(n_intervals, dc_store):
    """Phase 2: after the fast status-colored paint, recolor racks by U-fill."""
    dc_id = (dc_store or {}).get("dc_id", "")
    if not n_intervals or not dc_id:
        return dash.no_update
    from src.pages.floor_map import build_recolored_floor_map_figure

    fig = build_recolored_floor_map_figure(dc_id)
    return fig if fig is not None else dash.no_update


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
    t_devices = time_module.perf_counter()
    devices_resp = api.get_rack_devices(dc_id or "", name or "")
    devices_ms = round((time_module.perf_counter() - t_devices) * 1000, 1)
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

            # ── Rack unit diagram (or empty state)
            _build_rack_unit_diagram(name, u_height or 47, devices, fill, dark)
            if devices else
            html.Div(
                style={
                    "display": "flex", "flexDirection": "column",
                    "alignItems": "center", "justifyContent": "center",
                    "padding": "24px 16px", "gap": "8px",
                    "background": "#F9FAFB", "borderRadius": "10px",
                    "border": "1px solid #EAECF0",
                },
                children=[
                    DashIconify(icon="solar:server-square-linear",
                                width=28, color="#D0D5DD"),
                    dmc.Text("No devices found for this rack",
                             size="sm", c="#98A2B3", fw=500, ta="center"),
                ],
            ),
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


def _net_scope_is_device_panel(top_scope: str | None) -> bool:
    return (top_scope or "overview") in {"firewall", "load_balancer"}


def _net_scope_is_interface_panel(top_scope: str | None) -> bool:
    return (top_scope or "overview") in {"overview", "switch", "router_uplink"}


def _net_interface_table_footer(
    page: int,
    page_size: int,
    total: int,
    row_count: int,
    *,
    interface_scope: str | None = None,
    billing_items: list[dict] | None = None,
    billing_meta: dict | None = None,
) -> str:
    from src.utils.format_units import format_compact_money_tl

    if total <= 0:
        return "No interfaces in scope"
    start = (page - 1) * page_size + 1
    end = min(page * page_size, total)
    if row_count == 0:
        base = f"No matches — {total:,} interfaces in scope"
    else:
        base = f"Showing {start:,}–{end:,} of {total:,} interfaces"
    if interface_scope != "backbone":
        return base
    if billing_meta and not billing_meta.get("has_price"):
        return f"{base} — CRM unit price unavailable"
    page_cost = sum(float(it.get("estimated_cost_tl") or 0) for it in (billing_items or []))
    if page_cost > 0:
        return f"{base} — Page est. cost: {format_compact_money_tl(page_cost)}"
    return base


def _net_interface_table_page_count(total: int, page_size: int) -> int:
    if total <= 0:
        return 1
    return max(1, math.ceil(total / page_size))


def _net_interface_table_triggered_id() -> str | None:
    ctx = dash.callback_context
    try:
        triggered_id = getattr(ctx, "triggered_id", None)
    except dash.exceptions.MissingCallbackContextException:
        return None
    if triggered_id is None and ctx.triggered:
        triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    return triggered_id


def _net_export_interfaces_csv(items: list[dict], *, interface_scope: str | None = None) -> str:
    import csv
    import io

    fields = [
        "host",
        "interface_name",
        "interface_alias",
        "p95_rx_gbps",
        "p95_tx_gbps",
        "p95_total_gbps",
        "speed_gbps",
        "utilization_pct",
    ]
    include_billing = interface_scope == "backbone"
    if include_billing:
        fields.extend(["p95_billable_mbit", "unit_price_tl_per_mbit", "estimated_cost_tl"])
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for it in items or []:
        speed_gbps = (float(it.get("speed_bps") or 0) / 1e9) if it.get("speed_bps") is not None else 0.0
        rx_gbps = (float(it.get("p95_rx_bps") or 0) / 1e9) if it.get("p95_rx_bps") is not None else 0.0
        tx_gbps = (float(it.get("p95_tx_bps") or 0) / 1e9) if it.get("p95_tx_bps") is not None else 0.0
        total_gbps = (float(it.get("p95_total_bps") or 0) / 1e9) if it.get("p95_total_bps") is not None else 0.0
        row = {
            "host": it.get("host") or "",
            "interface_name": it.get("interface_name") or "",
            "interface_alias": it.get("interface_alias") or "",
            "p95_rx_gbps": round(rx_gbps, 3),
            "p95_tx_gbps": round(tx_gbps, 3),
            "p95_total_gbps": round(total_gbps, 3),
            "speed_gbps": round(speed_gbps, 3),
            "utilization_pct": round(float(it.get("utilization_pct") or 0), 2),
        }
        if include_billing:
            mbit_val = it.get("p95_billable_mbit")
            if mbit_val is None:
                mbit_val = float(it.get("p95_total_bps") or 0) / 1_000_000
            unit_val = it.get("unit_price_tl_per_mbit")
            cost_val = it.get("estimated_cost_tl")
            row["p95_billable_mbit"] = f"{float(mbit_val):.6f}" if mbit_val is not None else ""
            row["unit_price_tl_per_mbit"] = f"{float(unit_val):.4f}" if unit_val is not None else ""
            row["estimated_cost_tl"] = f"{float(cost_val):.2f}" if cost_val is not None else ""
        writer.writerow(row)
    return buf.getvalue()


@app.callback(
    dash.Output("net-filters-store", "data"),
    dash.Input("net-scope-tabs", "value"),
    dash.Input("net-switch-role-segment", "value"),
    dash.State("url", "pathname"),
    dash.State("app-time-range", "data"),
)
def refresh_net_filters_store(top_scope, switch_role, pathname, time_range):
    if not pathname or not pathname.startswith("/datacenter/"):
        return dash.no_update
    if _net_scope_is_device_panel(top_scope):
        return dash.no_update
    dc_id = pathname.replace("/datacenter/", "").strip("/")
    tr = time_range or default_time_range()
    interface_scope = dc_view.resolve_network_interface_scope(top_scope, switch_role)
    return api.get_dc_network_filters(dc_id, tr, interface_scope=interface_scope)


@app.callback(
    dash.Output("net-switch-role-wrap", "style"),
    dash.Input("net-scope-tabs", "value"),
)
def toggle_switch_role_segment(top_scope):
    if (top_scope or "overview") == "switch":
        return {"display": "block", "marginTop": "12px"}
    return {"display": "none"}


@app.callback(
    dash.Output("net-manufacturer-selector", "data"),
    dash.Output("net-manufacturer-selector", "value"),
    dash.Output("net-device-selector", "data"),
    dash.Output("net-device-selector", "value"),
    dash.Input("net-manufacturer-selector", "value"),
    dash.Input("net-filters-store", "data"),
)
def update_net_selectors(manufacturer, net_filters):
    """Manufacturer -> device cascade (scope-aware filters from store)."""
    net_filters = net_filters or {}
    devices_by_manu = net_filters.get("devices_by_manufacturer") or {}
    if not devices_by_manu:
        devices_by_manu_role = net_filters.get("devices_by_manufacturer_role") or {}
        for manu, roles_map in devices_by_manu_role.items():
            devs: set[str] = set()
            for dev_list in (roles_map or {}).values():
                devs.update(dev_list or [])
            devices_by_manu[manu] = sorted(devs)

    manufacturers = net_filters.get("manufacturers") or []
    manu_data = [{"label": m, "value": m} for m in manufacturers]

    if manufacturer:
        devices = sorted(devices_by_manu.get(manufacturer) or [])
    else:
        devices = sorted({d for devs in devices_by_manu.values() for d in (devs or [])})

    device_data = [{"label": d, "value": d} for d in devices]
    ctx = dash.callback_context
    triggered_id = getattr(ctx, "triggered_id", None)
    if triggered_id is None and ctx.triggered:
        triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if triggered_id == "net-filters-store":
        return manu_data, None, device_data, None
    return manu_data, dash.no_update, device_data, None


@app.callback(
    dash.Output("net-scope-subtitle", "children"),
    dash.Input("net-scope-tabs", "value"),
    dash.Input("net-switch-role-segment", "value"),
)
def update_net_scope_subtitle(top_scope, switch_role):
    return dc_view._network_scope_subtitle(top_scope, switch_role)


@app.callback(
    dash.Output("net-page-interface", "style"),
    dash.Output("net-page-firewall", "style"),
    dash.Output("net-page-load-balancer", "style"),
    dash.Output("net-donut-grid-wrap", "style"),
    dash.Output("net-single-gauge-wrap", "style"),
    dash.Output("net-export-btn-wrap", "style"),
    dash.Output("net-preview-collapse-wrap", "style"),
    dash.Input("net-scope-tabs", "value"),
    dash.Input("net-switch-role-segment", "value"),
)
def update_net_page_visibility(top_scope, switch_role):
    top_scope = top_scope or "overview"
    flags = dc_view._network_page_flags(top_scope, switch_role)
    block = {"display": "block"}
    none = {"display": "none"}
    return (
        block if flags["is_interface_page"] else none,
        block if top_scope == "firewall" else none,
        block if top_scope == "load_balancer" else none,
        block if flags["show_donut_grid"] else none,
        block if flags["show_single_gauge"] else none,
        block if flags["show_export"] else none,
        block if flags["show_preview_collapse"] else none,
    )


@app.callback(
    dash.Output("net-fw-kpi-container", "children"),
    dash.Output("net-firewall-table", "data"),
    dash.Input("net-scope-tabs", "value"),
    dash.State("url", "pathname"),
    dash.State("app-time-range", "data"),
)
def update_net_firewall_panel(top_scope, pathname, time_range):
    if (top_scope or "overview") != "firewall":
        return dash.no_update, dash.no_update
    if not pathname or not pathname.startswith("/datacenter/"):
        return dash.no_update, dash.no_update
    dc_id = pathname.replace("/datacenter/", "").strip("/")
    tr = time_range or default_time_range()
    fw_data = api.get_dc_network_firewall_summary(dc_id, tr)
    device_count, total_sessions, total_intrusions, ha_pairs = dc_view._firewall_aggregate_kpis(fw_data)
    kpis = dmc.SimpleGrid(
        cols=4,
        spacing="lg",
        children=[
            dc_view._kpi("Firewall Devices", f"{device_count:,}", _DC_ICONS["total_devices"], color="indigo"),
            dc_view._kpi("Active Sessions", f"{total_sessions:,}", _DC_ICONS["active_ports"], color="indigo"),
            dc_view._kpi("Intrusions", f"{total_intrusions:,}", _DC_ICONS["port_availability"], color="indigo"),
            dc_view._kpi("HA Devices", f"{ha_pairs:,}", _DC_ICONS["total_ports"], color="indigo"),
        ],
    )
    devices = (fw_data or {}).get("devices") or []
    rows = [
        {
            "host": d.get("host") or "",
            "device_name": d.get("device_name") or "",
            "manufacturer_name": d.get("manufacturer_name") or "",
            "cpu_utilization_pct": round(float(d.get("cpu_utilization_pct") or 0), 2),
            "memory_utilization_pct": round(float(d.get("memory_utilization_pct") or 0), 2),
            "active_sessions": int(d.get("active_sessions") or 0),
            "intrusions_detected": int(d.get("intrusions_detected") or 0),
            "intrusions_blocked": int(d.get("intrusions_blocked") or 0),
            "ha_mode": d.get("ha_mode") or "",
            "ha_cluster_name": d.get("ha_cluster_name") or "",
            "session_setup_rate": round(float(d.get("session_setup_rate") or 0), 2),
            "icmp_status": d.get("icmp_status") if d.get("icmp_status") is not None else "",
            "icmp_loss_pct": round(float(d.get("icmp_loss_pct") or 0), 2),
        }
        for d in devices
    ]
    return kpis, rows


@app.callback(
    dash.Output("net-top-preview-collapse", "in"),
    dash.Input("net-top-preview-toggle", "n_clicks"),
    dash.State("net-top-preview-collapse", "in"),
    prevent_initial_call=True,
)
def toggle_net_top_preview(n_clicks, opened):
    return not bool(opened)


@app.callback(
    dash.Output("net-kpi-container", "children"),
    dash.Output("net-donut-active-ports", "figure"),
    dash.Output("net-donut-utilization", "figure"),
    dash.Output("net-donut-icmp", "figure"),
    dash.Output("net-single-util-gauge", "figure"),
    dash.Output("net-top-interfaces-bar", "figure"),
    dash.Input("net-scope-tabs", "value"),
    dash.Input("net-switch-role-segment", "value"),
    dash.Input("net-manufacturer-selector", "value"),
    dash.Input("net-device-selector", "value"),
    dash.State("app-time-range", "data"),
    dash.State("url", "pathname"),
)
def update_net_kpis_and_charts(top_scope, switch_role, manufacturer, device_name, time_range, pathname):
    if not pathname or not pathname.startswith("/datacenter/"):
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    dc_id = pathname.replace("/datacenter/", "").strip("/")
    tr = time_range or default_time_range()
    top_scope = top_scope or "overview"

    if not _net_scope_is_interface_panel(top_scope):
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    interface_scope = dc_view.resolve_network_interface_scope(top_scope, switch_role)
    kpi1, kpi2, kpi3, kpi4 = dc_view._network_kpi_labels(interface_scope)

    port_summary = api.get_dc_network_port_summary(
        dc_id,
        tr,
        manufacturer=manufacturer,
        device_name=device_name,
        interface_scope=interface_scope,
    )
    percentile_data = api.get_dc_network_95th_percentile(
        dc_id,
        tr,
        top_n=10,
        manufacturer=manufacturer,
        device_name=device_name,
        interface_scope=interface_scope,
    )

    device_count = int(port_summary.get("device_count", 0) or 0)
    total_ports = int(port_summary.get("total_ports", 0) or 0)
    active_ports = int(port_summary.get("active_ports", 0) or 0)
    avg_icmp_loss_pct = float(port_summary.get("avg_icmp_loss_pct", 0) or 0)

    port_availability_pct = pct_float(active_ports, total_ports)
    icmp_availability_pct = max(0.0, min(100.0, 100.0 - avg_icmp_loss_pct))
    overall_util_pct = float(percentile_data.get("overall_port_utilization_pct", 0) or 0)

    if kpi4 == "P95 Utilization":
        kpi4_display = f"{overall_util_pct:.1f}%"
        kpi4_icon = _DC_ICONS["active_ports"]
    elif kpi4 == "ICMP Availability":
        kpi4_display = f"{icmp_availability_pct:.1f}%"
        kpi4_icon = _DC_ICONS["port_availability"]
    else:
        kpi4_display = f"{port_availability_pct:.1f}%"
        kpi4_icon = _DC_ICONS["port_availability"]

    kpis = dmc.SimpleGrid(
        cols=4,
        spacing="lg",
        children=[
            dc_view._kpi(kpi1, f"{device_count:,}", _DC_ICONS["total_devices"], color="indigo"),
            dc_view._kpi(kpi2, f"{active_ports:,}", _DC_ICONS["active_ports"], color="indigo"),
            dc_view._kpi(kpi3, f"{total_ports:,}", _DC_ICONS["total_ports"], color="indigo"),
            dc_view._kpi(kpi4, kpi4_display, kpi4_icon, color="indigo"),
        ],
    )

    donut_active = create_premium_gauge_chart(
        port_availability_pct, "", color="#FFB547", height=180
    )
    donut_util = create_premium_gauge_chart(
        overall_util_pct, "", color="#05CD99", height=180
    )
    donut_icmp = create_premium_gauge_chart(icmp_availability_pct, "", color="#4318FF", height=180)
    single_gauge = create_premium_gauge_chart(
        overall_util_pct, "", color="#05CD99", height=180
    )

    top_interfaces = percentile_data.get("top_interfaces") or []
    bar_labels = [
        (t.get("interface_alias") or t.get("interface_name") or "").strip() or "Unknown"
        for t in top_interfaces[:10]
    ]
    bar_values = [_bps_to_gbps(t.get("p95_total_bps")) for t in top_interfaces[:10]]
    bar_fig = create_horizontal_bar_chart(
        labels=bar_labels,
        values=bar_values,
        title=dc_view._network_bar_chart_title(interface_scope),
        color="#4318FF",
        height=280,
    )

    return kpis, donut_active, donut_util, donut_icmp, single_gauge, bar_fig


@app.callback(
    dash.Output("net-interface-table", "data"),
    dash.Output("net-interface-table", "columns"),
    dash.Output("net-interface-table", "page_size"),
    dash.Output("net-interface-table", "page_count"),
    dash.Output("net-interface-table", "page_current"),
    dash.Output("net-interface-table-footer", "children"),
    dash.Input("net-scope-tabs", "value"),
    dash.Input("net-switch-role-segment", "value"),
    dash.Input("net-manufacturer-selector", "value"),
    dash.Input("net-device-selector", "value"),
    dash.Input("net-interface-search", "value"),
    dash.Input("net-interface-table", "page_current"),
    dash.Input("net-interface-page-size", "value"),
    dash.State("app-time-range", "data"),
    dash.State("url", "pathname"),
)
def update_net_interface_table(
    top_scope,
    switch_role,
    manufacturer,
    device_name,
    search_value,
    page_current,
    page_size_sel,
    time_range,
    pathname,
):
    if not pathname or not pathname.startswith("/datacenter/"):
        return [], dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    top_scope = top_scope or "overview"
    if not _net_scope_is_interface_panel(top_scope):
        return [], dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    triggered_id = _net_interface_table_triggered_id()

    page_size_safe = max(1, min(200, int(page_size_sel or 50)))
    if triggered_id == "net-interface-table":
        page_current_safe = int(page_current or 0)
        page_current_out = dash.no_update
    else:
        page_current_safe = 0
        page_current_out = 0

    dc_id = pathname.replace("/datacenter/", "").strip("/")
    tr = time_range or default_time_range()
    interface_scope = dc_view.resolve_network_interface_scope(top_scope, switch_role)
    columns = dc_view._network_interface_table_columns(interface_scope)
    page_backend = page_current_safe + 1

    interface_data = api.get_dc_network_interface_table(
        dc_id,
        tr,
        page=page_backend,
        page_size=page_size_safe,
        search=search_value or "",
        manufacturer=manufacturer,
        device_name=device_name,
        interface_scope=interface_scope,
    )
    items = interface_data.get("items") or []
    total = int(interface_data.get("total") or len(items))
    rows = dc_view._interface_table_rows(items, interface_scope=interface_scope)
    footer = _net_interface_table_footer(
        page_backend,
        page_size_safe,
        total,
        len(rows),
        interface_scope=interface_scope,
        billing_items=items,
        billing_meta=interface_data.get("billing"),
    )
    page_count = _net_interface_table_page_count(total, page_size_safe)

    return rows, columns, page_size_safe, page_count, page_current_out, footer


@app.callback(
    dash.Output("net-interface-export-download", "data"),
    dash.Input("net-interface-export-btn", "n_clicks"),
    dash.State("net-scope-tabs", "value"),
    dash.State("net-switch-role-segment", "value"),
    dash.State("net-manufacturer-selector", "value"),
    dash.State("net-device-selector", "value"),
    dash.State("net-interface-search", "value"),
    dash.State("app-time-range", "data"),
    dash.State("url", "pathname"),
    prevent_initial_call=True,
)
def export_net_interfaces(n_clicks, top_scope, switch_role, manufacturer, device_name, search_value, time_range, pathname):
    if not n_clicks or not pathname or not pathname.startswith("/datacenter/"):
        return dash.no_update
    top_scope = top_scope or "overview"
    if not dc_view._network_page_flags(top_scope, switch_role).get("show_export"):
        return dash.no_update
    dc_id = pathname.replace("/datacenter/", "").strip("/")
    tr = time_range or default_time_range()
    interface_scope = dc_view.resolve_network_interface_scope(top_scope, switch_role)
    export_data = api.get_dc_network_interface_export(
        dc_id,
        tr,
        search=search_value or "",
        manufacturer=manufacturer,
        device_name=device_name,
        interface_scope=interface_scope,
    )
    csv_text = _net_export_interfaces_csv(
        export_data.get("items") or [],
        interface_scope=interface_scope,
    )
    scope_label = interface_scope or "overview"
    return dict(content=csv_text, filename=f"network_interfaces_{dc_id}_{scope_label}.csv")


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
    app.run(debug=True, dev_tools_ui=False, port=8050, use_reloader=False)
