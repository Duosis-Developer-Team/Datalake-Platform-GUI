# DC Detail view — Capacity Planning
# Tab hierarchy: Summary | Virtualization (Classic / Hyperconverged / Power) | Backup
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from src.services.shared import service
from src.utils.time_range import default_time_range
from src.utils.format_units import smart_storage, smart_memory, smart_cpu, pct_float
from src.components.charts import create_usage_donut_chart, create_gauge_chart
from src.components.header import create_detail_header
from src.components.s3_panel import build_dc_s3_panel


# ---------------------------------------------------------------------------
# Shared UI helpers
# ---------------------------------------------------------------------------

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
    """Placeholder for backup sub-tabs not yet fully implemented."""
    return html.Div(
        style={"padding": "60px", "textAlign": "center"},
        children=[
            DashIconify(icon="solar:shield-check-bold-duotone", width=48,
                        style={"color": "#A3AED0", "marginBottom": "12px"}),
            html.P(f"{name} backup metrics", style={"color": "#2B3674", "fontWeight": 600}),
            html.P("Data will be displayed here.", style={"color": "#A3AED0", "fontSize": "0.85rem"}),
        ],
    )


def _build_summary_tab(data: dict, tr: dict):
    """Summary tab — combined capacity planning view."""
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


# ---------------------------------------------------------------------------
# Main page builder
# ---------------------------------------------------------------------------

def build_dc_view(dc_id, time_range=None):
    """Build DC detail page for the given time range."""
    if not dc_id:
        return html.Div("No Data Center ID provided", style={"padding": "20px"})

    tr   = time_range or default_time_range()
    data = service.get_dc_details(dc_id, tr)

    # S3 pool metrics (may be empty for DCs without S3 pools)
    s3_data = service.get_dc_s3_pools(dc_id, tr)
    has_s3 = bool(s3_data.get("pools"))

    # Cluster lists for virtualization tab filters (S3-style)
    classic_clusters   = service.get_classic_cluster_list(dc_id, tr)
    hyperconv_clusters = service.get_hyperconv_cluster_list(dc_id, tr)

    dc_name = data["meta"]["name"]
    dc_loc  = data["meta"]["location"]

    energy    = data.get("energy", {})
    classic   = data.get("classic", {})
    hyperconv = data.get("hyperconv", {})
    power     = data.get("power", {})

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
            value="summary",
            children=[
                create_detail_header(
                    title=dc_name,
                    back_href="/datacenters",
                    back_label="Data Centers",
                    subtitle_badge=f"📍 {dc_loc}" if dc_loc else None,
                    subtitle_color="indigo",
                    time_range=tr,
                    icon="solar:server-square-bold-duotone",
                    tabs=dmc.TabsList(
                        style={"paddingTop": "8px"},
                        children=[
                            dmc.TabsTab("Summary",          value="summary"),
                            dmc.TabsTab("Virtualization",   value="virt"),
                            dmc.TabsTab("Backup",           value="backup"),
                            dmc.TabsTab("S3 Object Storage", value="s3") if has_s3 else None,
                        ],
                    ),
                ),

                # ── Summary ──────────────────────────────────────────────
                dmc.TabsPanel(
                    value="summary",
                    children=dmc.Stack(gap="lg", style={"padding": "0 30px"},
                                       children=[_build_summary_tab(data, tr)]),
                ),

                # ── Virtualization (nested tabs) ──────────────────────────
                dmc.TabsPanel(
                    value="virt",
                    children=html.Div(
                        style={"padding": "0 30px"},
                        children=[
                            dmc.Tabs(
                                color="violet",
                                variant="outline",
                                radius="md",
                                value="classic",
                                children=[
                                    dmc.TabsList(children=[
                                        dmc.TabsTab("Klasik Mimari",         value="classic"),
                                        dmc.TabsTab("Hyperconverged Mimari", value="hyperconv"),
                                        dmc.TabsTab("Power Mimari",          value="power"),
                                    ]),
                                    dmc.TabsPanel(
                                        value="classic",
                                        pt="lg",
                                        children=dmc.Stack(
                                            gap="lg",
                                            children=[x for x in [
                                                _cluster_header(
                                                    "virt-classic-cluster-selector",
                                                    classic_clusters,
                                                    "Select Classic clusters",
                                                ) if classic_clusters else None,
                                                html.Div(
                                                    id="classic-virt-panel",
                                                    children=_build_compute_tab(classic, "Classic Compute", color="blue"),
                                                ),
                                            ] if x is not None],
                                        ),
                                    ),
                                    dmc.TabsPanel(
                                        value="hyperconv",
                                        pt="lg",
                                        children=dmc.Stack(
                                            gap="lg",
                                            children=[x for x in [
                                                _cluster_header(
                                                    "virt-hyperconv-cluster-selector",
                                                    hyperconv_clusters,
                                                    "Select Hyperconverged clusters",
                                                ) if hyperconv_clusters else None,
                                                html.Div(
                                                    id="hyperconv-virt-panel",
                                                    children=_build_compute_tab(hyperconv, "Hyperconverged Compute", color="teal"),
                                                ),
                                            ] if x is not None],
                                        ),
                                    ),
                                    dmc.TabsPanel(
                                        value="power",
                                        pt="lg",
                                        children=_build_power_tab(power, energy),
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),

                # ── Backup (nested tabs) ──────────────────────────────────
                dmc.TabsPanel(
                    value="backup",
                    children=html.Div(
                        style={"padding": "0 30px"},
                        children=[
                            dmc.Tabs(
                                color="green",
                                variant="outline",
                                radius="md",
                                value="zerto",
                                children=[
                                    dmc.TabsList(children=[
                                        dmc.TabsTab("Zerto",     value="zerto"),
                                        dmc.TabsTab("Veeam",     value="veeam"),
                                        dmc.TabsTab("Netbackup", value="netbackup"),
                                        dmc.TabsTab("Nutanix",   value="nutanix"),
                                        dmc.TabsTab("S3",        value="s3"),
                                    ]),
                                    dmc.TabsPanel(value="zerto",     pt="lg", children=_build_backup_subtab("Zerto")),
                                    dmc.TabsPanel(value="veeam",     pt="lg", children=_build_backup_subtab("Veeam")),
                                    dmc.TabsPanel(value="netbackup", pt="lg", children=_build_backup_subtab("Netbackup")),
                                    dmc.TabsPanel(value="nutanix",   pt="lg", children=_build_backup_subtab("Nutanix")),
                                    dmc.TabsPanel(value="s3",        pt="lg", children=_build_backup_subtab("S3")),
                                ],
                            ),
                        ],
                    ),
                ),

                # ── S3 Object Storage ───────────────────────────────────────
                dmc.TabsPanel(
                    value="s3",
                    children=html.Div(
                        id="s3-dc-metrics-panel",
                        style={"padding": "0 30px", "marginTop": "16px"},
                        children=build_dc_s3_panel(dc_name, s3_data, tr, None) if has_s3 else html.Div(),
                    ),
                ) if has_s3 else None,
            ],
        )
    ])


def layout(dc_id=None):
    return build_dc_view(dc_id, default_time_range())
