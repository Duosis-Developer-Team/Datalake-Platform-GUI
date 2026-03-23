# Customer View - Billing-focused resource breakdown per customer.
# Tab hierarchy: Summary | Virtualization (Classic / Hyperconverged / Power) | Backup
import dash
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objs as go

from src.services import api_client as api
from src.utils.time_range import default_time_range
from src.utils.format_units import smart_storage, smart_memory, smart_cpu, pct_float, title_case
from src.components.header import create_detail_header
from src.pages.home import metric_card
from src.components.s3_panel import build_customer_s3_panel


# ---------------------------------------------------------------------------
# Shared UI helpers
# ---------------------------------------------------------------------------

def _metric(title: str, value, icon: str, color: str = "indigo"):
    """Standard billing metric card."""
    return html.Div(
        className="nexus-card",
        style={"padding": "20px"},
        children=[
            dmc.Group(align="center", gap="sm", style={"marginBottom": "8px"}, children=[
                dmc.ThemeIcon(size="lg", radius="md", variant="light", color=color,
                              children=DashIconify(icon=icon, width=22)),
                html.H3(title, style={"margin": 0, "color": "#A3AED0", "fontSize": "0.9rem"}),
            ]),
            html.H2(str(value), style={"margin": "0", "color": "#2B3674",
                                        "fontSize": "1.5rem", "fontWeight": "700"}),
        ],
    )


def _vm_table(vm_list: list, columns: list[str], row_fn, empty_cols: int = 5):
    """Generic scrollable VM/LPAR billing table."""
    return html.Div(
        style={"maxHeight": "420px", "overflowY": "auto"},
        children=[
            dmc.Table(
                striped=True,
                highlightOnHover=True,
                children=[
                    html.Thead(html.Tr([html.Th(c) for c in columns])),
                    html.Tbody(
                        [row_fn(r) for r in vm_list]
                        if vm_list
                        else [html.Tr([html.Td("No data", colSpan=empty_cols)])]
                    ),
                ],
            )
        ],
    )


def _section_card(title: str, subtitle: str | None = None, children=None):
    return html.Div(
        className="nexus-card",
        style={"padding": "20px"},
        children=[
            html.H3(title, style={"margin": "0 0 4px 0", "color": "#2B3674",
                                   "fontSize": "1rem", "fontWeight": 700}),
            html.P(subtitle, style={"margin": "0 0 12px 0", "color": "#A3AED0",
                                     "fontSize": "0.8rem"}) if subtitle else None,
            children or html.Div(),
        ],
    )


def _backup_placeholder(name: str):
    return html.Div(
        style={"padding": "60px", "textAlign": "center"},
        children=[
            DashIconify(icon="solar:shield-check-bold-duotone", width=48,
                        style={"color": "#A3AED0", "marginBottom": "12px"}),
            html.P(f"{name} backup data", style={"color": "#2B3674", "fontWeight": 600}),
            html.P("Detailed data will be shown here.", style={"color": "#A3AED0", "fontSize": "0.85rem"}),
        ],
    )


# ---------------------------------------------------------------------------
# Tab content builders
# ---------------------------------------------------------------------------

def _tab_summary(totals: dict, assets: dict):
    """Summary tab: aggregated billing overview."""
    classic   = assets.get("classic", {})
    hyperconv = assets.get("hyperconv", {})
    power     = assets.get("power", {})

    classic_vms   = int(classic.get("vm_count", 0) or 0)
    hyperconv_vms = int(hyperconv.get("vm_count", 0) or 0)
    power_lpars   = int(power.get("lpar_count", 0) or 0)
    total_vms     = int(totals.get("vms_total", 0) or 0)

    classic_cpu   = float(classic.get("cpu_total", 0) or 0)
    hyperconv_cpu = float(hyperconv.get("cpu_total", 0) or 0)
    power_cpu     = float(power.get("cpu_total", 0) or 0)

    classic_mem   = float(classic.get("memory_gb", 0) or 0)
    hyperconv_mem = float(hyperconv.get("memory_gb", 0) or 0)
    power_mem     = float(power.get("memory_total_gb", 0) or 0)

    classic_disk   = float(classic.get("disk_gb", 0) or 0)
    hyperconv_disk = float(hyperconv.get("disk_gb", 0) or 0)

    backup_totals = totals.get("backup", {}) or {}
    veeam_defined   = int(backup_totals.get("veeam_defined_sessions", 0) or 0)
    zerto_protected = int(backup_totals.get("zerto_protected_vms", 0) or 0)
    nb_pre_gib      = float(backup_totals.get("netbackup_pre_dedup_gib", 0) or 0)
    nb_post_gib     = float(backup_totals.get("netbackup_post_dedup_gib", 0) or 0)
    zerto_prov_gib  = float(backup_totals.get("zerto_provisioned_gib", 0) or 0)

    return dmc.Stack(gap="lg", children=[
        # VM count overview
        _section_card("VM / LPAR Summary", "Total provisioned instances per compute type",
            dmc.SimpleGrid(cols=4, spacing="lg", children=[
                _metric("Total Instances",   f"{total_vms:,}",     "solar:laptop-bold-duotone",          color="teal"),
                _metric("Classic VMs",        f"{classic_vms:,}",   "solar:laptop-bold-duotone",          color="blue"),
                _metric("Hyperconverged VMs", f"{hyperconv_vms:,}", "solar:laptop-bold-duotone",          color="indigo"),
                _metric("Power LPARs",        f"{power_lpars:,}",   "solar:server-square-bold-duotone",   color="grape"),
            ]),
        ),
        # Compute resource summary
        _section_card("Compute Resources", "Allocated CPU, Memory and Disk per compute type",
            children=html.Div([
                # Header row
                html.Div(
                    style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr 1fr",
                           "padding": "8px 0", "borderBottom": "2px solid #4318FF",
                           "fontSize": "0.8rem", "fontWeight": 700, "color": "#A3AED0"},
                    children=[html.Span("Compute Type"), html.Span("CPU (vCPU)"),
                              html.Span("Memory"), html.Span("Disk")],
                ),
                *[
                    html.Div(
                        style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr 1fr",
                               "padding": "10px 0", "borderBottom": "1px solid #F4F7FE",
                               "fontSize": "0.85rem"},
                        children=[
                            html.Span(label, style={"color": "#2B3674", "fontWeight": 600}),
                            html.Span(f"{cpu:.0f}", style={"color": "#4318FF"}),
                            html.Span(smart_memory(mem), style={"color": "#4318FF"}),
                            html.Span(smart_storage(disk), style={"color": "#4318FF"}),
                        ],
                    )
                    for label, cpu, mem, disk in [
                        ("Classic Compute",      classic_cpu,   classic_mem,   classic_disk),
                        ("Hyperconverged",        hyperconv_cpu, hyperconv_mem, hyperconv_disk),
                        ("Power Compute (IBM)",   power_cpu,     power_mem,     0),
                    ]
                ],
            ]),
        ),
        # Backup summary
        _section_card("Backup Services", "Backup session and storage consumption",
            dmc.SimpleGrid(cols=3, spacing="lg", children=[
                _metric("Veeam Sessions",        f"{veeam_defined:,}",     "material-symbols:backup-outline"),
                _metric("Zerto Protected VMs",   f"{zerto_protected:,}",   "material-symbols:shield-outline", color="teal"),
                _metric("NetBackup Pre-Dedup",   f"{nb_pre_gib:.2f} GiB",  "mdi:database-lock-outline",       color="orange"),
            ]),
        ),
        _section_card("Backup Capacity (Billing)", "Storage capacity billed per backup service",
            dmc.SimpleGrid(cols=3, spacing="lg", children=[
                _metric("NetBackup Stored (GiB)",   f"{nb_post_gib:.2f}",   "mdi:database-arrow-down-outline"),
                _metric("Zerto Max Provisioned",    f"{zerto_prov_gib:.2f} GiB", "solar:hdd-bold-duotone",  color="teal"),
                _metric("Pre-Dedup (GiB)",          f"{nb_pre_gib:.2f}",    "mdi:database-lock-outline",     color="orange"),
            ]),
        ),
    ])


def _tab_billing(totals: dict, assets: dict, backup_totals: dict, s3_data: dict | None = None):
    """Billing tab: invoice-style view combining compute, backup and S3."""
    classic   = assets.get("classic", {}) or {}
    hyperconv = assets.get("hyperconv", {}) or {}
    power     = assets.get("power", {}) or {}

    total_vms   = int(totals.get("vms_total", 0) or 0)
    total_cpu   = float(totals.get("cpu_total", 0.0) or 0.0)
    total_intel_mem = float(classic.get("memory_gb", 0) or 0) + float(hyperconv.get("memory_gb", 0) or 0)
    total_intel_disk = float(classic.get("disk_gb", 0) or 0) + float(hyperconv.get("disk_gb", 0) or 0)
    total_power_mem = float(power.get("memory_total_gb", 0) or 0)

    veeam_defined   = int(backup_totals.get("veeam_defined_sessions", 0) or 0)
    zerto_protected = int(backup_totals.get("zerto_protected_vms", 0) or 0)
    nb_pre_gib      = float(backup_totals.get("netbackup_pre_dedup_gib", 0) or 0)
    nb_post_gib     = float(backup_totals.get("netbackup_post_dedup_gib", 0) or 0)
    zerto_prov_gib  = float(backup_totals.get("zerto_provisioned_gib", 0) or 0)

    vaults = (s3_data or {}).get("vaults", []) or []
    vault_count = len(vaults)

    return dmc.Stack(
        gap="lg",
        children=[
            dmc.SimpleGrid(
                cols=4,
                spacing="lg",
                children=[
                    _metric("Total Instances", f"{total_vms:,}", "solar:laptop-bold-duotone", color="teal"),
                    _metric("Total CPU (vCPU)", f"{total_cpu:.1f}", "solar:cpu-bold-duotone"),
                    _metric("Intel Memory (GB)", smart_memory(total_intel_mem), "solar:ram-bold-duotone"),
                    _metric("Intel Disk (GB)", smart_storage(total_intel_disk), "solar:hdd-bold-duotone", color="orange"),
                ],
            ),
            _section_card(
                "Compute billing lines",
                "Per compute platform billable resource totals",
                html.Div(
                    className="nexus-card",
                    style={"padding": "0", "background": "transparent", "boxShadow": "none"},
                    children=dmc.Table(
                        striped=True,
                        highlightOnHover=True,
                        children=[
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("Line item"),
                                        html.Th("Instances"),
                                        html.Th("CPU (vCPU)"),
                                        html.Th("Memory"),
                                        html.Th("Disk"),
                                    ]
                                )
                            ),
                            html.Tbody(
                                [
                                    html.Tr(
                                        [
                                            html.Td("Classic Compute"),
                                            html.Td(f"{int(classic.get('vm_count', 0) or 0):,}"),
                                            html.Td(f"{float(classic.get('cpu_total', 0) or 0):.1f}"),
                                            html.Td(smart_memory(float(classic.get('memory_gb', 0) or 0))),
                                            html.Td(smart_storage(float(classic.get('disk_gb', 0) or 0))),
                                        ]
                                    ),
                                    html.Tr(
                                        [
                                            html.Td("Hyperconverged"),
                                            html.Td(f"{int(hyperconv.get('vm_count', 0) or 0):,}"),
                                            html.Td(f"{float(hyperconv.get('cpu_total', 0) or 0):.1f}"),
                                            html.Td(smart_memory(float(hyperconv.get('memory_gb', 0) or 0))),
                                            html.Td(smart_storage(float(hyperconv.get('disk_gb', 0) or 0))),
                                        ]
                                    ),
                                    html.Tr(
                                        [
                                            html.Td("Power Compute (IBM)"),
                                            html.Td(f"{int(power.get('lpar_count', 0) or 0):,}"),
                                            html.Td(f"{float(power.get('cpu_total', 0) or 0):.1f}"),
                                            html.Td(smart_memory(total_power_mem)),
                                            html.Td("-"),
                                        ]
                                    ),
                                ]
                            ),
                        ],
                    ),
                ),
            ),
            _section_card(
                "Backup billing lines",
                "Billable backup services and capacities",
                dmc.SimpleGrid(
                    cols=3,
                    spacing="lg",
                    children=[
                        _metric("Veeam sessions", veeam_defined, "material-symbols:backup-outline"),
                        _metric("Zerto protected VMs", zerto_protected, "material-symbols:shield-outline", color="teal"),
                        _metric("NetBackup stored (GiB)", f"{nb_post_gib:.2f}", "mdi:database-arrow-down-outline", color="orange"),
                    ],
                ),
            ),
            _section_card(
                "S3 Object Storage (billing)",
                "Vault-level objects relevant for billing",
                dmc.Group(
                    gap="xl",
                    children=[
                        dmc.Stack(
                            gap="xs",
                            children=[
                                dmc.Text("Vaults", size="sm", c="#A3AED0"),
                                dmc.Text(f"{vault_count}", fw=700, c="#2B3674"),
                            ],
                        ),
                    ],
                ),
            ),
        ],
    )


def _tab_classic(classic: dict):
    """Classic Compute (KM cluster) billing tab."""
    vm_count  = int(classic.get("vm_count", 0) or 0)
    cpu       = float(classic.get("cpu_total", 0) or 0)
    mem_gb    = float(classic.get("memory_gb", 0) or 0)
    disk_gb   = float(classic.get("disk_gb", 0) or 0)
    vm_list   = classic.get("vm_list", []) or []

    def row_fn(r):
        return html.Tr([
            html.Td(r.get("name")),
            html.Td(r.get("cluster", "-")),
            html.Td(f"{r.get('cpu', 0):.0f}"),
            html.Td(smart_memory(r.get("memory_gb", 0))),
            html.Td(smart_storage(r.get("disk_gb", 0))),
        ])

    return dmc.Stack(gap="lg", children=[
        dmc.SimpleGrid(cols=4, spacing="lg", children=[
            _metric("Total VMs",  f"{vm_count:,}",          "solar:laptop-bold-duotone",  color="blue"),
            _metric("CPU (vCPU)", f"{cpu:.0f}",             "solar:cpu-bold-duotone",     color="blue"),
            _metric("Memory",     smart_memory(mem_gb),     "solar:ram-bold-duotone",     color="blue", ),
            _metric("Disk",       smart_storage(disk_gb),   "solar:hdd-bold-duotone",     color="blue"),
        ]),
        _section_card("Classic VMs", "VMs hosted on Classic (KM) VMware clusters",
            _vm_table(vm_list,
                      ["VM Name", "Cluster", "CPU (vCPU)", "Memory", "Disk"],
                      row_fn,
                      empty_cols=5),
        ),
    ])


def _tab_hyperconv(hyperconv: dict):
    """Hyperconverged (non-KM VMware + Nutanix) billing tab."""
    vm_count    = int(hyperconv.get("vm_count", 0) or 0)
    vmware_only = int(hyperconv.get("vmware_only", 0) or 0)
    nutanix_cnt = int(hyperconv.get("nutanix_count", 0) or 0)
    cpu         = float(hyperconv.get("cpu_total", 0) or 0)
    mem_gb      = float(hyperconv.get("memory_gb", 0) or 0)
    disk_gb     = float(hyperconv.get("disk_gb", 0) or 0)
    vm_list     = hyperconv.get("vm_list", []) or []

    def row_fn(r):
        return html.Tr([
            html.Td(r.get("name")),
            html.Td(r.get("source", "-")),
            html.Td(r.get("cluster", "-")),
            html.Td(f"{r.get('cpu', 0):.0f}"),
            html.Td(smart_memory(r.get("memory_gb", 0))),
            html.Td(smart_storage(r.get("disk_gb", 0))),
        ])

    return dmc.Stack(gap="lg", children=[
        dmc.SimpleGrid(cols=4, spacing="lg", children=[
            _metric("Total VMs",       f"{vm_count:,}",        "solar:laptop-bold-duotone",  color="indigo"),
            _metric("CPU (vCPU)",      f"{cpu:.0f}",           "solar:cpu-bold-duotone",     color="indigo"),
            _metric("Memory",          smart_memory(mem_gb),   "solar:ram-bold-duotone",     color="indigo"),
            _metric("Disk",            smart_storage(disk_gb), "solar:hdd-bold-duotone",     color="indigo"),
        ]),
        _section_card("Platform Breakdown", "VMware-managed vs pure Nutanix (Acropolis)",
            dmc.Group(gap="xl", children=[
                dmc.Stack(gap="xs", children=[
                    dmc.Text("VMware-managed", c="#A3AED0", size="sm"),
                    dmc.Text(f"{vmware_only:,} VMs", fw=700, c="#2B3674"),
                ]),
                dmc.Stack(gap="xs", children=[
                    dmc.Text("Nutanix / Acropolis", c="#A3AED0", size="sm"),
                    dmc.Text(f"{nutanix_cnt:,} VMs", fw=700, c="#2B3674"),
                ]),
            ]),
        ),
        _section_card("Hyperconverged VMs", "VMs on non-KM clusters (VMware-managed Nutanix + Acropolis)",
            _vm_table(vm_list,
                      ["VM Name", "Source", "Cluster", "CPU (vCPU)", "Memory", "Disk"],
                      row_fn,
                      empty_cols=6),
        ),
    ])


def _tab_power(power: dict):
    """Power Mimari (IBM LPAR) billing tab."""
    lpars    = int(power.get("lpar_count", 0) or 0)
    cpu      = float(power.get("cpu_total", 0) or 0)
    mem_gb   = float(power.get("memory_total_gb", 0) or 0)
    vm_list  = power.get("vm_list", []) or []

    def row_fn(r):
        return html.Tr([
            html.Td(r.get("name")),
            html.Td(r.get("source", "Power HMC")),
            html.Td(f"{r.get('cpu', 0):.1f}"),
            html.Td(smart_memory(r.get("memory_gb", 0))),
            html.Td(r.get("state", "-")),
        ])

    return dmc.Stack(gap="lg", children=[
        dmc.SimpleGrid(cols=3, spacing="lg", children=[
            _metric("LPARs",       f"{lpars:,}",          "solar:server-square-bold-duotone", color="grape"),
            _metric("CPU (vCPU)", f"{cpu:.1f}",           "solar:cpu-bold-duotone",           color="grape"),
            _metric("Memory",      smart_memory(mem_gb),  "solar:ram-bold-duotone",           color="grape"),
        ]),
        _section_card("IBM LPARs", "IBM Power LPAR allocation for billing",
            _vm_table(vm_list,
                      ["LPAR Name", "Source", "CPU (vProc)", "Memory", "State"],
                      row_fn,
                      empty_cols=5),
        ),
    ])


def _tab_veeam(backup_assets: dict, backup_totals: dict):
    veeam       = backup_assets.get("veeam", {}) or {}
    veeam_types = veeam.get("session_types", []) or []
    defined     = int(backup_totals.get("veeam_defined_sessions", 0) or 0)

    return dmc.Stack(gap="lg", children=[
        dmc.SimpleGrid(cols=2, spacing="lg", children=[
            _metric("Defined Sessions", f"{defined:,}", "material-symbols:backup-outline"),
            _metric("Session Types",    f"{len(veeam_types):,}", "material-symbols:list-alt-outline", color="teal"),
        ]),
        _section_card("Sessions by Type", "Veeam backup session distribution",
            dmc.Table(
                striped=True, highlightOnHover=True,
                children=[
                    html.Thead(html.Tr([html.Th("Session Type"), html.Th("Defined Sessions")])),
                    html.Tbody(
                        [html.Tr([html.Td(r.get("type")), html.Td(r.get("count", 0))]) for r in veeam_types]
                        if veeam_types
                        else [html.Tr([html.Td("No data", colSpan=2)])],
                    ),
                ],
            ),
        ),
    ])


def _tab_zerto(backup_assets: dict, backup_totals: dict):
    zerto      = backup_assets.get("zerto", {}) or {}
    vpgs       = zerto.get("vpgs", []) or []
    protected  = int(backup_totals.get("zerto_protected_vms", 0) or 0)
    prov_total = float(backup_totals.get("zerto_provisioned_gib", 0) or 0)

    return dmc.Stack(gap="lg", children=[
        dmc.SimpleGrid(cols=2, spacing="lg", children=[
            _metric("Protected VMs",      f"{protected:,}",        "material-symbols:shield-outline", color="teal"),
            _metric("Total Provisioned",  f"{prov_total:.2f} GiB", "solar:hdd-bold-duotone",          color="teal"),
        ]),
        _section_card("VPG Provisioned Storage (last 30 days)", "Max provisioned storage per VPG",
            html.Div(style={"maxHeight": "360px", "overflowY": "auto"}, children=[
                dmc.Table(
                    striped=True, highlightOnHover=True,
                    children=[
                        html.Thead(html.Tr([html.Th("VPG Name"), html.Th("Provisioned (GiB)")])),
                        html.Tbody(
                            [html.Tr([html.Td(r.get("name")), html.Td(f"{r.get('provisioned_storage_gib', 0):.2f}")])
                             for r in vpgs]
                            if vpgs
                            else [html.Tr([html.Td("No data", colSpan=2)])],
                        ),
                    ],
                )
            ]),
        ),
    ])


def _tab_netbackup(backup_assets: dict, backup_totals: dict):
    nb = backup_assets.get("netbackup", {}) or {}
    pre_gib    = float(backup_totals.get("netbackup_pre_dedup_gib", 0) or 0)
    post_gib   = float(backup_totals.get("netbackup_post_dedup_gib", 0) or 0)
    dedup_fact = nb.get("deduplication_factor", "1x")

    return dmc.Stack(gap="lg", children=[
        dmc.SimpleGrid(cols=3, spacing="lg", children=[
            _metric("Pre-Dedup (GiB)",  f"{pre_gib:.2f}",  "mdi:database-lock-outline"),
            _metric("Stored (GiB)",     f"{post_gib:.2f}", "mdi:database-arrow-down-outline", color="teal"),
            _metric("Dedup Factor",     dedup_fact,        "mdi:percent-outline",             color="orange"),
        ]),
        _section_card("Billing Summary",
            "Total backup data transferred vs. stored after deduplication",
            dmc.Table(
                striped=True, highlightOnHover=True,
                children=[
                    html.Thead(html.Tr([html.Th("Metric"), html.Th("Value")])),
                    html.Tbody([
                        html.Tr([html.Td("Pre-Dedup Size"),  html.Td(f"{pre_gib:.2f} GiB")]),
                        html.Tr([html.Td("Post-Dedup Size"), html.Td(f"{post_gib:.2f} GiB")]),
                        html.Tr([html.Td("Dedup Ratio"),     html.Td(dedup_fact)]),
                    ]),
                ],
            ),
        ),
    ])


def _tab_physical_inventory(devices: list[dict]):
    """Physical Inventory tab: Boyner devices table (name, device_role, manufacturer, location). Title-case display."""
    total = len(devices or [])

    def row_fn(r):
        return html.Tr([
            html.Td(title_case(r.get("name") or "") or "-"),
            html.Td(title_case(r.get("device_role_name") or "") or "-"),
            html.Td(title_case(r.get("manufacturer_name") or "") or "-"),
            html.Td(title_case(r.get("location") or "") or "-"),
        ])

    return dmc.Stack(gap="lg", children=[
        dmc.SimpleGrid(cols=1, spacing="lg", children=[
            _metric("Total Physical Devices", f"{total:,}", "solar:server-bold-duotone", color="indigo"),
        ]),
        _section_card(
            "Device List",
            "NetBox physical inventory (tenant Boyner)",
            _vm_table(
                devices or [],
                ["Name", "Device Role", "Manufacturer", "Location"],
                row_fn,
                empty_cols=4,
            ),
        ),
    ])


# ---------------------------------------------------------------------------
# Main content block
# ---------------------------------------------------------------------------

def _customer_content(customer_name: str, time_range: dict | None = None):
    tr   = time_range or default_time_range()
    data = api.get_customer_resources(customer_name or "Boyner", tr)

    totals = data.get("totals", {})
    assets = data.get("assets", {})
    backup_assets = assets.get("backup", {}) or {}
    backup_totals = totals.get("backup", {}) or {}

    # S3 vault metrics (may be empty if customer has no S3 vaults)
    s3_data = api.get_customer_s3_vaults(customer_name or "Boyner", tr)
    has_s3 = bool(s3_data.get("vaults"))

    # Physical inventory (Boyner tenant_id=5): tab always shown for customer
    phys_inv_devices = api.get_physical_inventory_customer()
    has_phys_inv = True

    # --- agent debug logs (NDJSON) ---
    def _agent_log(hypothesis_id: str, message: str, data_obj: dict):
        try:
            import json, time
            with open("/Users/duosis-can/Datalake-Platform-GUI/.cursor/debug.log", "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "id": f"customer_view_{int(time.time()*1000)}",
                    "timestamp": int(time.time() * 1000),
                    "location": "src/pages/customer_view.py:_customer_content",
                    "message": message,
                    "data": data_obj,
                    "runId": "pre-fix",
                    "hypothesisId": hypothesis_id,
                }) + "\n")
        except Exception:
            pass

    _agent_log("H1", "enter _customer_content", {
        "customer_name": customer_name,
        "has_data": bool(data),
        "data_keys": sorted(list(data.keys())) if isinstance(data, dict) else str(type(data)),
        "totals_keys": sorted(list(totals.keys())) if isinstance(totals, dict) else str(type(totals)),
        "assets_keys": sorted(list(assets.keys())) if isinstance(assets, dict) else str(type(assets)),
        "backup_totals_keys": sorted(list(backup_totals.keys())) if isinstance(backup_totals, dict) else str(type(backup_totals)),
    })

    # Values used by Summary "Backup summary" cards (kept here to avoid NameError).
    veeam_defined = int(backup_totals.get("veeam_defined_sessions", 0) or 0)
    zerto_protected = int(backup_totals.get("zerto_protected_vms", 0) or 0)
    netbackup_pre_gib = float(backup_totals.get("netbackup_pre_dedup_gib", 0) or 0)
    netbackup_post_gib = float(backup_totals.get("netbackup_post_dedup_gib", 0) or 0)
    zerto_provisioned_gib = float(backup_totals.get("zerto_provisioned_gib", 0) or 0)
    storage_gb = float(backup_totals.get("ibm_storage_volume_gb", 0) or 0)

    _agent_log("H2", "computed backup metrics", {
        "veeam_defined": veeam_defined,
        "zerto_protected": zerto_protected,
        "netbackup_pre_gib": netbackup_pre_gib,
        "netbackup_post_gib": netbackup_post_gib,
        "zerto_provisioned_gib": zerto_provisioned_gib,
        "storage_gb": storage_gb,
    })

    # Intel (Virtualization tab) aggregates
    intel_asset = assets.get("intel", {}) or {}
    intel_vm_list = intel_asset.get("vm_list", []) or []

    intel_vms = {
        "total": int(totals.get("intel_vms_total", 0) or 0),
        "vmware": int(intel_asset.get("vmware_vm_count", 0) or 0),
        "nutanix": int(intel_asset.get("nutanix_vm_count", 0) or 0),
    }
    intel_cpu = {
        "total": float(totals.get("intel_cpu_total", 0) or 0),
        "vmware": float(intel_asset.get("vmware_cpu_total", 0) or 0),
        "nutanix": float(intel_asset.get("nutanix_cpu_total", 0) or 0),
    }

    intel_mem_raw = intel_asset.get("memory_gb", 0)
    intel_disk_raw = intel_asset.get("disk_gb", 0)

    _agent_log("H4", "intel mem/disk raw", {
        "intel_mem_raw_type": type(intel_mem_raw).__name__,
        "intel_mem_raw_keys": sorted(list(intel_mem_raw.keys())) if isinstance(intel_mem_raw, dict) else None,
        "intel_disk_raw_type": type(intel_disk_raw).__name__,
        "intel_disk_raw_keys": sorted(list(intel_disk_raw.keys())) if isinstance(intel_disk_raw, dict) else None,
    })

    def _coerce_float(x):
        if x is None:
            return 0.0
        if isinstance(x, (int, float)):
            return float(x)
        if isinstance(x, dict):
            for k in ("total", "value", "gb", "amount"):
                if k in x and isinstance(x.get(k), (int, float, str)):
                    try:
                        return float(x.get(k) or 0)
                    except Exception:
                        pass
            return 0.0
        try:
            return float(x)
        except Exception:
            return 0.0

    intel_mem = {"total": _coerce_float(intel_mem_raw)}
    intel_disk = {"total": _coerce_float(intel_disk_raw)}

    # Power / HANA (Backup tab uses these)
    power_asset = assets.get("power", {}) or {}
    power_vm_list = (
        power_asset.get("vm_list")
        or power_asset.get("lpar_list")
        or power_asset.get("lpars")
        or []
    )
    power_lpars = int(totals.get("power_lpar_total", power_asset.get("lpar_count", 0)) or 0)
    power_cpu = float(totals.get("power_cpu_total", power_asset.get("cpu_total", 0)) or 0)
    power_mem = _coerce_float(
        power_asset.get("memory_total_gb", power_asset.get("memory_gb", 0))
    )

    _agent_log("H5", "computed power aggregates", {
        "power_keys": sorted(list(power_asset.keys())) if isinstance(power_asset, dict) else str(type(power_asset)),
        "power_lpars": power_lpars,
        "power_cpu": power_cpu,
        "power_mem": power_mem,
        "power_vm_list_len": len(power_vm_list) if isinstance(power_vm_list, list) else str(type(power_vm_list)),
    })

    _agent_log("H3", "computed intel aggregates", {
        "intel_keys": sorted(list(intel_asset.keys())) if isinstance(intel_asset, dict) else str(type(intel_asset)),
        "intel_vms": intel_vms,
        "intel_cpu": intel_cpu,
        "intel_mem_total": intel_mem.get("total"),
        "intel_disk_total": intel_disk.get("total"),
        "intel_vm_list_len": len(intel_vm_list) if isinstance(intel_vm_list, list) else str(type(intel_vm_list)),
    })

    classic   = assets.get("classic", {}) or {}
    hyperconv = assets.get("hyperconv", {}) or {}

    virt_content = dmc.Tabs(
        color="violet",
        variant="outline",
        radius="md",
        value="classic",
        children=[
            dmc.TabsList(
                children=[
                    dmc.TabsTab("Klasik Mimari", value="classic"),
                    dmc.TabsTab("Hyperconverged Mimari", value="hyperconv"),
                    dmc.TabsTab("Power Mimari", value="power"),
                ]
            ),
            dmc.TabsPanel(value="classic", pt="lg", children=_tab_classic(classic)),
            dmc.TabsPanel(value="hyperconv", pt="lg", children=_tab_hyperconv(hyperconv)),
            dmc.TabsPanel(value="power", pt="lg", children=_tab_power(power_asset)),
        ],
    )

    backup_tabs = dmc.Tabs(
        color="green",
        variant="outline",
        radius="md",
        value="veeam",
        children=[
            dmc.TabsList(
                children=[
                    dmc.TabsTab("Veeam", value="veeam"),
                    dmc.TabsTab("Zerto", value="zerto"),
                    dmc.TabsTab("Netbackup", value="netbackup"),
                ]
            ),
            dmc.TabsPanel(value="veeam", pt="lg", children=_tab_veeam(backup_assets, backup_totals)),
            dmc.TabsPanel(value="zerto", pt="lg", children=_tab_zerto(backup_assets, backup_totals)),
            dmc.TabsPanel(value="netbackup", pt="lg", children=_tab_netbackup(backup_assets, backup_totals)),
        ],
    )

    return {
        "summary": _tab_summary(totals, assets),
        "virt": virt_content,
        "backup": dmc.Stack(
            gap="lg",
            children=[
                dmc.SimpleGrid(
                    cols=3,
                    spacing="lg",
                    children=[
                        metric_card("HANA VMs (LPARs)", power_lpars, "solar:laptop-bold-duotone", color="teal"),
                        metric_card("Total CPU (Power HMC)", f"{power_cpu:.1f}", "solar:cpu-bold-duotone"),
                        metric_card("Total Memory (Power HMC, GB)", f"{power_mem:.1f}", "solar:ram-bold-duotone", color="orange"),
                    ],
                ),
                backup_tabs,
            ],
        ),
        "billing": _tab_billing(totals, assets, backup_totals, s3_data),
        "s3": html.Div(
            id="s3-customer-metrics-panel",
            style={"padding": "0 30px"},
            children=build_customer_s3_panel(customer_name or "Boyner", s3_data, tr, None) if has_s3 else html.Div(),
        ),
        "has_s3": has_s3,
        "phys_inv": _tab_physical_inventory(phys_inv_devices),
        "has_phys_inv": has_phys_inv,
    }


# ---------------------------------------------------------------------------
# Page builders
# ---------------------------------------------------------------------------

def build_customer_layout(time_range=None, selected_customer=None):
    tr = time_range or default_time_range()
    chosen = selected_customer or "Boyner"

    content = _customer_content(chosen, tr)
    has_s3 = bool(content.get("has_s3"))
    has_phys_inv = bool(content.get("has_phys_inv"))

    tabs_list = dmc.TabsList(
        style={"paddingTop": "8px"},
        children=[
            dmc.TabsTab("Summary", value="summary"),
            dmc.TabsTab("Virtualization", value="virt"),
            dmc.TabsTab("Backup", value="backup"),
            dmc.TabsTab("Billing", value="billing"),
            dmc.TabsTab("Physical Inventory", value="phys-inv") if has_phys_inv else None,
            dmc.TabsTab("S3", value="s3") if has_s3 else None,
        ],
    )

    header = create_detail_header(
        title="Customer View",
        back_href="/",
        back_label="Overview",
        subtitle_badge=f"­şæñ {chosen}",
        subtitle_color="teal",
        time_range=tr,
        icon="solar:users-group-two-rounded-bold-duotone",
        tabs=tabs_list,
    )

    intro_card = dmc.SimpleGrid(
        cols=3,
        spacing="lg",
        style={"padding": "0 30px", "marginBottom": "24px"},
        children=[
            html.Div(
                className="nexus-card",
                style={"padding": "24px"},
                children=[
                    dmc.Group(justify="space-between", mb="lg", children=[
                        dmc.Group(gap="sm", children=[
                            dmc.ThemeIcon(
                                size="xl",
                                variant="light",
                                color="indigo",
                                radius="md",
                                children=DashIconify(icon="solar:users-group-two-rounded-bold-duotone", width=30),
                            ),
                            dmc.Stack(
                                gap=0,
                                children=[
                                    dmc.Text(chosen, fw=700, size="lg", c="#2B3674"),
                                    dmc.Text("Billing assets", size="sm", c="#A3AED0", fw=500),
                                ],
                            ),
                        ]),
                    ]),
                    dmc.Text(
                        "All metrics show resources allocated/provisioned to this customer across all platforms.",
                        size="sm",
                        c="#A3AED0",
                    ),
                ],
            ),
        ],
    )

    return html.Div(
        children=[
            dmc.Tabs(
                color="indigo",
                variant="pills",
                radius="md",
                value="summary",
                children=[
                    header,
                    intro_card,
                    dmc.TabsPanel(
                        value="summary",
                        children=dmc.Stack(gap="lg", style={"padding": "0 30px"}, children=[content.get("summary")]),
                    ),
                    dmc.TabsPanel(
                        value="virt",
                        children=html.Div(style={"padding": "0 30px"}, children=[content.get("virt")]),
                    ),
                    dmc.TabsPanel(
                        value="backup",
                        children=html.Div(style={"padding": "0 30px"}, children=[content.get("backup")]),
                    ),
                    dmc.TabsPanel(
                        value="billing",
                        children=dmc.Stack(gap="lg", style={"padding": "0 30px"}, children=[content.get("billing")]),
                    ),
                    dmc.TabsPanel(
                        value="phys-inv",
                        children=dmc.Stack(gap="lg", style={"padding": "0 30px"}, children=[content.get("phys_inv")]),
                    )
                    if has_phys_inv
                    else None,
                    dmc.TabsPanel(
                        value="s3",
                        children=content.get("s3") if has_s3 else html.Div(),
                    )
                    if has_s3
                    else None,
                ],
            )
        ]
    )


def layout():
    return build_customer_layout(default_time_range())
