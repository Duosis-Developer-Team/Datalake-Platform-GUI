"""
Backup job statistics section: layout + callbacks.

Built once per vendor (zerto/veeam/netbackup) and appended to each backup
sub-tab panel in backup_panel.py. Callbacks live here too — they listen to
the isolated `backup-time-range` store, the per-vendor granularity selector,
and the per-vendor group-by selector. They read pathname only as State to
derive the DC id, so they never depend on `app-time-range`.
"""
from __future__ import annotations

from typing import Any

import dash
from dash import Input, Output, State, callback, dcc, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objects as go

from src.services import api_client as api


VENDORS = ("zerto", "veeam", "netbackup")

# Stacked bar palette — keeps status colours consistent across vendors.
_STATUS_COLORS = {
    "success": "#12B886",
    "failed": "#FA5252",
    "warning": "#FAB005",
    "running": "#4DABF7",
    "other": "#ADB5BD",
}


def _api_wrapper(vendor: str):
    if vendor == "zerto":
        return api.get_dc_zerto_jobs
    if vendor == "veeam":
        return api.get_dc_veeam_jobs
    if vendor == "netbackup":
        return api.get_dc_netbackup_jobs
    raise ValueError(f"Unknown vendor: {vendor}")


def _vendor_label(vendor: str) -> str:
    return {"zerto": "Zerto", "veeam": "Veeam", "netbackup": "NetBackup"}.get(vendor, vendor)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def _kpi(title: str, value: str, icon: str, color: str) -> dmc.Paper:
    return dmc.Paper(
        className="nexus-card dc-kpi-card",
        shadow="sm",
        radius="md",
        withBorder=False,
        style={"padding": "12px 14px", "height": "100%", "boxSizing": "border-box"},
        children=dmc.Group(
            gap="sm",
            align="center",
            children=[
                dmc.ThemeIcon(
                    size="lg",
                    radius="xl",
                    variant="light",
                    color=color,
                    children=DashIconify(icon=icon, width=20),
                ),
                html.Div(
                    children=[
                        html.Div(title, style={"fontSize": "0.7rem", "color": "#A3AED0", "letterSpacing": "0.04em", "textTransform": "uppercase"}),
                        html.Div(value, style={"fontSize": "1.15rem", "fontWeight": 600, "color": "#2B3674"}),
                    ]
                ),
            ],
        ),
    )


def _empty_kpis() -> list:
    return [
        _kpi("Total Jobs", "—", "solar:layers-bold-duotone", "indigo"),
        _kpi("Success Rate", "—", "solar:shield-check-bold-duotone", "teal"),
        _kpi("Avg / Period", "—", "solar:chart-bold-duotone", "blue"),
        _kpi("Failed", "—", "solar:close-circle-bold-duotone", "red"),
    ]


def _empty_figure(message: str = "Loading…") -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        height=320,
        margin={"l": 40, "r": 16, "t": 16, "b": 40},
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis={"showgrid": False},
        yaxis={"gridcolor": "#F1F3F5"},
        annotations=[
            {
                "text": message,
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"color": "#A3AED0", "size": 13},
            }
        ],
    )
    return fig


def build_job_stats_section(vendor: str) -> html.Div:
    """
    Vendor (zerto|veeam|netbackup) için Job Statistics bölümü.

    Component ID'leri vendor-spesifik; her panel kendi state'ini tutar.
    """
    if vendor not in VENDORS:
        raise ValueError(f"Unknown vendor: {vendor}")
    label = _vendor_label(vendor)

    return html.Div(
        style={"marginTop": "20px"},
        children=[
            html.Div(
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "marginBottom": "12px",
                    "flexWrap": "wrap",
                    "gap": "12px",
                },
                children=[
                    html.Div(
                        children=[
                            html.H4(
                                f"{label} Job Statistics",
                                style={"margin": 0, "fontSize": "0.95rem", "color": "#2B3674"},
                            ),
                            html.Div(
                                style={"display": "flex", "alignItems": "center", "gap": "8px", "marginTop": "2px"},
                                children=[
                                    html.P(
                                        "Backup için ekstra zaman aralığı kullanılır.",
                                        style={"margin": 0, "fontSize": "0.75rem", "color": "#A3AED0"},
                                    ),
                                    html.Span(
                                        id=f"backup-jobs-{vendor}-asof",
                                        style={"fontSize": "0.72rem", "color": "#A3AED0", "fontStyle": "italic"},
                                        children="",
                                    ),
                                ],
                            ),
                        ]
                    ),
                    dmc.Group(
                        gap="md",
                        children=[
                            dmc.SegmentedControl(
                                id=f"backup-jobs-{vendor}-granularity",
                                value="day",
                                data=[
                                    {"label": "Daily", "value": "day"},
                                    {"label": "Weekly", "value": "week"},
                                    {"label": "Monthly", "value": "month"},
                                ],
                                size="xs",
                            ),
                            dmc.Select(
                                id=f"backup-jobs-{vendor}-groupby",
                                value="status",
                                data=[
                                    {"label": "Status", "value": "status"},
                                    {"label": "Job Type", "value": "job_type"},
                                    {"label": "Policy Type", "value": "policy_type"},
                                ],
                                size="xs",
                                allowDeselect=False,
                                style={"width": "150px"},
                            ),
                            dmc.Tooltip(
                                label="Cache'i yenile (canlı SQL)",
                                position="top",
                                withArrow=True,
                                children=dmc.ActionIcon(
                                    id=f"backup-jobs-{vendor}-refresh",
                                    variant="light",
                                    color="indigo",
                                    size="lg",
                                    children=DashIconify(icon="solar:refresh-bold-duotone", width=18),
                                ),
                            ),
                        ],
                    ),
                ],
            ),
            dcc.Loading(
                id=f"backup-jobs-{vendor}-loading",
                type="circle",
                color="#4318FF",
                delay_show=200,
                overlay_style={
                    "visibility": "visible",
                    "backgroundColor": "rgba(244, 247, 254, 0.65)",
                    "borderRadius": "12px",
                },
                children=[
                    html.Div(
                        id=f"backup-jobs-{vendor}-kpis",
                        style={
                            "display": "grid",
                            "gridTemplateColumns": "repeat(4, 1fr)",
                            "gap": "12px",
                            "marginBottom": "12px",
                        },
                        children=_empty_kpis(),
                    ),
                    html.Div(
                        className="nexus-card",
                        style={"padding": "12px"},
                        children=dcc.Graph(
                            id=f"backup-jobs-{vendor}-chart",
                            figure=_empty_figure(),
                            config={"displayModeBar": False},
                        ),
                    ),
                ],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Aggregation helpers (pure, testable)
# ---------------------------------------------------------------------------


def aggregate_series_by(series: list[dict], group_by: str) -> dict[str, dict[str, int]]:
    """
    Series → {period: {group_value: count}} matrix.

    group_by ∈ {'status', 'job_type', 'policy_type'}. Missing/None values
    bucket under 'Unknown'.
    """
    out: dict[str, dict[str, int]] = {}
    for point in series or []:
        period = str(point.get("period") or "")
        group_val = point.get(group_by)
        if group_val is None or group_val == "":
            group_val = "Unknown"
        group_val = str(group_val)
        cnt = int(point.get("count", 0) or 0)
        out.setdefault(period, {})
        out[period][group_val] = out[period].get(group_val, 0) + cnt
    return out


def build_figure(payload: dict, group_by: str) -> go.Figure:
    series = (payload or {}).get("series") or []
    if not series:
        return _empty_figure("Bu zaman aralığında veri yok")

    matrix = aggregate_series_by(series, group_by)
    periods = sorted(matrix.keys())
    if not periods:
        return _empty_figure("Bu zaman aralığında veri yok")

    # Collect unique group values across all periods, in display order
    group_values: list[str] = []
    seen: set[str] = set()
    for p in periods:
        for g in matrix[p]:
            if g not in seen:
                seen.add(g)
                group_values.append(g)

    # Sort for status to keep success first; otherwise alphabetic
    if group_by == "status":
        order = ["success", "warning", "failed", "running", "other"]
        group_values.sort(key=lambda g: order.index(g) if g in order else len(order))

    fig = go.Figure()
    for gv in group_values:
        ys = [matrix[p].get(gv, 0) for p in periods]
        color = _STATUS_COLORS.get(gv.lower()) if group_by == "status" else None
        fig.add_trace(
            go.Bar(
                name=gv if group_by != "status" else gv.title(),
                x=periods,
                y=ys,
                marker_color=color,
            )
        )

    fig.update_layout(
        barmode="stack",
        height=320,
        margin={"l": 40, "r": 16, "t": 24, "b": 40},
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis={"showgrid": False, "tickfont": {"size": 11}},
        yaxis={"gridcolor": "#F1F3F5", "tickfont": {"size": 11}},
        legend={"orientation": "h", "y": -0.18},
    )
    return fig


def build_kpis(payload: dict) -> list:
    totals = (payload or {}).get("totals") or {}
    total = int(totals.get("total") or 0)
    success_rate = float(totals.get("success_rate") or 0.0)
    avg = float(totals.get("avg_per_period") or 0.0)
    failed = int(totals.get("failed") or 0)
    return [
        _kpi("Total Jobs", f"{total:,}", "solar:layers-bold-duotone", "indigo"),
        _kpi("Success Rate", f"{success_rate:.1f}%", "solar:shield-check-bold-duotone", "teal"),
        _kpi("Avg / Period", f"{avg:,.0f}", "solar:chart-bold-duotone", "blue"),
        _kpi("Failed", f"{failed:,}", "solar:close-circle-bold-duotone", "red"),
    ]


def _extract_dc_id(pathname: str | None) -> str | None:
    if not pathname:
        return None
    p = pathname.rstrip("/")
    for prefix in ("/datacenter/", "/dc-detail/"):
        if p.startswith(prefix):
            tail = p[len(prefix):].strip("/")
            return tail or None
    return None


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


def _register_callbacks() -> None:
    for vendor in VENDORS:
        _make_callback(vendor)


def format_as_of(as_of: str | None) -> str:
    """ISO timestamp → 'Son güncelleme: HH:MM' (yerel saat formatı). Boşsa '' döner."""
    if not as_of:
        return ""
    s = str(as_of).strip()
    if not s:
        return ""
    # Normalize Zulu suffix for fromisoformat compatibility.
    s_norm = s.replace("Z", "+00:00")
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(s_norm)
    except (TypeError, ValueError):
        return ""
    return f"· Son güncelleme: {dt.strftime('%H:%M')}"


def should_skip_fetch(active_main_tab: str | None, dc_id: str | None) -> bool:
    """
    Lazy-fetch koşulu: Backup & Replication main tab aktif değilse callback'i
    no-op yap. dc_id None ise (DC sayfasında değiliz) da skip et.

    Saf fonksiyon — test edilebilir.
    """
    if not dc_id:
        return True
    if (active_main_tab or "") != "backup":
        return True
    return False


def _make_callback(vendor: str) -> None:
    wrapper = _api_wrapper(vendor)

    @callback(
        Output(f"backup-jobs-{vendor}-chart", "figure"),
        Output(f"backup-jobs-{vendor}-kpis", "children"),
        Output(f"backup-jobs-{vendor}-asof", "children"),
        Input("backup-time-range", "data"),
        Input(f"backup-jobs-{vendor}-granularity", "value"),
        Input(f"backup-jobs-{vendor}-groupby", "value"),
        Input(f"backup-jobs-{vendor}-refresh", "n_clicks"),
        Input("dc-main-tabs", "value"),
        State("url", "pathname"),
        prevent_initial_call=False,
    )
    def _update(
        tr: dict | None,
        granularity: str | None,
        group_by: str | None,
        refresh_n: int | None,
        active_main_tab: str | None,
        pathname: str | None,
    ):
        dc_id = _extract_dc_id(pathname)

        # Lazy fetch: Backup tab aktif değilse hiçbir şey yapma (no_update).
        # Bu sayede DC sayfası açıldığında veya başka tab'da dolaşırken
        # arka planda Veeam/Zerto/NetBackup endpoint'leri çağrılmaz.
        if should_skip_fetch(active_main_tab, dc_id):
            return dash.no_update, dash.no_update, dash.no_update

        # If the refresh button triggered this callback, drop cache first so
        # the wrapper goes through HTTP and the backend recomputes via live SQL.
        ctx = dash.callback_context
        if ctx.triggered:
            trig_id = ctx.triggered[0]["prop_id"].split(".")[0]
            if trig_id == f"backup-jobs-{vendor}-refresh" and refresh_n:
                try:
                    api.refresh_dc_backup_jobs_cache(dc_id, vendor=vendor)
                except Exception:
                    pass  # refresh fails → continue with current cache

        gran = granularity or "day"
        gb = group_by or "status"
        try:
            payload = wrapper(dc_id, tr or None, granularity=gran)
        except Exception:
            return _empty_figure("Veri alınamadı"), _empty_kpis(), ""
        if not isinstance(payload, dict):
            return _empty_figure("Beklenmeyen yanıt"), _empty_kpis(), ""
        as_of_label = format_as_of(payload.get("as_of"))
        return build_figure(payload, gb), build_kpis(payload), as_of_label


_register_callbacks()
