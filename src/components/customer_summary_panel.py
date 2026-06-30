"""Unified Customer View Summary panel — compact signals and problems list."""
from __future__ import annotations

import math
from typing import Any

import dash_mantine_components as dmc
from dash import html

from src.components.crm_sales_panel import format_crm_money
from src.components.sold_vs_used_panel import build_compliance_issue_table
from src.services import product_catalog as pc
from src.utils.visibility import (
    asset_has_usage,
    compute_sla_compliance_pct,
    compute_total_overage_loss_tl,
    count_outage_vms,
    filter_overusage_rows,
    is_meaningful_value,
)


def aggregate_sla_categories(dc_sla_items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Flatten category availability rows from all datacenter-services SLA items."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in dc_sla_items or []:
        for cat in item.get("categories") or []:
            if not isinstance(cat, dict):
                continue
            name = str(cat.get("category") or "").strip()
            key = name.lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(cat)
    return out


def collect_low_availability_services(
    service_breakdown: list[dict[str, Any]] | None,
    sla_categories: list[dict[str, Any]] | None,
    *,
    threshold: float = 98.0,
) -> list[dict[str, Any]]:
    """Return billed services whose matched AuraNotify availability is below threshold."""
    low: list[dict[str, Any]] = []
    for row in service_breakdown or []:
        label = str(row.get("service_label") or row.get("service_code") or "").strip()
        if not label:
            continue
        pct, matched = pc.service_availability_pct(label, sla_categories or [])
        if matched is None:
            continue
        if pct < threshold:
            low.append({"service_label": label, "availability_pct": pct})
    low.sort(key=lambda x: float(x.get("availability_pct") or 0))
    return low


def _fmt_resolution_hours(h: Any) -> str:
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


def _compact_kpi(title: str, display: str) -> html.Div:
    return html.Div(
        style={
            "padding": "14px 12px",
            "borderRadius": "12px",
            "background": "#F4F7FE",
            "textAlign": "center",
        },
        children=[
            html.Div(title, style={"color": "#A3AED0", "fontSize": "0.7rem", "fontWeight": 600}),
            html.Div(display, style={"color": "#2B3674", "fontSize": "1rem", "fontWeight": 800, "marginTop": "4px"}),
        ],
    )


def build_summary_signal_strip(
    signal_defs: list[tuple[Any, str, str]],
) -> dmc.SimpleGrid | None:
    """Compact KPI grid from (raw_value, title, display) tuples."""
    tiles = [_compact_kpi(title, display) for raw, title, display in signal_defs if is_meaningful_value(raw)]
    if not tiles:
        return None
    return dmc.SimpleGrid(
        cols={"base": 2, "sm": 3, "md": 4, "lg": 6},
        spacing="md",
        children=tiles,
    )


def _build_usage_signal_defs(
    *,
    totals: dict,
    assets: dict,
    backup_totals: dict,
    s3_data: dict | None,
) -> list[tuple[Any, str, str]]:
    """Usage-only signal definitions for the customer perspective summary."""
    classic = assets.get("classic", {}) or {}
    hyperconv = assets.get("hyperconv", {}) or {}
    pure_nx = assets.get("pure_nutanix", {}) or {}
    power = assets.get("power", {}) or {}

    total_vms = int(totals.get("vms_total", 0) or 0)
    veeam_defined = int(backup_totals.get("veeam_defined_sessions", 0) or 0)
    zerto_protected = int(backup_totals.get("zerto_protected_vms", 0) or 0)
    nb_pre_gib = float(backup_totals.get("netbackup_pre_dedup_gib", 0) or 0)
    vault_count = len((s3_data or {}).get("vaults") or [])

    signals: list[tuple[Any, str, str]] = [
        (total_vms, "Total instances", f"{total_vms:,}"),
        (veeam_defined, "Veeam sessions", f"{veeam_defined:,}"),
        (zerto_protected, "Zerto protected VMs", f"{zerto_protected:,}"),
        (nb_pre_gib, "NetBackup pre-dedup", f"{nb_pre_gib:.2f} GiB"),
        (vault_count, "S3 vaults", f"{vault_count:,}"),
    ]
    if asset_has_usage(classic):
        n = int(classic.get("vm_count", 0) or 0)
        signals.append((n, "Classic VMs", f"{n:,}"))
    if asset_has_usage(hyperconv):
        n = int(hyperconv.get("vm_count", 0) or 0)
        signals.append((n, "Hyperconverged VMs", f"{n:,}"))
    if asset_has_usage(pure_nx):
        n = int(pure_nx.get("vm_count", 0) or 0)
        signals.append((n, "Pure Nutanix VMs", f"{n:,}"))
    if asset_has_usage(power, instance_keys=("lpar_count",)):
        n = int(power.get("lpar_count", 0) or 0)
        signals.append((n, "Power LPARs", f"{n:,}"))
    return signals


def _build_signal_defs(
    *,
    totals: dict,
    assets: dict,
    backup_totals: dict,
    sales_summary: dict | None,
    s3_data: dict | None,
    itsm_summary: dict | None,
    vm_outage_counts: dict | None,
    sla_categories: list[dict[str, Any]] | None,
    service_breakdown: list[dict[str, Any]] | None,
    total_overage_loss: float | None = None,
) -> list[tuple[Any, str, str]]:
    """Billable + satisfaction signal definitions for the summary strip."""
    summary = sales_summary or {}
    currency = summary.get("currency")
    classic = assets.get("classic", {}) or {}
    hyperconv = assets.get("hyperconv", {}) or {}
    pure_nx = assets.get("pure_nutanix", {}) or {}
    power = assets.get("power", {}) or {}
    sm = itsm_summary or {}

    total_vms = int(totals.get("vms_total", 0) or 0)
    veeam_defined = int(backup_totals.get("veeam_defined_sessions", 0) or 0)
    zerto_protected = int(backup_totals.get("zerto_protected_vms", 0) or 0)
    nb_pre_gib = float(backup_totals.get("netbackup_pre_dedup_gib", 0) or 0)
    vault_count = len((s3_data or {}).get("vaults") or [])

    billable: list[tuple[Any, str, str]] = [
        (total_vms, "Total instances", f"{total_vms:,}"),
        (total_overage_loss, "Est. overage loss (total)", format_crm_money(total_overage_loss, currency)),
        (summary.get("active_order_value"), "Active order value", format_crm_money(summary.get("active_order_value"), currency)),
        (veeam_defined, "Veeam sessions", f"{veeam_defined:,}"),
        (zerto_protected, "Zerto protected VMs", f"{zerto_protected:,}"),
        (nb_pre_gib, "NetBackup pre-dedup", f"{nb_pre_gib:.2f} GiB"),
        (vault_count, "S3 vaults", f"{vault_count:,}"),
    ]
    if asset_has_usage(classic):
        n = int(classic.get("vm_count", 0) or 0)
        billable.append((n, "Classic VMs", f"{n:,}"))
    if asset_has_usage(hyperconv):
        n = int(hyperconv.get("vm_count", 0) or 0)
        billable.append((n, "Hyperconverged VMs", f"{n:,}"))
    if asset_has_usage(pure_nx):
        n = int(pure_nx.get("vm_count", 0) or 0)
        billable.append((n, "Pure Nutanix VMs", f"{n:,}"))
    if asset_has_usage(power, instance_keys=("lpar_count",)):
        n = int(power.get("lpar_count", 0) or 0)
        billable.append((n, "Power LPARs", f"{n:,}"))

    sla_pct = compute_sla_compliance_pct(sm)
    inc_open = int(sm.get("incident_open", 0) or 0)
    sr_open = int(sm.get("sr_open", 0) or 0)
    open_total = inc_open + sr_open
    outage_vms = count_outage_vms(vm_outage_counts)

    low_availability = collect_low_availability_services(service_breakdown, sla_categories)
    min_avail = None
    if low_availability:
        min_avail = min(float(x.get("availability_pct") or 100) for x in low_availability)
    elif sla_categories and service_breakdown:
        pcts = []
        for row in service_breakdown:
            label = str(row.get("service_label") or row.get("service_code") or "")
            pct, matched = pc.service_availability_pct(label, sla_categories)
            if matched is not None:
                pcts.append(pct)
        if pcts:
            min_avail = min(pcts)

    satisfaction: list[tuple[Any, str, str]] = [
        (sla_pct, "SLA compliance", f"{sla_pct:.1f}%" if sla_pct is not None else "-"),
        (min_avail, "Lowest service availability", f"{min_avail:.1f}%" if min_avail is not None else "-"),
        (sm.get("avg_resolution_hours"), "Avg ticket resolution", _fmt_resolution_hours(sm.get("avg_resolution_hours"))),
        (open_total, "Open tickets", f"{open_total:,}"),
        (outage_vms, "VMs with outages", f"{outage_vms:,}"),
    ]
    return billable + satisfaction


def build_summary_problems_section(
    *,
    overusage_rows: list[dict[str, Any]] | None,
    itsm_summary: dict | None,
    low_availability_services: list[dict[str, Any]] | None,
    currency: str | None = "TL",
    total_overage_loss: float | None = None,
) -> html.Div:
    """Bottom section: unified problems list (overusage, tickets, SLA, low availability)."""
    sm = itsm_summary or {}
    inc_open = int(sm.get("incident_open", 0) or 0)
    sr_open = int(sm.get("sr_open", 0) or 0)
    sla_breach = int(sm.get("sla_breach_count", 0) or 0)
    low_avail = low_availability_services or []

    problem_lines: list = []

    overusage_table = build_compliance_issue_table(overusage_rows, currency=currency)
    if overusage_table.children:
        overage_header_children: list = [
            dmc.Text("Resource overusage", size="sm", fw=700, c="#2B3674"),
        ]
        if is_meaningful_value(total_overage_loss):
            overage_header_children.append(
                dmc.Text(
                    f"Estimated total overage loss: {format_crm_money(total_overage_loss, currency)}",
                    size="sm",
                    fw=700,
                    c="#E03131",
                )
            )
        problem_lines.append(
            dmc.Stack(
                gap="xs",
                children=[
                    dmc.Group(justify="space-between", align="flex-start", children=overage_header_children),
                    overusage_table,
                ],
            )
        )

    if inc_open > 0 or sr_open > 0:
        problem_lines.append(
            dmc.Group(
                justify="space-between",
                children=[
                    dmc.Text("Open tickets", size="sm", fw=600, c="#2B3674"),
                    dmc.Badge(
                        f"{inc_open:,} incidents · {sr_open:,} service requests",
                        color="orange",
                        variant="light",
                        size="sm",
                    ),
                ],
            )
        )

    if sla_breach > 0:
        problem_lines.append(
            dmc.Group(
                justify="space-between",
                children=[
                    dmc.Text("SLA breach (open)", size="sm", fw=600, c="#2B3674"),
                    dmc.Badge(f"{sla_breach:,} past target resolution", color="red", variant="light", size="sm"),
                ],
            )
        )

    for svc in low_avail:
        label = str(svc.get("service_label") or "Service")
        pct = float(svc.get("availability_pct") or 0)
        problem_lines.append(
            dmc.Group(
                justify="space-between",
                children=[
                    dmc.Text(label, size="sm", fw=600, c="#2B3674"),
                    dmc.Badge(f"{pct:.1f}% (< 98%)", color="red", variant="light", size="sm"),
                ],
            )
        )

    if not problem_lines:
        return dmc.Alert(
            color="gray",
            variant="light",
            title="No issues in this period",
            children="No resource overusage, open ticket backlog, SLA breaches, or low availability detected.",
        )

    return dmc.Stack(
        gap="md",
        children=[
            dmc.Text("Issues requiring attention", size="sm", fw=700, c="#2B3674"),
            *problem_lines,
        ],
    )


def build_customer_summary_panel(
    customer_name: str,
    *,
    totals: dict,
    assets: dict,
    backup_totals: dict,
    sales_summary: dict | None = None,
    compliance_payload: dict | None = None,
    efficiency_rows: list[dict[str, Any]] | None = None,
    itsm_summary: dict | None = None,
    vm_outage_counts: dict | None = None,
    service_breakdown: list[dict[str, Any]] | None = None,
    s3_data: dict | None = None,
    sla_categories: list[dict[str, Any]] | None = None,
    perspective: str = "manager",
) -> html.Div:
    """Single unified summary card: header, compact signals, problems list."""
    if perspective == "customer":
        signal_defs = _build_usage_signal_defs(
            totals=totals,
            assets=assets,
            backup_totals=backup_totals,
            s3_data=s3_data,
        )
        signal_strip = build_summary_signal_strip(signal_defs)
        body_children: list = []
        if signal_strip is not None:
            body_children.append(
                dmc.Stack(
                    gap="xs",
                    children=[
                        dmc.Text("Resource usage", size="sm", fw=700, c="#2B3674"),
                        signal_strip,
                    ],
                )
            )
        if not body_children:
            return dmc.Alert(
                color="gray",
                variant="light",
                title="No usage data",
                children="No meaningful usage indicators for this customer in the selected period.",
            )
        return html.Div(
            className="nexus-card",
            style={"padding": "24px", "margin": "0"},
            children=[
                dmc.Stack(
                    gap="lg",
                    children=[
                        dmc.Group(
                            gap="xs",
                            align="center",
                            children=[
                                dmc.Text(customer_name, fw=700, size="lg", c="#2B3674"),
                            ],
                        ),
                        dmc.Text(
                            "Customer overview — provisioned resources and usage; see tabs for inventory detail.",
                            size="sm",
                            c="#A3AED0",
                            fw=500,
                        ),
                        dmc.Divider(color="#F4F7FE"),
                        *body_children,
                    ],
                ),
            ],
        )

    summary = sales_summary or {}
    currency = summary.get("currency")
    compliance_summary = (compliance_payload or {}).get("summary") or {}
    compliance_rows = (compliance_payload or {}).get("rows") or []
    overusage_source = compliance_rows if compliance_rows else (efficiency_rows or [])
    overusage_rows = filter_overusage_rows(overusage_source)
    total_overage_loss = compute_total_overage_loss_tl(compliance_payload, efficiency_rows)
    has_overuse = bool(compliance_summary.get("has_overuse")) or bool(overusage_rows) or total_overage_loss > 0
    low_availability = collect_low_availability_services(service_breakdown, sla_categories)

    signal_defs = _build_signal_defs(
        totals=totals,
        assets=assets,
        backup_totals=backup_totals,
        sales_summary=sales_summary,
        s3_data=s3_data,
        itsm_summary=itsm_summary,
        vm_outage_counts=vm_outage_counts,
        sla_categories=sla_categories,
        service_breakdown=service_breakdown,
        total_overage_loss=total_overage_loss,
    )
    signal_strip = build_summary_signal_strip(signal_defs)

    header_children: list = [
        dmc.Group(
            gap="xs",
            align="center",
            children=[
                dmc.Text(customer_name, fw=700, size="lg", c="#2B3674"),
                dmc.Badge("Resource overage", color="red", variant="filled", size="sm") if has_overuse else None,
            ],
        ),
        dmc.Text(
            "Customer overview — billable footprint and satisfaction signals; see Billing or drill-down tabs for detail.",
            size="sm",
            c="#A3AED0",
            fw=500,
        ),
    ]
    active_value = summary.get("active_order_value")
    if is_meaningful_value(active_value):
        header_children.append(
            dmc.Text(
                f"Active order value: {format_crm_money(active_value, currency)}",
                size="sm",
                c="#4318FF",
                fw=700,
            )
        )
    if has_overuse and is_meaningful_value(total_overage_loss):
        header_children.append(
            dmc.Text(
                f"Est. overage loss (total): {format_crm_money(total_overage_loss, currency)}",
                size="sm",
                c="#E03131",
                fw=700,
            )
        )

    body_children: list = []
    if signal_strip is not None:
        body_children.append(
            dmc.Stack(
                gap="xs",
                children=[
                    dmc.Text("Customer signals", size="sm", fw=700, c="#2B3674"),
                    signal_strip,
                ],
            )
        )

    body_children.append(
        build_summary_problems_section(
            overusage_rows=overusage_rows,
            itsm_summary=itsm_summary,
            low_availability_services=low_availability,
            currency=currency,
            total_overage_loss=total_overage_loss,
        )
    )

    if not signal_strip and not overusage_rows and not low_availability:
        return dmc.Alert(
            color="gray",
            variant="light",
            title="No summary data",
            children="No meaningful infrastructure, CRM, or satisfaction indicators for this customer in the selected period.",
        )

    return html.Div(
        className="nexus-card",
        style={"padding": "24px", "margin": "0"},
        children=[
            dmc.Stack(gap="lg", children=[*header_children, dmc.Divider(color="#F4F7FE"), *body_children]),
        ],
    )
