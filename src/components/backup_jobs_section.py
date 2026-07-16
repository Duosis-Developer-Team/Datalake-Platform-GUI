"""
Backup job statistics section: layout + callbacks.

Built once per vendor (zerto/veeam/netbackup) and appended to each backup
sub-tab panel in backup_panel.py. NetBackup also supports category-scoped
instances (image / application) with policy-type MultiSelect filtering.
"""
from __future__ import annotations

import dash
from dash import Input, Output, State, callback, dcc, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objects as go

from src.services import api_client as api


VENDORS = ("zerto", "veeam", "netbackup")
NETBACKUP_CATEGORIES = ("image", "application")

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


def _vendor_label(vendor: str, category: str | None = None) -> str:
    base = {"zerto": "Zerto", "veeam": "Veeam", "netbackup": "NetBackup"}.get(vendor, vendor)
    if category == "image":
        return f"{base} Image"
    if category == "application":
        return f"{base} Application"
    return base


def _section_id(vendor: str, category: str | None = None) -> str:
    """Component ID suffix: vendor or vendor-category for NetBackup splits."""
    if vendor == "netbackup" and category in NETBACKUP_CATEGORIES:
        return f"netbackup-{category}"
    return vendor


def filter_series_by_category(series: list[dict] | None, category: str | None) -> list[dict]:
    """Keep series points matching ``category`` (image|application). None = all."""
    if not category:
        return list(series or [])
    return [p for p in (series or []) if (p.get("category") or "") == category]


def filter_series_by_policy_types(
    series: list[dict] | None,
    policy_types: list[str] | None,
) -> list[dict]:
    """Keep series whose policy_type is in ``policy_types``. Empty/None = all."""
    if not policy_types:
        return list(series or [])
    chosen = {str(p).strip().upper() for p in policy_types if str(p).strip()}
    if not chosen:
        return list(series or [])
    out: list[dict] = []
    for point in series or []:
        pt = str(point.get("policy_type") or "").strip().upper()
        if pt in chosen:
            out.append(point)
    return out


def apply_job_filters(
    payload: dict | None,
    *,
    category: str | None = None,
    policy_types: list[str] | None = None,
) -> dict:
    """Return a shallow-copied payload with series/totals filtered client-side."""
    base = dict(payload or {})
    series = list(base.get("series") or [])
    series = filter_series_by_category(series, category)
    series = filter_series_by_policy_types(series, policy_types)
    filtered = dict(base)
    filtered["series"] = series
    total = sum(int(p.get("count", 0) or 0) for p in series)
    success = sum(int(p["count"]) for p in series if p.get("status") == "success")
    failed = sum(int(p["count"]) for p in series if p.get("status") == "failed")
    warning = sum(int(p["count"]) for p in series if p.get("status") == "warning")
    other = max(total - success - failed - warning, 0)
    success_rate = (success / total * 100.0) if total else 0.0
    period_count = len({p.get("period") for p in series if p.get("period")})
    avg_per_period = (total / period_count) if period_count else 0.0
    filtered["totals"] = {
        "total": total,
        "success": success,
        "failed": failed,
        "warning": warning,
        "other": other,
        "success_rate": round(success_rate, 2),
        "avg_per_period": round(avg_per_period, 2),
        "period_count": period_count,
    }
    return filtered


def available_policy_types(payload: dict | None, category: str | None = None) -> list[str]:
    """Distinct policy types for MultiSelect options (optionally category-scoped)."""
    if category and isinstance((payload or {}).get("policy_types"), dict):
        pts = (payload or {}).get("policy_types", {}).get(category) or []
        if pts:
            return sorted({str(p) for p in pts if p}, key=lambda s: s.upper())
    series = filter_series_by_category((payload or {}).get("series"), category)
    return sorted(
        {str(p.get("policy_type")) for p in series if p.get("policy_type")},
        key=lambda s: s.upper(),
    )


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
                        html.Div(
                            title,
                            style={
                                "fontSize": "0.7rem",
                                "color": "#A3AED0",
                                "letterSpacing": "0.04em",
                                "textTransform": "uppercase",
                            },
                        ),
                        html.Div(
                            value,
                            style={"fontSize": "1.15rem", "fontWeight": 600, "color": "#2B3674"},
                        ),
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


def build_job_stats_section(
    vendor: str,
    *,
    category: str | None = None,
    policy_type_options: list[str] | None = None,
) -> html.Div:
    """
    Vendor (zerto|veeam|netbackup) Job Statistics section.

    For NetBackup, pass ``category='image'|'application'`` to scope IDs and
    enable policy-type MultiSelect filtering.
    """
    if vendor not in VENDORS:
        raise ValueError(f"Unknown vendor: {vendor}")
    if category is not None and category not in NETBACKUP_CATEGORIES:
        raise ValueError(f"Unknown category: {category}")
    if category and vendor != "netbackup":
        raise ValueError("category is only supported for netbackup")

    sid = _section_id(vendor, category)
    label = _vendor_label(vendor, category)
    controls: list = [
        dmc.SegmentedControl(
            id=f"backup-jobs-{sid}-granularity",
            value="day",
            data=[
                {"label": "Daily", "value": "day"},
                {"label": "Weekly", "value": "week"},
                {"label": "Monthly", "value": "month"},
            ],
            size="xs",
        ),
        dmc.Select(
            id=f"backup-jobs-{sid}-groupby",
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
    ]
    if vendor == "netbackup" and category:
        opts = policy_type_options or []
        controls.insert(
            0,
            dmc.MultiSelect(
                id=f"backup-nb-policy-selector-{category}",
                data=[{"label": p, "value": p} for p in opts],
                value=list(opts),
                clearable=True,
                searchable=True,
                nothingFoundMessage="No policy types",
                placeholder="Policy types",
                size="xs",
                style={"minWidth": "220px"},
            ),
        )
    controls.append(
        dmc.Tooltip(
            label="Cache'i yenile (canlı SQL)",
            position="top",
            withArrow=True,
            children=dmc.ActionIcon(
                id=f"backup-jobs-{sid}-refresh",
                variant="light",
                color="indigo",
                size="lg",
                children=DashIconify(icon="solar:refresh-bold-duotone", width=18),
            ),
        )
    )

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
                                style={
                                    "display": "flex",
                                    "alignItems": "center",
                                    "gap": "8px",
                                    "marginTop": "2px",
                                },
                                children=[
                                    html.P(
                                        "Backup için ekstra zaman aralığı kullanılır.",
                                        style={"margin": 0, "fontSize": "0.75rem", "color": "#A3AED0"},
                                    ),
                                    html.Span(
                                        id=f"backup-jobs-{sid}-asof",
                                        style={
                                            "fontSize": "0.72rem",
                                            "color": "#A3AED0",
                                            "fontStyle": "italic",
                                        },
                                        children="",
                                    ),
                                ],
                            ),
                        ]
                    ),
                    dmc.Group(gap="md", children=controls),
                ],
            ),
            dcc.Loading(
                id=f"backup-jobs-{sid}-loading",
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
                        id=f"backup-jobs-{sid}-kpis",
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
                            id=f"backup-jobs-{sid}-chart",
                            figure=_empty_figure(),
                            config={"displayModeBar": False},
                        ),
                    ),
                ],
            ),
        ],
    )


def aggregate_series_by(series: list[dict], group_by: str) -> dict[str, dict[str, int]]:
    """Series → {period: {group_value: count}} matrix."""
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

    group_values: list[str] = []
    seen: set[str] = set()
    for p in periods:
        for g in matrix[p]:
            if g not in seen:
                seen.add(g)
                group_values.append(g)

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
            tail = p[len(prefix) :].strip("/")
            return tail or None
    return None


def format_as_of(as_of: str | None) -> str:
    """ISO timestamp → 'Son güncelleme: HH:MM'. Empty string when missing."""
    if not as_of:
        return ""
    s = str(as_of).strip()
    if not s:
        return ""
    s_norm = s.replace("Z", "+00:00")
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(s_norm)
    except (TypeError, ValueError):
        return ""
    return f"· Son güncelleme: {dt.strftime('%H:%M')}"


def should_skip_fetch(active_main_tab: str | None, dc_id: str | None) -> bool:
    if not dc_id:
        return True
    if (active_main_tab or "") != "backup":
        return True
    return False


def _make_callback(vendor: str, category: str | None = None) -> None:
    wrapper = _api_wrapper(vendor)
    sid = _section_id(vendor, category)
    uj_sid = f"dc-{vendor}-{category}" if category else f"dc-{vendor}"

    outputs = [
        Output(f"backup-jobs-{sid}-chart", "figure"),
        Output(f"backup-jobs-{sid}-kpis", "children"),
        Output(f"backup-jobs-{sid}-asof", "children"),
    ]
    inputs = [
        Input("backup-time-range", "data"),
        Input(f"backup-jobs-{sid}-granularity", "value"),
        Input(f"backup-jobs-{sid}-groupby", "value"),
        Input(f"backup-jobs-{sid}-refresh", "n_clicks"),
        # Gate on panel mount (not raw tab click) — avoids empty Outputs race.
        Input("backup-panels-ready", "data"),
        Input(f"backup-uj-{uj_sid}-filter-status", "value"),
        Input(f"backup-uj-{uj_sid}-filter-type", "value"),
    ]
    if vendor == "netbackup" and category:
        inputs.append(Input(f"backup-nb-policy-selector-{category}", "value"))
    states = [
        State("dc-main-tabs", "value"),
        State("url", "pathname"),
    ]

    @callback(
        *outputs,
        *inputs,
        *states,
        prevent_initial_call=True,
    )
    def _update(*args, _vendor=vendor, _category=category, _sid=sid):
        if _vendor == "netbackup" and _category:
            (
                tr,
                granularity,
                group_by,
                refresh_n,
                panels_ready,
                uj_statuses,
                uj_types,
                selected_policies,
                active_main_tab,
                pathname,
            ) = args
        else:
            (
                tr,
                granularity,
                group_by,
                refresh_n,
                panels_ready,
                uj_statuses,
                uj_types,
                active_main_tab,
                pathname,
            ) = args
            selected_policies = None

        if not panels_ready:
            return dash.no_update, dash.no_update, dash.no_update

        dc_id = _extract_dc_id(pathname)
        if should_skip_fetch(active_main_tab, dc_id):
            return dash.no_update, dash.no_update, dash.no_update

        ctx = dash.callback_context
        if ctx.triggered:
            trig_id = ctx.triggered[0]["prop_id"].split(".")[0]
            if trig_id == f"backup-jobs-{_sid}-refresh" and refresh_n:
                try:
                    api.refresh_dc_backup_jobs_cache(dc_id, vendor=_vendor)
                except Exception:
                    pass

        gran = granularity or "day"
        gb = group_by or "status"
        try:
            if _vendor == "netbackup":
                payload = wrapper(
                    dc_id,
                    tr or None,
                    granularity=gran,
                    statuses=uj_statuses or None,
                    policy_types=(
                        selected_policies
                        if isinstance(selected_policies, list) and selected_policies
                        else (uj_types or None)
                    ),
                    category=_category,
                )
            else:
                payload = wrapper(
                    dc_id,
                    tr or None,
                    granularity=gran,
                    statuses=uj_statuses or None,
                    job_types=uj_types or None,
                )
        except Exception:
            return _empty_figure("Veri alınamadı"), _empty_kpis(), ""
        if not isinstance(payload, dict):
            return _empty_figure("Beklenmeyen yanıt"), _empty_kpis(), ""

        filtered = apply_job_filters(
            payload,
            category=_category,
            policy_types=selected_policies if isinstance(selected_policies, list) else None,
        )
        as_of_label = format_as_of(payload.get("as_of"))
        return build_figure(filtered, gb), build_kpis(filtered), as_of_label


def _register_callbacks() -> None:
    for vendor in VENDORS:
        if vendor == "netbackup":
            # Category-scoped panels only (image + application). Unscoped
            # NetBackup job-stats IDs are no longer rendered in DC view.
            for cat in NETBACKUP_CATEGORIES:
                _make_callback(vendor, category=cat)
        else:
            _make_callback(vendor, category=None)


_register_callbacks()
