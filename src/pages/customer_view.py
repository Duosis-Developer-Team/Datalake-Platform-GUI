# Customer View — Billing-focused resource breakdown per customer.
# Tab hierarchy: Summary | Virtualization (Classic / Hyperconverged / Power) | Backup
import dash
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objs as go

from src.services.shared import service
from src.utils.time_range import default_time_range
from src.components.header import create_detail_header
from src.pages.home import metric_card


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
    """Summary tab — aggregated billing overview."""
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


# ---------------------------------------------------------------------------
# Main content block
# ---------------------------------------------------------------------------

def _customer_content(customer_name: str, time_range: dict | None = None):
    tr   = time_range or default_time_range()
    data = service.get_customer_resources(customer_name or "Boyner", tr)

    totals = data.get("totals", {})
    assets = data.get("assets", {})
    backup_assets = assets.get("backup", {}) or {}
    backup_totals = totals.get("backup", {}) or {}

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

    return [
        dmc.Tabs(
            color="indigo",
            variant="pills",
            radius="md",
            value="summary",
            children=[
                dmc.TabsList(
                    children=[
                        dmc.TabsTab("Summary",        value="summary"),
                        dmc.TabsTab("Virtualization", value="virt"),
                        dmc.TabsTab("Backup",         value="backup"),
                    ],
                    style={"padding": "0 30px", "marginBottom": "24px"},
                ),

                # ── Summary ──────────────────────────────────────────────
                dmc.TabsPanel(
                    value="summary",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[
                            dmc.SimpleGrid(
                                cols=3,
                                spacing="lg",
                                children=[
                                    metric_card("Total Customer VMs", totals.get("vms_total", 0), "solar:laptop-bold-duotone", color="teal"),
                                    metric_card("Intel VMs", totals.get("intel_vms_total", 0), "solar:laptop-bold-duotone"),
                                    metric_card("HANA LPARs", totals.get("power_lpar_total", 0), "solar:server-square-bold-duotone", color="orange"),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Compute summary", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    dmc.SimpleGrid(
                                        cols=3,
                                        spacing="lg",
                                        children=[
                                            metric_card("Total CPU (vCPU)", f"{totals.get('cpu_total', 0.0):.1f}", "solar:cpu-bold-duotone"),
                                            metric_card("Intel CPU (vCPU)", f"{totals.get('intel_cpu_total', 0.0):.1f}", "solar:cpu-bold-duotone"),
                                            metric_card("HANA CPU (vCPU)", f"{totals.get('power_cpu_total', 0.0):.1f}", "solar:cpu-bold-duotone", color="orange"),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Backup summary", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    dmc.SimpleGrid(
                                        cols=3,
                                        spacing="lg",
                                        children=[
                                            metric_card("Veeam sessions", veeam_defined, "material-symbols:backup-outline"),
                                            metric_card("Protected VMs (Zerto)", zerto_protected, "material-symbols:shield-outline", color="teal"),
                                            metric_card("IBM storage volume (GB)", f"{storage_gb:.1f}", "solar:hdd-bold-duotone", color="orange"),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Backup capacity (billing view)", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    dmc.SimpleGrid(
                                        cols=3,
                                        spacing="lg",
                                        children=[
                                            metric_card("NetBackup pre‑dedup (GiB)", f"{netbackup_pre_gib:.2f}", "mdi:database-lock-outline"),
                                            metric_card("NetBackup stored (GiB)", f"{netbackup_post_gib:.2f}", "mdi:database-arrow-down-outline", color="teal"),
                                            metric_card("Zerto max provisioned (GiB)", f"{zerto_provisioned_gib:.2f}", "solar:hdd-bold-duotone", color="orange"),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
                dmc.TabsPanel(
                    value="virt",
                    children=html.Div(
                        style={"padding": "0 30px"},
                        children=[
                            dmc.SimpleGrid(
                                cols=4,
                                spacing="lg",
                                children=[
                                    metric_card("Total Intel VMs", intel_vms.get("total", 0), "solar:laptop-bold-duotone", color="teal"),
                                    metric_card("Total CPU (Intel)", intel_cpu.get("total", 0.0), "solar:cpu-bold-duotone"),
                                    metric_card("Total Memory (Intel, GB)", f"{intel_mem.get('total', 0.0):.1f}", "solar:ram-bold-duotone"),
                                    metric_card("Total Disk (Intel, GB)", f"{intel_disk.get('total', 0.0):.1f}", "solar:hdd-bold-duotone", color="orange"),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Platform breakdown (Intel)", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    dmc.Stack(
                                        gap="sm",
                                        children=[
                                            dmc.Group(
                                                justify="space-between",
                                                children=[
                                                    dmc.Text("VMware", size="sm", c="#A3AED0"),
                                                    dmc.Text(
                                                        f"VMs: {intel_vms.get('vmware', 0)}, CPU: {intel_cpu.get('vmware', 0.0):.1f}",
                                                        size="sm",
                                                        fw=600,
                                                    ),
                                                ],
                                            ),
                                            dmc.Group(
                                                justify="space-between",
                                                children=[
                                                    dmc.Text("Nutanix", size="sm", c="#A3AED0"),
                                                    dmc.Text(
                                                        f"VMs: {intel_vms.get('nutanix', 0)}, CPU: {intel_cpu.get('nutanix', 0.0):.1f}",
                                                        size="sm",
                                                        fw=600,
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
                                    html.H3("Intel VMs of customer", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    html.Div(
                                        style={"maxHeight": "400px", "overflowY": "auto"},
                                        children=[
                                            dmc.Table(
                                                striped=True,
                                                highlightOnHover=True,
                                                children=[
                                                    html.Thead(
                                                        html.Tr(
                                                            [
                                                                html.Th("VM"),
                                                                html.Th("Source"),
                                                                html.Th("CPU (vCPU)"),
                                                                html.Th("Memory (GB)"),
                                                                html.Th("Disk (GB)"),
                                                            ]
                                                        )
                                                    ),
                                                    html.Tbody(
                                                        [
                                                            html.Tr(
                                                                [
                                                                    html.Td(row.get("name")),
                                                                    html.Td(row.get("source")),
                                                                    html.Td(f"{row.get('cpu', 0.0):.1f}"),
                                                                    html.Td(f"{row.get('memory_gb', 0.0):.1f}"),
                                                                    html.Td(f"{row.get('disk_gb', 0.0):.1f}"),
                                                                ]
                                                            )
                                                            for row in intel_vm_list
                                                        ]
                                                        if intel_vm_list
                                                        else [html.Tr([html.Td("No data", colSpan=5)])]
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),

                # ── Backup (nested) ───────────────────────────────────────
                dmc.TabsPanel(
                    value="backup",
                    children=html.Div(
                        style={"padding": "0 30px"},
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
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("HANA resource distribution", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    dcc.Graph(
                                        figure={
                                            "data": [
                                                go.Bar(name="CPU (vCPU)", x=["HANA"], y=[power_cpu]),
                                                go.Bar(name="Memory (GB)", x=["HANA"], y=[power_mem]),
                                            ],
                                            "layout": go.Layout(
                                                barmode="group",
                                                margin={"l": 40, "r": 10, "t": 10, "b": 40},
                                                height=260,
                                            ),
                                        },
                                        config={"displayModeBar": False},
                                    ),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("HANA VMs (LPARs) of customer", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    html.Div(
                                        style={"maxHeight": "400px", "overflowY": "auto"},
                                        children=[
                                            dmc.Table(
                                                striped=True,
                                                highlightOnHover=True,
                                                children=[
                                                    html.Thead(
                                                        html.Tr(
                                                            [
                                                                html.Th("LPAR"),
                                                                html.Th("Source"),
                                                                html.Th("CPU (vCPU)"),
                                                                html.Th("Memory (GB)"),
                                                                html.Th("State"),
                                                            ]
                                                        )
                                                    ),
                                                    html.Tbody(
                                                        [
                                                            html.Tr(
                                                                [
                                                                    html.Td(row.get("name")),
                                                                    html.Td(row.get("source")),
                                                                    html.Td(f"{row.get('cpu', 0.0):.1f}"),
                                                                    html.Td(f"{row.get('memory_gb', 0.0):.1f}"),
                                                                    html.Td(row.get("state") or "-"),
                                                                ]
                                                            )
                                                            for row in power_vm_list
                                                        ]
                                                        if power_vm_list
                                                        else [html.Tr([html.Td("No data", colSpan=5)])]
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
            ],
        )
    ]


# ---------------------------------------------------------------------------
# Page builders
# ---------------------------------------------------------------------------

def build_customer_layout(time_range=None, selected_customer=None):
    tr     = time_range or default_time_range()
    chosen = "Boyner"
    return html.Div([
        create_detail_header(
            title="Customer View",
            back_href="/",
            back_label="Overview",
            subtitle_badge="👤 Boyner",
            subtitle_color="teal",
            time_range=tr,
            icon="solar:users-group-two-rounded-bold-duotone",
            tabs=None,
        ),
        dmc.SimpleGrid(
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
                                dmc.ThemeIcon(size="xl", variant="light", color="indigo", radius="md",
                                              children=DashIconify(icon="solar:users-group-two-rounded-bold-duotone", width=30)),
                                dmc.Stack(gap=0, children=[
                                    dmc.Text("Boyner", fw=700, size="lg", c="#2B3674"),
                                    dmc.Text("Billing assets", size="sm", c="#A3AED0", fw=500),
                                ]),
                            ]),
                        ]),
                        dmc.Text(
                            "All metrics show resources allocated/provisioned to this customer across all platforms.",
                            size="sm", c="#A3AED0",
                        ),
                    ],
                ),
            ],
        ),
        html.Div(id="customer-view-content", children=_customer_content(chosen, tr)),
    ])


def layout():
    return build_customer_layout(default_time_range())
