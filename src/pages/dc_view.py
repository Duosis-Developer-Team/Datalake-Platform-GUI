# DC Detail view — Capacity Planning
# Tab hierarchy: Summary | Virtualization (Classic / Hyperconverged / Power) | Backup | Physical Inventory
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objects as go

from src.services import api_client as api
from src.utils.time_range import default_time_range
from src.utils.format_units import smart_storage, smart_memory, smart_cpu, pct_float, title_case
from src.components.charts import create_usage_donut_chart, create_gauge_chart
from src.components.header import create_detail_header
from src.components.s3_panel import build_dc_s3_panel
from src.components.backup_panel import (
    build_netbackup_panel,
    build_zerto_panel,
    build_veeam_panel,
)
from src.services import sla_service


# ---------------------------------------------------------------------------
# Shared UI helpers
# ---------------------------------------------------------------------------


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


def _build_power_tab(power: dict, energy: dict):
    """IBM Power Mimari tab content."""
    hosts    = power.get("hosts", 0)
    vios     = power.get("vios", 0)
    lpars    = power.get("lpar_count", 0)
    mem_total    = power.get("memory_total", 0.0)
    mem_assigned = power.get("memory_assigned", 0.0)
    cpu_used     = power.get("cpu_used", 0.0)
    cpu_assigned = power.get("cpu_assigned", 1.0) or 1.0

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
                    _section_title("Energy", "Daily average over report period"),
                    dmc.SimpleGrid(cols=2, spacing="lg", style={"marginTop": "12px"}, children=[
                        _kpi("IBM Power", f"{energy.get('ibm_kw', 0):.1f} kW",  "material-symbols:bolt-outline", color="orange"),
                        _kpi("Consumption", f"{energy.get('ibm_kwh', 0):,.0f} kWh", "material-symbols:bolt-outline", color="orange"),
                    ]),
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
    """Summary tab ÔÇö combined capacity planning view."""
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
    total_stor_cap  = classic.get("stor_cap", 0) + hyperconv.get("stor_cap", 0)
    total_stor_used = classic.get("stor_used", 0) + hyperconv.get("stor_used", 0)

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
                    ]),
                ],
            ),
            # IBM Power summary
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Power Compute (IBM)", "IBM Power resource summary"),
                    dmc.SimpleGrid(cols=3, spacing="lg", style={"marginTop": "12px"}, children=[
                        _kpi("IBM Hosts",   f"{power.get('hosts', 0):,}",       "solar:server-bold-duotone",       color="grape"),
                        _kpi("LPARs",       f"{power.get('lpar_count', 0):,}",  "solar:laptop-bold-duotone",       color="grape"),
                        _kpi("RAM Assigned", smart_memory(power.get("memory_assigned", 0)),
                             "solar:ram-bold-duotone", color="grape", is_text=True),
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
# Main page builder
# ---------------------------------------------------------------------------

def build_dc_view(dc_id, time_range=None):
    """Build DC detail page for the given time range."""
    if not dc_id:
        return html.Div("No Data Center ID provided", style={"padding": "20px"})

    tr   = time_range or default_time_range()
    data = api.get_dc_details(dc_id, tr)

    sla_by_dc = api.get_sla_by_dc(tr)
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

    # S3 pool metrics (may be empty for DCs without S3 pools)
    s3_data = api.get_dc_s3_pools(dc_id, tr)
    has_s3 = bool(s3_data.get("pools"))

    # Cluster lists for virtualization tab filters (S3-style)
    classic_clusters   = api.get_classic_cluster_list(dc_id, tr)
    hyperconv_clusters = api.get_hyperconv_cluster_list(dc_id, tr)

    dc_name = data["meta"]["name"]
    dc_loc  = data["meta"]["location"]

    # Physical inventory (NetBox devices in this DC)
    phys_inv = api.get_physical_inventory_dc(dc_name)
    has_phys_inv = phys_inv.get("total", 0) > 0

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
        ("backup", has_backup),
        ("obj-storage", has_s3),
        ("phys-inv", has_phys_inv),
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
                    right_extra=sla_badges,
                    tabs=dmc.TabsList(
                        style={"paddingTop": "8px"},
                        children=[
                            dmc.TabsTab("Summary", value="summary") if has_summary else None,
                            dmc.TabsTab("Virtualization", value="virt") if has_virt else None,
                            dmc.TabsTab("Backup & Replication", value="backup") if has_backup else None,
                            dmc.TabsTab("Object Storage", value="obj-storage") if has_s3 else None,
                            dmc.TabsTab("Physical Inventory", value="phys-inv") if has_phys_inv else None,
                        ],
                    ),
                ),

                # ÔöÇÔöÇ Summary ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
                dmc.TabsPanel(
                    value="summary",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[_build_summary_tab(data, tr)],
                    ),
                ) if has_summary else None,

                # ÔöÇÔöÇ Virtualization (nested tabs) ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
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
                                        children=_build_power_tab(power, energy),
                                    ) if has_power else None,
                                ],
                            ),
                        ],
                    ),
                ),

                # ÔöÇÔöÇ Backup (nested tabs) ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
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

                # ÔöÇÔöÇ Object Storage (with S3 subtab) ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
                dmc.TabsPanel(
                    value="obj-storage",
                    children=html.Div(
                        style={"padding": "0 30px"},
                        children=[
                            dmc.Tabs(
                                color="indigo",
                                variant="outline",
                                radius="md",
                                value="s3",
                                children=[
                                    dmc.TabsList(
                                        children=[
                                            dmc.TabsTab("S3", value="s3") if has_s3 else None,
                                        ]
                                    ),
                                    dmc.TabsPanel(
                                        value="s3",
                                        pt="lg",
                                        children=html.Div(
                                            id="s3-dc-metrics-panel",
                                            style={"marginTop": "0"},
                                            children=build_dc_s3_panel(dc_name, s3_data, tr, None) if has_s3 else html.Div(),
                                        ),
                                    ) if has_s3 else None,
                                ],
                            ),
                        ],
                    ),
                ) if has_s3 else None,

                # ÔöÇÔöÇ Physical Inventory ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
                dmc.TabsPanel(
                    value="phys-inv",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[_build_physical_inventory_dc_tab(phys_inv)],
                    ),
                ) if has_phys_inv else None,
            ],
        )
    ])


def layout(dc_id=None):
    return build_dc_view(dc_id, default_time_range())
