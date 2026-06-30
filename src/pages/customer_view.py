from __future__ import annotations
# Customer View - Billing-focused resource breakdown per customer.
# Tab hierarchy: Summary | Virtualization (Classic / Hyperconverged / Power) | Backup
import json
import dash
from dash import html, dcc, callback, Input, Output, State
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objs as go

import math
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from src.components.customer_loading import build_customer_loading_shell
from src.services import api_client as api
from src.utils.time_range import default_time_range
from src.utils.export_helpers import (
    records_to_dataframe,
    build_report_info_df,
    dataframes_to_excel_with_meta,
    dataframes_to_pdf_with_meta,
    csv_bytes_with_report_header,
    dash_send_excel_workbook,
    dash_send_csv_bytes,
    dash_send_pdf_workbook,
)
from src.utils.format_units import smart_storage, smart_memory, smart_cpu, pct_float, title_case
from src.components.header import create_detail_header
from src.pages.home import metric_card
from src.components.s3_panel import build_customer_s3_panel
from src.components.customer_summary_panel import (
    aggregate_sla_categories,
    build_customer_summary_panel,
)
from src.components.sold_vs_used_panel import (
    build_sold_vs_used_stack,
    filter_efficiency_rows,
)
from src.components.crm_sales_panel import (
    build_crm_active_orders_section,
    build_crm_invoiced_orders_section,
    build_crm_intro_kpi_strip,
    build_crm_summary_kv_panel,
    format_crm_money,
)
from src.services import auranotify_client as aura
from src.utils.time_range import time_range_to_bounds
from src.utils.visibility import (
    asset_has_usage,
    backup_vendor_has_data,
    is_meaningful_value,
)
from src.pages.customer_view_perspective import (
    PERSPECTIVE_CUSTOMER,
    PERSPECTIVE_MANAGER,
    default_perspective,
    effective_perspective,
    perspective_access,
    show_perspective_switch,
)


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


def _build_metrics_grid(
    metric_defs: list[tuple[Any, str, str, str, str]],
    *,
    cols: int = 4,
) -> dmc.SimpleGrid | None:
    """Build a KPI grid from (raw_value, title, display, icon, color) tuples; omit empty values."""
    cards = [
        _metric(title, display, icon, color=color)
        for raw, title, display, icon, color in metric_defs
        if is_meaningful_value(raw)
    ]
    if not cards:
        return None
    return dmc.SimpleGrid(cols=min(cols, len(cards)), spacing="lg", children=cards)


def _total_overage_loss_tl(efficiency_rows: list | None) -> float:
    return sum(float(r.get("overage_loss_tl") or 0) for r in (efficiency_rows or []))


def _metric(title: str, value, icon: str, color: str = "indigo"):
    """Standard billing metric card — vertical layout: icon → label → value."""
    return html.Div(
        className="nexus-card",
        style={
            "padding": "20px 16px",
            "minHeight": "120px",
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "justifyContent": "center",
            "textAlign": "center",
            "gap": "6px",
        },
        children=[
            dmc.ThemeIcon(size="xl", radius="md", variant="light", color=color,
                          children=DashIconify(icon=icon, width=24)),
            html.Span(title, style={
                "color": "#A3AED0",
                "fontSize": "0.72rem",
                "fontWeight": 600,
                "lineHeight": "1.3",
                "fontFamily": "DM Sans",
                "maxWidth": "140px",
            }),
            html.Div(str(value), style={
                "color": "#2B3674",
                "fontSize": "1.5rem",
                "fontWeight": "800",
                "fontFamily": "DM Sans",
                "letterSpacing": "-0.02em",
                "lineHeight": 1,
            }),
        ],
    )


def format_vm_metric_value(value, decimals: int = 1, suffix: str = "") -> str:
    """Plain-text metric for VM table cells (unit-testable)."""
    v = float(value or 0)
    if suffix == "%":
        v = max(0.0, v)
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
            html.Div(title, style={
                "margin": "0 0 2px 0", "color": "#2B3674",
                "fontSize": "1rem", "fontWeight": 700, "fontFamily": "DM Sans",
            }),
            html.Div(subtitle, style={
                "margin": "0 0 4px 0", "color": "#A3AED0", "fontSize": "0.78rem", "fontFamily": "DM Sans",
            }) if subtitle else None,
            html.Div(style={"height": "2px", "background": "linear-gradient(90deg,#4318FF,#05CD99)", "borderRadius": "2px", "width": "32px", "marginBottom": "14px"}),
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


def _itsm_tickets_for_export(tickets: list) -> list[dict]:
    """Flatten ITSM ticket dicts for export (timestamp strings, no nested objects)."""
    out = []
    for t in (tickets or []):
        if isinstance(t, dict):
            out.append({
                "source":                 t.get("source") or "",
                "id":                     t.get("id"),
                "subject":                t.get("subject") or "",
                "stage":                  t.get("stage") or "",
                "state_text":             t.get("state_text") or "",
                "status_name":            t.get("status_name") or "",
                "priority_name":          t.get("priority_name") or "",
                "category_name":          t.get("category_name") or "",
                "customer_user":          t.get("customer_user") or "",
                "agent_group_name":       t.get("agent_group_name") or "",
                "opened_at":              (t.get("opened_at") or "")[:19],
                "target_resolution_date": (t.get("target_resolution_date") or "")[:19],
                "closed_and_done_date":   (t.get("closed_and_done_date") or "")[:19],
                "resolution_hours":       t.get("resolution_hours"),
                "open_age_days":          t.get("open_age_days"),
            })
    return out


def _build_manager_export_sheets(
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
    *,
    itsm_summary: dict | None = None,
    itsm_extremes: dict | None = None,
    itsm_tickets: list | None = None,
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
    sheets["Classic_VMs_Real_CPU"] = _real_cpu_export_records(classic.get("vm_list") or [])
    sheets["HyperConv_VMs"] = _vm_records_for_export(hyperconv.get("vm_list") or [])
    sheets["HyperConv_VMs_Real_CPU"] = _real_cpu_export_records(hyperconv.get("vm_list") or [])
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

    # ITSM sheets
    if itsm_summary:
        summary_flat = {
            k: v for k, v in itsm_summary.items()
            if not isinstance(v, (list, dict))
        }
        if summary_flat:
            sheets["ITSM_Summary"] = [summary_flat]

    ex = itsm_extremes or {}
    long_tail_rows = _itsm_tickets_for_export(ex.get("long_tail") or [])
    if long_tail_rows:
        sheets["ITSM_Extremes_Closed"] = long_tail_rows

    sla_rows = _itsm_tickets_for_export(ex.get("sla_breach") or [])
    if sla_rows:
        sheets["ITSM_Extremes_OpenSlaBreach"] = sla_rows

    all_ticket_rows = _itsm_tickets_for_export(itsm_tickets or [])
    if all_ticket_rows:
        sheets["ITSM_All_Tickets"] = all_ticket_rows

    return sheets


def _build_customer_perspective_export_sheets(
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
    """Usage and inventory sheets for the customer-facing perspective."""
    sheets: dict[str, list[dict]] = {}
    sheets["Customer_Meta"] = [{"customer": customer_name}]
    trow = _dict_to_wide_row(totals)
    if trow:
        sheets["Summary_Usage_Totals"] = trow
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
    sheets["Classic_VMs_Real_CPU"] = _real_cpu_export_records(classic.get("vm_list") or [])
    sheets["HyperConv_VMs"] = _vm_records_for_export(hyperconv.get("vm_list") or [])
    sheets["HyperConv_VMs_Real_CPU"] = _real_cpu_export_records(hyperconv.get("vm_list") or [])
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

    sv = _s3_vault_rows(s3_data)
    if sv:
        sheets["S3_Vaults"] = sv

    phys = _device_records_for_export(phys_inv_devices)
    if phys:
        sheets["Physical_Inventory"] = phys

    return sheets


def _prefix_export_sheets(sheets: dict[str, list[dict]], prefix: str) -> dict[str, list[dict]]:
    return {f"{prefix}_{name}": rows for name, rows in sheets.items()}


def _build_export_sheets_for_user(
    export_context: dict,
    perspective_access_map: dict[str, bool],
) -> dict[str, list[dict]]:
    """Build export sheets for all perspectives the user may access."""
    kwargs = dict(
        customer_name=export_context.get("customer_name") or "",
        totals=export_context.get("totals") or {},
        backup_totals=export_context.get("backup_totals") or {},
        assets=export_context.get("assets") or {},
        classic=export_context.get("classic") or {},
        hyperconv=export_context.get("hyperconv") or {},
        pure_nx=export_context.get("pure_nx") or {},
        power_asset=export_context.get("power_asset") or {},
        s3_data=export_context.get("s3_data") or {},
        phys_inv_devices=export_context.get("phys_inv_devices") or [],
    )
    has_manager = bool(perspective_access_map.get("manager"))
    has_customer = bool(perspective_access_map.get("customer"))
    combined: dict[str, list[dict]] = {}

    if has_manager:
        manager_sheets = _build_manager_export_sheets(
            **kwargs,
            itsm_summary=export_context.get("itsm_summary") or {},
            itsm_extremes=export_context.get("itsm_extremes") or {},
            itsm_tickets=export_context.get("itsm_tickets") or [],
        )
        if has_manager and has_customer:
            combined.update(_prefix_export_sheets(manager_sheets, "Manager"))
        else:
            combined.update(manager_sheets)

    if has_customer:
        customer_sheets = _build_customer_perspective_export_sheets(**kwargs)
        if has_manager and has_customer:
            combined.update(_prefix_export_sheets(customer_sheets, "Customer"))
        else:
            combined.update(_prefix_export_sheets(customer_sheets, "Customer"))
    return combined


# Backward-compatible alias for tests and external callers.
_build_customer_export_sheets = _build_manager_export_sheets


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

def _tab_summary(
    customer_name: str,
    totals: dict,
    assets: dict,
    backup_totals: dict,
    *,
    sales_summary: dict | None = None,
    compliance_payload: dict | None = None,
    efficiency_rows: list | None = None,
    itsm_summary: dict | None = None,
    vm_outage_counts: dict | None = None,
    service_breakdown: list | None = None,
    s3_data: dict | None = None,
    sla_categories: list | None = None,
    perspective: str = PERSPECTIVE_MANAGER,
):
    """Summary tab: unified panel with compact signals and problems list."""
    return build_customer_summary_panel(
        customer_name,
        totals=totals,
        assets=assets,
        backup_totals=backup_totals,
        sales_summary=sales_summary,
        compliance_payload=compliance_payload,
        efficiency_rows=efficiency_rows,
        itsm_summary=itsm_summary,
        vm_outage_counts=vm_outage_counts,
        service_breakdown=service_breakdown,
        s3_data=s3_data,
        sla_categories=sla_categories,
        perspective=perspective,
    )


def _compute_billing_rows(
    classic: dict,
    hyperconv: dict,
    pure_nx: dict,
    power: dict,
) -> list[html.Tr]:
    """Table rows for platforms with provisioned resources."""
    rows: list[html.Tr] = []
    platforms = [
        ("Classic Compute", classic, "vm_count"),
        ("Hyperconverged", hyperconv, "vm_count"),
        ("Pure Nutanix (AHV)", pure_nx, "vm_count"),
        ("Power Compute (IBM)", power, "lpar_count"),
    ]
    for label, block, instance_key in platforms:
        if not asset_has_usage(block, instance_keys=(instance_key,)):
            continue
        inst = int(block.get(instance_key, 0) or 0)
        cpu = float(block.get("cpu_total", 0) or 0)
        mem = float(block.get("memory_gb", block.get("memory_total_gb", 0)) or 0)
        disk = float(block.get("disk_gb", 0) or 0)
        disk_cell = smart_storage(disk) if disk > 0 else "-"
        rows.append(
            html.Tr(
                [
                    html.Td(label),
                    html.Td(f"{inst:,}"),
                    html.Td(f"{cpu:.1f}"),
                    html.Td(smart_memory(mem)),
                    html.Td(disk_cell),
                ]
            )
        )
    return rows


def _tab_billing(
    totals: dict,
    assets: dict,
    backup_totals: dict,
    s3_data: dict | None = None,
    sales_summary: dict | None = None,
    crm_eff_panel: html.Div | None = None,
    *,
    customer_name: str = "",
    service_breakdown: list | None = None,
    sales_items: list | None = None,
    active_orders: list | None = None,
    active_items: list | None = None,
    efficiency_rows: list | None = None,
):
    """Billing tab: CRM commercial detail plus billable infrastructure lines."""
    sales_summary = sales_summary or {}
    classic = assets.get("classic", {}) or {}
    hyperconv = assets.get("hyperconv", {}) or {}
    pure_nx = assets.get("pure_nutanix", {}) or {}
    power = assets.get("power", {}) or {}
    total_vms = int(totals.get("vms_total", 0) or 0)
    total_cpu = float(totals.get("cpu_total", 0.0) or 0.0)
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

    nb_post_gib = float(backup_totals.get("netbackup_post_dedup_gib", 0) or 0)
    veeam_defined = int(backup_totals.get("veeam_defined_sessions", 0) or 0)
    zerto_protected = int(backup_totals.get("zerto_protected_vms", 0) or 0)

    vaults = (s3_data or {}).get("vaults", []) or []
    vault_count = len(vaults)
    cur = str(sales_summary.get("currency") or "TL")

    def _money(v):
        if v is None:
            return "-"
        return f"{float(v):,.2f} {cur}"

    children: list = []

    kpi_strip = build_crm_intro_kpi_strip(sales_summary, service_breakdown)
    if kpi_strip is not None:
        children.append(
            _section_card(
                "CRM — realized sales (YTD)",
                "Fulfilled / invoiced sales orders only (no pipeline) — see ADR-0010",
                kpi_strip,
            )
        )

    kv_panel = build_crm_summary_kv_panel(
        customer_name,
        sales_summary,
        service_breakdown,
        sales_items,
        active_items,
    )
    if kv_panel is not None and "No CRM sales metrics" not in str(kv_panel):
        children.append(
            _section_card(
                "CRM sales summary",
                "Open orders plus realized sales (YTD primary, lifetime secondary)",
                kv_panel,
            )
        )

    active_section = build_crm_active_orders_section(active_orders, active_items)
    if active_section is not None and "No active orders" not in str(active_section):
        children.append(
            _section_card(
                "Active orders",
                "Open CRM sales orders (active / submitted)",
                active_section,
            )
        )

    invoiced_section = build_crm_invoiced_orders_section(service_breakdown, efficiency_rows, sales_items)
    if invoiced_section is not None and "No invoiced orders yet" not in str(invoiced_section):
        children.append(
            _section_card(
                "Invoiced orders",
                "Fulfilled and invoiced CRM sales — service breakdown and line items",
                invoiced_section,
            )
        )

    if crm_eff_panel is not None and getattr(crm_eff_panel, "children", None):
        children.append(
            _section_card(
                "Sold vs used (other categories)",
                "Firewall, licensing, colocation, S3, and other mapped CRM categories",
                crm_eff_panel,
            )
        )

    infra_grid = _build_metrics_grid(
        [
            (total_vms, "Total instances", f"{total_vms:,}", "solar:laptop-bold-duotone", "teal"),
            (total_cpu, "Total CPU (vCPU)", f"{total_cpu:.1f}", "solar:cpu-bold-duotone", "indigo"),
            (total_intel_mem, "Intel memory", smart_memory(total_intel_mem), "solar:ram-bold-duotone", "blue"),
            (total_intel_disk, "Intel disk", smart_storage(total_intel_disk), "solar:database-bold-duotone", "orange"),
        ],
        cols=4,
    )
    if infra_grid is not None:
        children.append(
            _section_card(
                "Infrastructure totals",
                "Billable compute footprint for this customer",
                infra_grid,
            )
        )

    compute_rows = _compute_billing_rows(classic, hyperconv, pure_nx, power)
    if compute_rows:
        children.append(
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
                            html.Tbody(compute_rows),
                        ],
                    ),
                ),
            )
        )

    backup_grid = _build_metrics_grid(
        [
            (veeam_defined, "Veeam sessions", f"{veeam_defined:,}", "material-symbols:backup-outline", "indigo"),
            (zerto_protected, "Zerto protected VMs", f"{zerto_protected:,}", "material-symbols:shield-outline", "teal"),
            (nb_post_gib, "NetBackup stored (GiB)", f"{nb_post_gib:.2f}", "mdi:database-arrow-down-outline", "orange"),
        ],
        cols=3,
    )
    if backup_grid is not None:
        children.append(
            _section_card(
                "Backup billing lines",
                "Billable backup services and capacities",
                backup_grid,
            )
        )

    if vault_count > 0:
        children.append(
            _section_card(
                "S3 object storage (billing)",
                "Vault-level objects relevant for billing",
                dmc.Stack(
                    gap="xs",
                    children=[
                        dmc.Text("Vaults", size="sm", c="#A3AED0"),
                        dmc.Text(f"{vault_count}", fw=700, c="#2B3674"),
                    ],
                ),
            )
        )

    if not children:
        return dmc.Alert(
            color="gray",
            variant="light",
            title="No billing data",
            children="No commercial or billable infrastructure data for this customer.",
        )
    return dmc.Stack(gap="lg", children=children)


def _real_cpu_usage_status_badge(r: dict):
    if r.get("cpu_usage_exceeds_sold_max"):
        return dmc.Badge("Exceeds sold (peak)", color="red", variant="light", size="sm")
    if r.get("cpu_usage_exceeds_sold_avg"):
        return dmc.Badge("Exceeds sold (avg)", color="orange", variant="light", size="sm")
    return dmc.Text("—", c="dimmed", size="xs")


def _real_cpu_vm_table(vm_list: list, *, title: str, subtitle: str):
    cols = [
        "VM Name",
        "Cluster",
        "Host",
        "CPU Sold (GHz)",
        "CPU Real cap (GHz)",
        "CPU Used avg (GHz)",
        "CPU Used max (GHz)",
        "CPU % avg",
        "CPU % max",
        "Status",
    ]

    def row_fn(r):
        return html.Tr([
            html.Td(r.get("name")),
            html.Td(r.get("cluster", "-")),
            html.Td(r.get("vmhost") or "—"),
            _vm_metric_td(r.get("cpu_ghz_sales", r.get("cpu", 0)), decimals=0),
            _vm_metric_td(r.get("cpu_ghz_real", 0), decimals=1),
            _vm_metric_td(r.get("cpu_used_ghz_avg", 0), decimals=1),
            _vm_metric_td(r.get("cpu_used_ghz_max", 0), decimals=1),
            _vm_metric_td(r.get("cpu_pct_avg", r.get("cpu_mhz_avg", 0)), suffix="%"),
            _vm_metric_td(r.get("cpu_pct_max", r.get("cpu_mhz_max", 0)), suffix="%"),
            html.Td(_real_cpu_usage_status_badge(r)),
        ])

    return _section_card(
        title,
        subtitle,
        _vm_table(
            vm_list,
            cols,
            row_fn,
            empty_cols=len(cols),
            numeric_col_indices=frozenset({3, 4, 5, 6, 7, 8}),
            comfortable=True,
        ),
    )


def _real_cpu_export_records(vm_list: list | None) -> list[dict]:
    if not vm_list:
        return []
    out: list[dict] = []
    for r in vm_list:
        if not isinstance(r, dict):
            continue
        out.append({
            "name": r.get("name"),
            "cluster": r.get("cluster"),
            "vmhost": r.get("vmhost"),
            "cpu_ghz_sales": r.get("cpu_ghz_sales", r.get("cpu")),
            "cpu_ghz_real": r.get("cpu_ghz_real"),
            "cpu_used_ghz_avg": r.get("cpu_used_ghz_avg"),
            "cpu_used_ghz_max": r.get("cpu_used_ghz_max"),
            "cpu_pct_avg": r.get("cpu_pct_avg", r.get("cpu_mhz_avg")),
            "cpu_pct_max": r.get("cpu_pct_max", r.get("cpu_mhz_max")),
            "cpu_usage_exceeds_sold_avg": r.get("cpu_usage_exceeds_sold_avg"),
            "cpu_usage_exceeds_sold_max": r.get("cpu_usage_exceeds_sold_max"),
        })
    return out


def _tab_classic(classic: dict, vm_outage_counts: dict | None = None, crm_eff_panel: html.Div | None = None):
    """Classic Compute (KM cluster) billing tab."""
    vm_count = int(classic.get("vm_count", 0) or 0)
    cpu = float(classic.get("cpu_total", 0) or 0)
    cpu_real = float(classic.get("cpu_real_total", 0) or 0)
    cpu_used_max = float(classic.get("cpu_used_ghz_max_total", 0) or 0)
    mem_gb = float(classic.get("memory_gb", 0) or 0)
    disk_gb = float(classic.get("disk_gb", 0) or 0)
    vm_list = classic.get("vm_list", []) or []
    deleted = classic.get("deleted_vm_list", []) or []

    def row_fn(r):
        return html.Tr([
            html.Td(r.get("name")),
            html.Td(r.get("cluster", "-")),
            _vm_metric_td(r.get("cpu", 0), decimals=0),
            _vm_metric_td(r.get("cpu_pct_max", r.get("cpu_mhz_max", 0)), suffix="%"),
            _vm_metric_td(r.get("cpu_pct_avg", r.get("cpu_mhz_avg", 0)), suffix="%"),
            _vm_metric_td(r.get("cpu_pct_min", r.get("cpu_mhz_min", 0)), suffix="%"),
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
    head = [crm_eff_panel] if crm_eff_panel is not None and getattr(crm_eff_panel, "children", None) else []
    kpi_grid = _build_metrics_grid(
        [
            (vm_count, "Total VMs", f"{vm_count:,}", "solar:laptop-bold-duotone", "blue"),
            (cpu, "CPU (vCPU)", f"{cpu:.0f}", "solar:cpu-bold-duotone", "blue"),
            (cpu_real, "Real CPU cap", smart_cpu(cpu_real), "solar:cpu-bolt-bold-duotone", "gray"),
            (cpu_used_max, "Used max (GHz)", smart_cpu(cpu_used_max), "solar:chart-2-bold-duotone", "gray"),
            (mem_gb, "Memory", smart_memory(mem_gb), "solar:ram-bold-duotone", "blue"),
            (disk_gb, "Disk", smart_storage(disk_gb), "solar:database-bold-duotone", "blue"),
        ],
        cols=6,
    )
    body: list = head + ([kpi_grid] if kpi_grid is not None else [])
    body.append(
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
        )
    )
    body.append(
        _real_cpu_vm_table(
            vm_list,
            title="Classic VMs — CPU Usage vs Sold",
            subtitle=(
                "Flags VMs where measured usage (GHz) exceeds sold CPU (1 vCPU = 1 GHz), "
                "using real host capacity as the usage base."
            ),
        )
    )
    return dmc.Stack(gap="lg", children=body)


def _tab_hyperconv(
    hyperconv: dict,
    pure_nutanix: dict | None = None,
    vm_outage_counts: dict | None = None,
    crm_eff_panel: html.Div | None = None,
):
    """Hyperconverged (non-KM VMware + Nutanix) billing tab."""
    pure_nutanix = pure_nutanix or {}
    vm_count = int(hyperconv.get("vm_count", 0) or 0)
    vmware_only = int(hyperconv.get("vmware_only", 0) or 0)
    nutanix_cnt = int(hyperconv.get("nutanix_count", 0) or 0)
    pure_nx_vms = int(pure_nutanix.get("vm_count", 0) or 0)
    cpu = float(hyperconv.get("cpu_total", 0) or 0)
    cpu_real = float(hyperconv.get("cpu_real_total", 0) or 0)
    cpu_used_max = float(hyperconv.get("cpu_used_ghz_max_total", 0) or 0)
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
            _vm_metric_td(r.get("cpu_pct_max", r.get("cpu_mhz_max", 0)), suffix="%"),
            _vm_metric_td(r.get("cpu_pct_avg", r.get("cpu_mhz_avg", 0)), suffix="%"),
            _vm_metric_td(r.get("cpu_pct_min", r.get("cpu_mhz_min", 0)), suffix="%"),
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
    head_h = [crm_eff_panel] if crm_eff_panel is not None and getattr(crm_eff_panel, "children", None) else []
    kpi_grid = _build_metrics_grid(
        [
            (vm_count, "Total VMs", f"{vm_count:,}", "solar:laptop-bold-duotone", "indigo"),
            (cpu, "CPU (vCPU)", f"{cpu:.0f}", "solar:cpu-bold-duotone", "indigo"),
            (cpu_real, "Real CPU cap", smart_cpu(cpu_real), "solar:cpu-bolt-bold-duotone", "gray"),
            (cpu_used_max, "Used max (GHz)", smart_cpu(cpu_used_max), "solar:chart-2-bold-duotone", "gray"),
            (mem_gb, "Memory", smart_memory(mem_gb), "solar:ram-bold-duotone", "indigo"),
            (disk_gb, "Disk", smart_storage(disk_gb), "solar:database-bold-duotone", "indigo"),
        ],
        cols=6,
    )
    platform_stacks = []
    for label, count in (
        ("VMware (non-KM cluster)", vmware_only),
        ("Nutanix (VMware-managed)", nutanix_cnt),
        ("Pure Nutanix (AHV)", pure_nx_vms),
    ):
        if is_meaningful_value(count):
            platform_stacks.append(
                dmc.Stack(
                    gap="xs",
                    children=[
                        dmc.Text(label, c="#A3AED0", size="sm"),
                        dmc.Text(f"{count:,} VMs", fw=700, c="#2B3674"),
                    ],
                )
            )
    body_h: list = head_h + ([kpi_grid] if kpi_grid is not None else [])
    if platform_stacks:
        body_h.append(
            _section_card(
                "Platform breakdown",
                "VMware non-KM vs Nutanix on VMware-managed clusters vs Pure Nutanix (AHV-only clusters)",
                dmc.Group(gap="xl", children=platform_stacks),
            )
        )
    body_h.append(
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
        )
    )
    body_h.append(
        _real_cpu_vm_table(
            vm_list,
            title="Hyperconverged VMs — CPU Usage vs Sold",
            subtitle=(
                "Flags VMs where measured usage (GHz) exceeds sold CPU (1 vCPU = 1 GHz); "
                "Nutanix rows use 1 GHz/core (sales ≈ real cap)."
            ),
        )
    )
    return dmc.Stack(gap="lg", children=body_h)


def _tab_pure_nutanix(pure: dict, vm_outage_counts: dict | None = None, crm_eff_panel: html.Div | None = None):
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
            _vm_metric_td(r.get("cpu_pct_max", r.get("cpu_mhz_max", 0)), suffix="%"),
            _vm_metric_td(r.get("cpu_pct_avg", r.get("cpu_mhz_avg", 0)), suffix="%"),
            _vm_metric_td(r.get("cpu_pct_min", r.get("cpu_mhz_min", 0)), suffix="%"),
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
    head_p = [crm_eff_panel] if crm_eff_panel is not None else []
    return dmc.Stack(
        gap="lg",
        children=head_p
        + [
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


def _tab_power(power: dict, vm_outage_counts: dict | None = None, crm_eff_panel: html.Div | None = None):
    """Power Mimari (IBM LPAR) billing tab."""
    lpars = int(power.get("lpar_count", 0) or 0)
    cpu = float(power.get("cpu_total", 0) or 0)
    mem_gb = float(power.get("memory_total_gb", 0) or 0)
    disk_gb = float(power.get("disk_total_gb", 0) or 0)
    vm_list = power.get("vm_list", []) or []
    deleted = power.get("deleted_vm_list", []) or []

    def row_fn(r):
        return html.Tr([
            html.Td(r.get("name")),
            html.Td(r.get("lpar_name", "-")),
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
            html.Td(
                smart_storage(r.get("disk_gb", 0)),
                style={
                    "textAlign": "right",
                    "fontVariantNumeric": "tabular-nums",
                    "fontSize": "0.8125rem",
                    "verticalAlign": "middle",
                },
            ),
            _vm_metric_td(r.get("disk_used_max_gb", 0)),
            _vm_metric_td(r.get("disk_used_min_gb", 0)),
            html.Td(r.get("state", "-")),
            html.Td(_availability_cell(r.get("name"), vm_outage_counts)),
        ])

    cols = [
        "Host Name",
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
        "Disk",
        "Disk used max (GB)",
        "Disk used min (GB)",
        "State",
        "Availability",
    ]
    _power_numeric_cols = frozenset(range(3, 14))
    head_pw = [crm_eff_panel] if crm_eff_panel is not None else []
    return dmc.Stack(
        gap="lg",
        children=head_pw
        + [
            dmc.SimpleGrid(
                cols=4,
                spacing="lg",
                children=[
                    _metric("LPARs", f"{lpars:,}", "solar:server-square-bold-duotone", color="grape"),
                    _metric("CPU (vCPU)", f"{cpu:.1f}", "solar:cpu-bold-duotone", color="grape"),
                    _metric("Memory", smart_memory(mem_gb), "solar:ram-bold-duotone", color="grape"),
                    _metric("Disk", smart_storage(disk_gb), "solar:database-bold-duotone", color="grape"),
                ],
            ),
            _section_card(
                "IBM LPARs",
                "IBM Power LPAR allocation — HMC capacity with Zabbix agent memory/disk usage",
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


def _tab_veeam(backup_assets: dict, backup_totals: dict, crm_eff_panel: html.Div | None = None):
    veeam       = backup_assets.get("veeam", {}) or {}
    veeam_types = veeam.get("session_types", []) or []
    defined     = int(backup_totals.get("veeam_defined_sessions", 0) or 0)

    head_v = [crm_eff_panel] if crm_eff_panel is not None and getattr(crm_eff_panel, "children", None) else []
    kpi_v = _build_metrics_grid(
        [
            (defined, "Defined sessions", f"{defined:,}", "material-symbols:backup-outline", "indigo"),
            (len(veeam_types), "Session types", f"{len(veeam_types):,}", "material-symbols:list-alt-outline", "teal"),
        ],
        cols=2,
    )
    body_v = head_v + ([kpi_v] if kpi_v is not None else [])
    body_v.append(
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
        )
    )
    return dmc.Stack(gap="lg", children=body_v)


def _tab_zerto(backup_assets: dict, backup_totals: dict, crm_eff_panel: html.Div | None = None):
    zerto      = backup_assets.get("zerto", {}) or {}
    vpgs       = zerto.get("vpgs", []) or []
    protected  = int(backup_totals.get("zerto_protected_vms", 0) or 0)
    prov_total = float(backup_totals.get("zerto_provisioned_gib", 0) or 0)

    head_z = [crm_eff_panel] if crm_eff_panel is not None and getattr(crm_eff_panel, "children", None) else []
    kpi_z = _build_metrics_grid(
        [
            (protected, "Protected VMs", f"{protected:,}", "material-symbols:shield-outline", "teal"),
            (prov_total, "Total provisioned", f"{prov_total:.2f} GiB", "solar:database-bold-duotone", "teal"),
        ],
        cols=2,
    )
    body_z = head_z + ([kpi_z] if kpi_z is not None else [])
    body_z.append(
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
        )
    )
    return dmc.Stack(gap="lg", children=body_z)


def _tab_netbackup(backup_assets: dict, backup_totals: dict, crm_eff_panel: html.Div | None = None):
    nb = backup_assets.get("netbackup", {}) or {}
    pre_gib    = float(backup_totals.get("netbackup_pre_dedup_gib", 0) or 0)
    post_gib   = float(backup_totals.get("netbackup_post_dedup_gib", 0) or 0)
    dedup_fact = nb.get("deduplication_factor", "1x")

    head_nb = [crm_eff_panel] if crm_eff_panel is not None and getattr(crm_eff_panel, "children", None) else []
    kpi_nb = _build_metrics_grid(
        [
            (pre_gib, "Pre-dedup (GiB)", f"{pre_gib:.2f}", "mdi:database-lock-outline", "indigo"),
            (post_gib, "Stored (GiB)", f"{post_gib:.2f}", "mdi:database-arrow-down-outline", "teal"),
            (dedup_fact if dedup_fact not in (None, "1x", "1.0x") else None, "Dedup factor", dedup_fact, "mdi:percent-outline", "orange"),
        ],
        cols=3,
    )
    body_nb = head_nb + ([kpi_nb] if kpi_nb is not None else [])
    body_nb.append(
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
        )
    )
    return dmc.Stack(gap="lg", children=body_nb)


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

    children: list = []
    device_kpi = _build_metrics_grid(
        [(total, "Total physical devices", f"{total:,}", "solar:server-bold-duotone", "indigo")],
        cols=1,
    )
    if device_kpi is not None:
        children.append(device_kpi)
    children.append(
        _section_card(
            "Device list",
            "NetBox physical inventory (customer tenant scope)",
            _vm_table(
                devices or [],
                ["Name", "Device Role", "Manufacturer", "Location"],
                row_fn,
                empty_cols=4,
            ),
        )
    )
    return dmc.Stack(gap="lg", children=children)


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

    children: list = [
        dmc.Text(
            f"AuraNotify availability (customer ids: {cids or 'none'}) — "
            "aligned with report period start.",
            size="sm",
            c="dimmed",
        ),
    ]
    if svc:
        children.append(
            _section_card(
                "Service outages",
                "Infrastructure / service interruptions (source=service)",
                dmc.Table(
                    striped=True,
                    highlightOnHover=True,
                    children=[
                        html.Thead(html.Tr([html.Th(c) for c in svc_cols])),
                        html.Tbody([_svc_row(e) for e in svc if isinstance(e, dict)]),
                    ],
                ),
            )
        )
    if vm:
        children.append(
            _section_card(
                "VM outages",
                "Virtual machine downtime records (source=vm)",
                dmc.Table(
                    striped=True,
                    highlightOnHover=True,
                    children=[
                        html.Thead(html.Tr([html.Th(c) for c in vm_cols])),
                        html.Tbody([_vm_row(e) for e in vm if isinstance(e, dict)]),
                    ],
                ),
            )
        )
    if len(children) == 1:
        children.append(
            dmc.Alert(
                color="teal",
                variant="light",
                title="No outages in period",
                children="No service or VM downtime records for this customer in the selected report period.",
            )
        )
    return dmc.Stack(gap="lg", children=children)


def _fmt_hours(h) -> str:
    """Format float hours to human-readable string."""
    if h is None:
        return "-"
    try:
        h = float(h)
        if math.isnan(h):
            return "-"
    except (TypeError, ValueError):
        return "-"
    if h < 1:
        return f"{int(h * 60)} min"
    if h < 24:
        return f"{h:.1f} hr"
    return f"{h / 24:.1f} days"


def _priority_color(priority: str | None) -> str:
    p = (priority or "").lower()
    if "critical" in p or "urgent" in p or "p1" in p:
        return "red"
    if "high" in p or "p2" in p:
        return "orange"
    if "medium" in p or "p3" in p:
        return "yellow"
    return "blue"


def _itsm_ticket_table(tickets: list, source: str, cols: list) -> html.Div:
    """Scrollable ticket table for ITSM accordion."""
    filtered = [t for t in tickets if t.get("source") == source]

    def _row(t):
        stage = t.get("stage") or t.get("state_text") or t.get("status_name") or "-"
        priority = t.get("priority_name") or "-"
        target = (t.get("target_resolution_date") or "-")[:10] if t.get("target_resolution_date") else "-"
        return html.Tr([
            html.Td(dmc.Badge(stage, size="sm", variant="light",
                             color="green" if any(k in stage.lower() for k in ("closed", "done", "resolved"))
                             else "blue")),
            html.Td(t.get("customer_user") or "-"),
            html.Td(dmc.Badge(priority, size="xs", variant="dot",
                             color=_priority_color(priority))),
            html.Td(t.get("agent_group_name") or "-"),
            html.Td(t.get("subject") or "-",
                    style={"maxWidth": "280px", "overflow": "hidden",
                           "textOverflow": "ellipsis", "whiteSpace": "nowrap"}),
            html.Td(t.get("category_name") or "-"),
            html.Td(target),
        ])

    return html.Div(
        style={"maxHeight": "360px", "overflowY": "auto", "overflowX": "auto"},
        children=[
            dmc.Table(
                striped=True,
                highlightOnHover=True,
                withColumnBorders=True,
                className="customer-vm-table",
                children=[
                    html.Thead(html.Tr([html.Th(c) for c in cols])),
                    html.Tbody(
                        [_row(t) for t in filtered]
                        if filtered
                        else [html.Tr([html.Td("No data", colSpan=len(cols))])]
                    ),
                ],
            )
        ],
    )


def _tab_itsm(
    customer_name: str,
    tr: dict | None,
    itsm_summary: dict,
    itsm_extremes: dict,
    itsm_tickets: list,
):
    """ITSM tab: KPI grid + extreme cases accordion + all records accordion."""
    sm = itsm_summary or {}
    ex = itsm_extremes or {}
    all_tickets = itsm_tickets or []

    total       = int(sm.get("total_count", 0) or 0)
    inc_count   = int(sm.get("incident_count", 0) or 0)  # noqa: F841
    sr_count    = int(sm.get("sr_count", 0) or 0)        # noqa: F841
    inc_open    = int(sm.get("incident_open", 0) or 0)
    inc_closed  = int(sm.get("incident_closed", 0) or 0)
    sr_open     = int(sm.get("sr_open", 0) or 0)
    sr_closed   = int(sm.get("sr_closed", 0) or 0)
    sla_breach  = int(sm.get("sla_breach_count", 0) or 0)
    top_cat     = sm.get("top_category") or "-"
    avg_rh      = _fmt_hours(sm.get("avg_resolution_hours"))
    median_rh   = _fmt_hours(sm.get("median_resolution_hours"))
    p95_rh      = _fmt_hours(sm.get("p95_resolution_hours"))

    prio_dist   = sm.get("priority_distribution") or []
    state_dist  = sm.get("state_distribution") or []

    long_tail   = ex.get("long_tail") or []
    sla_list    = ex.get("sla_breach") or []

    inc_tickets = [t for t in all_tickets if t.get("source") == "incident"]
    sr_tickets  = [t for t in all_tickets if t.get("source") == "servicerequest"]

    inc_pair = inc_open + inc_closed
    sr_pair = sr_open + sr_closed
    kpi_grid = _build_metrics_grid(
        [
            (total, "Total records", f"{total:,}", "solar:ticket-bold-duotone", "indigo"),
            (inc_pair, "Incidents (open / closed)", f"{inc_open:,} / {inc_closed:,}", "solar:bug-minimalistic-bold-duotone", "blue"),
            (sr_pair, "Service requests (open / closed)", f"{sr_open:,} / {sr_closed:,}", "solar:document-add-bold-duotone", "teal"),
            (sla_breach, "SLA breach", f"{sla_breach:,}", "solar:danger-triangle-bold-duotone", "red"),
            (sm.get("avg_resolution_hours"), "Avg incident resolution", avg_rh, "solar:clock-circle-bold-duotone", "violet"),
            (sm.get("median_resolution_hours"), "Median resolution", median_rh, "solar:clock-square-bold-duotone", "grape"),
            (sm.get("p95_resolution_hours"), "P95 resolution", p95_rh, "solar:alarm-bold-duotone", "orange"),
            (top_cat if top_cat != "-" else None, "Top category", top_cat, "solar:tag-bold-duotone", "cyan"),
        ],
        cols=4,
    )

    # ---- Distribution charts ----
    charts_row = dmc.SimpleGrid(cols=2, spacing="lg", children=[
        _section_card("Priority Distribution", "Record counts by priority",
            dcc.Graph(
                config={"displayModeBar": False},
                style={"height": "200px"},
                figure={
                    "data": [{
                        "type": "bar", "orientation": "h",
                        "x": [d.get("count", 0) for d in prio_dist],
                        "y": [d.get("priority", "Unknown") for d in prio_dist],
                        "marker": {"color": "#4318FF"},
                    }],
                    "layout": {
                        "margin": {"l": 120, "r": 10, "t": 10, "b": 30},
                        "paper_bgcolor": "rgba(0,0,0,0)",
                        "plot_bgcolor": "rgba(0,0,0,0)",
                        "font": {"color": "#2B3674", "size": 11},
                        "xaxis": {"gridcolor": "#F4F7FE"},
                        "yaxis": {"automargin": True},
                    },
                },
            ) if prio_dist else dmc.Text("No priority data", c="dimmed", size="sm"),
        ),
        _section_card("State Distribution", "Record counts by state",
            dcc.Graph(
                config={"displayModeBar": False},
                style={"height": "200px"},
                figure={
                    "data": [{
                        "type": "bar", "orientation": "h",
                        "x": [d.get("count", 0) for d in state_dist],
                        "y": [d.get("stage", "Unknown") for d in state_dist],
                        "marker": {"color": "#63B3ED"},
                    }],
                    "layout": {
                        "margin": {"l": 140, "r": 10, "t": 10, "b": 30},
                        "paper_bgcolor": "rgba(0,0,0,0)",
                        "plot_bgcolor": "rgba(0,0,0,0)",
                        "font": {"color": "#2B3674", "size": 11},
                        "xaxis": {"gridcolor": "#F4F7FE"},
                        "yaxis": {"automargin": True},
                    },
                },
            ) if state_dist else dmc.Text("No state data", c="dimmed", size="sm"),
        ),
    ])

    # ---- Extreme cases accordion ----
    def _long_tail_row(t):
        rh = t.get("resolution_hours")
        closed = (t.get("closed_and_done_date") or "-")[:10] if t.get("closed_and_done_date") else "-"
        return html.Tr([
            html.Td(str(t.get("id") or "-")),
            html.Td(t.get("customer_user") or "-"),
            html.Td(t.get("subject") or "-",
                    style={"maxWidth": "240px", "overflow": "hidden",
                           "textOverflow": "ellipsis", "whiteSpace": "nowrap"}),
            html.Td(dmc.Badge(t.get("priority_name") or "-", size="xs",
                             color=_priority_color(t.get("priority_name")), variant="dot")),
            html.Td(f"{float(rh):.1f} hr" if rh is not None else "-"),
            html.Td(closed),
        ])

    def _sla_row(t):
        age = t.get("open_age_days")
        target = (t.get("target_resolution_date") or "-")[:10] if t.get("target_resolution_date") else "-"
        return html.Tr([
            html.Td(dmc.Badge(t.get("source") or "-", size="xs", variant="light", color="gray")),
            html.Td(str(t.get("id") or "-")),
            html.Td(t.get("subject") or "-",
                    style={"maxWidth": "220px", "overflow": "hidden",
                           "textOverflow": "ellipsis", "whiteSpace": "nowrap"}),
            html.Td(dmc.Badge(t.get("priority_name") or "-", size="xs",
                             color=_priority_color(t.get("priority_name")), variant="dot")),
            html.Td(t.get("agent_group_name") or "-"),
            html.Td(f"{float(age):.0f} days" if age is not None else "-"),
            html.Td(target),
        ])

    long_tail_table = html.Div(
        style={"maxHeight": "300px", "overflowY": "auto"},
        children=[dmc.Table(
            striped=True, highlightOnHover=True, withColumnBorders=True,
            children=[
                html.Thead(html.Tr([
                    html.Th("ID"), html.Th("User"), html.Th("Subject"),
                    html.Th("Priority"), html.Th("Resolution"), html.Th("Closed Date"),
                ])),
                html.Tbody(
                    [_long_tail_row(t) for t in long_tail]
                    if long_tail
                    else [html.Tr([html.Td("No outliers in this period", colSpan=6)])]
                ),
            ],
        )],
    )

    sla_table = html.Div(
        style={"maxHeight": "300px", "overflowY": "auto"},
        children=[dmc.Table(
            striped=True, highlightOnHover=True, withColumnBorders=True,
            children=[
                html.Thead(html.Tr([
                    html.Th("Type"), html.Th("ID"), html.Th("Subject"),
                    html.Th("Priority"), html.Th("Group"), html.Th("Open Age"), html.Th("Target Date"),
                ])),
                html.Tbody(
                    [_sla_row(t) for t in sla_list]
                    if sla_list
                    else [html.Tr([html.Td("No SLA breaches in this period", colSpan=7)])]
                ),
            ],
        )],
    )

    extremes_accordion = dmc.Accordion(
        chevronPosition="right",
        variant="separated",
        children=[
            dmc.AccordionItem(value="long_tail", children=[
                dmc.AccordionControl(
                    dmc.Group(gap="sm", children=[
                        dmc.ThemeIcon(size="sm", variant="light", color="orange",
                                     children=DashIconify(icon="solar:clock-circle-bold-duotone", width=16)),
                        dmc.Text(
                            f"Long-tail closed incidents (mean+1\u03c3) \u2014 {len(long_tail)} record(s)",
                            size="sm", fw=600,
                        ),
                    ])
                ),
                dmc.AccordionPanel(long_tail_table),
            ]),
            dmc.AccordionItem(value="sla_breach", children=[
                dmc.AccordionControl(
                    dmc.Group(gap="sm", children=[
                        dmc.ThemeIcon(size="sm", variant="light", color="red",
                                     children=DashIconify(icon="solar:danger-triangle-bold-duotone", width=16)),
                        dmc.Text(
                            f"SLA breach \u2014 still open \u2014 {len(sla_list)} record(s)",
                            size="sm", fw=600,
                        ),
                    ])
                ),
                dmc.AccordionPanel(sla_table),
            ]),
        ],
    )

    # ---- All records accordion ----
    _ticket_cols = [
        "Stage", "Customer User", "Priority", "Group", "Subject", "Category", "Target Date",
    ]
    all_tickets_accordion = dmc.Accordion(
        chevronPosition="right",
        variant="separated",
        children=[
            dmc.AccordionItem(value="incidents", children=[
                dmc.AccordionControl(
                    dmc.Group(gap="sm", children=[
                        dmc.ThemeIcon(size="sm", variant="light", color="blue",
                                     children=DashIconify(icon="solar:bug-minimalistic-bold-duotone", width=16)),
                        dmc.Text(f"Incidents \u2014 {len(inc_tickets)} record(s)", size="sm", fw=600),
                    ])
                ),
                dmc.AccordionPanel(
                    _itsm_ticket_table(all_tickets, "incident", _ticket_cols)
                ),
            ]),
            dmc.AccordionItem(value="servicerequests", children=[
                dmc.AccordionControl(
                    dmc.Group(gap="sm", children=[
                        dmc.ThemeIcon(size="sm", variant="light", color="teal",
                                     children=DashIconify(icon="solar:document-add-bold-duotone", width=16)),
                        dmc.Text(f"Service Requests \u2014 {len(sr_tickets)} record(s)", size="sm", fw=600),
                    ])
                ),
                dmc.AccordionPanel(
                    _itsm_ticket_table(all_tickets, "servicerequest", _ticket_cols)
                ),
            ]),
        ],
    )

    itsm_children: list = []
    if kpi_grid is not None:
        itsm_children.append(
            _section_card(
                "ITSM overview",
                f"Incidents and service requests for {customer_name} in the report period",
                kpi_grid,
            )
        )
    itsm_children.extend(
        [
            charts_row,
            _section_card(
                "Extreme cases",
                "Long-tail closed incidents (resolution > mean+1σ) and open SLA breaches",
                extremes_accordion,
            ),
            _section_card(
                "All records",
                "All tickets in the report period — expand to view incidents or service requests",
                all_tickets_accordion,
            ),
        ]
    )
    return dmc.Stack(gap="lg", children=itsm_children)


# ---------------------------------------------------------------------------
# Main content block
# ---------------------------------------------------------------------------

def _build_backup_tabs(
    backup_assets: dict,
    backup_totals: dict,
    eff_by_cat: list | None,
    *,
    include_sold_vs_used: bool,
) -> html.Div:
    """Backup vendor nested tabs; sold-vs-used panels optional (manager perspective only)."""
    backup_tab_defs: list[tuple[str, str, html.Div]] = []

    def _eff_panel(scope: str) -> html.Div | None:
        if not include_sold_vs_used:
            return None
        return build_sold_vs_used_stack(filter_efficiency_rows(eff_by_cat, scope))

    if backup_vendor_has_data(backup_totals, backup_assets, "veeam"):
        backup_tab_defs.append(
            ("veeam", "Veeam", _tab_veeam(backup_assets, backup_totals, crm_eff_panel=_eff_panel("backup.veeam")))
        )
    if backup_vendor_has_data(backup_totals, backup_assets, "zerto"):
        backup_tab_defs.append(
            ("zerto", "Zerto", _tab_zerto(backup_assets, backup_totals, crm_eff_panel=_eff_panel("backup.zerto")))
        )
    if backup_vendor_has_data(backup_totals, backup_assets, "netbackup"):
        backup_tab_defs.append(
            (
                "netbackup",
                "Netbackup",
                _tab_netbackup(backup_assets, backup_totals, crm_eff_panel=_eff_panel("backup.netbackup")),
            )
        )

    if backup_tab_defs:
        return dmc.Tabs(
            color="green",
            variant="outline",
            radius="md",
            value=backup_tab_defs[0][0],
            children=[
                dmc.TabsList(
                    children=[dmc.TabsTab(label, value=value) for value, label, _panel in backup_tab_defs]
                ),
                *[
                    dmc.TabsPanel(value=value, pt="lg", children=panel)
                    for value, _label, panel in backup_tab_defs
                ],
            ],
        )
    return dmc.Alert(
        color="gray",
        variant="light",
        title="No backup services",
        children="No billable backup vendor data for this customer in the selected period.",
    )


def _crm_rows_outside_virt_backup(eff_rows: list | None) -> list:
    """Categories for Billing tab (firewall, licensing, colocation, S3, etc.)."""
    out: list = []
    for r in eff_rows or []:
        g = str(r.get("gui_tab_binding") or "").lower()
        if not g.startswith("virtualization") and not g.startswith("backup"):
            out.append(r)
    return out


def _customer_content(customer_name: str, time_range: dict | None = None):
    tr = time_range or default_time_range()
    name = (customer_name or "").strip()
    if not name:
        empty = dmc.Alert(
            color="yellow",
            title="No customer selected",
            children="Open a customer from the Customers catalog to load metrics.",
        )
        return {
            "manager": {
                "summary": empty,
                "virt": empty,
                "avail": empty,
                "backup": empty,
                "billing": empty,
                "itsm": empty,
                "s3": html.Div(),
                "phys_inv": empty,
            },
            "customer": {
                "summary": empty,
                "virt": empty,
                "avail": empty,
                "backup": empty,
                "s3": html.Div(),
                "phys_inv": empty,
            },
            "has_s3": False,
            "has_phys_inv": False,
            "customer_name": "",
            "export_context": {},
        }

    start_ts, end_ts = time_range_to_bounds(tr)
    sla_start = start_ts.strftime("%Y-%m-%dT%H:%M:%S")
    sla_end = end_ts.strftime("%Y-%m-%dT%H:%M:%S")

    with ThreadPoolExecutor(max_workers=11) as pool:
        f_resources = pool.submit(api.get_customer_resources, name, tr)
        f_avail = pool.submit(api.get_customer_availability_bundle, name, tr)
        f_s3 = pool.submit(api.get_customer_s3_vaults, name, tr)
        f_phys = pool.submit(api.get_physical_inventory_customer, name)
        f_itsm_summary = pool.submit(api.get_customer_itsm_summary, name, tr)
        f_itsm_extremes = pool.submit(api.get_customer_itsm_extremes, name, tr)
        f_itsm_tickets = pool.submit(api.get_customer_itsm_tickets, name, tr)
        f_sales = pool.submit(api.get_customer_sales_summary, name)
        f_eff = pool.submit(api.get_customer_efficiency_by_category, name, tr)
        f_sales_items = pool.submit(api.get_customer_sales_items, name)
        f_active_orders = pool.submit(api.get_customer_sales_active_orders, name)
        f_active_items = pool.submit(api.get_customer_sales_active_items, name)
        f_service_breakdown = pool.submit(api.get_customer_sales_service_breakdown, name)
        f_sla = pool.submit(aura.get_dc_services_availability, sla_start, sla_end)
        data = f_resources.result()
        # Compliance reads infra from Redis populated by /resources — run after resources, not in parallel.
        compliance_payload = api.get_customer_resource_compliance(name, "virtualization", tr)
        avail_bundle = f_avail.result()
        s3_data = f_s3.result()
        phys_inv_devices = f_phys.result()
        itsm_summary = f_itsm_summary.result()
        itsm_extremes = f_itsm_extremes.result()
        itsm_tickets = f_itsm_tickets.result()
        sales_summary = f_sales.result()
        eff_by_cat = f_eff.result()
        sales_items = f_sales_items.result()
        active_orders = f_active_orders.result()
        active_items = f_active_items.result()
        service_breakdown = f_service_breakdown.result()
        sla_categories = aggregate_sla_categories(f_sla.result())

    vm_outage_counts = avail_bundle.get("vm_outage_counts") or {}

    totals = data.get("totals", {})
    assets = data.get("assets", {})
    backup_assets = assets.get("backup", {}) or {}
    backup_totals = totals.get("backup", {}) or {}

    has_s3 = bool(s3_data.get("vaults"))
    has_phys_inv = bool(phys_inv_devices)

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

    power_asset = assets.get("power", {}) or {}

    classic   = assets.get("classic", {}) or {}
    hyperconv = assets.get("hyperconv", {}) or {}
    pure_nx   = assets.get("pure_nutanix", {}) or {}
    show_pure_tab = asset_has_usage(pure_nx)
    show_classic_tab = asset_has_usage(classic)
    show_hyperconv_tab = asset_has_usage(hyperconv)
    show_power_tab = asset_has_usage(power_asset, instance_keys=("lpar_count",))

    virt_tab_defs: list[tuple[str, str, html.Div]] = []
    if show_classic_tab:
        virt_tab_defs.append(
            (
                "classic",
                "Klasik Mimari",
                _tab_classic(classic, vm_outage_counts),
            )
        )
    if show_hyperconv_tab:
        virt_tab_defs.append(
            (
                "hyperconv",
                "Hyperconverged Mimari",
                _tab_hyperconv(hyperconv, pure_nx, vm_outage_counts),
            )
        )
    if show_pure_tab:
        virt_tab_defs.append(
            (
                "pure_nx",
                "Pure Nutanix (AHV)",
                _tab_pure_nutanix(pure_nx, vm_outage_counts),
            )
        )
    if show_power_tab:
        virt_tab_defs.append(
            (
                "power",
                "Power Mimari",
                _tab_power(power_asset, vm_outage_counts),
            )
        )

    if virt_tab_defs:
        default_virt = virt_tab_defs[0][0]
        virt_content = dmc.Tabs(
            color="violet",
            variant="outline",
            radius="md",
            value=default_virt,
            children=[
                dmc.TabsList(
                    children=[dmc.TabsTab(label, value=value) for value, label, _panel in virt_tab_defs]
                ),
                *[
                    dmc.TabsPanel(value=value, pt="lg", children=panel)
                    for value, _label, panel in virt_tab_defs
                ],
            ],
        )
    else:
        virt_content = dmc.Alert(
            color="gray",
            variant="light",
            title="No virtualization assets",
            children="No provisioned compute instances were returned for this customer.",
        )

    backup_tabs_manager = _build_backup_tabs(
        backup_assets, backup_totals, eff_by_cat, include_sold_vs_used=True
    )
    backup_tabs_customer = _build_backup_tabs(
        backup_assets, backup_totals, eff_by_cat, include_sold_vs_used=False
    )

    s3_panel = html.Div(
        id="s3-customer-metrics-panel",
        style={"padding": "0 30px"},
        children=build_customer_s3_panel(name, s3_data, tr, None) if has_s3 else html.Div(),
    )
    phys_inv_panel = _tab_physical_inventory(phys_inv_devices)
    avail_panel = _tab_customer_availability(avail_bundle)

    summary_kwargs = dict(
        totals=totals,
        assets=assets,
        backup_totals=backup_totals,
        sales_summary=sales_summary,
        compliance_payload=compliance_payload,
        efficiency_rows=eff_by_cat,
        itsm_summary=itsm_summary,
        vm_outage_counts=vm_outage_counts,
        service_breakdown=service_breakdown,
        s3_data=s3_data,
        sla_categories=sla_categories,
    )

    export_context = {
        "customer_name": name,
        "totals": totals or {},
        "backup_totals": backup_totals or {},
        "assets": assets or {},
        "classic": classic,
        "hyperconv": hyperconv,
        "pure_nx": pure_nx,
        "power_asset": power_asset,
        "s3_data": s3_data or {},
        "phys_inv_devices": phys_inv_devices or [],
        "itsm_summary": itsm_summary or {},
        "itsm_extremes": itsm_extremes or {},
        "itsm_tickets": itsm_tickets or [],
        "compliance_payload": compliance_payload or {},
        "efficiency_rows": eff_by_cat or [],
        "sales_summary": sales_summary or {},
    }

    return {
        "manager": {
            "summary": _tab_summary(name, perspective=PERSPECTIVE_MANAGER, **summary_kwargs),
            "virt": virt_content,
            "avail": avail_panel,
            "backup": backup_tabs_manager,
            "billing": _tab_billing(
                totals,
                assets,
                backup_totals,
                s3_data,
                sales_summary=sales_summary,
                crm_eff_panel=build_sold_vs_used_stack(_crm_rows_outside_virt_backup(eff_by_cat)),
                customer_name=name,
                service_breakdown=service_breakdown,
                sales_items=sales_items,
                active_orders=active_orders,
                active_items=active_items,
                efficiency_rows=eff_by_cat,
            ),
            "itsm": _tab_itsm(name, tr, itsm_summary, itsm_extremes, itsm_tickets),
            "s3": s3_panel,
            "phys_inv": phys_inv_panel,
        },
        "customer": {
            "summary": _tab_summary(name, perspective=PERSPECTIVE_CUSTOMER, **summary_kwargs),
            "virt": virt_content,
            "avail": avail_panel,
            "backup": backup_tabs_customer,
            "s3": s3_panel,
            "phys_inv": phys_inv_panel,
        },
        "has_s3": has_s3,
        "has_phys_inv": has_phys_inv,
        "customer_name": name,
        "export_context": export_context,
    }


# ---------------------------------------------------------------------------
# Page builders
# ---------------------------------------------------------------------------

def _section_visible(visible_sections, code: str) -> bool:
    return visible_sections is None or code in visible_sections


def _build_customer_intro_card(chosen: str) -> dmc.SimpleGrid:
    return dmc.SimpleGrid(
        cols=3,
        spacing="lg",
        style={"padding": "0 30px", "marginBottom": "24px"},
        children=[
            html.Div(
                className="nexus-card",
                style={"padding": "24px"},
                children=[
                    dmc.Group(
                        justify="space-between",
                        mb="lg",
                        children=[
                            dmc.Group(
                                gap="sm",
                                children=[
                                    dmc.ThemeIcon(
                                        size="xl",
                                        variant="light",
                                        color="indigo",
                                        radius="md",
                                        children=DashIconify(
                                            icon="solar:users-group-two-rounded-bold-duotone",
                                            width=30,
                                        ),
                                    ),
                                    dmc.Stack(
                                        gap=0,
                                        children=[
                                            dmc.Text(chosen, fw=700, size="lg", c="#2B3674"),
                                            dmc.Text("Billing assets", size="sm", c="#A3AED0", fw=500),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                    dmc.Text(
                        "All metrics show resources allocated/provisioned to this customer across all platforms.",
                        size="sm",
                        c="#A3AED0",
                    ),
                ],
            ),
        ],
    )


def _build_customer_export_group(visible_sections) -> dmc.Group | None:
    if not _section_visible(visible_sections, "action:customer:export"):
        return None
    return dmc.Group(
        gap=6,
        align="center",
        children=[
            dmc.Text("Export", size="xs", c="dimmed"),
            dmc.Button("CSV", id="customer-export-csv", size="xs", variant="light", color="gray"),
            dmc.Button("Excel", id="customer-export-xlsx", size="xs", variant="light", color="gray"),
            dmc.Button("PDF", id="customer-export-pdf", size="xs", variant="light", color="gray"),
        ],
    )


def _build_perspective_switch(perspective: str) -> dmc.SegmentedControl:
    return dmc.SegmentedControl(
        id="customer-view-perspective",
        value=perspective,
        data=[
            {"label": "Manager", "value": PERSPECTIVE_MANAGER},
            {"label": "Customer", "value": PERSPECTIVE_CUSTOMER},
        ],
        size="xs",
        color="indigo",
    )


def _build_customer_header_extras(
    *,
    perspective: str,
    visible_sections,
) -> list:
    access = perspective_access(visible_sections)
    extras: list = []
    if show_perspective_switch(access):
        extras.append(_build_perspective_switch(perspective))
    export_group = _build_customer_export_group(visible_sections)
    if export_group is not None:
        extras.append(export_group)
    return extras


def _build_customer_tabs_list(
    perspective: str,
    *,
    has_s3: bool = False,
    has_phys_inv: bool = False,
) -> dmc.TabsList:
    tabs = [
        dmc.TabsTab("Summary", value="summary"),
        dmc.TabsTab("Virtualization", value="virt"),
        dmc.TabsTab("Availability", value="avail"),
        dmc.TabsTab("Backup", value="backup"),
    ]
    if perspective == PERSPECTIVE_MANAGER:
        tabs.extend(
            [
                dmc.TabsTab("Billing", value="billing"),
                dmc.TabsTab("ITSM", value="itsm"),
            ]
        )
    if has_phys_inv:
        tabs.append(dmc.TabsTab("Physical Inventory", value="phys-inv"))
    if has_s3:
        tabs.append(dmc.TabsTab("S3", value="s3"))
    return dmc.TabsList(style={"paddingTop": "8px"}, children=tabs)


def _perspective_tab_panels(
    tab_content: dict,
    *,
    perspective: str,
    has_s3: bool,
    has_phys_inv: bool,
) -> list:
    panels = [
        dmc.TabsPanel(
            value="summary",
            children=dmc.Stack(
                gap="lg",
                style={"padding": "0 30px"},
                children=[tab_content.get("summary")],
            ),
        ),
        dmc.TabsPanel(
            value="virt",
            children=html.Div(style={"padding": "0 30px"}, children=[tab_content.get("virt")]),
        ),
        dmc.TabsPanel(
            value="avail",
            children=dmc.Stack(
                gap="lg",
                style={"padding": "0 30px"},
                children=[tab_content.get("avail")],
            ),
        ),
        dmc.TabsPanel(
            value="backup",
            children=html.Div(style={"padding": "0 30px"}, children=[tab_content.get("backup")]),
        ),
    ]
    if perspective == PERSPECTIVE_MANAGER:
        panels.extend(
            [
                dmc.TabsPanel(
                    value="billing",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[tab_content.get("billing")],
                    ),
                ),
                dmc.TabsPanel(
                    value="itsm",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[tab_content.get("itsm")],
                    ),
                ),
            ]
        )
    if has_phys_inv:
        panels.append(
            dmc.TabsPanel(
                value="phys-inv",
                children=dmc.Stack(
                    gap="lg",
                    style={"padding": "0 30px"},
                    children=[tab_content.get("phys_inv")],
                ),
            )
        )
    if has_s3:
        panels.append(
            dmc.TabsPanel(value="s3", children=tab_content.get("s3") or html.Div())
        )
    return panels


def _resolve_tab_content(content: dict, perspective: str) -> dict:
    if "manager" in content and "customer" in content:
        return content.get(perspective) or content.get(PERSPECTIVE_MANAGER) or {}
    return content


def render_customer_loading_page(
    chosen: str,
    time_range,
    visible_sections=None,
    *,
    perspective: str | None = None,
) -> html.Div:
    access = perspective_access(visible_sections)
    perspective = effective_perspective(perspective, access)
    tr = time_range or default_time_range()
    header = create_detail_header(
        title="Customer View",
        back_href="/customers",
        back_label="Customers",
        subtitle_badge=f"Customer: {chosen}",
        subtitle_color="teal",
        time_range=tr,
        icon="solar:users-group-two-rounded-bold-duotone",
        tabs=_build_customer_tabs_list(perspective),
        right_extra=_build_customer_header_extras(perspective=perspective, visible_sections=visible_sections),
    )
    return html.Div(
        className="customer-page-enter",
        children=[
            dmc.Tabs(
                color="indigo",
                variant="pills",
                radius="md",
                value="summary",
                children=[
                    header,
                    _build_customer_intro_card(chosen),
                    dmc.TabsPanel(
                        value="summary",
                        children=build_customer_loading_shell(chosen),
                    ),
                ],
            ),
        ],
    )


def render_customer_page(
    chosen: str,
    time_range,
    content: dict,
    visible_sections=None,
    *,
    perspective: str | None = None,
) -> html.Div:
    access = perspective_access(visible_sections)
    perspective = effective_perspective(perspective, access)
    tr = time_range or default_time_range()
    has_s3 = bool(content.get("has_s3"))
    has_phys_inv = bool(content.get("has_phys_inv"))
    tab_content = _resolve_tab_content(content, perspective)
    header = create_detail_header(
        title="Customer View",
        back_href="/customers",
        back_label="Customers",
        subtitle_badge=f"Customer: {chosen}",
        subtitle_color="teal",
        time_range=tr,
        icon="solar:users-group-two-rounded-bold-duotone",
        tabs=_build_customer_tabs_list(perspective, has_s3=has_s3, has_phys_inv=has_phys_inv),
        right_extra=_build_customer_header_extras(perspective=perspective, visible_sections=visible_sections),
    )
    return html.Div(
        className="customer-page-enter",
        children=[
            dmc.Tabs(
                color="indigo",
                variant="pills",
                radius="md",
                value="summary",
                children=[
                    header,
                    *_perspective_tab_panels(
                        tab_content,
                        perspective=perspective,
                        has_s3=has_s3,
                        has_phys_inv=has_phys_inv,
                    ),
                ],
            ),
        ],
    )


def build_customer_layout_shell(visible_sections=None):
    """Phase A: instant skeleton shell; callbacks build content off the render path."""
    return html.Div([
        dcc.Store(
            id="customer-view-visible-sections",
            data=list(visible_sections) if visible_sections else None,
        ),
        dcc.Store(id="customer-view-perspective-store", data=None),
        dcc.Store(id="customer-export-store", data=None),
        dcc.Download(id="customer-export-download"),
        dcc.Loading(
            id="customer-view-content-loading",
            type="circle", color="#4318FF", delay_show=150,
            children=html.Div(id="customer-view-page-root", style={"minHeight": "60vh", "padding": "0 8px"}),
        ),
    ])


@callback(
    Output("customer-view-page-root", "children"),
    Input("url", "pathname"),
    Input("url", "search"),
    Input("app-time-range", "data"),
    State("customer-view-visible-sections", "data"),
)
def _fill_customer_view_content(pathname, search, time_range, visible_sections):
    """Phase B: show loading shell while async callback loads data."""
    if pathname != "/customer-view":
        return dash.no_update
    from urllib.parse import parse_qs
    chosen = (parse_qs((search or "").lstrip("?")).get("customer", [""])[0] or "").strip()
    tr = time_range or default_time_range()
    access = perspective_access(visible_sections)
    perspective = default_perspective(access)
    return render_customer_loading_page(chosen, tr, visible_sections, perspective=perspective)


def build_customer_layout(time_range=None, selected_customer=None, visible_sections=None):
    tr = time_range or default_time_range()
    chosen = (selected_customer or "").strip()
    vs = visible_sections

    if not chosen:
        return html.Div(
            style={"padding": "40px 30px"},
            children=[
                dmc.Alert(
                    color="yellow",
                    title="No customer selected",
                    children=[
                        "Open a customer from the ",
                        dmc.Anchor("Customers catalog", href="/customers", underline="always"),
                        " to view billing assets and metrics.",
                    ],
                )
            ],
        )

    export_group = _build_customer_export_group(vs)
    access = perspective_access(vs)
    perspective = default_perspective(access)
    export_toolbar = (
        html.Div(
            id="customer-export-toolbar",
            style={"display": "flex", "justifyContent": "flex-end", "padding": "8px 30px 0"},
            children=[export_group],
        )
        if export_group and not show_perspective_switch(access)
        else html.Div(id="customer-export-toolbar")
    )

    return html.Div(
        children=[
            dcc.Store(
                id="customer-view-visible-sections",
                data=list(vs) if vs is not None else None,
            ),
            dcc.Store(id="customer-view-perspective-store", data=perspective),
            dcc.Store(
                id="customer-export-store",
                data={"customer": chosen, "export_context": {}, "perspective_access": access},
            ),
            dcc.Download(id="customer-export-download"),
            export_toolbar,
            html.Div(
                id="customer-view-page-root",
                children=render_customer_loading_page(
                    chosen, tr, visible_sections=vs, perspective=perspective
                ),
            ),
        ],
    )


def layout():
    return build_customer_layout(default_time_range())


def _resolve_export_sheets_from_store(store: dict | None) -> dict[str, list[dict]]:
    store = store or {}
    export_context = store.get("export_context")
    perspective_access_map = store.get("perspective_access")
    if not isinstance(perspective_access_map, dict):
        perspective_access_map = perspective_access(None)
    if isinstance(export_context, dict) and export_context.get("customer_name"):
        return _build_export_sheets_for_user(export_context, perspective_access_map)
    sheets_raw = store.get("sheets")
    if isinstance(sheets_raw, dict) and sheets_raw:
        return sheets_raw
    if store.get("rows"):
        return {"Legacy": store.get("rows") or []}
    return {}


def _export_sheet_order() -> list[str]:
    return [
        "Customer_Meta",
        "Manager_Customer_Meta",
        "Customer_Customer_Meta",
        "Summary_Totals",
        "Manager_Summary_Totals",
        "Customer_Summary_Usage_Totals",
        "Backup_Totals",
        "Manager_Backup_Totals",
        "Customer_Backup_Totals",
        "Assets_Classic_Block",
        "Manager_Assets_Classic_Block",
        "Customer_Assets_Classic_Block",
        "Assets_Hyperconv_Block",
        "Manager_Assets_Hyperconv_Block",
        "Customer_Assets_Hyperconv_Block",
        "Assets_Pure_Nutanix_Block",
        "Manager_Assets_Pure_Nutanix_Block",
        "Customer_Assets_Pure_Nutanix_Block",
        "Assets_Power_Block",
        "Manager_Assets_Power_Block",
        "Customer_Assets_Power_Block",
        "Assets_Intel_Aggregate",
        "Manager_Assets_Intel_Aggregate",
        "Customer_Assets_Intel_Aggregate",
        "Classic_VMs",
        "Manager_Classic_VMs",
        "Customer_Classic_VMs",
        "Classic_VMs_Real_CPU",
        "Manager_Classic_VMs_Real_CPU",
        "Customer_Classic_VMs_Real_CPU",
        "HyperConv_VMs",
        "Manager_HyperConv_VMs",
        "Customer_HyperConv_VMs",
        "HyperConv_VMs_Real_CPU",
        "Manager_HyperConv_VMs_Real_CPU",
        "Customer_HyperConv_VMs_Real_CPU",
        "Pure_Nutanix_VMs",
        "Manager_Pure_Nutanix_VMs",
        "Customer_Pure_Nutanix_VMs",
        "Power_LPARS",
        "Manager_Power_LPARS",
        "Customer_Power_LPARS",
        "Backup_Veeam_Detail",
        "Manager_Backup_Veeam_Detail",
        "Customer_Backup_Veeam_Detail",
        "Backup_Zerto_Detail",
        "Manager_Backup_Zerto_Detail",
        "Customer_Backup_Zerto_Detail",
        "Backup_Netbackup_Detail",
        "Manager_Backup_Netbackup_Detail",
        "Customer_Backup_Netbackup_Detail",
        "Billing_Key_Metrics",
        "Manager_Billing_Key_Metrics",
        "S3_Vaults",
        "Manager_S3_Vaults",
        "Customer_S3_Vaults",
        "Physical_Inventory",
        "Manager_Physical_Inventory",
        "Customer_Physical_Inventory",
        "ITSM_Summary",
        "Manager_ITSM_Summary",
        "ITSM_Extremes_Closed",
        "Manager_ITSM_Extremes_Closed",
        "ITSM_Extremes_OpenSlaBreach",
        "Manager_ITSM_Extremes_OpenSlaBreach",
        "ITSM_All_Tickets",
        "Manager_ITSM_All_Tickets",
        "Legacy",
    ]


def _sheets_to_dataframes(sheets_raw: dict[str, list[dict]]) -> dict:
    order = _export_sheet_order()
    dfs = {}
    for name in order:
        recs = sheets_raw.get(name)
        if recs:
            dfs[name] = records_to_dataframe(recs if isinstance(recs, list) else [])
    for name, recs in sheets_raw.items():
        if name not in dfs and isinstance(recs, list):
            dfs[name] = records_to_dataframe(recs)
    return dfs


@callback(
    Output("customer-export-download", "data"),
    Input("customer-export-csv", "n_clicks"),
    Input("customer-export-xlsx", "n_clicks"),
    Input("customer-export-pdf", "n_clicks"),
    State("customer-export-store", "data"),
    State("app-time-range", "data"),
    prevent_initial_call=True,
)
def export_customer_view(nc, nx, npdf, store, time_range):
    if not nc and not nx and not npdf:
        raise dash.exceptions.PreventUpdate
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    tid = ctx.triggered[0]["prop_id"].split(".")[0]
    fmt_map = {
        "customer-export-csv": "csv",
        "customer-export-xlsx": "xlsx",
        "customer-export-pdf": "pdf",
    }
    fmt = fmt_map.get(tid)
    if not fmt:
        return dash.no_update
    if fmt == "csv" and not nc:
        raise dash.exceptions.PreventUpdate
    if fmt == "xlsx" and not nx:
        raise dash.exceptions.PreventUpdate
    if fmt == "pdf" and not npdf:
        raise dash.exceptions.PreventUpdate
    store = store or {}
    base = str(store.get("customer") or "customer_view")
    extra = {"customer": base}
    sheets_raw = _resolve_export_sheets_from_store(store)
    dfs = _sheets_to_dataframes(sheets_raw)

    if fmt == "xlsx":
        content = dataframes_to_excel_with_meta(dfs, time_range, "Customer_View", extra)
        return dash_send_excel_workbook(content, base)
    if fmt == "pdf":
        content = dataframes_to_pdf_with_meta(dfs, time_range, "Customer_View", extra)
        return dash_send_pdf_workbook(content, f"{base}.pdf")
    report_info = build_report_info_df(time_range, "Customer_View", extra)
    sections = [(k, v) for k, v in dfs.items()]
    if not sections:
        sections = [("Data", records_to_dataframe([]))]
    return dash_send_csv_bytes(csv_bytes_with_report_header(report_info, sections), base)
