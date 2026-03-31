# DC Detail view - Capacity Planning
# Tab hierarchy: Summary | Virtualization (Classic / Hyperconverged / Power) | Backup | Physical Inventory
import dash
from dash import html, dcc, dash_table, callback, Input, Output, State
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objects as go

from src.services import api_client as api
from src.utils.api_parallel import parallel_execute
from src.utils.time_range import default_time_range
from src.utils.format_units import (
    smart_storage,
    smart_memory,
    smart_cpu,
    pct_float,
    title_case,
    parse_storage_string,
)
from src.components.charts import (
    create_usage_donut_chart,
    create_avg_max_donut_chart,
    create_gauge_chart,
    create_dual_line_chart,
    create_sparkline_chart,
)
from src.components.charts import create_horizontal_bar_chart, create_capacity_area_chart, create_grouped_bar_chart
from src.components.header import create_detail_header
from src.components.s3_panel import build_dc_s3_panel
from src.components.backup_panel import (
    build_netbackup_panel,
    build_zerto_panel,
    build_veeam_panel,
)
from src.services import sla_service
from src.utils.export_helpers import records_to_dataframe, dash_send_dataframe


# ---------------------------------------------------------------------------
# Shared UI helpers
# ---------------------------------------------------------------------------


def _build_dc_export_rows(dc_code: str, data: dict, phys_inv: dict) -> list[dict]:
    """Flatten DC detail payload for CSV/Excel/PDF export."""
    rows: list[dict] = []
    meta = data.get("meta") or {}
    rows.append({"section": "meta", "key": "dc_code", "value": dc_code})
    for k, v in meta.items():
        rows.append({"section": "meta", "key": str(k), "value": v})
    for block_name in ("classic", "hyperconv", "power", "energy"):
        block = data.get(block_name)
        if not isinstance(block, dict):
            continue
        for k, v in block.items():
            rows.append({"section": block_name, "key": str(k), "value": v})
    br = phys_inv.get("by_role") or []
    if isinstance(br, list):
        for item in br:
            if isinstance(item, dict):
                rows.append({
                    "section": "phys_inv_by_role",
                    "key": str(item.get("role", "")),
                    "value": item.get("count", ""),
                })
    return rows


def _has_compute_data(d: dict | None) -> bool:
    """Return True if any meaningful compute metric exists for a section."""
    if not d:
        return False
    keys = ("hosts", "vms", "cpu_cap", "mem_cap", "stor_cap")
    return any(d.get(k) not in (None, 0, 0.0, "") for k in keys)


def _has_power_data(d: dict | None) -> bool:
    """Return True if any meaningful IBM Power metric exists for a section."""
    if not d:
        return False
    keys = ("hosts", "lpar_count", "cpu_used", "memory_total")
    return any(d.get(k) not in (None, 0, 0.0, "") for k in keys)


def _kpi(title: str, value, icon: str, color: str = "indigo", is_text: bool = False):
    """Standard KPI card used across all tabs."""
    return html.Div(
        className="nexus-card",
        style={"padding": "20px", "display": "flex", "alignItems": "center", "justifyContent": "space-between"},
        children=[
            html.Div([
                html.Span(title, style={"color": "#A3AED0", "fontSize": "0.9rem", "fontWeight": 500}),
                html.H3(
                    str(value),
                    style={
                        "color": "#2B3674",
                        "fontSize": "1.1rem" if is_text else "1.5rem",
                        "margin": "4px 0 0 0",
                    },
                ),
            ]),
            dmc.ThemeIcon(
                size="xl", radius="md", variant="light", color=color,
                children=DashIconify(icon=icon, width=24),
            ),
        ],
    )


def _chart_card(graph_component):
    return html.Div(
        className="nexus-card",
        style={"padding": "16px", "height": "250px", "display": "flex",
               "flexDirection": "column", "alignItems": "center",
               "justifyContent": "center", "overflow": "hidden"},
        children=graph_component,
    )


def _section_title(title: str, subtitle: str | None = None):
    return html.Div(
        style={"marginBottom": "4px"},
        children=[
            html.H3(title, style={"margin": 0, "color": "#2B3674", "fontSize": "1rem", "fontWeight": 700}),
            html.P(subtitle, style={"margin": "2px 0 0 0", "color": "#A3AED0", "fontSize": "0.8rem"}) if subtitle else None,
        ],
    )


def _capacity_metric_row(label: str, cap_val, used_val, pct: float, unit_fn=None):
    """Renders a capacity / allocated / utilisation trio inside a card row."""
    cap_str  = unit_fn(cap_val)  if unit_fn else str(cap_val)
    used_str = unit_fn(used_val) if unit_fn else str(used_val)
    return html.Div(
        style={"display": "flex", "justifyContent": "space-between", "alignItems": "center",
               "padding": "8px 0", "borderBottom": "1px solid #F4F7FE"},
        children=[
            html.Span(label, style={"color": "#2B3674", "fontWeight": 600, "fontSize": "0.85rem", "minWidth": "100px"}),
            html.Span(f"Capacity: {cap_str}", style={"color": "#A3AED0", "fontSize": "0.8rem"}),
            html.Span(f"Allocated: {used_str}", style={"color": "#4318FF", "fontSize": "0.8rem", "fontWeight": 600}),
            dmc.Badge(f"{pct:.1f}%", color="indigo" if pct < 80 else "red", variant="light", size="sm"),
        ],
    )


# ---------------------------------------------------------------------------
# Tab content builders
# ---------------------------------------------------------------------------

def _build_compute_tab(compute: dict, title: str, color: str = "indigo", is_power: bool = False):
    """Generic compute type tab panel content (Classic or Hyperconverged)."""
    hosts    = compute.get("hosts", 0)
    vms      = compute.get("vms", 0)
    cpu_cap  = compute.get("cpu_cap", 0.0)
    cpu_used = compute.get("cpu_used", 0.0)
    cpu_pct  = compute.get("cpu_pct", pct_float(cpu_used, cpu_cap))
    mem_cap  = compute.get("mem_cap", 0.0)
    mem_used = compute.get("mem_used", 0.0)
    mem_pct  = compute.get("mem_pct", pct_float(mem_used, mem_cap))
    cpu_pct_max = float(compute.get("cpu_pct_max") or 0)
    mem_pct_max = float(compute.get("mem_pct_max") or 0)
    stor_cap  = compute.get("stor_cap", 0.0)
    stor_used = compute.get("stor_used", 0.0)
    stor_pct  = pct_float(stor_used, stor_cap)

    # Convert TB to GB for display (smart_storage expects GB)
    stor_cap_gb  = stor_cap  * 1024
    stor_used_gb = stor_used * 1024

    return dmc.Stack(
        gap="lg",
        children=[
            # KPI row
            dmc.SimpleGrid(cols=4, spacing="lg", children=[
                _kpi("Total Hosts", f"{hosts:,}", "solar:server-bold-duotone", color=color),
                _kpi("Total VMs / LPARs", f"{vms:,}", "solar:laptop-bold-duotone", color=color),
                _kpi("CPU Capacity",  smart_cpu(cpu_cap),  "solar:cpu-bold-duotone",   color=color, is_text=True),
                _kpi("RAM Capacity",  smart_memory(mem_cap), "solar:ram-bold-duotone", color=color, is_text=True),
            ]),
            # Donut charts
            dmc.SimpleGrid(cols=3, spacing="lg", children=[
                _chart_card(dcc.Graph(
                    figure=(
                        create_avg_max_donut_chart(cpu_pct, cpu_pct_max, "CPU Usage (peak)")
                        if cpu_pct_max > 0
                        else create_usage_donut_chart(cpu_pct, "CPU Usage")
                    ),
                    config={"displayModeBar": False},
                    style={"height": "100%", "width": "100%"},
                )),
                _chart_card(dcc.Graph(
                    figure=(
                        create_avg_max_donut_chart(mem_pct, mem_pct_max, "RAM Usage (peak)")
                        if mem_pct_max > 0
                        else create_usage_donut_chart(mem_pct, "RAM Usage")
                    ),
                    config={"displayModeBar": False},
                    style={"height": "100%", "width": "100%"},
                )),
                _chart_card(dcc.Graph(
                    figure=create_usage_donut_chart(stor_pct, "Storage Usage"),
                    config={"displayModeBar": False},
                    style={"height": "100%", "width": "100%"},
                )),
            ]),
            # Capacity details card
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Capacity Planning", "Host-level resources vs. allocated to workloads"),
                    html.Div(style={"marginTop": "12px"}, children=[
                        _capacity_metric_row("CPU", cpu_cap, cpu_used, cpu_pct, smart_cpu),
                        _capacity_metric_row("Memory", mem_cap, mem_used, mem_pct, smart_memory),
                        _capacity_metric_row("Storage", stor_cap_gb, stor_used_gb, stor_pct, smart_storage),
                    ]),
                ],
            ),
        ],
    )


def _build_power_tab(
    power: dict,
    energy: dict,
    storage_capacity: dict | None = None,
    storage_performance: dict | None = None,
    san_bottleneck: dict | None = None,
):
    """IBM Power Mimari tab content."""
    hosts    = power.get("hosts", 0)
    vios     = power.get("vios", 0)
    lpars    = power.get("lpar_count", 0)
    mem_total    = power.get("memory_total", 0.0)
    mem_assigned = power.get("memory_assigned", 0.0)
    cpu_used     = power.get("cpu_used", 0.0)
    cpu_assigned = power.get("cpu_assigned", 1.0) or 1.0

    storage_capacity = storage_capacity or {}
    storage_performance = storage_performance or {}
    san_bottleneck = san_bottleneck or {}

    # Storage capacity aggregation (raw strings -> GB float).
    storage_systems = storage_capacity.get("systems") or []
    total_gb = sum(parse_storage_string(s.get("total_mdisk_capacity")) for s in storage_systems)
    used_gb = sum(parse_storage_string(s.get("total_used_capacity")) for s in storage_systems)
    free_gb = sum(parse_storage_string(s.get("total_free_space")) for s in storage_systems)
    storage_pct = pct_float(used_gb, total_gb)

    storage_series = storage_performance.get("series") or []
    iops_vals = [float(s.get("iops", 0) or 0) for s in storage_series]
    throughput_vals = [float(s.get("throughput_mb", 0) or 0) for s in storage_series]
    latency_vals = [float(s.get("latency_ms", 0) or 0) for s in storage_series]
    avg_iops = (sum(iops_vals) / len(iops_vals)) if iops_vals else 0.0
    avg_throughput = (sum(throughput_vals) / len(throughput_vals)) if throughput_vals else 0.0
    avg_latency = (sum(latency_vals) / len(latency_vals)) if latency_vals else 0.0

    issues = san_bottleneck.get("issues") or []
    has_san_bottleneck = bool(san_bottleneck.get("has_issue", False)) and bool(issues)

    return dmc.Stack(
        gap="lg",
        children=[
            dmc.SimpleGrid(cols=4, spacing="lg", children=[
                _kpi("IBM Hosts",   f"{hosts:,}", "solar:server-bold-duotone",        color="grape"),
                _kpi("VIOS",        f"{vios:,}",  "solar:server-square-bold-duotone",  color="grape"),
                _kpi("LPARs",       f"{lpars:,}", "solar:laptop-bold-duotone",          color="grape"),
                _kpi("Last Updated", "Live",       "solar:clock-circle-bold-duotone",   color="grape", is_text=True),
            ]),
            dmc.SimpleGrid(cols=2, spacing="lg", children=[
                _chart_card(dcc.Graph(
                    figure=create_gauge_chart(mem_assigned, mem_total or 1, "Memory Assigned", color="#05CD99"),
                    config={"displayModeBar": False},
                    style={"height": "100%", "width": "100%"},
                )),
                _chart_card(dcc.Graph(
                    figure=create_gauge_chart(cpu_used, cpu_assigned, "CPU Used", color="#4318FF"),
                    config={"displayModeBar": False},
                    style={"height": "100%", "width": "100%"},
                )),
            ]),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Capacity Planning", "IBM Power resource allocation"),
                    html.Div(style={"marginTop": "12px"}, children=[
                        _capacity_metric_row(
                            "Memory",
                            mem_total, mem_assigned,
                            pct_float(mem_assigned, mem_total),
                            smart_memory,
                        ),
                    ]),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Storage Capacity (Capacity & Cost)", "IBM-backed storage utilization"),
                    html.Div(
                        style={"marginTop": "12px"},
                        children=(
                            _chart_card(
                                dcc.Graph(
                                    figure=create_gauge_chart(used_gb, total_gb or 1, "Storage Capacity", color="#FFB547"),
                                    config={"displayModeBar": False},
                                    style={"height": "100%", "width": "100%"},
                                )
                            )
                            if storage_systems
                            else dmc.Alert("No storage capacity data available.", color="orange", radius="md")
                        ),
                    ),
                    html.Div(
                        style={"marginTop": "12px"},
                        children=(
                            html.Div(
                                children=[
                                    _capacity_metric_row(
                                        "Storage",
                                        total_gb,
                                        used_gb,
                                        storage_pct,
                                        smart_storage,
                                    ),
                                    html.Div(
                                        f"Free capacity: {smart_storage(free_gb)}",
                                        style={"color": "#A3AED0", "fontSize": "0.85rem", "fontWeight": 700, "marginTop": "8px"},
                                    ),
                                ]
                            )
                            if storage_systems
                            else None
                        ),
                    ),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Average Storage Performance", "Daily averages (IOPS / throughput / latency)"),
                    html.Div(
                        style={"marginTop": "12px"},
                        children=(
                            dmc.SimpleGrid(
                                cols=3,
                                spacing="lg",
                                children=[
                                    html.Div(
                                        style={"padding": "6px", "height": "150px"},
                                        children=[
                                            dmc.Text("IOPS", fw=700, c="#2B3674", size="sm"),
                                            dmc.Text(f"{avg_iops:,.0f} io/s", fw=900, c="#4318FF", size="lg", style={"marginTop": "4px"}),
                                            dcc.Graph(
                                                figure=create_sparkline_chart(iops_vals, "IOPS", "io/s", color="#4318FF"),
                                                config={"displayModeBar": False},
                                                style={"height": "80px"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"padding": "6px", "height": "150px"},
                                        children=[
                                            dmc.Text("Throughput", fw=700, c="#2B3674", size="sm"),
                                            dmc.Text(f"{avg_throughput:,.1f} MB/s", fw=900, c="#05CD99", size="lg", style={"marginTop": "4px"}),
                                            dcc.Graph(
                                                figure=create_sparkline_chart(throughput_vals, "Throughput", "MB/s", color="#05CD99"),
                                                config={"displayModeBar": False},
                                                style={"height": "80px"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"padding": "6px", "height": "150px"},
                                        children=[
                                            dmc.Text("Latency", fw=700, c="#2B3674", size="sm"),
                                            dmc.Text(f"{avg_latency:,.1f} ms", fw=900, c="#FFB547", size="lg", style={"marginTop": "4px"}),
                                            dcc.Graph(
                                                figure=create_sparkline_chart(latency_vals, "Latency", "ms", color="#FFB547"),
                                                config={"displayModeBar": False},
                                                style={"height": "80px"},
                                            ),
                                        ],
                                    ),
                                ],
                            )
                            if storage_series
                            else dmc.Alert("No storage performance data available.", color="orange", radius="md")
                        ),
                    ),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("SAN Bottleneck", "Storage/SAN bottleneck risk summary"),
                    html.Div(
                        style={"marginTop": "12px"},
                        children=(
                            dmc.Alert("No SAN bottleneck detected.", color="teal", radius="md", title="SAN Bottleneck")
                            if not has_san_bottleneck
                            else dmc.Alert(
                                "Storage/SAN bottleneck risk detected.",
                                color="orange",
                                radius="md",
                                title="SAN Bottleneck Risk",
                            )
                        ),
                    ),
                    html.Div(
                        style={"marginTop": "12px", "overflowX": "auto"},
                        children=(
                            dmc.Table(
                                striped=True,
                                highlightOnHover=True,
                                withTableBorder=False,
                                withColumnBorders=False,
                                verticalSpacing="sm",
                                horizontalSpacing="md",
                                children=[
                                    html.Thead(
                                        html.Tr(
                                            [
                                                html.Th(
                                                    "Port",
                                                    style={
                                                        "color": "#A3AED0",
                                                        "fontWeight": 600,
                                                        "fontSize": "0.72rem",
                                                        "textTransform": "uppercase",
                                                        "letterSpacing": "0.07em",
                                                    },
                                                ),
                                                html.Th(
                                                    "Zero Buffer Credit",
                                                    style={
                                                        "color": "#A3AED0",
                                                        "fontWeight": 600,
                                                        "fontSize": "0.72rem",
                                                        "textTransform": "uppercase",
                                                        "letterSpacing": "0.07em",
                                                        "textAlign": "right",
                                                    },
                                                ),
                                                html.Th(
                                                    "Too Many RDYs",
                                                    style={
                                                        "color": "#A3AED0",
                                                        "fontWeight": 600,
                                                        "fontSize": "0.72rem",
                                                        "textTransform": "uppercase",
                                                        "letterSpacing": "0.07em",
                                                        "textAlign": "right",
                                                    },
                                                ),
                                            ]
                                        )
                                    ),
                                    html.Tbody(
                                        [
                                            html.Tr(
                                                [
                                                    html.Td(issue.get("portname") or ""),
                                                    html.Td(dmc.Badge(str(issue.get("swfcportnotxcredits") or 0), color="orange", variant="light", size="sm")),
                                                    html.Td(dmc.Badge(str(issue.get("swfcporttoomanyrdys") or 0), color="orange", variant="light", size="sm")),
                                                ]
                                            )
                                            for issue in (issues or [])[:8]
                                        ]
                                    ),
                                ],
                            )
                            if has_san_bottleneck
                            else html.Div()
                        ),
                    ),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Energy", "Daily average over report period"),
                    dmc.SimpleGrid(cols=2, spacing="lg", style={"marginTop": "12px"}, children=[
                        _kpi("IBM Power", f"{energy.get('ibm_kw', 0):.1f} kW",  "material-symbols:bolt-outline", color="orange"),
                        _kpi("Consumption", f"{energy.get('ibm_kwh', 0):,.0f} kWh", "material-symbols:bolt-outline", color="orange"),
                    ]),
                ],
            ),
        ],
    )


def _has_san_data(switches: list[str] | None) -> bool:
    """Return True if at least one brocade switch exists for the DC."""
    return bool(switches)


def _build_san_subtab(port_usage: dict, health_alerts: list[dict], traffic_trend: list[dict]):
    """Network > SAN subtab content (executive + cost + risk oriented)."""
    port_usage = port_usage or {}
    total_ports = int(port_usage.get("total_ports", 0) or 0)
    licensed_ports = int(port_usage.get("licensed_ports", 0) or 0)
    active_ports = int(port_usage.get("active_ports", 0) or 0)
    no_link_ports = int(port_usage.get("no_link_ports", 0) or 0)
    disabled_ports = int(port_usage.get("disabled_ports", 0) or 0)

    licensed_pct = pct_float(licensed_ports, total_ports)
    active_pct = pct_float(active_ports, licensed_ports)

    # Expand delta-based health rows into (port, error_type, delta) rows.
    alerts_rows: list[tuple[str, str, str, int, str]] = []
    for item in health_alerts or []:
        switch_host = str(item.get("switch_host") or "")
        port_name = str(item.get("port_name") or "")

        crc_delta = int(item.get("crc_errors_delta", 0) or 0)
        link_failures_delta = int(item.get("link_failures_delta", 0) or 0)
        loss_of_sync_delta = int(item.get("loss_of_sync_delta", 0) or 0)
        loss_of_signal_delta = int(item.get("loss_of_signal_delta", 0) or 0)

        if crc_delta > 0:
            alerts_rows.append((switch_host, port_name, "Data Integrity Errors", crc_delta, "red"))
        if link_failures_delta > 0:
            alerts_rows.append((switch_host, port_name, "Connection Failures", link_failures_delta, "orange"))
        if loss_of_sync_delta > 0:
            alerts_rows.append((switch_host, port_name, "Signal Sync Loss", loss_of_sync_delta, "yellow"))
        if loss_of_signal_delta > 0:
            alerts_rows.append((switch_host, port_name, "Physical Signal Lost", loss_of_signal_delta, "yellow"))

    alerts_rows.sort(key=lambda x: x[3], reverse=True)

    if not alerts_rows:
        health_panel = dmc.Alert(
            "SAN Health: %100",
            color="teal",
            title="Risk",
            radius="md",
        )
    else:
        table = dmc.Table(
            striped=True,
            highlightOnHover=True,
            withTableBorder=False,
            withColumnBorders=False,
            style={"tableLayout": "fixed", "width": "100%"},
            verticalSpacing="sm",
            horizontalSpacing="md",
            children=[
                html.Thead(
                    html.Tr(
                        [
                            html.Th(
                                "Switch",
                                style={"color": "#A3AED0", "fontWeight": 600, "fontSize": "0.72rem", "textTransform": "uppercase",
                                       "letterSpacing": "0.07em", "width": "25%"},
                            ),
                            html.Th(
                                "Port",
                                style={"color": "#A3AED0", "fontWeight": 600, "fontSize": "0.72rem", "textTransform": "uppercase",
                                       "letterSpacing": "0.07em", "width": "20%"},
                            ),
                            html.Th(
                                "Error Type",
                                style={"color": "#A3AED0", "fontWeight": 600, "fontSize": "0.72rem", "textTransform": "uppercase",
                                       "letterSpacing": "0.07em", "width": "35%"},
                            ),
                            html.Th(
                                "Event Count",
                                style={"color": "#A3AED0", "fontWeight": 600, "fontSize": "0.72rem", "textTransform": "uppercase",
                                       "letterSpacing": "0.07em", "textAlign": "right", "width": "20%"},
                            ),
                        ]
                    )
                ),
                html.Tbody(
                    [
                        html.Tr(
                            [
                                html.Td(
                                    r[0],
                                    style={"width": "25%", "whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis"},
                                ),
                                html.Td(
                                    r[1],
                                    style={"width": "20%", "whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis"},
                                ),
                                html.Td(
                                    r[2],
                                    style={"width": "35%", "whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis"},
                                ),
                                html.Td(dmc.Badge(str(r[3]), color=r[4], variant="light", size="sm")),
                            ]
                        )
                        for r in alerts_rows
                    ]
                ),
            ],
        )
        health_panel = table

    # Traffic trend
    sorted_trend = sorted(traffic_trend or [], key=lambda x: x.get("ts"))
    timestamps = [r.get("ts") for r in sorted_trend if r.get("ts") is not None]
    in_vals = [r.get("in_rate", 0) for r in sorted_trend]
    out_vals = [r.get("out_rate", 0) for r in sorted_trend]

    traffic_chart = create_dual_line_chart(
        timestamps=timestamps,
        in_vals=in_vals[: len(timestamps)],
        out_vals=out_vals[: len(timestamps)],
        title="SAN Backbone Traffic Trend",
        height=260,
    )

    available_pct = pct_float(active_ports, total_ports)

    return dmc.Stack(
        gap="lg",
        children=[
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Port License Efficiency", "Pod License vs Real Usage (ROI)"),
                    dmc.SimpleGrid(
                        cols=4,
                        spacing="lg",
                        style={"marginTop": "12px"},
                        children=[
                            _kpi("Active Ports", f"{active_ports:,}", "solar:signal-bold-duotone", color="indigo"),
                            _kpi("No Link / Offline Ports", f"{no_link_ports:,}", "solar:port-bold-duotone", color="indigo"),
                            _kpi("Admin Disabled Ports", f"{disabled_ports:,}", "solar:pause-circle-bold-duotone", color="indigo"),
                            _kpi("Licensed Ports", f"{licensed_ports:,}", "solar:ticket-bold-duotone", color="indigo"),
                        ],
                    ),
                    dmc.SimpleGrid(
                        cols=3,
                        spacing="lg",
                        style={"marginTop": "18px"},
                        children=[
                            html.Div(
                                style={"width": "100%"},
                                children=[
                                    _chart_card(
                                        dcc.Graph(
                                            figure=create_usage_donut_chart(licensed_pct, "Pod License ROI", color="#4318FF"),
                                            config={"displayModeBar": False},
                                            style={"height": "100%", "width": "100%"},
                                        )
                                    ),
                                    html.P(
                                        "Coverage: Licensed ports divided by total ports.",
                                        style={"color": "#A3AED0", "fontSize": "0.72rem", "marginTop": "6px", "textAlign": "center"},
                                    ),
                                ],
                            ),
                            html.Div(
                                style={"width": "100%"},
                                children=[
                                    _chart_card(
                                        dcc.Graph(
                                            figure=create_usage_donut_chart(active_pct, "Active vs Licensed", color="#05CD99"),
                                            config={"displayModeBar": False},
                                            style={"height": "100%", "width": "100%"},
                                        )
                                    ),
                                    html.P(
                                        "Utilization: Active ports divided by licensed ports (admin-enabled + operational).",
                                        style={"color": "#A3AED0", "fontSize": "0.72rem", "marginTop": "6px", "textAlign": "center"},
                                    ),
                                ],
                            ),
                            html.Div(
                                style={"width": "100%"},
                                children=[
                                    _chart_card(
                                        dcc.Graph(
                                            figure=create_usage_donut_chart(available_pct, "Port Availability", color="#FFB547"),
                                            config={"displayModeBar": False},
                                            style={"height": "100%", "width": "100%"},
                                        )
                                    ),
                                    html.P(
                                        "Availability: Active ports divided by total ports. Remaining ports are No Link/Offline or Admin Disabled.",
                                        style={"color": "#A3AED0", "fontSize": "0.72rem", "marginTop": "6px", "textAlign": "center"},
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("SAN Health & Risk", "Recent error events are listed below"),
                    html.Div(
                        style={"marginTop": "6px"},
                        children=[
                            dmc.Text(
                                "Event Count is derived from the latest delta counters. Any value above 0 indicates a potential hardware/connection issue.",
                                c="#A3AED0",
                                size="xs",
                                fw=600,
                            ),
                        ],
                    ),
                    html.Div(style={"marginTop": "12px"}, children=[health_panel]),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Traffic Trend (Capacity Planning)", "Approach towards backbone bandwidth limits"),
                    html.Div(style={"marginTop": "12px"}, children=[_chart_card(dcc.Graph(figure=traffic_chart, config={"displayModeBar": False}))]),
                ],
            ),
        ],
    )


def _build_backup_subtab(name: str):
    """Legacy placeholder for backup sub-tabs (kept for future use if needed)."""
    return html.Div(
        style={"padding": "60px", "textAlign": "center"},
        children=[
            DashIconify(
                icon="solar:shield-check-bold-duotone",
                width=48,
                style={"color": "#A3AED0", "marginBottom": "12px"},
            ),
            html.P(
                f"{name} backup metrics",
                style={"color": "#2B3674", "fontWeight": 600},
            ),
            html.P(
                "Data will be displayed here.",
                style={"color": "#A3AED0", "fontSize": "0.85rem"},
            ),
        ],
    )


def _build_summary_tab(data: dict, tr: dict):
    """Summary tab: combined capacity planning view."""
    classic    = data.get("classic", {})
    hyperconv  = data.get("hyperconv", {})
    intel      = data.get("intel", {})
    power      = data.get("power", {})
    energy     = data.get("energy", {})

    # Combined totals
    total_hosts = (classic.get("hosts", 0) + hyperconv.get("hosts", 0) + power.get("hosts", 0))
    # intel.vms = cl_vms + nutanix_vms (cluster-level dedup: no double-count of hyperconv VMs)
    total_vms   = intel.get("vms", 0) + power.get("lpar_count", 0)

    # Total CPU capacity (GHz) across all compute types
    total_cpu_cap  = classic.get("cpu_cap", 0) + hyperconv.get("cpu_cap", 0)
    total_cpu_used = classic.get("cpu_used", 0) + hyperconv.get("cpu_used", 0)
    # Total Memory (GB)
    total_mem_cap  = classic.get("mem_cap", 0) + hyperconv.get("mem_cap", 0)
    total_mem_used = classic.get("mem_used", 0) + hyperconv.get("mem_used", 0)
    # Total Storage (TB)
    total_stor_cap  = classic.get("stor_cap", 0) + hyperconv.get("stor_cap", 0) + power.get("storage_cap_tb", 0)
    total_stor_used = classic.get("stor_used", 0) + hyperconv.get("stor_used", 0) + power.get("storage_used_tb", 0)

    cpu_pct  = pct_float(total_cpu_used, total_cpu_cap)
    mem_pct  = pct_float(total_mem_used, total_mem_cap)
    stor_pct = pct_float(total_stor_used * 1024, total_stor_cap * 1024)

    return dmc.Stack(
        gap="lg",
        children=[
            # Combined KPIs
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Combined Infrastructure", "All compute types combined"),
                    dmc.SimpleGrid(cols=4, spacing="lg", style={"marginTop": "12px"}, children=[
                        _kpi("Total Hosts", f"{total_hosts:,}", "solar:server-bold-duotone"),
                        _kpi("Total VMs / LPARs", f"{total_vms:,}", "solar:laptop-bold-duotone"),
                        _kpi("CPU Capacity",  smart_cpu(total_cpu_cap),  "solar:cpu-bold-duotone",   is_text=True),
                        _kpi("RAM Capacity",  smart_memory(total_mem_cap), "solar:ram-bold-duotone", is_text=True),
                    ]),
                ],
            ),
            # Capacity overview charts
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Resource Utilization", "Capacity vs. workload allocation (all VMware compute)"),
                    dmc.SimpleGrid(cols=3, spacing="lg", style={"marginTop": "12px"}, children=[
                        _chart_card(dcc.Graph(
                            figure=create_usage_donut_chart(cpu_pct, "CPU Usage"),
                            config={"displayModeBar": False},
                            style={"height": "100%", "width": "100%"},
                        )),
                        _chart_card(dcc.Graph(
                            figure=create_usage_donut_chart(mem_pct, "RAM Usage"),
                            config={"displayModeBar": False},
                            style={"height": "100%", "width": "100%"},
                        )),
                        _chart_card(dcc.Graph(
                            figure=create_usage_donut_chart(stor_pct, "Storage Usage"),
                            config={"displayModeBar": False},
                            style={"height": "100%", "width": "100%"},
                        )),
                    ]),
                ],
            ),
            # Detailed capacity table
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Capacity Detail", "Host capacity vs. allocated to VMs"),
                    html.Div(style={"marginTop": "12px"}, children=[
                        _capacity_metric_row("CPU (Classic)",      classic.get("cpu_cap", 0),
                                             classic.get("cpu_used", 0),
                                             classic.get("cpu_pct", pct_float(classic.get("cpu_used", 0), classic.get("cpu_cap", 1))),
                                             smart_cpu),
                        _capacity_metric_row("CPU (Hyperconv)",    hyperconv.get("cpu_cap", 0),
                                             hyperconv.get("cpu_used", 0),
                                             hyperconv.get("cpu_pct", pct_float(hyperconv.get("cpu_used", 0), hyperconv.get("cpu_cap", 1))),
                                             smart_cpu),
                        _capacity_metric_row("RAM (Classic)",      classic.get("mem_cap", 0),
                                             classic.get("mem_used", 0),
                                             classic.get("mem_pct", pct_float(classic.get("mem_used", 0), classic.get("mem_cap", 1))),
                                             smart_memory),
                        _capacity_metric_row("RAM (Hyperconv)",    hyperconv.get("mem_cap", 0),
                                             hyperconv.get("mem_used", 0),
                                             hyperconv.get("mem_pct", pct_float(hyperconv.get("mem_used", 0), hyperconv.get("mem_cap", 1))),
                                             smart_memory),
                        _capacity_metric_row("Storage (Classic)",  classic.get("stor_cap", 0) * 1024,
                                             classic.get("stor_used", 0) * 1024,
                                             pct_float(classic.get("stor_used", 0), classic.get("stor_cap", 1)),
                                             smart_storage),
                        _capacity_metric_row("Storage (Hyperconv)", hyperconv.get("stor_cap", 0) * 1024,
                                             hyperconv.get("stor_used", 0) * 1024,
                                             pct_float(hyperconv.get("stor_used", 0), hyperconv.get("stor_cap", 1)),
                                             smart_storage),
                        _capacity_metric_row("Storage (Power)",  power.get("storage_cap_tb", 0) * 1024,
                                             power.get("storage_used_tb", 0) * 1024,
                                             pct_float(power.get("storage_used_tb", 0), power.get("storage_cap_tb", 1)),
                                             smart_storage) if power.get("storage_cap_tb", 0) > 0 else None,
                    ]),
                ],
            ),
            # IBM Power summary
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Power Compute (IBM)", "IBM Power resource summary"),
                    dmc.SimpleGrid(cols=4, spacing="lg", style={"marginTop": "12px"}, children=[
                        _kpi("IBM Hosts",   f"{power.get('hosts', 0):,}",       "solar:server-bold-duotone",       color="grape"),
                        _kpi("LPARs",       f"{power.get('lpar_count', 0):,}",  "solar:laptop-bold-duotone",       color="grape"),
                        _kpi("RAM Assigned", smart_memory(power.get("memory_assigned", 0)),
                             "solar:ram-bold-duotone", color="grape", is_text=True),
                        _kpi("Storage", smart_storage(power.get("storage_cap_tb", 0) * 1024),
                             "solar:database-bold-duotone", color="grape", is_text=True) if power.get("storage_cap_tb", 0) > 0 else None,
                    ]),
                ],
            ),
            # Energy breakdown
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Energy Breakdown", "Daily average over report period"),
                    dmc.SimpleGrid(cols=3, spacing="lg", style={"marginTop": "12px"}, children=[
                        _kpi("IBM Power",  f"{energy.get('ibm_kw', 0):.1f} kW",      "material-symbols:bolt-outline", color="orange"),
                        _kpi("vCenter",    f"{energy.get('vcenter_kw', 0):.1f} kW",   "material-symbols:bolt-outline", color="orange"),
                        _kpi("Total",      f"{energy.get('total_kw', 0):.1f} kW",     "material-symbols:bolt-outline", color="orange"),
                    ]),
                    dmc.Divider(style={"margin": "12px 0"}),
                    dmc.SimpleGrid(cols=3, spacing="lg", children=[
                        _kpi("IBM kWh",    f"{energy.get('ibm_kwh', 0):,.0f} kWh",    "material-symbols:bolt-outline", color="yellow"),
                        _kpi("vCenter kWh", f"{energy.get('vcenter_kwh', 0):,.0f} kWh", "material-symbols:bolt-outline", color="yellow"),
                        _kpi("Total kWh",  f"{energy.get('total_kwh', 0):,.0f} kWh",  "material-symbols:bolt-outline", color="yellow"),
                    ]),
                ],
            ),
        ],
    )


def _build_physical_inventory_dc_tab(phys_inv: dict):
    """Physical Inventory tab: total devices, by role bar chart, by role+manufacturer bar chart."""
    total = phys_inv.get("total", 0)
    by_role = phys_inv.get("by_role", [])
    by_rm = phys_inv.get("by_role_manufacturer", [])

    # Horizontal bar: device_role_name (title-case display)
    role_labels = [title_case(r["role"]) for r in by_role]
    role_counts = [r["count"] for r in by_role]
    fig_role = go.Figure(
        data=[go.Bar(
            x=role_counts or [0],
            y=role_labels or ["No data"],
            orientation="h",
            marker_color="#4318FF",
            text=role_counts,
            textposition="outside",
            textfont=dict(size=12, color="#2B3674"),
        )]
    )
    fig_role.update_layout(
        margin=dict(l=20, r=50, t=10, b=20),
        height=280,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(showgrid=False, zeroline=False, categoryorder="total ascending"),
        font=dict(family="DM Sans, sans-serif", color="#A3AED0", size=11),
    )

    # Grouped bar: per role, manufacturers (subset by role for readability; show top roles)
    roles_for_rm = list(dict.fromkeys(r["role"] for r in by_rm))[:8]
    rm_filtered = [r for r in by_rm if r["role"] in roles_for_rm]
    if not rm_filtered:
        fig_rm = go.Figure()
        fig_rm.update_layout(
            margin=dict(l=20, r=20, t=30, b=40),
            height=300,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            annotations=[dict(text="No role/manufacturer data", x=0.5, y=0.5, showarrow=False, font=dict(size=14))],
        )
    else:
        # Pivot: x = manufacturer (per role), y = count; group by role
        role_to_manu = {}
        for r in rm_filtered:
            ro = r["role"]
            if ro not in role_to_manu:
                role_to_manu[ro] = []
            role_to_manu[ro].append((r["manufacturer"], r["count"]))
        colors = ["#4318FF", "#05CD99", "#FFB547", "#E85347", "#7551FF", "#00D9FF", "#F7B84B", "#0FBA81"]
        fig_rm = go.Figure()
        for i, (role, pairs) in enumerate(role_to_manu.items()):
            manu = [title_case(p[0]) for p in pairs]
            cnts = [p[1] for p in pairs]
            fig_rm.add_trace(go.Bar(
                name=title_case(role),
                x=manu,
                y=cnts,
                marker_color=colors[i % len(colors)],
            ))
        fig_rm.update_layout(
            barmode="group",
            margin=dict(l=20, r=20, t=30, b=80),
            height=320,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=True,
            legend=dict(orientation="h", yanchor="top", y=1.08),
            xaxis=dict(showgrid=False, zeroline=False, tickangle=-35),
            yaxis=dict(showgrid=False, zeroline=False),
            font=dict(family="DM Sans, sans-serif", color="#A3AED0", size=11),
        )

    return dmc.Stack(
        gap="lg",
        children=[
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Physical Inventory", "NetBox devices in this DC"),
                    dmc.SimpleGrid(cols=1, spacing="lg", style={"marginTop": "12px"}, children=[
                        _kpi("Total Devices", f"{total:,}", "solar:server-bold-duotone", color="indigo"),
                    ]),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Devices by Role", "Device role distribution"),
                    dcc.Graph(figure=fig_role, config={"displayModeBar": False}, style={"height": "280px"}),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Manufacturer by Role", "Per device role, manufacturer breakdown"),
                    dcc.Graph(figure=fig_rm, config={"displayModeBar": False}, style={"height": "320px"}),
                ],
            ),
        ],
    )

# ---------------------------------------------------------------------------
# Network (Zabbix) + Intel Storage (Zabbix) - Dedicated UI builders
# ---------------------------------------------------------------------------


def _bps_to_gbps(value_bps) -> float:
    """Convert bits-per-second to Gbps for display."""
    try:
        return float(value_bps or 0) / 1e9
    except (TypeError, ValueError):
        return 0.0


def _health_icon(status: str | None) -> tuple[str, str]:
    """Return (icon_name, color) based on a disk health text."""
    s = (status or "").upper()
    ok = any(k in s for k in ("OK", "HEALTHY", "UP", "NORMAL"))
    if ok:
        return "solar:check-circle-bold-duotone", "#05CD99"
    return "solar:danger-triangle-bold-duotone", "#FFB547"


def _build_network_dashboard_subtab(net_filters: dict, port_summary: dict, percentile_data: dict, interface_table: dict):
    """
    Network Dashboard subtab:
    - Hierarchical filters (Manufacturer -> Device Role -> Device)
    - KPI cards
    - Donut charts
    - Top-N (95th percentile) bar chart
    - Paginated interface bandwidth table
    """
    net_filters = net_filters or {}
    port_summary = port_summary or {}
    percentile_data = percentile_data or {}
    interface_table = interface_table or {}

    device_count = int(port_summary.get("device_count", 0) or 0)
    total_ports = int(port_summary.get("total_ports", 0) or 0)
    active_ports = int(port_summary.get("active_ports", 0) or 0)
    avg_icmp_loss_pct = float(port_summary.get("avg_icmp_loss_pct", 0) or 0)

    port_availability_pct = pct_float(active_ports, total_ports)
    icmp_availability_pct = max(0.0, min(100.0, 100.0 - avg_icmp_loss_pct))
    overall_util_pct = float(percentile_data.get("overall_port_utilization_pct", 0) or 0)

    # Build initial filter options (default selection = None => "All")
    manufacturers = net_filters.get("manufacturers") or []
    roles_by_manufacturer = net_filters.get("roles_by_manufacturer") or {}
    devices_by_manufacturer_role = net_filters.get("devices_by_manufacturer_role") or {}

    roles_all = sorted({r for roles in roles_by_manufacturer.values() for r in (roles or [])})
    devices_all = sorted(
        {
            d
            for roles_map in devices_by_manufacturer_role.values()
            for devs in roles_map.values()
            for d in (devs or [])
        }
    )

    manufacturers_data = [{"label": m, "value": m} for m in manufacturers]
    roles_data = [{"label": r, "value": r} for r in roles_all]
    devices_data = [{"label": d, "value": d} for d in devices_all]

    # KPIs (initial)
    kpis = dmc.SimpleGrid(
        cols=4,
        spacing="lg",
        children=[
            _kpi("Total Devices", f"{device_count:,}", "solar:server-bold-duotone", color="indigo"),
            _kpi("Active Ports", f"{active_ports:,}", "solar:signal-bold-duotone", color="indigo"),
            _kpi("Total Ports", f"{total_ports:,}", "solar:port-bold-duotone", color="indigo"),
            _kpi("Port Availability", f"{port_availability_pct:.1f}%", "solar:graph-bold-duotone", color="indigo"),
        ],
    )

    # Donut charts (initial)
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

    # Interface table (initial page=1)
    items = interface_table.get("items") or []
    rows = []
    for it in items:
        rows.append(
            {
                "interface_name": it.get("interface_name") or "",
                "interface_alias": it.get("interface_alias") or "",
                "p95_total_gbps": round(_bps_to_gbps(it.get("p95_total_bps")), 3),
                "speed_gbps": round(_bps_to_gbps(it.get("speed_bps")), 3),
                "utilization_pct": round(float(it.get("utilization_pct") or 0), 2),
            }
        )

    columns = [
        {"name": "Interface", "id": "interface_name"},
        {"name": "Alias", "id": "interface_alias"},
        {"name": "P95 Total (Gbps)", "id": "p95_total_gbps", "type": "numeric"},
        {"name": "Speed (Gbps)", "id": "speed_gbps", "type": "numeric"},
        {"name": "Utilization (%)", "id": "utilization_pct", "type": "numeric"},
    ]

    data_table = dash_table.DataTable(
        id="net-interface-table",
        columns=columns,
        data=rows,
        page_current=0,
        page_size=50,
        page_action="custom",
        sort_action="native",
        style_table={"overflowX": "auto", "marginTop": "6px"},
        style_cell={
            "padding": "8px",
            "color": "#2B3674",
            "fontFamily": "DM Sans, sans-serif",
            "fontSize": "12px",
            "borderColor": "#E9ECEF",
        },
        style_header={
            "backgroundColor": "#F4F7FE",
            "color": "#2B3674",
            "fontWeight": 700,
            "fontFamily": "DM Sans, sans-serif",
            "fontSize": "12px",
        },
    )

    return dmc.Stack(
        gap="lg",
        children=[
            dcc.Store(id="net-filters-store", data=net_filters),
            dmc.SimpleGrid(
                cols=3,
                spacing="lg",
                children=[
                    dmc.Select(
                        id="net-manufacturer-selector",
                        label="Manufacturer",
                        placeholder="All manufacturers",
                        data=manufacturers_data,
                        value=None,
                        clearable=True,
                        searchable=True,
                        nothingFoundMessage="No manufacturers",
                    ),
                    dmc.Select(
                        id="net-role-selector",
                        label="Device Role",
                        placeholder="All roles",
                        data=roles_data,
                        value=None,
                        clearable=True,
                        searchable=True,
                        nothingFoundMessage="No roles",
                    ),
                    dmc.Select(
                        id="net-device-selector",
                        label="Device",
                        placeholder="All devices",
                        data=devices_data,
                        value=None,
                        clearable=True,
                        searchable=True,
                        nothingFoundMessage="No devices",
                    ),
                ],
                style={"marginTop": "10px"},
            ),

            html.Div(id="net-kpi-container", children=kpis),

            dmc.SimpleGrid(
                cols=3,
                spacing="lg",
                children=[
                    _chart_card(
                        dcc.Graph(
                            id="net-donut-active-ports",
                            figure=donut_active,
                            config={"displayModeBar": False},
                            style={"height": "180px"},
                        )
                    ),
                    _chart_card(
                        dcc.Graph(
                            id="net-donut-utilization",
                            figure=donut_util,
                            config={"displayModeBar": False},
                            style={"height": "180px"},
                        )
                    ),
                    _chart_card(
                        dcc.Graph(
                            id="net-donut-icmp",
                            figure=donut_icmp,
                            config={"displayModeBar": False},
                            style={"height": "180px"},
                        )
                    ),
                ],
            ),

            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Bandwidth (95th Percentile)", "Top consumers across the selected time range"),
                    _chart_card(
                        dcc.Graph(
                            id="net-top-interfaces-bar",
                            figure=bar_fig,
                            config={"displayModeBar": False},
                            style={"height": "320px"},
                        )
                    ),
                ],
            ),

            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Interface Details", "Paginated p95 bandwidth table"),
                    dmc.TextInput(
                        id="net-interface-search",
                        placeholder="Search interface name / alias...",
                        value="",
                        leftSection=DashIconify(icon="solar:magnifer-linear", width=16, color="#A3AED0"),
                        style={"marginTop": "6px", "marginBottom": "6px"},
                    ),
                    data_table,
                ],
            ),
        ],
    )


def _build_intel_storage_subtab(device_list: list[dict], zabbix_storage_capacity: dict, zabbix_storage_trend: dict):
    """Intel Storage subtab (Zabbix)."""
    device_list = device_list or []
    zabbix_storage_capacity = zabbix_storage_capacity or {}
    zabbix_storage_trend = zabbix_storage_trend or {}

    # Device selector (optional): empty/cleared => aggregate across all devices.
    device_options_map: dict[str, str] = {}
    for d in device_list:
        host_val = d.get("host")
        if not host_val:
            continue
        host_key = str(host_val)
        label = d.get("device_name") or host_key
        device_options_map.setdefault(host_key, label)

    device_options = [{"label": device_options_map[k], "value": k} for k in sorted(device_options_map.keys())]

    device_selector = dmc.Select(
        id="intel-storage-device-selector",
        data=device_options,
        value=None,
        clearable=True,
        searchable=True,
        placeholder="All Devices",
        nothingFoundMessage="No devices",
        style={"minWidth": "260px"},
    )

    # Donuts/trend initial values: aggregate (host=None).
    total_bytes = float(zabbix_storage_capacity.get("total_capacity_bytes", 0) or 0)
    used_bytes = float(zabbix_storage_capacity.get("used_capacity_bytes", 0) or 0)
    free_bytes = float(zabbix_storage_capacity.get("free_capacity_bytes", 0) or 0)

    # Zabbix bytes -> GB for smart_storage
    bytes_to_gb = lambda b: (float(b) / (1024.0 ** 3)) if b else 0.0
    total_gb = bytes_to_gb(total_bytes)
    used_gb = bytes_to_gb(used_bytes)
    free_gb = bytes_to_gb(free_bytes)

    used_pct = pct_float(used_gb, total_gb)
    free_pct = max(0.0, 100.0 - used_pct)

    # Donuts
    donut_total = create_usage_donut_chart(100.0, f"Total {smart_storage(total_gb)}", color="#FFB547")
    donut_used = create_usage_donut_chart(used_pct, "Used Capacity", color="#4318FF")
    donut_free = create_usage_donut_chart(free_pct, "Free Capacity", color="#05CD99")

    # Trend
    series = zabbix_storage_trend.get("series") or []
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

    disk_container = html.Div(
        id="intel-disk-container",
        children=[
            dmc.Text("Select a device to load disks.", size="sm", c="#A3AED0"),
            html.Div(id="intel-disk-trend-container"),
        ],
    )

    return dmc.Stack(
        gap="lg",
        children=[
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Device Filter", "Optional. Empty selection => show all devices"),
                    device_selector,
                    dcc.Store(id="intel-storage-device-store", data=None),
                ],
            ),
            dmc.SimpleGrid(
                cols=3,
                spacing="lg",
                children=[
                    _chart_card(dcc.Graph(id="intel-donut-total", figure=donut_total, config={"displayModeBar": False})),
                    _chart_card(dcc.Graph(id="intel-donut-used", figure=donut_used, config={"displayModeBar": False})),
                    _chart_card(dcc.Graph(id="intel-donut-free", figure=donut_free, config={"displayModeBar": False})),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Capacity Planning", "Capacity utilization over time (downsampled daily)"),
                    _chart_card(dcc.Graph(id="intel-capacity-trend-chart", figure=trend_fig, config={"displayModeBar": False}, style={"height": "260px"})),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Disk Performance", "Select a device to view disk metrics"),
                    disk_container,
                ],
            ),
        ],
    )


def _build_ibm_storage_subtab(storage_capacity: dict, storage_performance: dict, san_bottleneck: dict):
    """IBM Storage subtab (reuses Power panel data, but focuses on storage)."""
    storage_capacity = storage_capacity or {}
    storage_performance = storage_performance or {}
    san_bottleneck = san_bottleneck or {}

    systems = storage_capacity.get("systems") or []
    storage_system_count = len(systems)

    total_gb = sum(parse_storage_string(s.get("total_mdisk_capacity")) for s in systems)
    used_gb = sum(parse_storage_string(s.get("total_used_capacity")) for s in systems)
    free_gb = sum(parse_storage_string(s.get("total_free_space")) for s in systems)
    storage_pct = pct_float(used_gb, total_gb)

    # Storage systems breakdown (used vs free)
    labels = []
    used_series = []
    free_series = []
    for s in systems:
        labels.append(s.get("name") or s.get("storage_ip") or "System")
        used_series.append(parse_storage_string(s.get("total_used_capacity")))
        free_series.append(parse_storage_string(s.get("total_free_space")))

    breakdown_fig = (
        create_grouped_bar_chart(
            labels=labels,
            series_dict={"Used": used_series, "Free": free_series},
            title="Storage Systems (Used vs Free)",
            height=380,
        )
        if systems
        else go.Figure()
    )

    # Performance cards
    storage_series = storage_performance.get("series") or []
    iops_vals = [float(s.get("iops", 0) or 0) for s in storage_series]
    throughput_vals = [float(s.get("throughput_mb", 0) or 0) for s in storage_series]
    latency_vals = [float(s.get("latency_ms", 0) or 0) for s in storage_series]
    avg_iops = (sum(iops_vals) / len(iops_vals)) if iops_vals else 0.0
    avg_throughput = (sum(throughput_vals) / len(throughput_vals)) if throughput_vals else 0.0
    avg_latency = (sum(latency_vals) / len(latency_vals)) if latency_vals else 0.0

    issues = san_bottleneck.get("issues") or []
    has_san_bottleneck = bool(san_bottleneck.get("has_issue", False)) and bool(issues)

    san_bottleneck_panel = (
        dmc.Alert("No SAN bottleneck detected.", color="teal", radius="md", title="SAN Bottleneck")
        if not has_san_bottleneck
        else dmc.Stack(
            gap="sm",
            children=[
                dmc.Alert("Storage/SAN bottleneck risk detected.", color="orange", radius="md", title="SAN Bottleneck"),
                dmc.Table(
                    striped=True,
                    highlightOnHover=True,
                    withTableBorder=False,
                    withColumnBorders=False,
                    style={"tableLayout": "fixed", "width": "100%"},
                    verticalSpacing="sm",
                    horizontalSpacing="md",
                    children=[
                        html.Thead(
                            html.Tr(
                                [
                                    html.Th(
                                        "Port",
                                        style={"color": "#A3AED0", "fontWeight": 600, "fontSize": "0.72rem", "textTransform": "uppercase", "letterSpacing": "0.07em", "width": "50%"},
                                    ),
                                    html.Th(
                                        "Not XCredits",
                                        style={"color": "#A3AED0", "fontWeight": 600, "fontSize": "0.72rem", "textTransform": "uppercase", "letterSpacing": "0.07em", "textAlign": "right", "width": "25%"},
                                    ),
                                    html.Th(
                                        "Too Many RDys",
                                        style={"color": "#A3AED0", "fontWeight": 600, "fontSize": "0.72rem", "textTransform": "uppercase", "letterSpacing": "0.07em", "textAlign": "right", "width": "25%"},
                                    ),
                                ]
                            )
                        ),
                        html.Tbody(
                            [
                                html.Tr(
                                    [
                                        html.Td(i.get("portname") or ""),
                                        html.Td(
                                            dmc.Badge(str(i.get("swfcportnotxcredits") or 0), color="orange", variant="light", size="sm"),
                                            style={"textAlign": "right"},
                                        ),
                                        html.Td(
                                            dmc.Badge(str(i.get("swfcporttoomanyrdys") or 0), color="orange", variant="light", size="sm"),
                                            style={"textAlign": "right"},
                                        ),
                                    ]
                                )
                                for i in (issues or [])[:8]
                            ]
                        ),
                    ],
                ),
            ],
        )
    )

    return dmc.Stack(
        gap="lg",
        children=[
            dmc.SimpleGrid(
                cols=4,
                spacing="lg",
                children=[
                    _kpi("Storage Systems", f"{storage_system_count:,}", "solar:database-bold-duotone", color="grape"),
                    _kpi("Total Capacity", smart_storage(total_gb), "solar:storage-bold-duotone", color="grape", is_text=True),
                    _kpi("Used Capacity", smart_storage(used_gb), "solar:storage-bold-duotone", color="grape", is_text=True),
                    _kpi("Utilization", f"{storage_pct:.1f}%", "solar:graph-bold-duotone", color="grape"),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Storage Capacity", "Gauge and systems breakdown"),
                    dmc.SimpleGrid(
                        cols=2,
                        spacing="lg",
                        children=[
                            _chart_card(
                                dcc.Graph(
                                    figure=create_gauge_chart(used_gb, total_gb or 1, "Storage Capacity", color="#FFB547"),
                                    config={"displayModeBar": False},
                                    style={"height": "250px"},
                                )
                            ),
                            _chart_card(dcc.Graph(figure=breakdown_fig, config={"displayModeBar": False}, style={"height": "250px"})),
                        ],
                    ),
                    html.Div(
                        style={"marginTop": "12px"},
                        children=[
                            _capacity_metric_row("Storage", total_gb, used_gb, storage_pct, smart_storage),
                            html.Div(
                                f"Free capacity: {smart_storage(free_gb)}",
                                style={"color": "#A3AED0", "fontSize": "0.85rem", "fontWeight": 700, "marginTop": "8px"},
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Average Storage Performance", "Daily averages (IOPS / throughput / latency)"),
                    dmc.SimpleGrid(
                        cols=3,
                        spacing="lg",
                        children=[
                            html.Div(
                                style={"padding": "6px", "height": "150px"},
                                children=[
                                    dmc.Text("IOPS", fw=700, c="#2B3674", size="sm"),
                                    dmc.Text(f"{avg_iops:,.0f} io/s", fw=900, c="#4318FF", size="lg", style={"marginTop": "4px"}),
                                    dcc.Graph(figure=create_sparkline_chart(iops_vals, "IOPS", "io/s", color="#4318FF"), config={"displayModeBar": False}, style={"height": "80px"}),
                                ],
                            ),
                            html.Div(
                                style={"padding": "6px", "height": "150px"},
                                children=[
                                    dmc.Text("Throughput", fw=700, c="#2B3674", size="sm"),
                                    dmc.Text(f"{avg_throughput:,.1f} MB/s", fw=900, c="#05CD99", size="lg", style={"marginTop": "4px"}),
                                    dcc.Graph(figure=create_sparkline_chart(throughput_vals, "Throughput", "MB/s", color="#05CD99"), config={"displayModeBar": False}, style={"height": "80px"}),
                                ],
                            ),
                            html.Div(
                                style={"padding": "6px", "height": "150px"},
                                children=[
                                    dmc.Text("Latency", fw=700, c="#2B3674", size="sm"),
                                    dmc.Text(f"{avg_latency:,.2f} ms", fw=900, c="#FFB547", size="lg", style={"marginTop": "4px"}),
                                    dcc.Graph(figure=create_sparkline_chart(latency_vals, "Latency", "ms", color="#FFB547"), config={"displayModeBar": False}, style={"height": "80px"}),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("SAN Bottleneck", "Storage/SAN risk summary"),
                    san_bottleneck_panel,
                ],
            ),
        ],
    )

# ---------------------------------------------------------------------------
# Main page builder
# ---------------------------------------------------------------------------

def build_dc_view(dc_id, time_range=None):
    """Build DC detail page for the given time range."""
    if not dc_id:
        return html.Div("No Data Center ID provided", style={"padding": "20px"})

    tr = time_range or default_time_range()
    batch1 = parallel_execute(
        {
            "data": lambda: api.get_dc_details(dc_id, tr),
            "sla_by_dc": lambda: api.get_sla_by_dc(tr),
            "s3_data": lambda: api.get_dc_s3_pools(dc_id, tr),
            "classic_clusters": lambda: api.get_classic_cluster_list(dc_id, tr),
            "hyperconv_clusters": lambda: api.get_hyperconv_cluster_list(dc_id, tr),
        }
    )
    data = batch1["data"]
    sla_by_dc = batch1["sla_by_dc"]
    s3_data = batch1["s3_data"]
    classic_clusters = batch1["classic_clusters"]
    hyperconv_clusters = batch1["hyperconv_clusters"]

    sla_entry = sla_by_dc.get(str(dc_id).upper())
    sla_badges = []
    if sla_entry:
        try:
            availability = float(sla_entry.get("availability_pct", 0.0))
            period_h = float(sla_entry.get("period_hours", 0.0))
            downtime_h = float(sla_entry.get("downtime_hours", 0.0))
            sla_badges = [
                dmc.Badge(
                    f"Availability: %{sla_service.format_pct(availability, 2)}",
                    variant="light",
                    color="teal" if availability >= 99.9 else "orange",
                    radius="xl",
                    size="md",
                    style={"textTransform": "none", "fontWeight": 600, "letterSpacing": 0},
                ),
                dmc.Group(
                    gap="sm",
                    justify="flex-end",
                    children=[
                        dmc.Badge(
                            f"Period: {period_h:,.0f} h",
                            variant="light",
                            color="indigo",
                            radius="xl",
                            size="md",
                            style={"textTransform": "none", "fontWeight": 500, "letterSpacing": 0},
                        ),
                        dmc.Badge(
                            f"Downtime: {downtime_h:,.1f} h",
                            variant="light",
                            color="red" if downtime_h > 0 else "teal",
                            radius="xl",
                            size="md",
                            style={"textTransform": "none", "fontWeight": 500, "letterSpacing": 0},
                        ),
                    ],
                ),
            ]
        except Exception:
            sla_badges = []

    has_s3 = bool(s3_data.get("pools"))

    dc_name = data["meta"]["name"]
    dc_loc  = data["meta"]["location"]

    batch2 = parallel_execute(
        {
            "phys_inv": lambda: api.get_physical_inventory_dc(dc_name),
            "san_switches": lambda: api.get_dc_san_switches(dc_id, tr),
            "net_filters": lambda: api.get_dc_network_filters(dc_id, tr),
        }
    )
    phys_inv = batch2["phys_inv"]
    has_phys_inv = phys_inv.get("total", 0) > 0

    export_rows = _build_dc_export_rows(str(dc_id), data, phys_inv)
    export_group = dmc.Group(
        gap=6,
        align="center",
        children=[
            dmc.Text("Export", size="xs", c="dimmed"),
            dmc.Button("CSV", id="dc-export-csv", size="xs", variant="light", color="gray"),
            dmc.Button("Excel", id="dc-export-xlsx", size="xs", variant="light", color="gray"),
            dmc.Button("PDF", id="dc-export-pdf", size="xs", variant="light", color="gray"),
        ],
    )
    header_right_extra = list(sla_badges or []) + [export_group]

    san_switches = batch2["san_switches"]
    has_san = _has_san_data(san_switches)
    san_port_usage = api.get_dc_san_port_usage(dc_id, tr) if has_san else {}
    san_health_alerts = api.get_dc_san_health(dc_id, tr) if has_san else []
    san_traffic_trend = api.get_dc_san_traffic_trend(dc_id, tr) if has_san else []

    net_filters = batch2["net_filters"]
    has_network = bool((net_filters or {}).get("manufacturers"))
    net_port_summary = api.get_dc_network_port_summary(dc_id, tr) if has_network else {}
    net_percentile = api.get_dc_network_95th_percentile(dc_id, tr, top_n=20) if has_network else {}
    net_interface_table = api.get_dc_network_interface_table(dc_id, tr, page=1, page_size=50, search="") if has_network else {}

    energy    = data.get("energy", {})
    classic   = data.get("classic", {})
    hyperconv = data.get("hyperconv", {})
    power     = data.get("power", {})

    # Backup datasets (per DC)
    nb_data = api.get_dc_netbackup_pools(dc_id, tr)
    zerto_data = api.get_dc_zerto_sites(dc_id, tr)
    veeam_data = api.get_dc_veeam_repos(dc_id, tr)

    # Determine which sections actually have data
    has_classic = _has_compute_data(classic)
    has_hyperconv = _has_compute_data(hyperconv)
    has_power = _has_power_data(power)

    storage_capacity = {}
    storage_performance = {}
    san_bottleneck = {}
    if has_power:
        storage_capacity = api.get_dc_storage_capacity(dc_id, tr)
        storage_performance = api.get_dc_storage_performance(dc_id, tr)
        san_bottleneck = api.get_dc_san_bottleneck(dc_id, tr)

    # Intel Storage (Zabbix)
    zabbix_storage_capacity = api.get_dc_zabbix_storage_capacity(dc_id, tr)
    has_intel_storage = int(zabbix_storage_capacity.get("storage_device_count", 0) or 0) > 0
    zabbix_storage_devices = api.get_dc_zabbix_storage_devices(dc_id, tr) if has_intel_storage else []
    zabbix_storage_trend = api.get_dc_zabbix_storage_trend(dc_id, tr) if has_intel_storage else {}

    has_storage = bool(has_intel_storage or has_power or has_s3)

    has_virt = has_classic or has_hyperconv or has_power
    has_summary = has_virt

    # Backup subtabs enabled only when data exists
    has_zerto = bool(zerto_data.get("sites"))
    has_veeam = bool(veeam_data.get("repos"))
    has_netbackup = bool(nb_data.get("pools"))
    has_nutanix_backup = False
    has_backup = has_zerto or has_veeam or has_netbackup or has_nutanix_backup

    # S3 presence already computed above
    # has_s3 = bool(s3_data.get("pools"))

    # Determine default active outer tab: first tab that actually has data
    tabs_order = [
        ("summary", has_summary),
        ("virt", has_virt),
        ("storage", has_storage),
        ("backup", has_backup),
        ("phys-inv", has_phys_inv),
        ("network", has_network or has_san),
    ]
    default_outer_tab = next((t for t, ok in tabs_order if ok), "summary")

    # Determine default virtualization inner tab
    virt_order = [
        ("classic", has_classic),
        ("hyperconv", has_hyperconv),
        ("power", has_power),
    ]
    default_virt_tab = next((t for t, ok in virt_order if ok), "classic")

    def _cluster_header(selector_id: str, clusters: list[str], placeholder: str):
        return html.Div(
            style={"display": "flex", "justifyContent": "flex-end", "alignItems": "center", "marginBottom": "16px"},
            children=dmc.MultiSelect(
                id=selector_id,
                data=[{"label": c, "value": c} for c in clusters],
                value=list(clusters),
                clearable=True,
                searchable=True,
                nothingFoundMessage="No clusters",
                placeholder=placeholder,
                size="sm",
                style={"minWidth": "260px"},
            ),
        )

    return html.Div([
        dcc.Store(
            id="dc-export-store",
            data={"dc_name": dc_name, "rows": export_rows},
        ),
        dcc.Download(id="dc-export-download"),
        dmc.Tabs(
            color="indigo",
            variant="pills",
            radius="md",
            value=default_outer_tab,
            children=[
                create_detail_header(
                    title=dc_name,
                    back_href="/datacenters",
                    back_label="Data Centers",
                    subtitle_badge=f"­şôı {dc_loc}" if dc_loc else None,
                    subtitle_color="indigo",
                    time_range=tr,
                    icon="solar:server-square-bold-duotone",
                    right_extra=header_right_extra,
                    tabs=dmc.TabsList(
                        style={"paddingTop": "8px"},
                        children=[
                            dmc.TabsTab("Summary", value="summary") if has_summary else None,
                            dmc.TabsTab("Virtualization", value="virt") if has_virt else None,
                            dmc.TabsTab("Storage", value="storage") if has_storage else None,
                            dmc.TabsTab("Backup & Replication", value="backup") if has_backup else None,
                            dmc.TabsTab("Physical Inventory", value="phys-inv") if has_phys_inv else None,
                            dmc.TabsTab("Network", value="network") if (has_network or has_san) else None,
                        ],
                    ),
                ),

                # Summary tab
                dmc.TabsPanel(
                    value="summary",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[_build_summary_tab(data, tr)],
                    ),
                ) if has_summary else None,

                # Virtualization (nested tabs)
                dmc.TabsPanel(
                    value="virt",
                    children=html.Div(
                        style={"padding": "0 30px"},
                        children=[
                            dmc.Tabs(
                                color="violet",
                                variant="outline",
                                radius="md",
                                value=default_virt_tab,
                                children=[
                                    dmc.TabsList(
                                        children=[
                                            dmc.TabsTab("Klasik Mimari", value="classic") if has_classic else None,
                                            dmc.TabsTab("Hyperconverged Mimari", value="hyperconv") if has_hyperconv else None,
                                            dmc.TabsTab("Power Mimari", value="power") if has_power else None,
                                        ]
                                    ),
                                    dmc.TabsPanel(
                                        value="classic",
                                        pt="lg",
                                        children=dmc.Stack(
                                            gap="lg",
                                            children=[
                                                _cluster_header(
                                                    "virt-classic-cluster-selector",
                                                    classic_clusters or [],
                                                    "Select Classic clusters",
                                                ),
                                                html.Div(
                                                    id="classic-virt-panel",
                                                    children=_build_compute_tab(classic, "Classic Compute", color="blue"),
                                                ),
                                            ],
                                        ),
                                    ) if has_classic else None,
                                    dmc.TabsPanel(
                                        value="hyperconv",
                                        pt="lg",
                                        children=dmc.Stack(
                                            gap="lg",
                                            children=[
                                                _cluster_header(
                                                    "virt-hyperconv-cluster-selector",
                                                    hyperconv_clusters or [],
                                                    "Select Hyperconverged clusters",
                                                ),
                                                html.Div(
                                                    id="hyperconv-virt-panel",
                                                    children=_build_compute_tab(hyperconv, "Hyperconverged Compute", color="teal"),
                                                ),
                                            ],
                                        ),
                                    ) if has_hyperconv else None,
                                    dmc.TabsPanel(
                                        value="power",
                                        pt="lg",
                                        children=_build_power_tab(
                                            power,
                                            energy,
                                            storage_capacity,
                                            storage_performance,
                                            san_bottleneck,
                                        ),
                                    ) if has_power else None,
                                ],
                            ),
                        ],
                    ),
                ),

                # Backup (nested tabs)
                dmc.TabsPanel(
                    value="backup",
                    children=html.Div(
                        style={"padding": "0 30px"},
                        children=[
                            dmc.Tabs(
                                color="green",
                                variant="outline",
                                radius="md",
                                value="zerto" if has_zerto else "veeam" if has_veeam else "netbackup",
                                children=[
                                    dmc.TabsList(
                                        children=[
                                            dmc.TabsTab("Zerto", value="zerto") if has_zerto else None,
                                            dmc.TabsTab("Veeam", value="veeam") if has_veeam else None,
                                            dmc.TabsTab("NetBackup", value="netbackup") if has_netbackup else None,
                                            dmc.TabsTab("Nutanix", value="nutanix") if has_nutanix_backup else None,
                                        ]
                                    ),
                                    dmc.TabsPanel(
                                        value="zerto",
                                        pt="lg",
                                        children=html.Div(
                                            id="backup-zerto-panel",
                                            children=build_zerto_panel(zerto_data, None) if has_zerto else html.Div(),
                                        ),
                                    ) if has_zerto else None,
                                    dmc.TabsPanel(
                                        value="veeam",
                                        pt="lg",
                                        children=html.Div(
                                            id="backup-veeam-panel",
                                            children=build_veeam_panel(veeam_data, None) if has_veeam else html.Div(),
                                        ),
                                    ) if has_veeam else None,
                                    dmc.TabsPanel(
                                        value="netbackup",
                                        pt="lg",
                                        children=html.Div(
                                            id="backup-netbackup-panel",
                                            children=build_netbackup_panel(nb_data, None) if has_netbackup else html.Div(),
                                        ),
                                    ) if has_netbackup else None,
                                    dmc.TabsPanel(
                                        value="nutanix",
                                        pt="lg",
                                        children=_build_backup_subtab("Nutanix"),
                                    ) if has_nutanix_backup else None,
                                ],
                            ),
                        ],
                    ),
                ) if has_backup else None,

                # Physical Inventory
                dmc.TabsPanel(
                    value="phys-inv",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[_build_physical_inventory_dc_tab(phys_inv)],
                    ),
                ) if has_phys_inv else None,
                # Storage (Intel / IBM)
                dmc.TabsPanel(
                    value="storage",
                    children=html.Div(
                        style={"padding": "0 30px"},
                        children=[
                            dmc.Tabs(
                                color="indigo",
                                variant="outline",
                                radius="md",
                                value="intel" if has_intel_storage else "ibm" if has_power else "obj-storage",
                                children=[
                                    dmc.TabsList(
                                        children=[
                                            dmc.TabsTab("Intel Storage", value="intel") if has_intel_storage else None,
                                            dmc.TabsTab("IBM Storage", value="ibm") if has_power else None,
                                            dmc.TabsTab("Object Storage - S3", value="obj-storage") if has_s3 else None,
                                        ]
                                    ),
                                    dmc.TabsPanel(
                                        value="intel",
                                        pt="lg",
                                        children=_build_intel_storage_subtab(
                                            zabbix_storage_devices,
                                            zabbix_storage_capacity,
                                            zabbix_storage_trend,
                                        ),
                                    ) if has_intel_storage else None,
                                    dmc.TabsPanel(
                                        value="ibm",
                                        pt="lg",
                                        children=_build_ibm_storage_subtab(
                                            storage_capacity,
                                            storage_performance,
                                            san_bottleneck,
                                        ),
                                    ) if has_power else None,
                                    dmc.TabsPanel(
                                        value="obj-storage",
                                        pt="lg",
                                        children=html.Div(
                                            id="s3-dc-metrics-panel",
                                            style={"marginTop": "0"},
                                            children=build_dc_s3_panel(dc_name, s3_data, tr, None) if has_s3 else html.Div(),
                                        ),
                                    ) if has_s3 else None,
                                ],
                            )
                        ],
                    ),
                ) if has_storage else None,

                # Network (Dashboard / SAN)
                dmc.TabsPanel(
                    value="network",
                    children=html.Div(
                        style={"padding": "0 30px"},
                        children=[
                            dmc.Tabs(
                                color="indigo",
                                variant="outline",
                                radius="md",
                                value="dashboard" if has_network else "san",
                                children=[
                                    dmc.TabsList(
                                        children=[
                                            dmc.TabsTab("Dashboard", value="dashboard") if has_network else None,
                                            dmc.TabsTab("SAN", value="san") if has_san else None,
                                        ]
                                    ),
                                    dmc.TabsPanel(
                                        value="dashboard",
                                        pt="lg",
                                        children=_build_network_dashboard_subtab(
                                            net_filters,
                                            net_port_summary,
                                            net_percentile,
                                            net_interface_table,
                                        ),
                                    ) if has_network else None,
                                    dmc.TabsPanel(
                                        value="san",
                                        pt="lg",
                                        children=_build_san_subtab(
                                            san_port_usage,
                                            san_health_alerts,
                                            san_traffic_trend,
                                        ),
                                    ) if has_san else None,
                                ],
                            )
                        ],
                    ),
                ) if (has_network or has_san) else None,
            ],
        )
    ])


def layout(dc_id=None):
    return build_dc_view(dc_id, default_time_range())


@callback(
    Output("dc-export-download", "data"),
    Input("dc-export-csv", "n_clicks"),
    Input("dc-export-xlsx", "n_clicks"),
    Input("dc-export-pdf", "n_clicks"),
    State("dc-export-store", "data"),
    prevent_initial_call=True,
)
def export_dc_detail(nc, nx, np, store):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    tid = ctx.triggered[0]["prop_id"].split(".")[0]
    fmt_map = {"dc-export-csv": "csv", "dc-export-xlsx": "xlsx", "dc-export-pdf": "pdf"}
    fmt = fmt_map.get(tid)
    if not fmt:
        return dash.no_update
    store = store or {}
    rows = store.get("rows") or []
    base = str(store.get("dc_name") or "dc_detail")
    df = records_to_dataframe(rows)
    return dash_send_dataframe(df, base, fmt)
