from __future__ import annotations
# Customer View - Billing-focused resource breakdown per customer.
# Tab hierarchy: Summary | Virtualization (Classic / Hyperconverged / Power) | Backup
import json
import dash
from dash import html, dcc, callback, Input, Output, State
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objs as go

from src.services import api_client as api
from src.utils.time_range import default_time_range
from src.utils.export_helpers import (
    records_to_dataframe,
    build_report_info_df,
    dataframes_to_excel_with_meta,
    csv_bytes_with_report_header,
    dash_send_excel_workbook,
    dash_send_csv_bytes,
)
from src.utils.format_units import smart_storage, smart_memory, smart_cpu, pct_float, title_case
from src.components.header import create_detail_header
from src.pages.home import metric_card
from src.components.s3_panel import build_customer_s3_panel


# ---------------------------------------------------------------------------
# Shared UI helpers
# ---------------------------------------------------------------------------


def _intel_vm_cpu_breakdown(totals: dict, intel_asset: dict) -> tuple[dict, dict]:
    """
    Map customer-api nested assets.intel (vms/cpu) to UI breakdown dicts.
    Legacy flat keys (vmware_vm_count, etc.) are not populated by the API.
    """
    intel_vms_sub = intel_asset.get("vms", {}) or {}
    intel_cpu_sub = intel_asset.get("cpu", {}) or {}
    intel_vms = {
        "total": int(totals.get("intel_vms_total", 0) or 0),
        "vmware": int(intel_vms_sub.get("vmware", 0) or 0),
        "nutanix": int(intel_vms_sub.get("nutanix", 0) or 0),
    }
    intel_cpu = {
        "total": float(totals.get("intel_cpu_total", 0) or 0),
        "vmware": float(intel_cpu_sub.get("vmware", 0) or 0),
        "nutanix": float(intel_cpu_sub.get("nutanix", 0) or 0),
    }
    return intel_vms, intel_cpu


def _backup_storage_volume_gb(backup_totals: dict) -> float:
    """Backup IBM storage volume from totals.backup (primary key: storage_volume_gb)."""
    return float(
        backup_totals.get("storage_volume_gb", backup_totals.get("ibm_storage_volume_gb", 0)) or 0
    )


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


def format_vm_metric_value(value, decimals: int = 1, suffix: str = "") -> str:
    """Plain-text metric for VM table cells (unit-testable)."""
    v = float(value or 0)
    body = f"{v:.{decimals}f}"
    if suffix == "%":
        return f"{body}%"
    return f"{body}{suffix}" if suffix else body


def _vm_metric_td(value, decimals: int = 1, suffix: str = ""):
    """Right-aligned numeric cell for VM/LPAR billing tables."""
    return html.Td(
        format_vm_metric_value(value, decimals, suffix),
        style={
            "textAlign": "right",
            "fontVariantNumeric": "tabular-nums",
            "fontSize": "0.8125rem",
            "color": "#2B3674",
            "fontWeight": 600,
            "verticalAlign": "middle",
        },
    )


def _vm_table(
    vm_list: list,
    columns: list[str],
    row_fn,
    empty_cols: int = 5,
    numeric_col_indices: frozenset | None = None,
    comfortable: bool = False,
):
    """Generic scrollable VM/LPAR billing table (horizontal + vertical scroll when wide).

    When comfortable=True, applies customer-vm-table-wrap / customer-vm-table classes
    for padding, min-width, and sticky header (see assets/style.css).
    """
    numeric_col_indices = numeric_col_indices or frozenset()
    header_cells = [
        html.Th(
            c,
            style={
                "textAlign": "right" if i in numeric_col_indices else "left",
                "verticalAlign": "bottom",
            },
        )
        for i, c in enumerate(columns)
    ]
    wrap_kwargs: dict = {
        "style": {
            "maxHeight": "420px",
            "overflowY": "auto",
            "overflowX": "auto",
            "WebkitOverflowScrolling": "touch",
        },
        "children": [
            dmc.Table(
                striped=True,
                highlightOnHover=True,
                withColumnBorders=True,
                className="customer-vm-table" if comfortable else None,
                children=[
                    html.Thead(html.Tr(header_cells)),
                    html.Tbody(
                        [row_fn(r) for r in vm_list]
                        if vm_list
                        else [html.Tr([html.Td("No data", colSpan=empty_cols)])]
                    ),
                ],
            )
        ],
    }
    if comfortable:
        wrap_kwargs["className"] = "customer-vm-table-wrap"
    return html.Div(**wrap_kwargs)


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


def _availability_cell(vm_name: str | None, vm_outage_counts: dict | None):
    """vm_outage_counts: lowercased VM name -> number of downtime records in period."""
    key = (vm_name or "").strip().lower()
    c = int((vm_outage_counts or {}).get(key, 0))
    if c <= 0:
        return dmc.Badge("OK", color="green", size="sm", variant="light")
    return dmc.Badge(f"{c} outage(s)", color="red", size="sm", variant="light")


def _export_cell(v):
    if isinstance(v, (dict, list)):
        try:
            return json.dumps(v, ensure_ascii=False, default=str)[:8000]
        except Exception:
            return str(v)[:8000]
    return v


def _dict_to_wide_row(d: dict | None) -> list[dict]:
    if not isinstance(d, dict) or not d:
        return []
    return [{str(k): _export_cell(d[k]) for k in sorted(d.keys(), key=str)}]


def _vm_records_for_export(vm_list: list | None) -> list[dict]:
    if not vm_list:
        return []
    out: list[dict] = []
    for r in vm_list:
        if isinstance(r, dict):
            out.append({str(k): _export_cell(v) for k, v in r.items()})
    return out


def _device_records_for_export(devices: list | None) -> list[dict]:
    return _vm_records_for_export(devices)


def _s3_vault_rows(s3_data: dict | None) -> list[dict]:
    if not isinstance(s3_data, dict):
        return []
    vaults = s3_data.get("vaults") or []
    out: list[dict] = []
    for v in vaults:
        if isinstance(v, dict):
            out.append({str(k): _export_cell(x) for k, x in v.items()})
    return out


def _build_customer_export_sheets(
    customer_name: str,
    totals: dict,
    backup_totals: dict,
    assets: dict,
    classic: dict,
    hyperconv: dict,
    pure_nx: dict,
    power_asset: dict,
    s3_data: dict,
    phys_inv_devices: list,
) -> dict[str, list[dict]]:
    sheets: dict[str, list[dict]] = {}
    sheets["Customer_Meta"] = [{"customer": customer_name}]
    trow = _dict_to_wide_row(totals)
    if trow:
        sheets["Summary_Totals"] = trow
    brow = _dict_to_wide_row(backup_totals)
    if brow:
        sheets["Backup_Totals"] = brow

    for label, block in (
        ("Assets_Classic_Block", classic),
        ("Assets_Hyperconv_Block", hyperconv),
        ("Assets_Pure_Nutanix_Block", pure_nx),
        ("Assets_Power_Block", power_asset),
    ):
        w = _dict_to_wide_row(block)
        if w:
            sheets[label] = w

    intel_asset = assets.get("intel", {}) or {}
    iw = _dict_to_wide_row(intel_asset)
    if iw:
        sheets["Assets_Intel_Aggregate"] = iw

    sheets["Classic_VMs"] = _vm_records_for_export(classic.get("vm_list") or [])
    sheets["HyperConv_VMs"] = _vm_records_for_export(hyperconv.get("vm_list") or [])
    sheets["Pure_Nutanix_VMs"] = _vm_records_for_export(pure_nx.get("vm_list") or [])
    pl = (
        power_asset.get("vm_list")
        or power_asset.get("lpar_list")
        or power_asset.get("lpars")
        or []
    )
    sheets["Power_LPARS"] = _vm_records_for_export(pl)

    backup_assets = assets.get("backup", {}) or {}
    for bk, key in (
        ("Backup_Veeam_Detail", "veeam"),
        ("Backup_Zerto_Detail", "zerto"),
        ("Backup_Netbackup_Detail", "netbackup"),
    ):
        sub = backup_assets.get(key)
        if isinstance(sub, dict) and sub:
            br = _dict_to_wide_row(sub)
            if br:
                sheets[bk] = br

    bill = _dict_to_wide_row(
        {
            "intel_vms_total": totals.get("intel_vms_total"),
            "power_lpar_total": totals.get("power_lpar_total"),
            "vms_total": totals.get("vms_total"),
            "intel_cpu_total": totals.get("intel_cpu_total"),
            "power_cpu_total": totals.get("power_cpu_total"),
        }
    )
    if bill:
        sheets["Billing_Key_Metrics"] = bill

    sv = _s3_vault_rows(s3_data)
    if sv:
        sheets["S3_Vaults"] = sv

    phys = _device_records_for_export(phys_inv_devices)
    if phys:
        sheets["Physical_Inventory"] = phys

    return sheets


def _deleted_vms_panel(deleted_names: list[str] | None):
    """Names-only list for VMs whose name starts with underscore (removed inventory)."""
    names = [n for n in (deleted_names or []) if n]
    if not names:
        return html.Div()
    return html.Div(
        style={"marginTop": "16px"},
        children=[
            dmc.Text("Deleted VMs (name prefix _)", size="sm", fw=600, c="#2B3674", mb="xs"),
            dmc.Text(
                "These VMs are not included in the main list.",
                size="xs",
                c="dimmed",
                mb="sm",
            ),
            html.Div(
                style={"maxHeight": "200px", "overflowY": "auto"},
                children=[
                    dmc.Table(
                        striped=True,
                        highlightOnHover=True,
                        children=[
                            html.Thead(html.Tr([html.Th("VM name")])),
                            html.Tbody(
                                [html.Tr([html.Td(n)]) for n in sorted(names)],
                            ),
                        ],
                    )
                ],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Tab content builders
# ---------------------------------------------------------------------------

def _tab_summary(totals: dict, assets: dict):
    """Summary tab: aggregated billing overview."""
    classic   = assets.get("classic", {})
    hyperconv = assets.get("hyperconv", {})
    pure_nx   = assets.get("pure_nutanix", {}) or {}
    power     = assets.get("power", {})

    classic_vms   = int(classic.get("vm_count", 0) or 0)
    hyperconv_vms = int(hyperconv.get("vm_count", 0) or 0)
    pure_nx_vms   = int(pure_nx.get("vm_count", 0) or 0)
    power_lpars   = int(power.get("lpar_count", 0) or 0)
    total_vms     = int(totals.get("vms_total", 0) or 0)

    classic_cpu   = float(classic.get("cpu_total", 0) or 0)
    hyperconv_cpu = float(hyperconv.get("cpu_total", 0) or 0)
    pure_nx_cpu   = float(pure_nx.get("cpu_total", 0) or 0)
    power_cpu     = float(power.get("cpu_total", 0) or 0)

    classic_mem   = float(classic.get("memory_gb", 0) or 0)
    hyperconv_mem = float(hyperconv.get("memory_gb", 0) or 0)
    pure_nx_mem   = float(pure_nx.get("memory_gb", 0) or 0)
    power_mem     = float(power.get("memory_total_gb", 0) or 0)

    classic_disk   = float(classic.get("disk_gb", 0) or 0)
    hyperconv_disk = float(hyperconv.get("disk_gb", 0) or 0)
    pure_nx_disk   = float(pure_nx.get("disk_gb", 0) or 0)

    backup_totals = totals.get("backup", {}) or {}
    veeam_defined   = int(backup_totals.get("veeam_defined_sessions", 0) or 0)
    zerto_protected = int(backup_totals.get("zerto_protected_vms", 0) or 0)
    nb_pre_gib      = float(backup_totals.get("netbackup_pre_dedup_gib", 0) or 0)
    nb_post_gib     = float(backup_totals.get("netbackup_post_dedup_gib", 0) or 0)
    zerto_prov_gib  = float(backup_totals.get("zerto_provisioned_gib", 0) or 0)

    summary_grid = [
        _metric("Total Instances",   f"{total_vms:,}",     "solar:laptop-bold-duotone",          color="teal"),
        _metric("Classic VMs",        f"{classic_vms:,}",   "solar:laptop-bold-duotone",          color="blue"),
        _metric("Hyperconverged VMs", f"{hyperconv_vms:,}", "solar:laptop-bold-duotone",          color="indigo"),
        _metric("Pure Nutanix (AHV)", f"{pure_nx_vms:,}",   "solar:laptop-bold-duotone",          color="cyan"),
        _metric("Power LPARs",        f"{power_lpars:,}",   "solar:server-square-bold-duotone",   color="grape"),
    ]

    return dmc.Stack(gap="lg", children=[
        # VM count overview
        _section_card("VM / LPAR Summary", "Total provisioned instances per compute type",
            dmc.SimpleGrid(cols=5, spacing="lg", children=summary_grid),
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
                        ("Pure Nutanix (AHV)",    pure_nx_cpu,   pure_nx_mem,   pure_nx_disk),
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
                _metric("Zerto Max Provisioned",    f"{zerto_prov_gib:.2f} GiB", "solar:database-bold-duotone",  color="teal"),
                _metric("Pre-Dedup (GiB)",          f"{nb_pre_gib:.2f}",    "mdi:database-lock-outline",     color="orange"),
            ]),
        ),
    ])


def _tab_billing(totals: dict, assets: dict, backup_totals: dict, s3_data: dict | None = None):
    """Billing tab: invoice-style view combining compute, backup and S3."""
    classic   = assets.get("classic", {}) or {}
    hyperconv = assets.get("hyperconv", {}) or {}
    pure_nx   = assets.get("pure_nutanix", {}) or {}
    power     = assets.get("power", {}) or {}

    total_vms   = int(totals.get("vms_total", 0) or 0)
    total_cpu   = float(totals.get("cpu_total", 0.0) or 0.0)
    total_intel_mem = (
        float(classic.get("memory_gb", 0) or 0)
        + float(hyperconv.get("memory_gb", 0) or 0)
        + float(pure_nx.get("memory_gb", 0) or 0)
    )
    total_intel_disk = (
        float(classic.get("disk_gb", 0) or 0)
        + float(hyperconv.get("disk_gb", 0) or 0)
        + float(pure_nx.get("disk_gb", 0) or 0)
    )
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
                    _metric("Intel Disk (GB)", smart_storage(total_intel_disk), "solar:database-bold-duotone", color="orange"),
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
                                            html.Td("Pure Nutanix (AHV)"),
                                            html.Td(f"{int(pure_nx.get('vm_count', 0) or 0):,}"),
                                            html.Td(f"{float(pure_nx.get('cpu_total', 0) or 0):.1f}"),
                                            html.Td(smart_memory(float(pure_nx.get('memory_gb', 0) or 0))),
                                            html.Td(smart_storage(float(pure_nx.get('disk_gb', 0) or 0))),
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


def _tab_classic(classic: dict, vm_outage_counts: dict | None = None):
    """Classic Compute (KM cluster) billing tab."""
    vm_count = int(classic.get("vm_count", 0) or 0)
    cpu = float(classic.get("cpu_total", 0) or 0)
    mem_gb = float(classic.get("memory_gb", 0) or 0)
    disk_gb = float(classic.get("disk_gb", 0) or 0)
    vm_list = classic.get("vm_list", []) or []
    deleted = classic.get("deleted_vm_list", []) or []

    def row_fn(r):
        return html.Tr([
            html.Td(r.get("name")),
            html.Td(r.get("cluster", "-")),
            _vm_metric_td(r.get("cpu", 0), decimals=0),
            _vm_metric_td(r.get("cpu_mhz_max", 0), suffix="%"),
            _vm_metric_td(r.get("cpu_mhz_avg", 0), suffix="%"),
            _vm_metric_td(r.get("cpu_mhz_min", 0), suffix="%"),
            html.Td(
                smart_memory(r.get("memory_gb", 0)),
                style={
                    "textAlign": "right",
                    "fontVariantNumeric": "tabular-nums",
                    "fontSize": "0.8125rem",
                    "verticalAlign": "middle",
                },
            ),
            _vm_metric_td(r.get("mem_pct_max", 0), suffix="%"),
            _vm_metric_td(r.get("mem_pct_avg", 0), suffix="%"),
            _vm_metric_td(r.get("mem_pct_min", 0), suffix="%"),
            html.Td(
                smart_storage(r.get("disk_gb", 0)),
                style={
                    "textAlign": "right",
                    "fontVariantNumeric": "tabular-nums",
                    "fontSize": "0.8125rem",
                    "verticalAlign": "middle",
                },
            ),
            _vm_metric_td(r.get("disk_used_min_gb", 0), suffix=" GiB"),
            _vm_metric_td(r.get("disk_used_max_gb", 0), suffix=" GiB"),
            html.Td(_availability_cell(r.get("name"), vm_outage_counts)),
        ])

    cols = [
        "VM Name",
        "Cluster",
        "CPU (vCPU)",
        "CPU % max",
        "CPU % avg",
        "CPU % min",
        "Memory",
        "Mem % max",
        "Mem % avg",
        "Mem % min",
        "Disk (prov.)",
        "Disk used min (GiB)",
        "Disk used max (GiB)",
        "Availability",
    ]
    _classic_numeric_cols = frozenset(range(2, 13))
    return dmc.Stack(
        gap="lg",
        children=[
            dmc.SimpleGrid(
                cols=4,
                spacing="lg",
                children=[
                    _metric("Total VMs", f"{vm_count:,}", "solar:laptop-bold-duotone", color="blue"),
                    _metric("CPU (vCPU)", f"{cpu:.0f}", "solar:cpu-bold-duotone", color="blue"),
                    _metric("Memory", smart_memory(mem_gb), "solar:ram-bold-duotone", color="blue"),
                    _metric("Disk", smart_storage(disk_gb), "solar:database-bold-duotone", color="blue"),
                ],
            ),
            _section_card(
                "Classic VMs",
                "VMs hosted on Classic (KM) VMware clusters — usage min/avg/max over report period",
                dmc.Stack(
                    gap="md",
                    children=[
                        _vm_table(
                            vm_list,
                            cols,
                            row_fn,
                            empty_cols=len(cols),
                            numeric_col_indices=_classic_numeric_cols,
                            comfortable=True,
                        ),
                        _deleted_vms_panel(deleted),
                    ],
                ),
            ),
        ],
    )


def _tab_hyperconv(
    hyperconv: dict,
    pure_nutanix: dict | None = None,
    vm_outage_counts: dict | None = None,
):
    """Hyperconverged (non-KM VMware + Nutanix) billing tab."""
    pure_nutanix = pure_nutanix or {}
    vm_count = int(hyperconv.get("vm_count", 0) or 0)
    vmware_only = int(hyperconv.get("vmware_only", 0) or 0)
    nutanix_cnt = int(hyperconv.get("nutanix_count", 0) or 0)
    pure_nx_vms = int(pure_nutanix.get("vm_count", 0) or 0)
    cpu = float(hyperconv.get("cpu_total", 0) or 0)
    mem_gb = float(hyperconv.get("memory_gb", 0) or 0)
    disk_gb = float(hyperconv.get("disk_gb", 0) or 0)
    vm_list = hyperconv.get("vm_list", []) or []
    deleted = hyperconv.get("deleted_vm_list", []) or []

    def row_fn(r):
        return html.Tr([
            html.Td(r.get("name")),
            html.Td(r.get("source", "-")),
            html.Td(r.get("cluster", "-")),
            _vm_metric_td(r.get("cpu", 0), decimals=0),
            _vm_metric_td(r.get("cpu_mhz_max", 0), suffix="%"),
            _vm_metric_td(r.get("cpu_mhz_avg", 0), suffix="%"),
            _vm_metric_td(r.get("cpu_mhz_min", 0), suffix="%"),
            html.Td(
                smart_memory(r.get("memory_gb", 0)),
                style={
                    "textAlign": "right",
                    "fontVariantNumeric": "tabular-nums",
                    "fontSize": "0.8125rem",
                    "verticalAlign": "middle",
                },
            ),
            _vm_metric_td(r.get("mem_pct_max", 0), suffix="%"),
            _vm_metric_td(r.get("mem_pct_avg", 0), suffix="%"),
            _vm_metric_td(r.get("mem_pct_min", 0), suffix="%"),
            html.Td(
                smart_storage(r.get("disk_gb", 0)),
                style={
                    "textAlign": "right",
                    "fontVariantNumeric": "tabular-nums",
                    "fontSize": "0.8125rem",
                    "verticalAlign": "middle",
                },
            ),
            _vm_metric_td(r.get("disk_used_min_gb", 0), suffix=" GiB"),
            _vm_metric_td(r.get("disk_used_max_gb", 0), suffix=" GiB"),
            html.Td(_availability_cell(r.get("name"), vm_outage_counts)),
        ])

    cols = [
        "VM Name",
        "Source",
        "Cluster",
        "CPU (vCPU)",
        "CPU % max",
        "CPU % avg",
        "CPU % min",
        "Memory",
        "Mem % max",
        "Mem % avg",
        "Mem % min",
        "Disk (prov.)",
        "Disk used min (GiB)",
        "Disk used max (GiB)",
        "Availability",
    ]
    _hyperconv_numeric_cols = frozenset(range(3, 14))
    return dmc.Stack(
        gap="lg",
        children=[
            dmc.SimpleGrid(
                cols=4,
                spacing="lg",
                children=[
                    _metric("Total VMs", f"{vm_count:,}", "solar:laptop-bold-duotone", color="indigo"),
                    _metric("CPU (vCPU)", f"{cpu:.0f}", "solar:cpu-bold-duotone", color="indigo"),
                    _metric("Memory", smart_memory(mem_gb), "solar:ram-bold-duotone", color="indigo"),
                    _metric("Disk", smart_storage(disk_gb), "solar:database-bold-duotone", color="indigo"),
                ],
            ),
            _section_card(
                "Platform Breakdown",
                "VMware non-KM vs Nutanix on VMware-managed clusters vs Pure Nutanix (AHV-only clusters)",
                dmc.Group(
                    gap="xl",
                    children=[
                        dmc.Stack(
                            gap="xs",
                            children=[
                                dmc.Text("VMware (non-KM cluster)", c="#A3AED0", size="sm"),
                                dmc.Text(f"{vmware_only:,} VMs", fw=700, c="#2B3674"),
                            ],
                        ),
                        dmc.Stack(
                            gap="xs",
                            children=[
                                dmc.Text("Nutanix (VMware-managed)", c="#A3AED0", size="sm"),
                                dmc.Text(f"{nutanix_cnt:,} VMs", fw=700, c="#2B3674"),
                            ],
                        ),
                        dmc.Stack(
                            gap="xs",
                            children=[
                                dmc.Text("Pure Nutanix (AHV)", c="#A3AED0", size="sm"),
                                dmc.Text(f"{pure_nx_vms:,} VMs", fw=700, c="#2B3674"),
                            ],
                        ),
                    ],
                ),
            ),
            _section_card(
                "Hyperconverged VMs",
                "VMs on non-KM clusters (VMware-managed Nutanix + Acropolis)",
                dmc.Stack(
                    gap="md",
                    children=[
                        _vm_table(
                            vm_list,
                            cols,
                            row_fn,
                            empty_cols=len(cols),
                            numeric_col_indices=_hyperconv_numeric_cols,
                            comfortable=True,
                        ),
                        _deleted_vms_panel(deleted),
                    ],
                ),
            ),
        ],
    )


def _tab_pure_nutanix(pure: dict, vm_outage_counts: dict | None = None):
    """Pure Nutanix (AHV-only) clusters — no matching VMware non-KM cluster name."""
    vm_count = int(pure.get("vm_count", 0) or 0)
    clusters = int(pure.get("cluster_count", 0) or 0)
    cpu = float(pure.get("cpu_total", 0) or 0)
    mem_gb = float(pure.get("memory_gb", 0) or 0)
    disk_gb = float(pure.get("disk_gb", 0) or 0)
    vm_list = pure.get("vm_list", []) or []
    deleted = pure.get("deleted_vm_list", []) or []

    def row_fn(r):
        return html.Tr([
            html.Td(r.get("name")),
            html.Td(r.get("source", "-")),
            html.Td(r.get("cluster", "-")),
            _vm_metric_td(r.get("cpu", 0), decimals=0),
            _vm_metric_td(r.get("cpu_mhz_max", 0), suffix="%"),
            _vm_metric_td(r.get("cpu_mhz_avg", 0), suffix="%"),
            _vm_metric_td(r.get("cpu_mhz_min", 0), suffix="%"),
            html.Td(
                smart_memory(r.get("memory_gb", 0)),
                style={
                    "textAlign": "right",
                    "fontVariantNumeric": "tabular-nums",
                    "fontSize": "0.8125rem",
                    "verticalAlign": "middle",
                },
            ),
            _vm_metric_td(r.get("mem_pct_max", 0), suffix="%"),
            _vm_metric_td(r.get("mem_pct_avg", 0), suffix="%"),
            _vm_metric_td(r.get("mem_pct_min", 0), suffix="%"),
            html.Td(
                smart_storage(r.get("disk_gb", 0)),
                style={
                    "textAlign": "right",
                    "fontVariantNumeric": "tabular-nums",
                    "fontSize": "0.8125rem",
                    "verticalAlign": "middle",
                },
            ),
            _vm_metric_td(r.get("disk_used_min_gb", 0), suffix=" GiB"),
            _vm_metric_td(r.get("disk_used_max_gb", 0), suffix=" GiB"),
            html.Td(_availability_cell(r.get("name"), vm_outage_counts)),
        ])

    cols = [
        "VM Name",
        "Source",
        "Cluster",
        "CPU (vCPU)",
        "CPU % max",
        "CPU % avg",
        "CPU % min",
        "Memory",
        "Mem % max",
        "Mem % avg",
        "Mem % min",
        "Disk (prov.)",
        "Disk used min (GiB)",
        "Disk used max (GiB)",
        "Availability",
    ]
    _pure_nx_numeric_cols = frozenset(range(3, 14))
    return dmc.Stack(
        gap="lg",
        children=[
            dmc.SimpleGrid(
                cols=5,
                spacing="lg",
                children=[
                    _metric("Clusters (AHV-only)", f"{clusters:,}", "solar:cloud-bold-duotone", color="cyan"),
                    _metric("Total VMs", f"{vm_count:,}", "solar:laptop-bold-duotone", color="cyan"),
                    _metric("CPU (vCPU)", f"{cpu:.0f}", "solar:cpu-bold-duotone", color="cyan"),
                    _metric("Memory", smart_memory(mem_gb), "solar:ram-bold-duotone", color="cyan"),
                    _metric("Disk", smart_storage(disk_gb), "solar:database-bold-duotone", color="cyan"),
                ],
            ),
            _section_card(
                "Pure Nutanix VMs",
                "VMs on Nutanix clusters with no VMware vCenter cluster name match (after normalization)",
                dmc.Stack(
                    gap="md",
                    children=[
                        _vm_table(
                            vm_list,
                            cols,
                            row_fn,
                            empty_cols=len(cols),
                            numeric_col_indices=_pure_nx_numeric_cols,
                            comfortable=True,
                        ),
                        _deleted_vms_panel(deleted),
                    ],
                ),
            ),
        ],
    )


def _tab_power(power: dict, vm_outage_counts: dict | None = None):
    """Power Mimari (IBM LPAR) billing tab."""
    lpars = int(power.get("lpar_count", 0) or 0)
    cpu = float(power.get("cpu_total", 0) or 0)
    mem_gb = float(power.get("memory_total_gb", 0) or 0)
    vm_list = power.get("vm_list", []) or []
    deleted = power.get("deleted_vm_list", []) or []

    def row_fn(r):
        return html.Tr([
            html.Td(r.get("name")),
            html.Td(r.get("source", "Power HMC")),
            _vm_metric_td(r.get("cpu", 0), decimals=1),
            _vm_metric_td(r.get("cpu_pct_max", 0), suffix="%"),
            _vm_metric_td(r.get("cpu_pct_avg", 0), suffix="%"),
            _vm_metric_td(r.get("cpu_pct_min", 0), suffix="%"),
            html.Td(
                smart_memory(r.get("memory_gb", 0)),
                style={
                    "textAlign": "right",
                    "fontVariantNumeric": "tabular-nums",
                    "fontSize": "0.8125rem",
                    "verticalAlign": "middle",
                },
            ),
            _vm_metric_td(r.get("mem_pct_max", 0), suffix="%"),
            _vm_metric_td(r.get("mem_pct_avg", 0), suffix="%"),
            _vm_metric_td(r.get("mem_pct_min", 0), suffix="%"),
            html.Td(r.get("state", "-")),
            html.Td(_availability_cell(r.get("name"), vm_outage_counts)),
        ])

    cols = [
        "LPAR Name",
        "Source",
        "CPU (vProc)",
        "CPU % max",
        "CPU % avg",
        "CPU % min",
        "Memory",
        "Mem % max",
        "Mem % avg",
        "Mem % min",
        "State",
        "Availability",
    ]
    _power_numeric_cols = frozenset(range(2, 10))
    return dmc.Stack(
        gap="lg",
        children=[
            dmc.SimpleGrid(
                cols=3,
                spacing="lg",
                children=[
                    _metric("LPARs", f"{lpars:,}", "solar:server-square-bold-duotone", color="grape"),
                    _metric("CPU (vCPU)", f"{cpu:.1f}", "solar:cpu-bold-duotone", color="grape"),
                    _metric("Memory", smart_memory(mem_gb), "solar:ram-bold-duotone", color="grape"),
                ],
            ),
            _section_card(
                "IBM LPARs",
                "IBM Power LPAR allocation — CPU/Memory usage % over report period",
                dmc.Stack(
                    gap="md",
                    children=[
                        _vm_table(
                            vm_list,
                            cols,
                            row_fn,
                            empty_cols=len(cols),
                            numeric_col_indices=_power_numeric_cols,
                            comfortable=True,
                        ),
                        _deleted_vms_panel(deleted),
                    ],
                ),
            ),
        ],
    )


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
            _metric("Total Provisioned",  f"{prov_total:.2f} GiB", "solar:database-bold-duotone",          color="teal"),
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


def _tab_sales(customer_name: str):
    """Sales tab: CRM sales summary KPI cards, line items table, and efficiency overview."""
    summary = api.get_customer_sales_summary(customer_name)
    items = api.get_customer_sales_items(customer_name)
    efficiency = api.get_customer_sales_efficiency(customer_name)

    currency = summary.get("currency") or "TL"

    def _fmt_money(v, cur=currency):
        if v is None:
            return "-"
        return f"{float(v):,.2f} {cur}"

    def _fmt_num(v):
        if v is None:
            return "-"
        return str(int(v))

    kpi_cards = dmc.SimpleGrid(
        cols=5,
        spacing="lg",
        children=[
            _metric("YTD Revenue",         _fmt_money(summary.get("ytd_revenue_total")), "solar:money-bag-bold-duotone", color="green"),
            _metric("Open Pipeline",       _fmt_money(summary.get("pipeline_value")),    "solar:target-bold-duotone",    color="indigo"),
            _metric("Active Orders",       _fmt_num(summary.get("active_order_count")),  "solar:cart-bold-duotone",      color="cyan"),
            _metric("Active Contracts",    _fmt_num(summary.get("active_contract_count")),"solar:document-text-bold-duotone", color="orange"),
            _metric("Estimated MRR",       _fmt_money(summary.get("estimated_mrr")),     "solar:calendar-bold-duotone",  color="violet"),
        ],
    )

    def _items_row(r):
        return html.Tr([
            html.Td(r.get("source_type") or "-"),
            html.Td(r.get("reference_number") or "-"),
            html.Td((r.get("date") or "-")[:10]),
            html.Td(r.get("status") or "-"),
            html.Td(r.get("product_name") or r.get("productdescription") or "-"),
            html.Td(r.get("unit") or "-"),
            html.Td(f"{float(r['quantity']):,.0f}" if r.get("quantity") is not None else "-"),
            html.Td(_fmt_money(r.get("line_total"), r.get("currency") or currency)),
        ])

    items_table = dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=True,
        children=[
            html.Thead(html.Tr([
                html.Th("Type"), html.Th("Reference"), html.Th("Date"),
                html.Th("Status"), html.Th("Product"), html.Th("Unit"),
                html.Th("Qty"), html.Th("Total"),
            ])),
            html.Tbody([_items_row(r) for r in (items or [])] or [html.Tr([html.Td("No data", colSpan=8)])]),
        ],
    )

    def _eff_row(r):
        pct = r.get("catalog_coverage_pct")
        return html.Tr([
            html.Td(r.get("product_name") or "-"),
            html.Td(r.get("unit") or "-"),
            html.Td(f"{float(r['total_billed_qty']):,.2f}" if r.get("total_billed_qty") is not None else "-"),
            html.Td(_fmt_money(r.get("total_billed_amount"), r.get("currency") or currency)),
            html.Td(_fmt_money(r.get("catalog_unit_price"), currency) if r.get("catalog_unit_price") is not None else "-"),
            html.Td(f"{pct:.1f}%" if pct is not None else "-"),
        ])

    eff_table = dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=True,
        children=[
            html.Thead(html.Tr([
                html.Th("Product"), html.Th("Unit"), html.Th("Billed Qty"),
                html.Th("Billed Amount"), html.Th("Catalog Price"), html.Th("Coverage %"),
            ])),
            html.Tbody([_eff_row(r) for r in (efficiency or [])] or [html.Tr([html.Td("No data", colSpan=6)])]),
        ],
    )

    return dmc.Stack(gap="lg", children=[
        kpi_cards,
        _section_card(
            "Sales & Invoice Line Items",
            "Billed products across invoices and active sales orders",
            [items_table],
        ),
        _section_card(
            "Product Efficiency",
            "Billed quantity vs catalog unit price — coverage percentage per product",
            [eff_table],
        ),
    ])


def _tab_physical_inventory(devices: list[dict]):
    """Physical Inventory tab: device table (name, device_role, manufacturer, location). Title-case display."""
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
            "NetBox physical inventory (customer tenant scope)",
            _vm_table(
                devices or [],
                ["Name", "Device Role", "Manufacturer", "Location"],
                row_fn,
                empty_cols=4,
            ),
        ),
    ])


def _tab_customer_availability(avail: dict):
    """AuraNotify: service outages and VM-level outages for the customer."""
    svc = avail.get("service_downtimes") or []
    vm = avail.get("vm_downtimes") or []
    cid = avail.get("customer_id")
    cids = [x for x in (avail.get("customer_ids") or []) if x is not None]
    if not cids and cid is not None:
        cids = [cid]

    def _svc_row(e: dict):
        return html.Tr(
            [
                html.Td(str(e.get("category") or "-")),
                html.Td(str(e.get("group_name") or "-")),
                html.Td(str(e.get("type") or "-")),
                html.Td(str(e.get("start_time") or "-")),
                html.Td(str(e.get("end_time") or "-")),
                html.Td(str(e.get("duration_minutes") or "-")),
                html.Td(str(e.get("service_impact") or e.get("outage_status") or "-")),
            ]
        )

    def _vm_row(e: dict):
        return html.Tr(
            [
                html.Td(str(e.get("vm_name") or e.get("vm") or e.get("category") or "-")),
                html.Td(str(e.get("group_name") or "-")),
                html.Td(str(e.get("start_time") or "-")),
                html.Td(str(e.get("end_time") or "-")),
                html.Td(str(e.get("duration_minutes") or "-")),
                html.Td(str(e.get("reason") or "-")),
            ]
        )

    svc_cols = [
        "Category",
        "Datacenter group",
        "Type",
        "Start",
        "End",
        "Duration (min)",
        "Impact",
    ]
    vm_cols = ["VM / Subject", "Datacenter group", "Start", "End", "Duration (min)", "Reason"]

    return dmc.Stack(
        gap="lg",
        children=[
            dmc.Text(
                f"AuraNotify availability (customer ids: {cids or 'none'}) — "
                "aligned with report period start.",
                size="sm",
                c="dimmed",
            ),
            _section_card(
                "Service outages",
                "Infrastructure / service interruptions (source=service)",
                dmc.Table(
                    striped=True,
                    highlightOnHover=True,
                    children=[
                        html.Thead(html.Tr([html.Th(c) for c in svc_cols])),
                        html.Tbody(
                            [_svc_row(e) for e in svc if isinstance(e, dict)]
                            if svc
                            else [html.Tr([html.Td("No data", colSpan=len(svc_cols))])],
                        ),
                    ],
                ),
            ),
            _section_card(
                "VM outages",
                "Virtual machine downtime records (source=vm)",
                dmc.Table(
                    striped=True,
                    highlightOnHover=True,
                    children=[
                        html.Thead(html.Tr([html.Th(c) for c in vm_cols])),
                        html.Tbody(
                            [_vm_row(e) for e in vm if isinstance(e, dict)]
                            if vm
                            else [html.Tr([html.Td("No data", colSpan=len(vm_cols))])],
                        ),
                    ],
                ),
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Main content block
# ---------------------------------------------------------------------------

def _customer_content(customer_name: str, time_range: dict | None = None):
    tr = time_range or default_time_range()
    name = (customer_name or "").strip()
    if not name:
        empty = dmc.Alert(
            color="yellow",
            title="No customer selected",
            children="Choose a customer from the sidebar to load metrics.",
        )
        return {
            "summary": empty,
            "virt": empty,
            "avail": empty,
            "backup": empty,
            "billing": empty,
            "sales": empty,
            "s3": html.Div(),
            "has_s3": False,
            "phys_inv": empty,
            "has_phys_inv": False,
            "export_sheets": {},
        }

    data = api.get_customer_resources(name, tr)
    avail_bundle = api.get_customer_availability_bundle(name, tr)
    vm_outage_counts = avail_bundle.get("vm_outage_counts") or {}

    totals = data.get("totals", {})
    assets = data.get("assets", {})
    backup_assets = assets.get("backup", {}) or {}
    backup_totals = totals.get("backup", {}) or {}

    # S3 vault metrics (may be empty if customer has no S3 vaults)
    s3_data = api.get_customer_s3_vaults(name, tr)
    has_s3 = bool(s3_data.get("vaults"))

    # Physical inventory for the customer tenant scope (API-side filter)
    phys_inv_devices = api.get_physical_inventory_customer()
    has_phys_inv = True

    # Values used by Summary "Backup summary" cards (kept here to avoid NameError).
    veeam_defined = int(backup_totals.get("veeam_defined_sessions", 0) or 0)
    zerto_protected = int(backup_totals.get("zerto_protected_vms", 0) or 0)
    netbackup_pre_gib = float(backup_totals.get("netbackup_pre_dedup_gib", 0) or 0)
    netbackup_post_gib = float(backup_totals.get("netbackup_post_dedup_gib", 0) or 0)
    zerto_provisioned_gib = float(backup_totals.get("zerto_provisioned_gib", 0) or 0)
    storage_gb = _backup_storage_volume_gb(backup_totals)

    # Intel (Virtualization tab) aggregates
    intel_asset = assets.get("intel", {}) or {}
    intel_vm_list = intel_asset.get("vm_list", []) or []

    intel_vms, intel_cpu = _intel_vm_cpu_breakdown(totals, intel_asset)

    intel_mem_raw = intel_asset.get("memory_gb", 0)
    intel_disk_raw = intel_asset.get("disk_gb", 0)

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

    classic   = assets.get("classic", {}) or {}
    hyperconv = assets.get("hyperconv", {}) or {}
    pure_nx   = assets.get("pure_nutanix", {}) or {}
    show_pure_tab = int(pure_nx.get("vm_count", 0) or 0) > 0

    virt_tabs_list = [
        dmc.TabsTab("Klasik Mimari", value="classic"),
        dmc.TabsTab("Hyperconverged Mimari", value="hyperconv"),
    ]
    if show_pure_tab:
        virt_tabs_list.append(dmc.TabsTab("Pure Nutanix (AHV)", value="pure_nx"))
    virt_tabs_list.append(dmc.TabsTab("Power Mimari", value="power"))

    virt_panels_list = [
        dmc.TabsPanel(value="classic", pt="lg", children=_tab_classic(classic, vm_outage_counts)),
        dmc.TabsPanel(
            value="hyperconv", pt="lg", children=_tab_hyperconv(hyperconv, pure_nx, vm_outage_counts)
        ),
    ]
    if show_pure_tab:
        virt_panels_list.append(
            dmc.TabsPanel(value="pure_nx", pt="lg", children=_tab_pure_nutanix(pure_nx, vm_outage_counts))
        )
    virt_panels_list.append(
        dmc.TabsPanel(value="power", pt="lg", children=_tab_power(power_asset, vm_outage_counts))
    )

    virt_content = dmc.Tabs(
        color="violet",
        variant="outline",
        radius="md",
        value="classic",
        children=[
            dmc.TabsList(children=virt_tabs_list),
            *virt_panels_list,
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

    export_sheets = _build_customer_export_sheets(
        name,
        totals or {},
        backup_totals or {},
        assets or {},
        classic,
        hyperconv,
        pure_nx,
        power_asset,
        s3_data,
        phys_inv_devices or [],
    )

    return {
        "summary": _tab_summary(totals, assets),
        "virt": virt_content,
        "avail": _tab_customer_availability(avail_bundle),
        "sales": _tab_sales(name),
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
            children=build_customer_s3_panel(name, s3_data, tr, None) if has_s3 else html.Div(),
        ),
        "has_s3": has_s3,
        "phys_inv": _tab_physical_inventory(phys_inv_devices),
        "has_phys_inv": has_phys_inv,
        "export_sheets": export_sheets,
    }


# ---------------------------------------------------------------------------
# Page builders
# ---------------------------------------------------------------------------

def build_customer_layout(time_range=None, selected_customer=None, visible_sections=None):
    tr = time_range or default_time_range()
    chosen = (selected_customer or "").strip()
    vs = visible_sections

    def cv(code: str) -> bool:
        return vs is None or code in vs

    if not chosen:
        return html.Div(
            style={"padding": "40px 30px"},
            children=[
                dmc.Alert(
                    color="yellow",
                    title="No customer selected",
                    children=(
                        "Select a customer from the sidebar. If the list is empty, "
                        "configure WARMED_CUSTOMERS or ensure NetBox inventory includes tenant names."
                    ),
                )
            ],
        )

    content = _customer_content(chosen, tr)
    has_s3 = bool(content.get("has_s3"))
    has_phys_inv = bool(content.get("has_phys_inv"))

    tabs_list = dmc.TabsList(
        style={"paddingTop": "8px"},
        children=[
            dmc.TabsTab("Summary", value="summary"),
            dmc.TabsTab("Virtualization", value="virt"),
            dmc.TabsTab("Availability", value="avail"),
            dmc.TabsTab("Backup", value="backup"),
            dmc.TabsTab("Billing", value="billing"),
            dmc.TabsTab("Sales", value="sales"),
            dmc.TabsTab("Physical Inventory", value="phys-inv") if has_phys_inv else None,
            dmc.TabsTab("S3", value="s3") if has_s3 else None,
        ],
    )

    export_sheets = content.get("export_sheets") or {}
    export_group = (
        dmc.Group(
            gap=6,
            align="center",
            children=[
                dmc.Text("Export", size="xs", c="dimmed"),
                dmc.Button("CSV", id="customer-export-csv", size="xs", variant="light", color="gray"),
                dmc.Button("Excel", id="customer-export-xlsx", size="xs", variant="light", color="gray"),
                dmc.Button("PDF", id="customer-export-pdf", size="xs", variant="light", color="gray"),
            ],
        )
        if cv("action:customer:export")
        else None
    )

    header = create_detail_header(
        title="Customer View",
        back_href="/",
        back_label="Overview",
        subtitle_badge=f"Customer: {chosen}",
        subtitle_color="teal",
        time_range=tr,
        icon="solar:users-group-two-rounded-bold-duotone",
        tabs=tabs_list,
        right_extra=[export_group] if export_group else [],
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

    return dcc.Loading(
        id="customer-view-page-loading",
        type="circle",
        color="#4318FF",
        delay_show=200,
        overlay_style={"visibility": "visible", "backgroundColor": "rgba(244, 247, 254, 0.75)"},
        children=html.Div(
            className="customer-page-enter",
            children=[
            dcc.Store(
                id="customer-export-store",
                data={"customer": chosen, "sheets": export_sheets},
            ),
            dcc.Download(id="customer-export-download"),
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
                        value="avail",
                        children=dmc.Stack(
                            gap="lg", style={"padding": "0 30px"}, children=[content.get("avail")]
                        ),
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
                        value="sales",
                        children=dmc.Stack(gap="lg", style={"padding": "0 30px"}, children=[content.get("sales")]),
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
            ],
        ),
    )


def layout():
    return build_customer_layout(default_time_range())


@callback(
    Output("customer-export-download", "data"),
    Input("customer-export-csv", "n_clicks"),
    Input("customer-export-xlsx", "n_clicks"),
    State("customer-export-store", "data"),
    State("app-time-range", "data"),
    prevent_initial_call=True,
)
def export_customer_view(nc, nx, store, time_range):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    tid = ctx.triggered[0]["prop_id"].split(".")[0]
    fmt_map = {"customer-export-csv": "csv", "customer-export-xlsx": "xlsx"}
    fmt = fmt_map.get(tid)
    if not fmt:
        return dash.no_update
    store = store or {}
    base = str(store.get("customer") or "customer_view")
    extra = {"customer": base}
    sheets_raw = store.get("sheets")
    if not isinstance(sheets_raw, dict):
        sheets_raw = {}
    if not sheets_raw and store.get("rows"):
        sheets_raw = {"Legacy": store.get("rows") or []}

    order = [
        "Customer_Meta",
        "Summary_Totals",
        "Backup_Totals",
        "Assets_Classic_Block",
        "Assets_Hyperconv_Block",
        "Assets_Pure_Nutanix_Block",
        "Assets_Power_Block",
        "Assets_Intel_Aggregate",
        "Classic_VMs",
        "HyperConv_VMs",
        "Pure_Nutanix_VMs",
        "Power_LPARS",
        "Backup_Veeam_Detail",
        "Backup_Zerto_Detail",
        "Backup_Netbackup_Detail",
        "Billing_Key_Metrics",
        "S3_Vaults",
        "Physical_Inventory",
        "Legacy",
    ]
    dfs = {}
    for name in order:
        recs = sheets_raw.get(name)
        if recs:
            dfs[name] = records_to_dataframe(recs if isinstance(recs, list) else [])
    for name, recs in sheets_raw.items():
        if name not in dfs and isinstance(recs, list):
            dfs[name] = records_to_dataframe(recs)

    if fmt == "xlsx":
        content = dataframes_to_excel_with_meta(dfs, time_range, "Customer_View", extra)
        return dash_send_excel_workbook(content, base)
    report_info = build_report_info_df(time_range, "Customer_View", extra)
    sections = [(k, v) for k, v in dfs.items()]
    if not sections:
        sections = [("Data", records_to_dataframe([]))]
    return dash_send_csv_bytes(csv_bytes_with_report_header(report_info, sections), base)
