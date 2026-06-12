from __future__ import annotations
# DC Detail view - Capacity Planning
# Tab hierarchy: Summary | Virtualization (Classic / Hyperconverged / Power) | Backup | Physical Inventory
import json
import logging
import math
import time
import dash
from dash import html, dcc, dash_table, callback, Input, Output, State, MATCH
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objects as go

from src.services import api_client as api
from src.pages.dc_summary_sellable import build_summary_sellable_section
from src.utils.virt_sellable_aggregate import merge_power_panels_for_summary
from src.utils.api_parallel import parallel_execute
from src.utils.time_range import default_time_range
from src.utils.format_units import (
    smart_storage,
    smart_memory,
    smart_cpu,
    format_power_capacity_count,
    pct_float,
    alloc_pct_float,
    title_case,
    parse_storage_string,
    format_compact_decimal,
    format_compact_money_tl,
    format_full_decimal,
)
from src.utils.ibm_storage_capacity import (
    aggregate_ibm_storage_capacities,
    compute_system_capacities_gb,
)
from src.components.charts import (
    create_usage_donut_chart,
    create_avg_max_donut_chart,
    create_gauge_chart,
    create_premium_gauge_chart,
    create_premium_gauge_with_avg,
    create_dual_line_chart,
    create_sparkline_chart,
)
from src.components.charts import create_horizontal_bar_chart, create_premium_horizontal_bar_chart, create_capacity_area_chart, create_grouped_bar_chart, create_storage_breakdown_chart
from src.components.dc_loading import build_dc_loading_shell, build_dc_tab_loading_shell
from src.components.header import create_detail_header
from src.components.s3_panel import build_dc_s3_panel
from src.components.backup_panel import (
    build_netbackup_panel,
    build_zerto_panel,
    build_veeam_panel,
)
# noqa: F401 — import for side effect (registers backup-jobs callbacks)
from src.components import backup_jobs_section  # noqa: F401
from src.services import sla_service
from src.utils.dc_display import format_dc_display_name, resolve_dc_display_from_summary
from src.components.dc_availability_panel import build_dc_availability_panel
from src.utils.export_helpers import (
    records_to_dataframe,
    build_report_info_df,
    dataframes_to_excel_with_meta,
    csv_bytes_with_report_header,
    dash_send_excel_workbook,
    dash_send_csv_bytes,
)

# ---------------------------------------------------------------------------
# KPI Icon Standard — one icon per concept
# ---------------------------------------------------------------------------

_DC_ICONS: dict[str, str] = {
    # ── Compute / Hosts ───────────────────────────────────────────────────────
    "hosts":             "solar:server-bold-duotone",              # rack server        ✓
    "ibm_hosts":         "solar:server-square-bold-duotone",       # IBM-style server   ✓
    "vms":               "solar:laptop-bold-duotone",              # virtual machine    ✓
    "lpars":             "solar:layers-minimalistic-bold-duotone", # logical partitions ✓
    "vios":              "solar:settings-bold-duotone",            # system service     ✓
    "clusters":          "solar:chart-2-bold-duotone",
    "platforms":         "solar:layers-minimalistic-bold-duotone",

    # ── CPU / RAM / Storage ───────────────────────────────────────────────────
    # solar:ram-bold-duotone & solar:storage-bold-duotone don't exist in Iconify CDN
    "cpu":               "solar:cpu-bold-duotone",                 # CPU chip           ✓
    "ram":               "solar:widget-4-bold-duotone",            # memory grid/blocks ✓
    "storage":           "solar:cloud-storage-bold-duotone",
    "storage_systems":   "solar:database-bold-duotone",            # DB stack = storage system  ✓
    "disk":              "solar:chart-bold-duotone",

    # ── Network / Ports ───────────────────────────────────────────────────────
    # solar:port-bold-duotone doesn't exist in Iconify CDN
    # total_devices=server distinguishes it from manufacturers=buildings on Physical Inventory tab
    "total_devices":     "solar:server-bold-duotone",              # device = server    ✓
    "active_ports":      "solar:bolt-circle-bold-duotone",         # active = energized ✓
    "total_ports":       "solar:link-bold-duotone",                 # link = port connections    ✓
    "no_link_ports":     "solar:close-circle-bold-duotone",        # X = no connection  ✓
    "disabled_ports":    "solar:pause-circle-bold-duotone",        # paused/disabled    ✓
    "licensed_ports":    "solar:ticket-bold-duotone",              # license ticket     ✓
    "port_availability": "solar:graph-bold-duotone",               # availability graph ✓

    # ── Energy / Power ────────────────────────────────────────────────────────
    # All 6 visible on screen at once → 6 distinct confirmed icons
    "ibm_power_kw":      "material-symbols:power-rounded",         # power button       ✓
    "vcenter_kw":        "material-symbols:cloud",                 # cloud (vCenter)    ✓
    "total_kw":          "material-symbols:flash-on",              # lightning = total  ✓
    "ibm_kwh":           "material-symbols:bolt-outline",          # bolt = energy      ✓
    "vcenter_kwh":       "solar:cloud-storage-bold-duotone",       # cloud energy       ✓
    "total_kwh":         "solar:chart-2-bold-duotone",             # aggregate chart    ✓

    # ── Physical Inventory ────────────────────────────────────────────────────
    # All 4 visible at once → 4 distinct icons
    # total_devices=server, device_roles=widget-4, top_role=graph, manufacturers=buildings
    "device_roles":      "solar:widget-4-bold-duotone",            # role grid          ✓
    "top_role":          "solar:graph-bold-duotone",               # top = highest bar  ✓
    "manufacturers":     "solar:buildings-bold-duotone",           # factory/buildings  ✓

    # ── Storage subtab (IBM Storage) — all 4 on screen at once ───────────────
    # storage_systems=database, total_capacity=chart-2, used_capacity=chart-bold, utilization=graph-bold
    "total_capacity":    "solar:chart-2-bold-duotone",             # aggregate total    ✓ (distinct from storage_systems=database)
    "used_capacity":     "solar:chart-bold-duotone",               # bar = used amount  ✓
    "utilization":       "solar:graph-bold-duotone",               # line graph %       ✓

    # ── IBM Power summary (all visible together on Summary tab) ───────────────
    # Summary tab: ibm_hosts=server-square, lpars=layers-minimalistic, ram_assigned=database, ibm_storage=chart-bold
    # Energy section also on Summary: power-rounded, cloud, flash-on, bolt-outline, cloud-storage, chart-2
    # ram_assigned=database and ibm_storage=chart-bold are the only unique ones not reused on that page
    "ram_assigned":      "solar:database-bold-duotone",            # memory/data store  ✓ (distinct from lpars=layers)
    "ibm_storage":       "solar:chart-bold-duotone",               # IBM storage bar    ✓ (distinct from vcenter_kwh=cloud-storage)
    "last_updated":      "solar:clock-circle-bold-duotone",        # clock              ✓
}

# ---------------------------------------------------------------------------
# Shared UI helpers
# ---------------------------------------------------------------------------


def _export_cell_value(v):
    if isinstance(v, (dict, list)):
        try:
            return json.dumps(v, ensure_ascii=False, default=str)[:8000]
        except Exception:
            return str(v)[:8000]
    return v


def _scalar_block_to_wide_row(block: dict | None) -> list[dict]:
    if not isinstance(block, dict) or not block:
        return []
    row = {str(k): _export_cell_value(block[k]) for k in sorted(block.keys(), key=str)}
    return [row]


def _meta_export_rows(meta: dict | None, dc_code: str) -> list[dict]:
    rows = [{"field": "dc_code", "value": dc_code}]
    if not isinstance(meta, dict):
        return rows
    for k in sorted(meta.keys(), key=str):
        rows.append({"field": str(k), "value": _export_cell_value(meta[k])})
    return rows


def _phys_by_role_export_rows(phys_inv: dict) -> list[dict]:
    br = phys_inv.get("by_role") or []
    out: list[dict] = []
    if isinstance(br, list):
        for item in br:
            if isinstance(item, dict):
                out.append({"role": str(item.get("role", "")), "count": item.get("count", "")})
    return out


def _network_interface_export_rows(interface_table: dict | None) -> list[dict]:
    if not isinstance(interface_table, dict):
        return []
    items = interface_table.get("items") or []
    out: list[dict] = []
    for r in items:
        if isinstance(r, dict):
            out.append({str(k): _export_cell_value(v) for k, v in r.items()})
    return out


def _backup_rows_for_export(product: str, payload: dict | None) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    raw_rows = payload.get("rows")
    if isinstance(raw_rows, list) and raw_rows:
        out: list[dict] = []
        for r in raw_rows:
            if isinstance(r, dict):
                row = {"product": product}
                for k, v in r.items():
                    row[str(k)] = _export_cell_value(v)
                out.append(row)
        return out
    if product == "NetBackup":
        pools = payload.get("pools") or []
        return [
            {"product": product, **{str(k): _export_cell_value(v) for k, v in p.items()}}
            for p in pools
            if isinstance(p, dict)
        ]
    if product == "Zerto":
        sites = payload.get("sites") or []
        return [
            {"product": product, **{str(k): _export_cell_value(v) for k, v in s.items()}}
            for s in sites
            if isinstance(s, dict)
        ]
    if product == "Veeam":
        repos = payload.get("repos") or []
        return [
            {"product": product, **{str(k): _export_cell_value(v) for k, v in x.items()}}
            for x in repos
            if isinstance(x, dict)
        ]
    return []


def _build_dc_export_sheets(
    dc_code: str,
    data: dict,
    phys_inv: dict,
    net_interface_table: dict | None,
    nb_data: dict | None,
    zerto_data: dict | None,
    veeam_data: dict | None,
) -> dict[str, list[dict]]:
    """Tabular sections for CSV/Excel export (JSON-serializable)."""
    sheets: dict[str, list[dict]] = {}
    meta = data.get("meta") or {}
    sheets["Meta"] = _meta_export_rows(meta, dc_code)

    classic = data.get("classic")
    if isinstance(classic, dict) and classic:
        sheets["Classic_Metrics"] = _scalar_block_to_wide_row(classic)

    hyperconv = data.get("hyperconv")
    if isinstance(hyperconv, dict) and hyperconv:
        sheets["HyperConv_Metrics"] = _scalar_block_to_wide_row(hyperconv)

    power = data.get("power")
    if isinstance(power, dict) and power:
        sheets["Power_Metrics"] = _scalar_block_to_wide_row(power)

    energy = data.get("energy")
    if isinstance(energy, dict) and energy:
        sheets["Energy_Metrics"] = _scalar_block_to_wide_row(energy)

    intel = data.get("intel")
    if isinstance(intel, dict) and intel:
        sheets["Intel_Legacy"] = _scalar_block_to_wide_row(intel)

    phys = _phys_by_role_export_rows(phys_inv)
    if phys:
        sheets["Physical_Inventory"] = phys

    net_rows = _network_interface_export_rows(net_interface_table)
    if net_rows:
        sheets["Network_Interfaces"] = net_rows

    backup_combined: list[dict] = []
    backup_combined.extend(_backup_rows_for_export("NetBackup", nb_data))
    backup_combined.extend(_backup_rows_for_export("Zerto", zerto_data))
    backup_combined.extend(_backup_rows_for_export("Veeam", veeam_data))
    if backup_combined:
        sheets["Backup"] = backup_combined

    return sheets


def _has_compute_data(d: dict | None) -> bool:
    """Return True if any meaningful compute metric exists for a section."""
    if not d:
        return False
    keys = ("hosts", "vms", "cpu_cap", "mem_cap", "stor_cap")
    return any(d.get(k) not in (None, 0, 0.0, "") for k in keys)


def _has_power_data(d: dict | None) -> bool:
    """Return True if any meaningful IBM Power compute or storage metric exists."""
    if not d:
        return False
    keys = (
        "hosts",
        "lpar_count",
        "cpu_used",
        "memory_total",
        "vios",
        "storage_cap_tb",
        "storage_used_tb",
    )
    return any(d.get(k) not in (None, 0, 0.0, "") for k in keys)


def _fmt_tl_short(value: float | int | None) -> tuple[str, str]:
    """Compress a TL amount into a human label and return (short, full) tuple.

    The short variant is suitable for KPI cards (e.g. "1.55 Trilyon TL") while
    the full variant carries the exact comma-grouped number for the tooltip.
    """
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        v = 0.0
    full = f"{v:,.0f} TL"
    abs_v = abs(v)
    if abs_v >= 1e12:
        return f"{v/1e12:.2f} Trilyon TL", full
    if abs_v >= 1e9:
        return f"{v/1e9:.2f} Milyar TL", full
    if abs_v >= 1e6:
        return f"{v/1e6:.2f} Milyon TL", full
    if abs_v >= 1e3:
        return f"{v/1e3:.1f} Bin TL", full
    return full, full


def _kpi_with_tooltip(
    title: str,
    short_value: str,
    tooltip_full: str,
    icon: str,
    color: str = "indigo",
    stagger: int = 1,
):
    """KPI card with a small info icon tooltip — does NOT wrap the card in Tooltip."""
    return _kpi(title, short_value, icon, color=color, is_text=True, stagger=stagger, tooltip=tooltip_full)


def _kpi(
    title: str,
    value,
    icon: str,
    color: str = "indigo",
    is_text: bool = False,
    stagger: int = 1,
    tooltip: str | None = None,
    opacity: float | None = None,
    background: str | None = None,
):
    """Standard KPI card used across all tabs."""
    label_children: list = [
        html.Span(
            title,
            style={
                "color": "#A3AED0",
                "fontSize": "0.75rem",
                "fontWeight": 500,
                "letterSpacing": "0.02em",
                "textTransform": "uppercase",
                "display": "-webkit-box",
                "WebkitLineClamp": 2,
                "WebkitBoxOrient": "vertical",
                "overflow": "hidden",
                "lineHeight": "1.3",
            },
        ),
    ]
    if tooltip:
        label_children.append(
            dmc.Tooltip(
                label=tooltip,
                position="top",
                withArrow=True,
                multiline=True,
                w=260,
                children=DashIconify(
                    icon="solar:info-circle-bold-duotone",
                    width=12,
                    style={"color": "#A3AED0", "marginLeft": "3px", "cursor": "pointer", "flexShrink": 0},
                ),
            )
        )
    card_style: dict = {
        "padding": "20px",
        "display": "flex",
        "alignItems": "center",
        "justifyContent": "space-between",
    }
    if opacity is not None:
        card_style["opacity"] = opacity
    if background:
        card_style["background"] = background

    return html.Div(
        className=f"nexus-card dc-kpi-card dc-stagger-{stagger}",
        style=card_style,
        children=[
            html.Div(
                style={"minWidth": 0, "flex": 1},
                children=[
                    html.Div(style={"display": "flex", "alignItems": "center"}, children=label_children),
                    html.H3(
                        str(value),
                        style={
                            "color": "#2B3674",
                            "fontSize": "1.1rem" if is_text else "1.5rem",
                            "fontWeight": 900,
                            "margin": "6px 0 0 0",
                            "letterSpacing": "-0.02em",
                        },
                    ),
                ],
            ),
            dmc.ThemeIcon(
                size=48,
                radius="xl",
                variant="light",
                color=color,
                style={
                    "background": "linear-gradient(135deg, rgba(67, 24, 255, 0.08) 0%, rgba(5, 205, 153, 0.08) 100%)",
                },
                children=DashIconify(icon=icon, width=26),
            ),
        ],
    )


def _gauge_wrap(
    fig,
    label: str,
    avg_label: str = "",
    subtitle: str = "",
    badge: str | None = None,
    secondary_subtitle: str = "",
    graph_id: str | None = None,
):
    """Renders gauge with an HTML label above — label never clips into the gauge arc."""
    sub_text = subtitle if subtitle else (f"avg {avg_label}" if avg_label else "")
    subtitle_nodes: list = []
    if sub_text:
        subtitle_nodes.append(
            html.Span(sub_text, style={"fontSize": "0.68rem", "color": "#A3AED0", "display": "block"})
        )
    if secondary_subtitle:
        subtitle_nodes.append(
            html.Span(
                secondary_subtitle,
                className="cpu-alloc-real-hint",
                style={"fontSize": "0.62rem", "color": "#8F9BB3", "display": "block"},
            )
        )
    label_nodes = [
        html.Span(label, style={
            "fontSize": "0.72rem",
            "fontWeight": 600,
            "color": "#A3AED0",
            "textTransform": "uppercase",
            "letterSpacing": "0.04em",
            "lineHeight": "1.3",
            "whiteSpace": "normal",
            "wordBreak": "break-word",
        }),
    ]
    if badge:
        label_nodes.append(
            dmc.Badge(badge, color="red", size="xs", variant="light", style={"verticalAlign": "middle"})
        )
    return html.Div(
        style={"textAlign": "center", "display": "flex", "flexDirection": "column", "width": "100%"},
        children=[
            html.Div(
                style={"padding": "8px 4px 0", "minHeight": "32px"},
                children=[
                    html.Div(
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "justifyContent": "center",
                            "flexWrap": "wrap",
                            "gap": "4px",
                        },
                        children=label_nodes,
                    ),
                    *subtitle_nodes,
                ],
            ),
            html.Div(
                style={
                    "width": "100%",
                    "aspectRatio": "16 / 11",
                    "maxWidth": "360px",
                    "margin": "0 auto",
                },
                children=dcc.Graph(
                    **({"id": graph_id} if graph_id else {}),
                    figure=fig,
                    config={"displayModeBar": False, "responsive": True},
                    style={"height": "100%", "width": "100%"},
                ),
            ),
        ],
    )


def _network_gauge_labels(interface_scope: str | None) -> tuple[str, str, str]:
    """HTML labels for overview network gauge trio."""
    if interface_scope == "backbone":
        return "Interface Availability", "P95 Utilization", "ICMP Availability"
    return "Port Availability", "Port Utilization", "ICMP Availability"


def _cpu_allocation_gauge_block(compute: dict, cpu_cap: float):
    """Physical CPU allocation gauge with overalloc badge."""
    real = float(compute.get("cpu_alloc_ghz_vm", 0) or 0)
    real_pct = alloc_pct_float(real, cpu_cap)
    over_real = bool(compute.get("cpu_overallocated_real")) or (cpu_cap > 0 and real > cpu_cap)
    primary_sub = (
        f"{smart_cpu(real)} / {smart_cpu(cpu_cap)}"
        + (f" ({real_pct:.1f}%)" if real_pct > 100 else "")
        if cpu_cap > 0 else ""
    )
    return _gauge_wrap(
        create_premium_gauge_chart(real_pct, "", color="#4318FF", allow_over_100=True),
        "CPU Allocation",
        subtitle=primary_sub,
        badge="Overallocated" if over_real else None,
    )


def _chart_card(graph_component):
    return html.Div(
        className="nexus-card dc-chart-card",
        style={
            "padding": "16px",
            "height": "300px",
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "justifyContent": "center",
            "overflow": "hidden",
        },
        children=graph_component,
    )


def _has_value(*values) -> bool:
    """Return True if at least one value is meaningfully non-zero."""
    for v in values:
        try:
            if float(v or 0) > 0:
                return True
        except (TypeError, ValueError):
            pass
    return False


def _dynamic_chart_grid(items: list, spacing: str = "lg") -> html.Div | None:
    """
    Accept (has_data: bool, graph_component) pairs — render only where has_data is True.

    - 0 visible  → None  (caller should hide the entire section)
    - 1 visible  → cols=1 (full-width single card)
    - 2 visible  → cols=2
    - 3+ visible → cols=3
    """
    visible = [graph_comp for has_data, graph_comp in items if has_data]
    if not visible:
        return None
    cols = min(len(visible), 3)
    return dmc.SimpleGrid(
        cols=cols,
        spacing=spacing,
        style={"marginTop": "12px"},
        children=[_chart_card(g) for g in visible],
    )


def _section_title(title: str, subtitle: str | None = None):
    return html.Div(
        className="dc-section-title",
        style={"marginBottom": "4px"},
        children=[
            html.H3(
                title,
                style={
                    "margin": 0,
                    "color": "#2B3674",
                    "fontSize": "1.05rem",
                    "fontWeight": 800,
                    "letterSpacing": "-0.01em",
                },
            ),
            html.P(
                subtitle,
                style={
                    "margin": "4px 0 0 0",
                    "color": "#A3AED0",
                    "fontSize": "0.8rem",
                    "fontWeight": 500,
                },
            ) if subtitle else None,
        ],
    )


def _format_tl(value: float) -> str:
    """Format a TL amount with thousands separators and short suffix for large numbers."""
    if value <= 0:
        return "—"
    if value >= 1e9:
        return f"{value/1e9:,.2f}B TL"
    if value >= 1e6:
        return f"{value/1e6:,.2f}M TL"
    if value >= 1e3:
        return f"{value/1e3:,.1f}K TL"
    return f"{value:,.0f} TL"


def _capacity_pct_badge_color(pct: float) -> str:
    return "indigo" if pct < 60 else "yellow" if pct < 80 else "red"


def _capacity_pct_bar_color(pct: float) -> str:
    return "#05CD99" if pct < 60 else "#FFB547" if pct < 80 else "#EE5D50"


def _capacity_value_cell(value_str: str, pct: float):
    """Value with colored percentage badge in parentheses."""
    return html.Div(
        style={"display": "flex", "alignItems": "center", "gap": "6px", "flexWrap": "wrap"},
        children=[
            html.Span(value_str, style={"color": "#4318FF", "fontSize": "0.8rem", "fontWeight": 600}),
            dmc.Badge(
                f"({pct:.1f}%)",
                color=_capacity_pct_badge_color(pct),
                variant="light",
                size="sm",
            ),
        ],
    )


def _capacity_alloc_bar(pct: float):
    """Horizontal allocation bar; full width when pct exceeds 100%."""
    bar_pct = min(float(pct), 100.0)
    bar_color = _capacity_pct_bar_color(pct)
    if pct > 100:
        bar_color = "#EE5D50"
    return html.Div(
        style={
            "height": "6px",
            "borderRadius": "3px",
            "background": "#EEF2FF",
            "overflow": "hidden",
        },
        children=html.Div(
            style={
                "width": f"{bar_pct:.1f}%",
                "height": "100%",
                "borderRadius": "3px",
                "background": f"linear-gradient(90deg, #4318FF 0%, {bar_color} 100%)",
                "transition": "width 0.6s cubic-bezier(0.25, 0.8, 0.25, 1)",
            },
        ),
    )


def _capacity_resource_table(rows: list[dict]):
    """One row per resource: total, allocation, sales (CPU only), max util, bar."""
    header_style = {
        "color": "#A3AED0",
        "fontSize": "0.72rem",
        "fontWeight": 700,
        "textTransform": "uppercase",
        "letterSpacing": "0.04em",
    }
    cell_style = {"padding": "10px 8px", "verticalAlign": "middle"}
    label_style = {"color": "#2B3674", "fontWeight": 700, "fontSize": "0.85rem"}

    def _metric_cell(pair: tuple[str, float] | None):
        if pair is None:
            return html.Td("—", style={**cell_style, "color": "#A3AED0"})
        value_str, pct = pair
        return html.Td(_capacity_value_cell(value_str, pct), style=cell_style)

    body_rows = []
    for row in rows:
        body_rows.append(
                    html.Tr(
                [
                    html.Td(row["label"], style={**cell_style, **label_style}),
                    html.Td(
                        row["total_str"],
                        style={**cell_style, "color": "#2B3674", "fontSize": "0.8rem", "fontWeight": 600},
                    ),
                    _metric_cell(row.get("allocation")),
                    _metric_cell(row.get("max_util")),
                    html.Td(_capacity_alloc_bar(row["bar_pct"]), style=cell_style),
                ]
            )
        )

    return html.Div(
        style={"overflowX": "auto"},
        children=[
            html.Table(
                style={"width": "100%", "borderCollapse": "collapse"},
                children=[
                    html.Thead(
                        html.Tr(
                            [
                                html.Th("Resource", style=header_style),
                                html.Th("Total", style=header_style),
                                html.Th(
                                    dmc.Tooltip(
                                        label=(
                                            "Sum of VM-configured resources (latest allocation snapshot). "
                                            "May exceed 100% when RAM is overcommitted."
                                        ),
                                        children=html.Span("Physical allocation"),
                                    ),
                                    style=header_style,
                                ),
                                html.Th(
                                    dmc.Tooltip(
                                        label=(
                                            "Cluster-level peak RAM usage in the selected report period "
                                            "(cluster_metrics time series). Sellable gate uses "
                                            "max(allocation%, peak%)."
                                        ),
                                        children=html.Span("Max utilization"),
                                    ),
                                    style=header_style,
                                ),
                                html.Th("", style=header_style),
                            ]
                        )
                    ),
                    html.Tbody(body_rows),
                ],
            )
        ],
    )


def _build_compute_capacity_rows(
    *,
    cpu_cap: float,
    cpu_alloc_ghz: float,
    cpu_alloc_pct: float,
    cpu_pct_max: float,
    cpu_pct: float,
    mem_cap: float,
    mem_alloc_gb: float,
    mem_alloc_pct: float,
    mem_pct_max: float,
    mem_pct: float,
    stor_cap_gb: float,
    stor_provisioned_gb: float,
    stor_used_gb: float,
    stor_alloc_vm_pct: float,
    stor_pct: float,
) -> list[dict]:
    """Build three capacity planning rows for Classic/Hyperconv compute tabs."""
    cpu_max_pct = cpu_pct_max or cpu_pct
    mem_peak_pct = mem_pct_max or mem_pct
    return [
        {
            "label": "CPU",
            "total_str": smart_cpu(cpu_cap),
            "allocation": (smart_cpu(cpu_alloc_ghz), cpu_alloc_pct),
            "max_util": (
                smart_cpu(cpu_cap * cpu_max_pct / 100.0 if cpu_cap else 0),
                cpu_max_pct,
            ),
            "bar_pct": cpu_alloc_pct,
        },
        {
            "label": "Memory",
            "total_str": smart_memory(mem_cap),
            "allocation": (smart_memory(mem_alloc_gb), mem_alloc_pct),
            "max_util": (
                smart_memory(mem_cap * mem_peak_pct / 100.0 if mem_cap else 0),
                mem_peak_pct,
            ),
            "bar_pct": mem_alloc_pct,
        },
        {
            "label": "Storage",
            "total_str": smart_storage(stor_cap_gb),
            "allocation": (smart_storage(stor_provisioned_gb), stor_alloc_vm_pct),
            "max_util": (smart_storage(stor_used_gb), stor_pct),
            "bar_pct": stor_alloc_vm_pct,
        },
    ]


def _capacity_metric_row(label: str, cap_val, used_val, pct: float, unit_fn=None, potential_tl: float = 0.0):
    """Renders a capacity / allocated / utilisation trio inside a card row."""
    cap_str  = unit_fn(cap_val)  if unit_fn else str(cap_val)
    used_str = unit_fn(used_val) if unit_fn else str(used_val)
    pct_color = "#05CD99" if pct < 60 else "#FFB547" if pct < 80 else "#EE5D50"
    return html.Div(
        className="dc-capacity-row",
        style={
            "display": "grid",
            "gridTemplateColumns": "140px 1fr 1fr 1fr 70px 90px",
            "alignItems": "center",
            "gap": "12px",
            "padding": "8px 0",
            "borderBottom": "1px solid #F4F7FE",
        },
        children=[
            html.Span(
                label,
                style={"color": "#2B3674", "fontWeight": 700, "fontSize": "0.85rem"},
            ),
            html.Span(
                f"Capacity: {cap_str}",
                style={"color": "#A3AED0", "fontSize": "0.8rem"},
            ),
            html.Span(
                f"Potential: {_format_tl(potential_tl)}" if potential_tl > 0 else "",
                style={"color": "#05CD99", "fontSize": "0.8rem", "fontWeight": 600},
            ),
            html.Span(
                f"Allocated: {used_str}",
                style={"color": "#4318FF", "fontSize": "0.8rem", "fontWeight": 600},
            ),
            dmc.Badge(
                f"{pct:.1f}%",
                color="indigo" if pct < 60 else "yellow" if pct < 80 else "red",
                variant="light",
                size="sm",
                style={"textAlign": "center"},
            ),
            html.Div(
                style={
                    "height": "6px",
                    "borderRadius": "3px",
                    "background": "#EEF2FF",
                    "overflow": "hidden",
                },
                children=html.Div(
                    style={
                        "width": f"{min(pct, 100):.1f}%",
                        "height": "100%",
                        "borderRadius": "3px",
                        "background": f"linear-gradient(90deg, #4318FF 0%, {pct_color} 100%)",
                        "transition": "width 0.6s cubic-bezier(0.25, 0.8, 0.25, 1)",
                    },
                ),
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Tab content builders
# ---------------------------------------------------------------------------

def _build_compute_tab(compute: dict, title: str, color: str = "indigo", is_power: bool = False, slug: str | None = None):
    """Generic compute type tab panel content (Classic or Hyperconverged)."""
    if not slug:
        slug = title.lower().replace(" ", "-").replace("/", "-")
    hosts    = compute.get("hosts", 0)
    vms      = compute.get("vms", 0)
    cpu_cap  = compute.get("cpu_cap", 0.0)
    cpu_used = compute.get("cpu_used", 0.0)
    cpu_pct  = float(compute.get("cpu_util_pct") or compute.get("cpu_pct") or pct_float(cpu_used, cpu_cap))
    mem_cap  = compute.get("mem_cap", 0.0)
    mem_used = compute.get("mem_used", 0.0)
    mem_pct  = float(compute.get("mem_util_pct") or compute.get("mem_pct") or pct_float(mem_used, mem_cap))
    cpu_pct_max = float(compute.get("cpu_util_pct_max") or compute.get("cpu_pct_max") or 0)
    mem_pct_max = float(compute.get("mem_util_pct_max") or compute.get("mem_pct_max") or 0)
    stor_cap  = compute.get("stor_cap", 0.0)
    stor_used = compute.get("stor_used", 0.0)
    stor_pct  = pct_float(stor_used, stor_cap)

    # Convert TB to GB for display (smart_storage expects GB)
    stor_cap_gb  = stor_cap  * 1024
    stor_used_gb = stor_used * 1024

    cpu_alloc_ghz = float(compute.get("cpu_alloc_ghz_vm", 0) or 0)
    mem_alloc_gb  = float(compute.get("mem_alloc_gb_vm", 0) or 0)
    cpu_alloc_pct = alloc_pct_float(cpu_alloc_ghz, cpu_cap)
    mem_alloc_pct = alloc_pct_float(mem_alloc_gb, mem_cap)

    # VM-level storage breakdown.
    stor_provisioned_gb = float(compute.get("stor_provisioned_gb", 0) or 0)
    stor_actual_used_gb = float(compute.get("stor_actual_used_gb", 0) or 0)
    stor_util_pct  = stor_pct
    stor_alloc_vm_pct = alloc_pct_float(stor_provisioned_gb, stor_cap_gb) if stor_cap_gb > 0 else 0.0

    capacity_rows = _build_compute_capacity_rows(
        cpu_cap=cpu_cap,
        cpu_alloc_ghz=cpu_alloc_ghz,
        cpu_alloc_pct=cpu_alloc_pct,
        cpu_pct_max=cpu_pct_max,
        cpu_pct=cpu_pct,
        mem_cap=mem_cap,
        mem_alloc_gb=mem_alloc_gb,
        mem_alloc_pct=mem_alloc_pct,
        mem_pct_max=mem_pct_max,
        mem_pct=mem_pct,
        stor_cap_gb=stor_cap_gb,
        stor_provisioned_gb=stor_provisioned_gb,
        stor_used_gb=stor_used_gb,
        stor_alloc_vm_pct=stor_alloc_vm_pct,
        stor_pct=stor_pct,
    )

    util_grid = _dynamic_chart_grid([
        (_has_value(cpu_cap), _gauge_wrap(
            create_premium_gauge_chart(cpu_pct_max or cpu_pct, "", color="#4318FF"),
            "CPU Usage (Max)",
            subtitle=f"avg {cpu_pct:.1f}%",
        )),
        (_has_value(mem_cap), _gauge_wrap(
            create_premium_gauge_chart(mem_pct_max or mem_pct, "", color="#05CD99"),
            "RAM Usage (Max)",
            subtitle=f"avg {mem_pct:.1f}%",
        )),
        (_has_value(stor_cap), _gauge_wrap(
            create_premium_gauge_chart(min(stor_util_pct, 100), "", color="#FFB547"),
            "Storage Usage",
            subtitle=(
                f"{smart_storage(stor_used_gb)} / {smart_storage(stor_cap_gb)} used"
                if stor_cap_gb > 0 else ""
            ),
        )),
    ])
    alloc_grid = _dynamic_chart_grid([
        (_has_value(cpu_cap), _cpu_allocation_gauge_block(compute, cpu_cap)),
        (_has_value(mem_cap), _gauge_wrap(
            create_premium_gauge_chart(mem_alloc_pct, "", color="#05CD99", allow_over_100=True),
            "RAM Allocation",
            subtitle=(
                f"{smart_memory(mem_alloc_gb)} / {smart_memory(mem_cap)}"
                + (f" ({mem_alloc_pct:.0f}%)" if mem_alloc_pct > 100 else "")
                if mem_cap > 0 else ""
            ),
        )),
        (_has_value(stor_cap), _gauge_wrap(
            create_premium_gauge_chart(stor_alloc_vm_pct, "", color="#FFB547", allow_over_100=True),
            "Storage Allocation",
            subtitle=(
                f"{smart_storage(stor_provisioned_gb)} / {smart_storage(stor_cap_gb)} provisioned"
                if stor_provisioned_gb > 0 and stor_cap_gb > 0
                else (f"{smart_storage(stor_used_gb)} / {smart_storage(stor_cap_gb)}" if stor_cap_gb > 0 else "")
            ),
        )),
    ])

    alloc_panel_children: list = []
    if alloc_grid is not None:
        alloc_panel_children.append(alloc_grid)

    gauges_section: list = []
    if util_grid is not None or alloc_panel_children:
        gauges_section = [
            dmc.Group(
                justify="flex-end",
                style={"marginTop": "8px"},
                children=[
                    dmc.SegmentedControl(
                        id={"type": "compute-gauge-mode", "slug": slug},
                        value="utilization",
                        data=[
                            {"label": "Utilization", "value": "utilization"},
                            {"label": "Allocation", "value": "allocation"},
                        ],
                        size="xs",
                        color="indigo",
                    ),
                ],
            ),
            html.Div(
                id={"type": "compute-gauge-util", "slug": slug},
                children=util_grid,
            ),
            html.Div(
                id={"type": "compute-gauge-alloc", "slug": slug},
                children=alloc_panel_children or None,
                style={"display": "none"},
            ),
        ]

    return dmc.Stack(
        gap="lg",
        children=[
            # KPI row
            dmc.SimpleGrid(cols={"base": 2, "md": 4}, spacing="md", children=[
                _kpi("Total Hosts", f"{hosts:,}", _DC_ICONS["hosts"], color=color),
                _kpi("Total VMs / LPARs", f"{vms:,}", _DC_ICONS["vms"], color=color),
                _kpi("CPU Capacity",  smart_cpu(cpu_cap),  _DC_ICONS["cpu"],   color=color, is_text=True),
                _kpi("RAM Capacity",  smart_memory(mem_cap), _DC_ICONS["ram"], color=color, is_text=True),
            ]),
            *gauges_section,
            # Capacity details card
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Capacity Planning", "Physical capacity vs. utilization and VM allocation"),
                    html.Div(style={"marginTop": "12px"}, children=[
                        _capacity_resource_table(capacity_rows),
                        html.P(
                            (
                                "Memory: Physical allocation sums VM-configured RAM; max utilization is "
                                "cluster peak host usage. Allocation % can exceed utilization % under "
                                "overcommit. Progress bars reflect allocation only. CRM sellable applies "
                                f"max(allocation%, peak%) against the threshold "
                                f"({max(mem_alloc_pct, mem_pct_max or mem_pct):.1f}% gate for this scope)."
                            ),
                            style={
                                "margin": "10px 0 0",
                                "color": "#A3AED0",
                                "fontSize": "0.75rem",
                                "lineHeight": 1.45,
                            },
                        ),
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
    cpu_total_pu = power.get("cpu_total_procunits", 0.0) or 0.0
    cpu_total_cores = power.get("cpu_total_cores", 0.0) or 0.0
    cpu_avail_pu = power.get("cpu_available_procunits", 0.0) or 0.0
    cpu_avail_cores = power.get("cpu_available_cores", 0.0) or 0.0
    cpu_allocated_pu = max(cpu_total_pu - cpu_avail_pu, 0.0)
    cpu_allocated_cores = max(cpu_total_cores - cpu_avail_cores, 0.0)

    # Potential Sellable revenue — Power: 1 core = 3.3 GHz eşdeğeri,
    # CRM CPU fiyatı (SAP Power HANA CPU) 1 GHz/vCPU üzerinden tutulduğu için
    # cores × 3.3 × cpu_unit_price formülü uygulanır.
    power_unit_prices = power.get("unit_prices", {}) or {}
    power_multiplier  = float(power.get("sellable_multiplier", 3.3) or 3.3)
    cpu_potential_tl  = cpu_total_cores * power_multiplier * float(power_unit_prices.get("cpu_vcpu", 0) or 0)

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
            dmc.SimpleGrid(cols={"base": 2, "md": 4}, spacing="md", children=[
                _kpi("IBM Hosts",   f"{hosts:,}", _DC_ICONS["ibm_hosts"],   color="grape"),
                _kpi("VIOS",        f"{vios:,}",  _DC_ICONS["vios"],        color="grape"),
                _kpi("LPARs",       f"{lpars:,}", _DC_ICONS["lpars"],       color="grape"),
                _kpi("Last Updated", "Live",       _DC_ICONS["last_updated"], color="grape", is_text=True),
            ]),
            _dynamic_chart_grid([
                (_has_value(mem_total), _gauge_wrap(
                    create_gauge_chart(mem_assigned, mem_total or 1, "", color="#05CD99", height=220),
                    "Memory Assigned",
                )),
                (_has_value(cpu_assigned), _gauge_wrap(
                    create_gauge_chart(cpu_used, cpu_assigned, "", color="#4318FF", height=220),
                    "CPU Used",
                )),
                (_has_value(cpu_total_pu), _gauge_wrap(
                    create_gauge_chart(cpu_allocated_pu, cpu_total_pu or 1, "", color="#FF6B6B", height=220),
                    "CPU Assigned",
                )),
            ]),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Capacity Planning", "IBM Power resource allocation"),
                    html.Div(style={"marginTop": "12px"}, children=[
                        _capacity_metric_row(
                            "CPU (Proc Units)",
                            cpu_total_pu,
                            cpu_allocated_pu,
                            pct_float(cpu_allocated_pu, cpu_total_pu),
                            format_power_capacity_count,
                        ),
                        _capacity_metric_row(
                            "CPU Cores",
                            cpu_total_cores,
                            cpu_allocated_cores,
                            pct_float(cpu_allocated_cores, cpu_total_cores),
                            format_power_capacity_count,
                        ),
                        _capacity_metric_row(
                            "CPU (GHz)",
                            cpu_total_cores * power_multiplier,
                            cpu_allocated_cores * power_multiplier,
                            pct_float(cpu_allocated_cores, cpu_total_cores),
                            smart_cpu,
                            potential_tl=cpu_potential_tl,
                        ),
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
                                _gauge_wrap(
                                    create_gauge_chart(used_gb, total_gb or 1, "", color="#FFB547", height=220),
                                    "Storage Capacity",
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
                        _kpi("IBM Power", f"{energy.get('ibm_kw', 0):.1f} kW",  _DC_ICONS["ibm_power_kw"], color="orange"),
                        _kpi("Consumption", f"{energy.get('ibm_kwh', 0):,.0f} kWh", _DC_ICONS["ibm_kwh"], color="orange"),
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
                            _kpi("Active Ports", f"{active_ports:,}", _DC_ICONS["active_ports"], color="indigo"),
                            _kpi("No Link / Offline Ports", f"{no_link_ports:,}", _DC_ICONS["no_link_ports"], color="indigo"),
                            _kpi("Admin Disabled Ports", f"{disabled_ports:,}", _DC_ICONS["disabled_ports"], color="indigo"),
                            _kpi("Licensed Ports", f"{licensed_ports:,}", _DC_ICONS["licensed_ports"], color="indigo"),
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
                                        _gauge_wrap(create_premium_gauge_chart(licensed_pct, "", color="#4318FF"), "Pod License ROI")
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
                                        _gauge_wrap(create_premium_gauge_chart(active_pct, "", color="#05CD99"), "Active vs Licensed")
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
                                        _gauge_wrap(create_premium_gauge_chart(available_pct, "", color="#FFB547"), "Port Availability")
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


def _build_crm_sales_potential_panel(dc_id: str) -> html.Div:
    """CRM realized sales + sellable headroom KPIs (no sold-% gauges)."""
    v2 = api.get_dc_sales_potential_v2(dc_id)
    if not isinstance(v2, dict):
        return html.Div()
    summ = v2.get("dc_customer_summary") or {}
    ytd = float(summ.get("total_billed_ytd") or 0)
    cust = int(summ.get("customer_count") or 0)
    rem = float(v2.get("general_remaining_pct") or 0)
    pot = float(v2.get("potential_revenue_tl") or 0)

    ytd_short, ytd_full = _fmt_tl_short(ytd)
    pot_short, pot_full = _fmt_tl_short(pot)

    return html.Div(
        className="nexus-card",
        style={"padding": "20px"},
        children=[
            _section_title(
                "Sellable potential (CRM)",
                "Sellable headroom on Nutanix CPU/RAM proxy — threshold-bound ceiling (ADR-0014)",
            ),
            dmc.SimpleGrid(
                cols={"base": 2, "md": 4},
                spacing="md",
                style={"marginTop": "12px"},
                children=[
                    _kpi_with_tooltip("YTD Realized", ytd_short, ytd_full, "solar:money-bag-bold-duotone"),
                    _kpi("Sellable Remaining %", f"{rem:.1f}", "solar:chart-square-bold-duotone"),
                    _kpi_with_tooltip(
                        "Potential Revenue",
                        pot_short,
                        pot_full,
                        "solar:wallet-money-bold-duotone",
                    ),
                    _kpi("VM-Mapped Customers", f"{cust:,}", "solar:users-group-rounded-bold-duotone"),
                ],
            ),
        ],
    )


def _build_sellable_inline_kpi(
    dc_id: str | None,
    families: list[str] | str,
    title: str,
    *,
    color: str = "violet",
    selected_clusters: list[str] | None = None,
    container_id: str | None = None,
) -> html.Div | None:
    """Inline 'Sellable Potential' card for a sub-tab (Faz 6).

    Aggregates ``crm-engine`` /sellable-potential/by-panel results for one or
    more ``family`` keys (e.g. ``virt_hyperconverged`` or
    ``backup_zerto_replication``) and renders a 4-card KPI grid: CPU sellable /
    RAM sellable / Storage sellable / Total potential TL — all in the
    constrained (ratio-bound) space because that's what's actually monetisable.

    When ``selected_clusters`` is provided for a virt family, the crm-engine
    reads total + allocated for that scope from datacenter-api
    ``/compute/{kind}?clusters=...`` so this card matches the DC view
    Capacity Planning card for the same selection. ``container_id`` lets
    Dash callbacks target the outer wrapper Div as an Output.
    """
    if isinstance(families, str):
        families = [families]
    families = [f for f in families if f]

    if not dc_id or not families:
        if container_id:
            return html.Div(id=container_id)
        return None

    panels: list[dict] = []
    for fam in families:
        try:
            chunk = api.get_sellable_by_panel(
                dc_code=str(dc_id),
                family=fam,
                clusters=selected_clusters if fam in ("virt_classic", "virt_hyperconverged") else None,
            ) or []
            if isinstance(chunk, list):
                panels.extend(chunk)
        except Exception:
            continue

    if set(families) & {"virt_power", "virt_power_hana"}:
        panels = merge_power_panels_for_summary(panels)

    if not panels:
        if container_id:
            return html.Div(id=container_id)
        return None

    by_kind: dict[str, dict[str, float]] = {
        "cpu":     {
            "constrained": 0.0, "raw": 0.0, "tl": 0.0, "unit": "vCPU",
            "total": 0.0, "allocated": 0.0, "threshold_pct": 80.0,
            "min": 0.0, "max": 0.0, "tl_min": 0.0, "tl_max": 0.0, "has_range": 0.0,
        },
        "ram":     {
            "constrained": 0.0, "raw": 0.0, "tl": 0.0, "unit": "GB",
            "total": 0.0, "allocated": 0.0, "threshold_pct": 80.0,
            "min": 0.0, "max": 0.0, "tl_min": 0.0, "tl_max": 0.0, "has_range": 0.0,
        },
        "storage": {
            "constrained": 0.0, "raw": 0.0, "tl": 0.0, "unit": "GB",
            "total": 0.0, "allocated": 0.0, "threshold_pct": 85.0,
            "min": 0.0, "max": 0.0, "tl_min": 0.0, "tl_max": 0.0, "has_range": 0.0,
        },
    }
    total_tl = 0.0
    total_tl_max = 0.0
    has_data = False
    for p in panels:
        if not isinstance(p, dict):
            continue
        kind = (p.get("resource_kind") or "other").lower()
        if kind not in by_kind:
            total_tl += float(p.get("potential_tl") or 0.0)
            total_tl_max += float(
                p.get("potential_tl_max") if p.get("potential_tl_max") is not None else (p.get("potential_tl") or 0.0)
            )
            continue
        constrained = float(p.get("sellable_constrained") or 0.0)
        tl = float(p.get("potential_tl") or 0.0)
        by_kind[kind]["constrained"] += constrained
        by_kind[kind]["raw"]         += float(p.get("sellable_raw") or 0.0)
        by_kind[kind]["tl"]          += tl
        by_kind[kind]["total"]       += float(p.get("total") or 0.0)
        by_kind[kind]["allocated"]   += float(p.get("allocated") or 0.0)
        # Architecture-aware storage range (IBM capacity shared by KM + Power).
        s_min = p.get("sellable_min")
        s_max = p.get("sellable_max")
        if s_min is not None and s_max is not None:
            by_kind[kind]["min"] += float(s_min)
            by_kind[kind]["max"] += float(s_max)
            by_kind[kind]["tl_min"] += float(p.get("potential_tl_min") or 0.0)
            by_kind[kind]["tl_max"] += float(p.get("potential_tl_max") or 0.0)
            by_kind[kind]["has_range"] = 1.0
            total_tl_max += float(p.get("potential_tl_max") or tl)
        else:
            by_kind[kind]["min"] += constrained
            by_kind[kind]["max"] += constrained
            by_kind[kind]["tl_min"] += tl
            by_kind[kind]["tl_max"] += tl
            total_tl_max += tl
        thresh = p.get("threshold_pct")
        if thresh is not None:
            by_kind[kind]["threshold_pct"] = float(thresh)
        unit = p.get("display_unit")
        if unit:
            by_kind[kind]["unit"] = unit
        total_tl += tl
        has_data = True

    if not has_data and total_tl <= 0:
        if container_id:
            return html.Div(id=container_id)
        return None

    def _fmt_unit(value: float, unit: str) -> str:
        if unit.lower() in ("vcpu", "cpu", "core", "adet"):
            return f"{value:,.0f} {unit}"
        return f"{value:,.0f} {unit}"

    cpu = by_kind["cpu"]
    ram = by_kind["ram"]
    stor = by_kind["storage"]

    cpu_has_dual = any(
        p.get("sellable_physical") is not None and p.get("sellable_effective") is not None
        for p in panels
        if (p.get("resource_kind") or "").lower() == "cpu"
    )
    if cpu_has_dual:
        cpu_phys = sum(float(p.get("sellable_physical") or 0) for p in panels if (p.get("resource_kind") or "").lower() == "cpu")
        cpu_eff = sum(float(p.get("sellable_effective") or p.get("sellable_constrained") or 0) for p in panels if (p.get("resource_kind") or "").lower() == "cpu")
        cpu_phys_tl = sum(float(p.get("potential_tl_physical") or 0) for p in panels if (p.get("resource_kind") or "").lower() == "cpu")
        cpu_eff_tl = sum(float(p.get("potential_tl_effective") or p.get("potential_tl") or 0) for p in panels if (p.get("resource_kind") or "").lower() == "cpu")
        cpu["physical"] = cpu_phys
        cpu["effective"] = cpu_eff
        cpu["tl_phys"] = cpu_phys_tl
        cpu["tl_eff"] = cpu_eff_tl

    def _kpi_with_sub(
        label: str,
        value: str,
        sub_short: str,
        sub_full: str,
        ic: str,
        c: str = color,
    ) -> html.Div:
        card = html.Div(
            className="nexus-card dc-kpi-card dc-stagger-1",
            style={
                "padding": "18px",
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "space-between",
                "gap": "12px",
                "minHeight": "140px",
                "height": "100%",
                "width": "100%",
                "boxSizing": "border-box",
            },
            children=[
                html.Div(
                    style={"display": "flex", "flexDirection": "column", "minWidth": 0, "flex": "1 1 auto"},
                    children=[
                        html.Span(label, style={
                            "color": "#A3AED0", "fontSize": "0.78rem", "fontWeight": 500,
                            "letterSpacing": "0.02em", "textTransform": "uppercase",
                        }),
                        html.H3(value, style={
                            "color": "#2B3674", "fontSize": "1.15rem", "fontWeight": 900,
                            "margin": "6px 0 2px 0", "letterSpacing": "-0.02em",
                        }),
                        html.Span(sub_short, style={"color": "#4318FF", "fontSize": "0.78rem", "fontWeight": 700}),
                    ],
                ),
                dmc.ThemeIcon(
                    size=42, radius="xl", variant="light", color=c,
                    children=DashIconify(icon=ic, width=22),
                ),
            ],
        )
        return html.Div(
            style={"width": "100%", "height": "100%", "display": "flex", "flexDirection": "column"},
            title=sub_full if sub_full and sub_full != sub_short else None,
            children=card,
        )

    cpu_short, cpu_full = _fmt_tl_short(cpu["tl"])
    if cpu_has_dual:
        cpu_short = f"{_fmt_tl_short(cpu.get('tl_phys', 0))[0]} – {_fmt_tl_short(cpu.get('tl_eff', 0))[0]}"
        cpu_full = (
            f"Physical: {smart_cpu(cpu.get('physical', 0))} · "
            f"Effective: {cpu.get('effective', 0):,.0f} {cpu['unit']}"
        )
    ram_short, ram_full = _fmt_tl_short(ram["tl"])
    stor_short, stor_full = _fmt_tl_short(stor["tl"])
    total_short, total_full = _fmt_tl_short(total_tl)

    # Storage range display: "X – Y" when IBM-shared capacity yields a range.
    stor_has_range = bool(stor.get("has_range")) and stor["max"] > stor["min"] + 1e-6
    if stor_has_range:
        stor_value = f"{stor['min']:,.0f} – {stor['max']:,.0f} {stor['unit']}"
        stor_tl_min_short, _ = _fmt_tl_short(stor["tl_min"])
        stor_tl_max_short, _ = _fmt_tl_short(stor["tl_max"])
        stor_short = f"{stor_tl_min_short} – {stor_tl_max_short}"
        stor_full = (
            "IBM storage alanı hem KM datastore hem Power olarak satılabildiğinden aralık verilir. "
            f"Min (garanti): {stor['min']:,.0f} {stor['unit']} · Max (paylaşımlı dahil): {stor['max']:,.0f} {stor['unit']}"
        )
    else:
        stor_value = _fmt_unit(stor["constrained"], stor["unit"])

    total_has_range = (
        total_tl_max > total_tl + 1e-6
        or (cpu_has_dual and abs(cpu.get("tl_phys", 0) - cpu.get("tl_eff", 0)) > 1e-6)
    )
    if total_has_range:
        tl_lo = min(total_tl, total_tl_max, cpu.get("tl_phys", total_tl), cpu.get("tl_eff", total_tl))
        tl_hi = max(total_tl, total_tl_max, cpu.get("tl_phys", total_tl), cpu.get("tl_eff", total_tl))
        total_max_short, total_max_full = _fmt_tl_short(tl_hi)
        total_min_short, _ = _fmt_tl_short(tl_lo)
        total_value = f"{total_min_short} – {total_max_short}"
        total_tooltip = (
            f"Min (garanti): {total_min_short} · Max (paylaşımlı / efektif): {total_max_full}"
        )
    else:
        total_value = total_short
        total_tooltip = total_full or "constrained × catalog price"

    cards = [
        _kpi_with_sub(
            "CPU Sellable",
            (
                f"Phys {smart_cpu(cpu.get('physical', 0))} | Eff {_fmt_unit(cpu.get('effective', cpu['constrained']), cpu['unit'])}"
                if cpu_has_dual
                else _fmt_unit(cpu["constrained"], cpu["unit"])
            ),
            cpu_short,
            cpu_full,
            _DC_ICONS["cpu"],
        ),
        _kpi_with_sub(
            "RAM Sellable",
            _fmt_unit(ram["constrained"], ram["unit"]),
            ram_short,
            ram_full,
            _DC_ICONS["ram"],
        ),
        _kpi_with_sub(
            "Storage Sellable",
            stor_value,
            stor_short,
            stor_full,
            _DC_ICONS["storage"],
        ),
        _kpi_with_sub(
            "Total Potential",
            total_value,
            "× catalog price",
            total_tooltip,
            "solar:wallet-money-bold-duotone",
            c="grape",
        ),
    ]

    sub_lines: list = []
    if stor_has_range:
        sub_lines.append(
            dmc.Badge(
                "Storage aralığı: IBM kapasitesi KM + Power arasında paylaşımlı",
                color="blue",
                variant="light",
                size="sm",
            )
        )
    for kind_label, k in (("CPU", cpu), ("RAM", ram), ("Storage", stor)):
        if k["raw"] > 0 and k["constrained"] < k["raw"] - 1e-6:
            sub_lines.append(
                dmc.Badge(
                    f"{kind_label} ratio-bound: {_fmt_unit(k['raw'] - k['constrained'], k['unit'])} lost",
                    color="orange",
                    variant="light",
                    size="sm",
                )
            )

    from src.utils.sellable_power_hints import power_sellable_constraint_hints

    for hint in power_sellable_constraint_hints(
        families,
        cpu_raw=cpu["raw"],
        cpu_constrained=cpu["constrained"],
        ram_raw=ram["raw"],
        ram_total=float(ram.get("total") or 0),
        ram_allocated=float(ram.get("allocated") or 0),
        ram_threshold_pct=float(ram.get("threshold_pct") or 80.0),
    ):
        color = "orange" if hint.startswith("CPU blocked") else "yellow"
        sub_lines.append(
            dmc.Badge(hint, color=color, variant="light", size="sm"),
        )

    div_kwargs: dict = {
        "className": "nexus-card",
        "style": {"padding": "20px"},
        "children": [
            _section_title(title, "Constrained sellable headroom (ratio-aware) and TL potential"),
            html.Div(
                style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(4, minmax(0, 1fr))",
                    "gap": "16px",
                    "alignItems": "stretch",
                    "marginTop": "12px",
                },
                children=cards,
            ),
            dmc.Group(gap="xs", style={"marginTop": "10px"}, children=sub_lines) if sub_lines else None,
        ],
    }
    if container_id:
        div_kwargs["id"] = container_id
    return html.Div(**div_kwargs)


def _build_summary_tab(
    data: dict,
    tr: dict,
    dc_id: str | None = None,
    *,
    sellable_summary: dict | None = None,
    show_sellable: bool = True,
    classic_clusters: list[str] | None = None,
    hyperconv_clusters: list[str] | None = None,
):
    """Summary tab: Combined Infrastructure + sellable executive overview."""
    classic = data.get("classic", {})
    hyperconv = data.get("hyperconv", {})
    intel = data.get("intel", {})
    power = data.get("power", {})

    total_hosts = classic.get("hosts", 0) + hyperconv.get("hosts", 0) + power.get("hosts", 0)
    total_vms = intel.get("vms", 0) + power.get("lpar_count", 0)
    total_cpu_cap = classic.get("cpu_cap", 0) + hyperconv.get("cpu_cap", 0)
    total_mem_cap = classic.get("mem_cap", 0) + hyperconv.get("mem_cap", 0)

    summary_children: list = [
        html.Div(
            className="nexus-card",
            style={"padding": "20px"},
            children=[
                _section_title("Combined Infrastructure", "All compute types combined"),
                dmc.SimpleGrid(cols=4, spacing="lg", style={"marginTop": "12px"}, children=[
                    _kpi("Total Hosts", f"{total_hosts:,}", _DC_ICONS["hosts"]),
                    _kpi("Total VMs / LPARs", f"{total_vms:,}", _DC_ICONS["vms"]),
                    _kpi("CPU Capacity", smart_cpu(total_cpu_cap), _DC_ICONS["cpu"], is_text=True),
                    _kpi("RAM Capacity", smart_memory(total_mem_cap), _DC_ICONS["ram"], is_text=True),
                ]),
            ],
        ),
    ]

    if show_sellable and dc_id:
        sellable_block = build_summary_sellable_section(
            str(dc_id),
            sellable_summary,
            classic_clusters=classic_clusters,
            hyperconv_clusters=hyperconv_clusters,
        )
        if sellable_block is not None:
            summary_children.append(sellable_block)

    return dmc.Stack(gap="lg", children=summary_children)


def _build_physical_inventory_dc_tab(phys_inv: dict):
    """Physical Inventory tab: total devices, by role bar chart, by role+manufacturer bar chart."""
    total = phys_inv.get("total", 0)
    by_role = phys_inv.get("by_role", [])
    by_rm = phys_inv.get("by_role_manufacturer", [])

    # Horizontal bar: device_role_name (title-case display)
    role_labels = [title_case(r["role"]) for r in by_role]
    role_counts = [r["count"] for r in by_role]

    # B1. Dynamic chart height
    dynamic_height = max(340, len(role_labels) * 36)

    # B2. Dynamic left margin based on longest label
    max_label_len = max((len(l) for l in role_labels), default=10)
    left_margin = min(max_label_len * 7 + 10, 220)

    # B3. Conditional text position
    max_count = max(role_counts) if role_counts else 1
    text_positions = [
        "inside" if c > max_count * 0.35 else "outside"
        for c in role_counts
    ]
    text_colors = [
        "white" if c > max_count * 0.35 else "#2B3674"
        for c in role_counts
    ]

    fig_role = go.Figure(
        data=[go.Bar(
            x=role_counts or [0],
            y=role_labels or ["No data"],
            orientation="h",
            marker=dict(
                color=role_counts,
                colorscale=[
                    [0.0, "#C4B5FD"],
                    [0.4, "#7551FF"],
                    [0.7, "#4318FF"],
                    [1.0, "#05CD99"],
                ],
                showscale=False,
                line=dict(color="rgba(0,0,0,0)", width=0),
            ),
            text=role_counts,
            textposition=text_positions,
            textfont=dict(size=11, family="DM Sans", weight=700, color=text_colors),
            hovertemplate="<b>%{y}</b><br>%{x:,} devices<extra></extra>",
            width=0.65,
        )]
    )
    fig_role.update_traces(marker_cornerradius=8)
    fig_role.update_layout(
        margin=dict(l=left_margin, r=70, t=10, b=10),
        height=dynamic_height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        bargap=0.28,
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            range=[0, max(role_counts or [1]) * 1.22],
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            categoryorder="total ascending",
            tickfont=dict(family="DM Sans", size=12, color="#2B3674"),
        ),
        font=dict(family="DM Sans, sans-serif", color="#2B3674", size=12),
    )

    # Horizontal stacked bar: Y=role, X=count, color=manufacturer
    rm_filtered = list(by_rm)
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
        # Top 8 manufacturers by total count
        manu_totals: dict = {}
        for r in rm_filtered:
            m = title_case(r.get("manufacturer") or "Unknown")
            manu_totals[m] = manu_totals.get(m, 0) + r["count"]
        top_manufacturers = [m for m, _ in sorted(manu_totals.items(), key=lambda x: -x[1])[:8]]

        # Top 12 roles by total device count
        role_totals: dict = {}
        for r in rm_filtered:
            role = title_case(r["role"])
            role_totals[role] = role_totals.get(role, 0) + r["count"]
        all_roles_rm = [role for role, _ in sorted(role_totals.items(), key=lambda x: -x[1])[:12]]

        colors = ["#4318FF", "#05CD99", "#FFB547", "#7551FF", "#00DBE3",
                  "#FF6B6B", "#A78BFA", "#0FBA81"]

        # Dynamic left margin based on longest label
        rm_left = min(max((len(r) for r in all_roles_rm), default=10) * 7 + 10, 240)

        fig_rm = go.Figure()
        for i, manu in enumerate(top_manufacturers):
            x_vals = []
            for role in all_roles_rm:
                count = next(
                    (r["count"] for r in rm_filtered
                     if title_case(r["role"]) == role and title_case(r.get("manufacturer") or "") == manu),
                    0
                )
                x_vals.append(count)
            fig_rm.add_trace(go.Bar(
                name=manu,
                y=all_roles_rm,
                x=x_vals,
                orientation="h",
                marker=dict(color=colors[i % len(colors)], opacity=0.92),
                hovertemplate="<b>%{y}</b><br>" + manu + ": <b>%{x:,} devices</b><extra></extra>",
            ))

        try:
            fig_rm.update_traces(marker_cornerradius=4)
        except Exception:
            pass

        rm_height = max(360, len(all_roles_rm) * 38)
        fig_rm.update_layout(
            barmode="stack",
            bargap=0.25,
            margin=dict(l=rm_left, r=20, t=10, b=60),
            height=rm_height,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.12,
                xanchor="center",
                x=0.5,
                font=dict(size=11, family="DM Sans", color="#2B3674"),
                bgcolor="rgba(255,255,255,0.9)",
                bordercolor="rgba(227,234,252,0.8)",
                borderwidth=1,
                itemsizing="constant",
            ),
            xaxis=dict(
                showgrid=True,
                gridcolor="rgba(227, 234, 252, 0.5)",
                gridwidth=1,
                zeroline=False,
                tickfont=dict(family="DM Sans", size=11, color="#A3AED0"),
            ),
            yaxis=dict(
                showgrid=False,
                zeroline=False,
                categoryorder="total ascending",
                tickfont=dict(family="DM Sans", size=12, color="#2B3674", weight=600),
                automargin=True,
            ),
            hoverlabel=dict(
                bgcolor="rgba(255,255,255,0.97)",
                bordercolor="rgba(67,24,255,0.15)",
                font=dict(family="DM Sans", size=12, color="#2B3674"),
            ),
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
                    dmc.SimpleGrid(cols=4, spacing="lg", style={"marginTop": "12px"}, children=[
                        _kpi("Total Devices", f"{total:,}", _DC_ICONS["total_devices"], color="indigo", stagger=1),
                        _kpi("Device Roles", f"{len(by_role):,}", _DC_ICONS["device_roles"], color="violet", stagger=2),
                        _kpi("Top Role", title_case(by_role[0]["role"]) if by_role else "—", _DC_ICONS["top_role"], color="grape", is_text=True, stagger=3),
                        _kpi("Manufacturers", f"{len(set(r['manufacturer'] for r in by_rm)) if by_rm else 0}", _DC_ICONS["manufacturers"], color="teal", stagger=4),
                    ]),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Devices by Role", "Device role distribution"),
                    html.Div(
                        style={"overflowY": "auto", "maxHeight": "480px"},
                        children=dcc.Graph(
                            figure=fig_role,
                            config={"displayModeBar": False},
                            style={"height": f"{dynamic_height}px"},
                        ),
                    ),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Manufacturer by Role", "Stacked by manufacturer, sorted by total devices"),
                    dcc.Graph(figure=fig_rm, config={"displayModeBar": False}, style={"height": f"{rm_height}px"}),
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


NETWORK_TOP_SCOPES = ["overview", "switch", "router_uplink", "firewall", "load_balancer"]

NETWORK_TOP_LABELS: dict[str, tuple[str, str]] = {
    "overview": ("Overview", "Device health and all billable interfaces (unified view)"),
    "switch": ("Switch", "Backbone, leaf, spine and management port analytics"),
    "router_uplink": ("Router Uplinks", "Carrier uplink interfaces for billing"),
    "firewall": ("Firewall", "Firewall device sessions, HA and security metrics"),
    "load_balancer": ("Load Balancer", "Citrix ADC health (vserver metrics pending Zabbix items)"),
}

NETWORK_TOP_PERMISSIONS: dict[str, str] = {
    "overview": "sub:dc_view:net:overview",
    "switch": "sub:dc_view:net:switch",
    "router_uplink": "sub:dc_view:net:router_uplink",
    "firewall": "sub:dc_view:net:firewall",
    "load_balancer": "sub:dc_view:net:load_balancer",
}

SWITCH_ROLE_SCOPES = ["backbone", "leaf", "spine", "management"]

SWITCH_ROLE_LABELS: dict[str, tuple[str, str]] = {
    "backbone": ("Backbone", "Billing interfaces — 95th percentile bandwidth"),
    "leaf": ("Leaf", "Data ports (shared ports excluded)"),
    "spine": ("Spine", "Spine interconnect ports"),
    "management": ("Management", "Management and OOB ports"),
}

NETWORK_API_SCOPE: dict[str, str | None] = {
    "overview": None,
    "router_uplink": "router_uplink",
}


def resolve_network_interface_scope(top_scope: str | None, switch_role: str | None = None) -> str | None:
    """Map UI tab + switch segment to datacenter-api interface_scope."""
    scope = top_scope or "overview"
    if scope == "switch":
        return switch_role or "backbone"
    if scope == "overview":
        return None
    return NETWORK_API_SCOPE.get(scope)


def _network_scope_subtitle(top_scope: str | None, switch_role: str | None = None) -> str:
    scope = top_scope or "overview"
    if scope == "switch":
        role = switch_role or "backbone"
        return SWITCH_ROLE_LABELS.get(role, ("", ""))[1]
    return NETWORK_TOP_LABELS.get(scope, ("", ""))[1]


def _visible_network_scopes(sec_check=None) -> list[str]:
    check = sec_check or (lambda _code: True)
    scopes = [scope for scope, perm in NETWORK_TOP_PERMISSIONS.items() if check(perm)]
    if scopes:
        return scopes
    if check("sec:dc_view:network"):
        return ["overview"]
    return []


def _network_kpi_labels(interface_scope: str | None) -> tuple[str, str, str, str]:
    if interface_scope == "backbone":
        return (
            "Billable Devices",
            "Active Interfaces",
            "Total Interfaces",
            "P95 Utilization",
        )
    if interface_scope == "router_uplink":
        return ("Router Devices", "Active Uplinks", "Total Uplinks", "ICMP Availability")
    return ("Total Devices", "Active Ports", "Total Ports", "Port Availability")


def _network_interface_table_columns(interface_scope: str | None) -> list[dict]:
    cols = [
        {"name": "Host", "id": "host"},
        {"name": "Interface", "id": "interface_name"},
        {"name": "Alias", "id": "interface_alias"},
        {"name": "P95 RX (Gbps)", "id": "p95_rx_gbps", "type": "numeric"},
        {"name": "P95 TX (Gbps)", "id": "p95_tx_gbps", "type": "numeric"},
        {"name": "P95 Total (Gbps)", "id": "p95_total_gbps", "type": "numeric"},
        {"name": "Speed (Gbps)", "id": "speed_gbps", "type": "numeric"},
        {"name": "Util %", "id": "utilization_pct", "type": "numeric"},
    ]
    if interface_scope == "backbone":
        cols[5]["name"] = "P95 Billable (Gbps)"
        cols.extend(
            [
                {"name": "P95 Billable (Mbit)", "id": "p95_billable_mbit"},
                {"name": "Unit Price (TL/Mbit)", "id": "unit_price_tl_per_mbit"},
                {"name": "Est. Cost (TL)", "id": "estimated_cost_tl"},
            ]
        )
    return cols


def _network_bar_chart_title(interface_scope: str | None) -> str:
    if interface_scope == "backbone":
        return "Top 10 Billable Interfaces — P95 Preview (Gbps)"
    if interface_scope == "router_uplink":
        return "Top 10 Router Uplinks — P95 Preview (Gbps)"
    return "Top 10 Interfaces — P95 Preview (Gbps)"


def _network_table_section_titles(
    interface_scope: str | None,
    billing: bool,
    billing_meta: dict | None = None,
) -> tuple[str, str]:
    if interface_scope == "backbone":
        subtitle = "P95 billable bandwidth (RX+TX) with CRM unit pricing"
        if billing_meta and billing_meta.get("has_price"):
            product_name = billing_meta.get("product_name") or "Veri Merkezi Erişim ve L3 DDoS"
            unit_price = float(billing_meta.get("unit_price_tl") or 0)
            subtitle = f"{product_name} — {unit_price:,.2f} TL/Mbit"
        elif billing_meta and not billing_meta.get("has_price"):
            subtitle = "CRM unit price unavailable — cost columns empty"
        return ("Billable Interface Table", subtitle)
    if billing:
        return (
            "Billable Interface Table",
            "P95 interface utilization for all in-scope interfaces",
        )
    return (
        "Interface Utilization Table",
        "P95 utilization across interfaces in the selected scope",
    )


def _network_page_flags(top_scope: str | None, switch_role: str | None = None) -> dict:
    scope = top_scope or "overview"
    iface_scope = resolve_network_interface_scope(scope, switch_role)
    billing = iface_scope in ("backbone", "router_uplink")
    switch_segment = switch_role or "backbone"
    return {
        "top_scope": scope,
        "interface_scope": iface_scope,
        "billing": billing,
        "show_export": billing,
        "show_donut_grid": scope == "overview",
        "show_single_gauge": scope == "switch" and switch_segment == "leaf",
        "show_preview_collapse": billing or scope == "overview",
        "is_interface_page": scope in ("overview", "switch", "router_uplink"),
    }


def _firewall_aggregate_kpis(firewall_data: dict) -> tuple[int, int, int, int]:
    devices = (firewall_data or {}).get("devices") or []
    total_sessions = sum(int(d.get("active_sessions") or 0) for d in devices)
    total_intrusions = sum(int(d.get("intrusions_detected") or 0) for d in devices)
    ha_pairs = sum(1 for d in devices if (d.get("ha_mode") or "").strip())
    return len(devices), total_sessions, total_intrusions, ha_pairs


def _interface_table_rows(items: list, interface_scope: str | None = None) -> list[dict]:
    rows = []
    include_billing = interface_scope == "backbone"
    for it in items or []:
        row = {
            "host": it.get("host") or "",
            "interface_name": it.get("interface_name") or "",
            "interface_alias": it.get("interface_alias") or "",
            "p95_rx_gbps": round(_bps_to_gbps(it.get("p95_rx_bps")), 3),
            "p95_tx_gbps": round(_bps_to_gbps(it.get("p95_tx_bps")), 3),
            "p95_total_gbps": round(_bps_to_gbps(it.get("p95_total_bps")), 3),
            "speed_gbps": round(_bps_to_gbps(it.get("speed_bps")), 3),
            "utilization_pct": round(float(it.get("utilization_pct") or 0), 2),
        }
        if include_billing:
            mbit = it.get("p95_billable_mbit")
            unit_price = it.get("unit_price_tl_per_mbit")
            est_cost = it.get("estimated_cost_tl")
            row["p95_billable_mbit"] = format_compact_decimal(mbit) if mbit is not None else "-"
            row["unit_price_tl_per_mbit"] = (
                format_full_decimal(unit_price, decimals=4) if unit_price is not None else "-"
            )
            row["estimated_cost_tl"] = (
                format_compact_money_tl(est_cost) if est_cost is not None else "-"
            )
        rows.append(row)
    return rows


def _build_network_interface_page(
    net_filters: dict,
    port_summary: dict,
    percentile_data: dict,
    interface_table: dict,
    top_scope: str = "overview",
    switch_role: str = "backbone",
):
    """Interface utilization page (overview, switch segments, router uplinks)."""
    flags = _network_page_flags(top_scope, switch_role)
    interface_scope = flags["interface_scope"]
    billing = flags["billing"]
    kpi1, kpi2, kpi3, kpi4 = _network_kpi_labels(interface_scope)
    table_title, table_subtitle = _network_table_section_titles(
        interface_scope,
        billing,
        (interface_table or {}).get("billing"),
    )

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

    manufacturers = net_filters.get("manufacturers") or []
    devices_by_manufacturer = net_filters.get("devices_by_manufacturer") or {}
    if not devices_by_manufacturer:
        devices_by_manufacturer_role = net_filters.get("devices_by_manufacturer_role") or {}
        for manu, roles_map in devices_by_manufacturer_role.items():
            devs: set[str] = set()
            for dev_list in (roles_map or {}).values():
                devs.update(dev_list or [])
            devices_by_manufacturer[manu] = sorted(devs)
    devices_all = sorted({d for devs in devices_by_manufacturer.values() for d in (devs or [])})

    if kpi4 == "P95 Utilization":
        kpi4_value = f"{overall_util_pct:.1f}%"
    elif kpi4 == "ICMP Availability":
        kpi4_value = f"{icmp_availability_pct:.1f}%"
    else:
        kpi4_value = f"{port_availability_pct:.1f}%"

    kpis = dmc.SimpleGrid(
        cols=4,
        spacing="lg",
        children=[
            _kpi(kpi1, f"{device_count:,}", _DC_ICONS["total_devices"], color="indigo", stagger=1),
            _kpi(kpi2, f"{active_ports:,}", _DC_ICONS["active_ports"], color="indigo", stagger=2),
            _kpi(kpi3, f"{total_ports:,}", _DC_ICONS["total_ports"], color="indigo", stagger=3),
            _kpi(
                kpi4,
                kpi4_value,
                _DC_ICONS["active_ports"] if kpi4 == "P95 Utilization" else _DC_ICONS["port_availability"],
                color="indigo",
                stagger=4,
            ),
        ],
    )

    gauge_l1, gauge_l2, gauge_l3 = _network_gauge_labels(interface_scope)
    donut_active = create_premium_gauge_chart(port_availability_pct, "", color="#FFB547", height=180)
    donut_util = create_premium_gauge_chart(overall_util_pct, "", color="#05CD99", height=180)
    donut_icmp = create_premium_gauge_chart(icmp_availability_pct, "", color="#4318FF", height=180)
    single_gauge = create_premium_gauge_chart(overall_util_pct, "", color="#05CD99", height=180)

    top_interfaces = percentile_data.get("top_interfaces") or []
    bar_labels = [
        (t.get("interface_alias") or t.get("interface_name") or "").strip() or "Unknown"
        for t in top_interfaces[:10]
    ]
    bar_values = [_bps_to_gbps(t.get("p95_total_bps")) for t in top_interfaces[:10]]
    bar_fig = create_premium_horizontal_bar_chart(
        labels=bar_labels,
        values=bar_values,
        title=_network_bar_chart_title(interface_scope),
        unit_suffix="Gbps",
        height=280,
    )

    items = interface_table.get("items") or []
    total_count = int(interface_table.get("total") or len(items))
    page_size_init = 50
    page_count_init = max(1, math.ceil(total_count / page_size_init)) if total_count else 1
    columns = _network_interface_table_columns(interface_scope)

    return dmc.Stack(
        gap="lg",
        children=[
            dmc.SimpleGrid(
                cols=2,
                spacing="lg",
                children=[
                    dmc.Select(
                        id="net-manufacturer-selector",
                        label="Manufacturer",
                        placeholder="All manufacturers",
                        data=[{"label": m, "value": m} for m in manufacturers],
                        value=None,
                        clearable=True,
                        searchable=True,
                        nothingFoundMessage="No manufacturers",
                    ),
                    dmc.Select(
                        id="net-device-selector",
                        label="Device",
                        placeholder="All devices",
                        data=[{"label": d, "value": d} for d in devices_all],
                        value=None,
                        clearable=True,
                        searchable=True,
                        nothingFoundMessage="No devices",
                    ),
                ],
            ),
            html.Div(id="net-kpi-container", children=kpis),
            html.Div(
                id="net-donut-grid-wrap",
                style={"display": "block" if flags["show_donut_grid"] else "none"},
                children=[
                    dmc.SimpleGrid(
                        cols=3,
                        spacing="lg",
                        children=[
                            _chart_card(
                                _gauge_wrap(donut_active, gauge_l1, graph_id="net-donut-active-ports")
                            ),
                            _chart_card(
                                _gauge_wrap(donut_util, gauge_l2, graph_id="net-donut-utilization")
                            ),
                            _chart_card(
                                _gauge_wrap(donut_icmp, gauge_l3, graph_id="net-donut-icmp")
                            ),
                        ],
                    )
                ],
            ),
            html.Div(
                id="net-single-gauge-wrap",
                style={"display": "block" if flags["show_single_gauge"] else "none"},
                children=[
                    _chart_card(
                        _gauge_wrap(single_gauge, "P95 Utilization", graph_id="net-single-util-gauge")
                    )
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    dmc.Group(
                        justify="space-between",
                        align="flex-end",
                        children=[
                            html.Div(
                                children=[
                                    _section_title(table_title, table_subtitle),
                                ]
                            ),
                            html.Div(
                                id="net-export-btn-wrap",
                                style={"display": "block" if flags["show_export"] else "none"},
                                children=[
                                    dmc.Button(
                                        "Export All CSV",
                                        id="net-interface-export-btn",
                                        variant="light",
                                        color="indigo",
                                        leftSection=DashIconify(icon="solar:download-minimalistic-linear", width=16),
                                    ),
                                ],
                            ),
                        ],
                    ),
                    dmc.Group(
                        grow=True,
                        align="flex-end",
                        children=[
                            dmc.TextInput(
                                id="net-interface-search",
                                placeholder="Search host / interface / alias...",
                                value="",
                                leftSection=DashIconify(icon="solar:magnifer-linear", width=16, color="#A3AED0"),
                            ),
                            dmc.Select(
                                id="net-interface-page-size",
                                label="Rows per page",
                                data=[
                                    {"label": "50", "value": "50"},
                                    {"label": "100", "value": "100"},
                                    {"label": "200", "value": "200"},
                                ],
                                value="50",
                                allowDeselect=False,
                                style={"maxWidth": "160px"},
                            ),
                        ],
                    ),
                    dmc.Text(
                        id="net-interface-table-footer",
                        children=f"Showing 1–{min(len(items), 50)} of {total_count:,} interfaces",
                        size="sm",
                        c="dimmed",
                        style={"marginTop": "8px", "marginBottom": "4px"},
                    ),
                    dash_table.DataTable(
                        id="net-interface-table",
                        columns=columns,
                        data=_interface_table_rows(items),
                        page_current=0,
                        page_size=page_size_init,
                        page_count=page_count_init,
                        page_action="custom",
                        sort_action="none",
                        filter_action="none",
                        style_table={"overflowX": "auto", "marginTop": "6px"},
                        style_cell={
                            "padding": "10px 14px",
                            "color": "#2B3674",
                            "fontFamily": "DM Sans, sans-serif",
                            "fontSize": "0.82rem",
                            "borderColor": "#F4F7FE",
                            "fontWeight": 500,
                        },
                        style_header={
                            "backgroundColor": "#F8F9FC",
                            "color": "#A3AED0",
                            "fontWeight": 700,
                            "fontFamily": "DM Sans, sans-serif",
                            "fontSize": "0.72rem",
                            "textTransform": "uppercase",
                            "letterSpacing": "0.05em",
                            "borderBottom": "2px solid #E9EDF7",
                        },
                    ),
                ],
            ),
            html.Div(
                id="net-preview-collapse-wrap",
                style={"display": "block" if flags["show_preview_collapse"] else "none"},
                children=[
                    dmc.Collapse(
                        id="net-top-preview-collapse",
                        **{"in": False},
                        children=[
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px", "marginTop": "8px"},
                                children=[
                                    _section_title(
                                        "Interface Utilization (95th Percentile)",
                                        "Top 10 preview — use the table above for full billing data",
                                    ),
                                    _chart_card(
                                        dcc.Graph(
                                            id="net-top-interfaces-bar",
                                            figure=bar_fig,
                                            config={"displayModeBar": False},
                                            style={"height": "280px"},
                                        )
                                    ),
                                ],
                            )
                        ],
                    ),
                    dmc.Button(
                        "Show Top 10 Preview",
                        id="net-top-preview-toggle",
                        variant="subtle",
                        color="gray",
                        size="xs",
                        style={"marginTop": "6px"},
                    ),
                ],
            ),
            dcc.Download(id="net-interface-export-download"),
        ],
    )


def _build_network_firewall_page(firewall_data: dict) -> html.Div:
    device_count, total_sessions, total_intrusions, ha_pairs = _firewall_aggregate_kpis(firewall_data)
    kpis = dmc.SimpleGrid(
        cols=4,
        spacing="lg",
        children=[
            _kpi("Firewall Devices", f"{device_count:,}", _DC_ICONS["total_devices"], color="indigo"),
            _kpi("Active Sessions", f"{total_sessions:,}", _DC_ICONS["active_ports"], color="indigo"),
            _kpi("Intrusions", f"{total_intrusions:,}", _DC_ICONS["port_availability"], color="indigo"),
            _kpi("HA Devices", f"{ha_pairs:,}", _DC_ICONS["total_ports"], color="indigo"),
        ],
    )
    devices = (firewall_data or {}).get("devices") or []
    rows = [
        {
            "host": d.get("host") or "",
            "device_name": d.get("device_name") or "",
            "manufacturer_name": d.get("manufacturer_name") or "",
            "cpu_utilization_pct": round(float(d.get("cpu_utilization_pct") or 0), 2),
            "memory_utilization_pct": round(float(d.get("memory_utilization_pct") or 0), 2),
            "active_sessions": int(d.get("active_sessions") or 0),
            "intrusions_detected": int(d.get("intrusions_detected") or 0),
            "intrusions_blocked": int(d.get("intrusions_blocked") or 0),
            "ha_mode": d.get("ha_mode") or "",
            "ha_cluster_name": d.get("ha_cluster_name") or "",
            "session_setup_rate": round(float(d.get("session_setup_rate") or 0), 2),
            "icmp_status": d.get("icmp_status") if d.get("icmp_status") is not None else "",
            "icmp_loss_pct": round(float(d.get("icmp_loss_pct") or 0), 2),
        }
        for d in devices
    ]
    return dmc.Stack(
        gap="lg",
        children=[
            html.Div(id="net-fw-kpi-container", children=kpis),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Firewall Devices", "Sessions, HA mode and security counters"),
                    dash_table.DataTable(
                        id="net-firewall-table",
                        columns=[
                            {"name": "Host", "id": "host"},
                            {"name": "Device", "id": "device_name"},
                            {"name": "Manufacturer", "id": "manufacturer_name"},
                            {"name": "CPU %", "id": "cpu_utilization_pct", "type": "numeric"},
                            {"name": "Memory %", "id": "memory_utilization_pct", "type": "numeric"},
                            {"name": "Sessions", "id": "active_sessions", "type": "numeric"},
                            {"name": "Intrusions", "id": "intrusions_detected", "type": "numeric"},
                            {"name": "Blocked", "id": "intrusions_blocked", "type": "numeric"},
                            {"name": "Session Rate", "id": "session_setup_rate", "type": "numeric"},
                            {"name": "HA Mode", "id": "ha_mode"},
                            {"name": "HA Cluster", "id": "ha_cluster_name"},
                            {"name": "ICMP Status", "id": "icmp_status"},
                            {"name": "ICMP Loss %", "id": "icmp_loss_pct", "type": "numeric"},
                        ],
                        data=rows,
                        page_size=25,
                        sort_action="native",
                        style_table={"overflowX": "auto", "marginTop": "8px"},
                    ),
                ],
            ),
        ],
    )


def _build_network_load_balancer_page(lb_data: dict) -> html.Div:
    devices = (lb_data or {}).get("devices") or []
    rows = [
        {
            "host": d.get("host") or "",
            "device_name": d.get("device_name") or "",
            "manufacturer_name": d.get("manufacturer_name") or "",
            "cpu_utilization_pct": round(float(d.get("cpu_utilization_pct") or 0), 2),
            "memory_utilization_pct": round(float(d.get("memory_utilization_pct") or 0), 2),
            "icmp_loss_pct": round(float(d.get("icmp_loss_pct") or 0), 2),
            "active_ports": int(d.get("active_ports_count") or 0),
            "total_ports": int(d.get("total_ports_count") or 0),
        }
        for d in devices
    ]
    return dmc.Stack(
        gap="lg",
        children=[
            dmc.Alert(
                "Citrix ADC vserver metrics (RX/TX byte rate, customer vserver name) are not yet "
                "collected in Zabbix. Device-level health is shown below until templates are defined.",
                title="Vserver metrics pending",
                color="yellow",
                radius="md",
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Load Balancer Health", "ICMP/CPU/RAM and port summary"),
                    dash_table.DataTable(
                        id="net-load-balancer-table",
                        columns=[
                            {"name": "Host", "id": "host"},
                            {"name": "Device", "id": "device_name"},
                            {"name": "Manufacturer", "id": "manufacturer_name"},
                            {"name": "CPU %", "id": "cpu_utilization_pct", "type": "numeric"},
                            {"name": "Memory %", "id": "memory_utilization_pct", "type": "numeric"},
                            {"name": "ICMP Loss %", "id": "icmp_loss_pct", "type": "numeric"},
                            {"name": "Active Ports", "id": "active_ports", "type": "numeric"},
                            {"name": "Total Ports", "id": "total_ports", "type": "numeric"},
                        ],
                        data=rows,
                        page_size=25,
                        sort_action="native",
                        style_table={"overflowX": "auto", "marginTop": "8px"},
                    ),
                ],
            ),
        ],
    )


def _build_network_zabbix_section(
    net_filters: dict,
    port_summary: dict,
    percentile_data: dict,
    interface_table: dict,
    firewall_data: dict,
    lb_data: dict,
    sec_check=None,
) -> html.Div:
    check = sec_check or (lambda _code: True)
    visible_scopes = _visible_network_scopes(sec_check=check)
    default_scope = visible_scopes[0] if visible_scopes else "overview"
    default_switch_role = SWITCH_ROLE_SCOPES[0]
    iface_flags = _network_page_flags(default_scope, default_switch_role)
    show_iface = iface_flags["is_interface_page"]
    show_fw = default_scope == "firewall"
    show_lb = default_scope == "load_balancer"

    tab_items = [
        dmc.TabsTab(NETWORK_TOP_LABELS[scope][0], value=scope)
        for scope in visible_scopes
        if scope in NETWORK_TOP_LABELS
    ]
    zabbix_children: list = []
    if tab_items:
        zabbix_children.append(
            dmc.Tabs(
                id="net-scope-tabs",
                value=default_scope,
                color="indigo",
                variant="outline",
                radius="md",
                children=[dmc.TabsList(children=tab_items)],
            )
        )
        zabbix_children.append(
            html.Div(
                id="net-switch-role-wrap",
                style={"display": "block" if default_scope == "switch" else "none", "marginTop": "12px"},
                children=[
                    dmc.SegmentedControl(
                        id="net-switch-role-segment",
                        value=default_switch_role,
                        data=[
                            {"label": SWITCH_ROLE_LABELS[role][0], "value": role}
                            for role in SWITCH_ROLE_SCOPES
                        ],
                        fullWidth=True,
                    ),
                ],
            )
        )
        zabbix_children.append(
            dmc.Text(
                id="net-scope-subtitle",
                children=_network_scope_subtitle(default_scope, default_switch_role),
                c="#A3AED0",
                size="sm",
                style={"marginTop": "8px"},
            )
        )
        zabbix_children.append(
            html.Div(
                id="net-page-interface",
                style={"display": "block" if show_iface else "none"},
                children=[
                    _build_network_interface_page(
                        net_filters,
                        port_summary,
                        percentile_data,
                        interface_table,
                        top_scope=default_scope if default_scope != "switch" else "switch",
                        switch_role=default_switch_role,
                    )
                ],
            )
        )
        zabbix_children.append(
            html.Div(
                id="net-page-firewall",
                style={"display": "block" if show_fw else "none"},
                children=[_build_network_firewall_page(firewall_data)],
            )
        )
        zabbix_children.append(
            html.Div(
                id="net-page-load-balancer",
                style={"display": "block" if show_lb else "none"},
                children=[_build_network_load_balancer_page(lb_data)],
            )
        )
    return html.Div(
        style={"padding": "0 30px"},
        children=[
            dcc.Store(id="net-filters-store", data=net_filters or {}),
            dcc.Store(id="net-firewall-store", data=firewall_data or {}),
            dcc.Store(id="net-load-balancer-store", data=lb_data or {}),
            dmc.Stack(gap="lg", children=zabbix_children),
        ],
    )


def _build_storage_section_with_san(
    has_intel_storage: bool,
    has_ibm_storage: bool,
    has_power: bool,
    has_s3: bool,
    has_san: bool,
    zabbix_storage_devices: list,
    zabbix_storage_capacity: dict,
    zabbix_storage_trend: dict,
    storage_capacity: dict,
    storage_performance: dict,
    dc_name: str,
    s3_data: dict,
    tr: dict,
    san_port_usage: dict,
    san_health_alerts: list,
    san_traffic_trend: list,
    sec_check=None,
    has_datastore: bool = False,
    datastore_mapping: dict | None = None,
) -> html.Div | None:
    check = sec_check or (lambda _code: True)
    show_km_datastore = bool(has_datastore)
    show_ibm = bool(has_ibm_storage or has_power)
    if not (
        show_km_datastore
        or show_ibm
        or has_s3
        or (has_san and check("sub:dc_view:storage:san"))
    ):
        return None

    default_tab = (
        "km-datastore-outer"
        if show_km_datastore
        else "ibm"
        if show_ibm
        else "san"
        if has_san and check("sub:dc_view:storage:san")
        else "obj-storage"
    )

    tab_list = []
    if show_km_datastore:
        tab_list.append(dmc.TabsTab("KM Datastore", value="km-datastore-outer"))
    if show_ibm:
        tab_list.append(dmc.TabsTab("IBM Storage", value="ibm"))
    if has_san and check("sub:dc_view:storage:san"):
        tab_list.append(dmc.TabsTab("SAN Switch", value="san"))
    if has_s3:
        tab_list.append(dmc.TabsTab("Object Storage - S3", value="obj-storage"))

    panels = []
    if show_km_datastore:
        panels.append(
            dmc.TabsPanel(
                value="km-datastore-outer",
                pt="lg",
                children=_build_datastore_subtab(datastore_mapping or {}),
            )
        )
    if show_ibm:
        panels.append(
            dmc.TabsPanel(
                value="ibm",
                pt="lg",
                children=_build_ibm_storage_subtab(storage_capacity, storage_performance),
            )
        )
    if has_san and check("sub:dc_view:storage:san"):
        panels.append(
            dmc.TabsPanel(
                value="san",
                pt="lg",
                children=html.Div(
                    children=[
                        _section_title("SAN Switch", "Brocade switch licensing and health"),
                        _build_san_subtab(san_port_usage, san_health_alerts, san_traffic_trend),
                    ]
                ),
            )
        )
    if has_s3:
        panels.append(
            dmc.TabsPanel(
                value="obj-storage",
                pt="lg",
                children=html.Div(
                    id="s3-dc-metrics-panel",
                    style={"marginTop": "0"},
                    children=build_dc_s3_panel(dc_name, s3_data, tr, None),
                ),
            )
        )

    return html.Div(
        style={"padding": "0 30px"},
        children=[
            dmc.Tabs(
                color="indigo",
                variant="outline",
                radius="md",
                value=default_tab,
                children=[dmc.TabsList(children=tab_list), *panels],
            )
        ],
    )


_DS_GiB = 1024 ** 3


def _ds_usage_palette(pct: float):
    """Gradient + solid color for a datastore usage level (matches IBM/Intel subtabs)."""
    if pct >= 90:
        return ("linear-gradient(90deg, #FF6B6B, #EE5D50)", "#EE5D50")
    if pct >= 75:
        return ("linear-gradient(90deg, #FFD080, #FFB547)", "#FFB547")
    return ("linear-gradient(90deg, #868CFF, #4318FF)", "#4318FF")


def _ds_usage_bar(used_pct: float, height: str = "34px", show_label: bool = True):
    """Premium used/free split bar."""
    used_pct = max(0.0, min(100.0, used_pct))
    free_pct = 100.0 - used_pct
    grad, _ = _ds_usage_palette(used_pct)
    label = show_label and used_pct > 10
    return html.Div(
        style={"display": "flex", "borderRadius": "8px", "overflow": "hidden", "height": height, "background": "#EAF0F7"},
        children=[
            html.Div(
                style={
                    "width": f"{used_pct}%", "background": grad,
                    "display": "flex", "alignItems": "center", "justifyContent": "center",
                },
                children=html.Span(
                    f"{used_pct:.1f}%",
                    style={"color": "white", "fontSize": "0.74rem", "fontWeight": 800, "fontFamily": "DM Sans"},
                ) if label else None,
            ),
        ],
    )


def _ds_vdc_label(datacenter_name: str | None) -> str:
    """`DC13-KM-SSD-vDC` -> `KM-SSD`."""
    s = (datacenter_name or "").strip()
    for pre in ("DC13-", "DC12-", "DC11-"):
        if s.startswith(pre):
            s = s[len(pre):]
            break
    return s.replace("-vDC", "").replace("-VDC", "") or "—"


def _ds_vdc_badge(datacenter_name: str | None):
    lbl = _ds_vdc_label(datacenter_name)
    up = lbl.upper()
    if "NUTANIX" in up:
        color = "teal"
    elif "SSD" in up:
        color = "violet"
    elif "KM" in up:
        color = "indigo"
    else:
        color = "gray"
    return dmc.Badge(lbl, color=color, variant="light", size="sm", radius="sm")


def _ds_type_badge(ds_type: str | None):
    t = (ds_type or "").strip().upper()
    color = "grape" if t.startswith("VMFS") else "cyan" if t in ("NFS", "NAS", "NFS41") else "gray"
    return dmc.Badge(ds_type or "—", color=color, variant="outline", size="sm", radius="sm")


def _ds_backing_badge(backing: str | None):
    """IBM-backed vs Intel-backed datastore badge (storage range model)."""
    b = (backing or "").strip().lower()
    if b == "ibm":
        return dmc.Badge("IBM", color="blue", variant="filled", size="sm", radius="sm")
    return dmc.Badge("INTEL", color="cyan", variant="light", size="sm", radius="sm")


# ---------------------------------------------------------------------------
# Hosts panel (Klasik / Hyperconverged) — host-based capacity & usage detail.
# Collapsible section at the bottom of the virtualization tabs; content is
# filled by cluster-selector-aware callbacks (see app.py).
# ---------------------------------------------------------------------------


def _host_metric_row(
    label: str,
    used: float,
    cap: float,
    unit: str,
    alloc: float | None = None,
    alloc_pct: float | None = None,
):
    """Single resource row inside a host card: % + numeric capacity-usage."""
    pct = (100.0 * used / cap) if cap > 0 else 0.0
    _, solid = _ds_usage_palette(pct)
    children = [
        html.Div(
            style={"display": "flex", "justifyContent": "space-between", "alignItems": "baseline", "marginBottom": "4px"},
            children=[
                html.Span(
                    label,
                    style={"fontSize": "0.72rem", "fontWeight": 700, "color": "#A3AED0",
                           "textTransform": "uppercase", "letterSpacing": "0.04em", "fontFamily": "DM Sans"},
                ),
                html.Span(
                    children=[
                        html.Span(f"%{pct:.1f}", style={"fontWeight": 800, "color": solid, "marginRight": "6px"}),
                        html.Span(f"{used:,.1f} / {cap:,.1f} {unit}", style={"color": "#2B3674", "fontWeight": 600}),
                    ],
                    style={"fontSize": "0.78rem", "fontFamily": "DM Sans", "whiteSpace": "nowrap"},
                ),
            ],
        ),
        _ds_usage_bar(pct, height="10px", show_label=False),
    ]
    if alloc is not None:
        children.append(
            html.Div(
                f"Tahsis (satış): {alloc:,.1f} {unit}" + (f" · %{alloc_pct:.1f}" if alloc_pct is not None else ""),
                style={"fontSize": "0.7rem", "color": "#A3AED0", "marginTop": "3px", "fontFamily": "DM Sans"},
            )
        )
    return html.Div(style={"marginBottom": "10px"}, children=children)


def _host_card(h: dict, color: str = "blue"):
    """Single host card: cluster badge + VM count + CPU/RAM(/Disk) bars."""
    host_name = h.get("host") or "Unknown"
    cpu_phys = float(h.get("cpu_alloc_ghz_physical") or 0)
    cpu_eff = float(h.get("cpu_alloc_ghz") or 0)
    cpu_row = _host_metric_row(
        "CPU",
        float(h.get("cpu_used_ghz") or 0), float(h.get("cpu_cap_ghz") or 0), "GHz",
        alloc=cpu_eff, alloc_pct=float(h.get("cpu_alloc_pct") or 0),
    )
    cpu_row.children.append(
        html.Div(
            f"Physical alloc: {cpu_phys:,.1f} GHz · Effective: {cpu_eff:,.1f} GHz (1 vCPU=1 GHz)",
            style={"fontSize": "0.7rem", "color": "#A3AED0", "marginTop": "3px", "fontFamily": "DM Sans"},
        )
    )
    rows = [
        cpu_row,
        _host_metric_row(
            "Memory",
            float(h.get("mem_used_gb") or 0), float(h.get("mem_cap_gb") or 0), "GB",
            alloc=float(h.get("mem_alloc_gb") or 0), alloc_pct=float(h.get("mem_alloc_pct") or 0),
        ),
    ]
    # HCI hosts expose their own per-host storage (Nutanix); show when present.
    if float(h.get("stor_cap_gb") or 0) > 0:
        rows.append(
            _host_metric_row(
                "Disk",
                float(h.get("stor_used_host_gb") or 0) / 1024.0,
                float(h.get("stor_cap_gb") or 0) / 1024.0,
                "TB",
            )
        )
    return html.Div(
        className="nexus-card",
        style={
            "padding": "16px",
            "background": "#FBFCFE",
            "border": "1px solid #E6EBF5",
            "boxShadow": "none",
        },
        children=[
            html.Div(
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "center",
                       "marginBottom": "12px", "gap": "8px"},
                children=[
                    html.Span(
                        host_name,
                        title=host_name,
                        style={"fontWeight": 800, "color": "#2B3674", "fontSize": "0.9rem",
                               "fontFamily": "DM Sans", "overflow": "hidden",
                               "textOverflow": "ellipsis", "whiteSpace": "nowrap", "minWidth": 0},
                    ),
                    html.Div(
                        style={"display": "flex", "gap": "6px", "flexShrink": 0},
                        children=[
                            dmc.Badge(h.get("cluster") or "—", color=color, variant="light", size="sm", radius="sm"),
                            dmc.Badge(f"{int(h.get('vm_count') or 0)} VM", color="gray", variant="outline", size="sm", radius="sm"),
                        ],
                    ),
                ],
            ),
            *rows,
        ],
    )


def _build_hosts_panel_content(hosts_data: dict, color: str = "blue"):
    """Host card grid — rendered into the collapsible Hosts panel by callbacks."""
    hosts = (hosts_data or {}).get("hosts") or []
    if not hosts:
        return dmc.Alert(
            "Seçili cluster'lar için host verisi bulunamadı.",
            title="Veri yok",
            color="gray",
            radius="md",
        )
    return dmc.SimpleGrid(
        cols={"base": 1, "md": 2, "xl": 3},
        spacing="md",
        children=[_host_card(h, color) for h in hosts],
    )


def _build_hosts_panel_shell(
    slug: str,
    color: str = "blue",
    *,
    initial_data: dict | None = None,
):
    """Collapsible Hosts panel shell with optional prefetched content."""
    count = int((initial_data or {}).get("host_count") or 0)
    count_label = f"{count} host" if count else "—"
    initial_content = (
        _build_hosts_panel_content(initial_data, color)
        if initial_data and count
        else None
    )
    return html.Div(
        className="nexus-card",
        style={"padding": "20px"},
        children=[
            html.Div(
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "gap": "12px"},
                children=[
                    _section_title(
                        "Host Detayları",
                        "Seçili cluster'ların hostları — CPU / RAM kapasite, kullanım ve satış tahsisi",
                    ),
                    html.Div(
                        style={"display": "flex", "alignItems": "center", "gap": "8px", "flexShrink": 0},
                        children=[
                            dmc.Badge(
                                id=f"hosts-count-{slug}",
                                children=count_label,
                                color=color,
                                variant="light",
                                size="lg",
                                radius="sm",
                            ),
                            dmc.Button(
                                "Göster",
                                id=f"hosts-toggle-{slug}",
                                variant="light",
                                color=color,
                                size="xs",
                                radius="md",
                                rightSection=DashIconify(icon="solar:alt-arrow-down-bold", width=14),
                            ),
                        ],
                    ),
                ],
            ),
            dmc.Collapse(
                id=f"hosts-collapse-{slug}",
                **{"in": False},
                children=html.Div(
                    id=f"hosts-panel-{slug}",
                    style={"marginTop": "16px"},
                    children=initial_content,
                ),
            ),
        ],
    )


def _build_datastore_subtab(datastore_mapping: dict):
    """
    VMware Datastore subtab — klasik mimari "storage eşleştirmesi".

    Premium layout: KPI strip → capacity-by-vDC bars → fullest-datastore highlights
    → full datastore table (with usage data-bars) → host↔datastore mapping table.
    Surfaces all three collected tables (metrics_agg + host_mount + inventory).
    """
    datastores = (datastore_mapping or {}).get("datastores") or []

    if not datastores:
        return html.Div(
            className="nexus-card",
            style={"padding": "20px"},
            children=[
                _section_title("Datastore Eşleştirme", "VMware datastore kapasite, host eşleştirmesi ve envanter"),
                dmc.Alert(
                    "Bu data center için datastore verisi bulunamadı.",
                    title="Veri yok",
                    color="gray",
                    radius="md",
                ),
            ],
        )

    # ── Aggregates ─────────────────────────────────────────────────────────
    total_cap = sum(ds.get("capacity_bytes") or 0 for ds in datastores)
    total_used = sum(ds.get("used_bytes") or 0 for ds in datastores)
    total_free = sum(ds.get("free_bytes") or 0 for ds in datastores)
    overall_pct = (total_used / total_cap * 100) if total_cap > 0 else 0.0
    total_vms = sum(int(ds.get("vm_count") or 0) for ds in datastores)

    host_set: set[str] = set()
    inaccessible_mounts = 0
    for ds in datastores:
        for h in ds.get("hosts") or []:
            if h.get("host_moid"):
                host_set.add(h["host_moid"])
            if h.get("accessible") is False:
                inaccessible_mounts += 1

    vdc_groups: dict[str, dict] = {}
    for ds in datastores:
        key = ds.get("datacenter_name") or "—"
        g = vdc_groups.setdefault(key, {"cap": 0, "used": 0, "count": 0})
        g["cap"] += ds.get("capacity_bytes") or 0
        g["used"] += ds.get("used_bytes") or 0
        g["count"] += 1

    type_counts: dict[str, int] = {}
    for ds in datastores:
        t = ds.get("type") or "—"
        type_counts[t] = type_counts.get(t, 0) + 1

    # ── KPI strip ──────────────────────────────────────────────────────────
    used_color = "red" if overall_pct >= 90 else "orange" if overall_pct >= 75 else "indigo"
    kpi_strip = dmc.SimpleGrid(
        cols={"base": 2, "sm": 3, "lg": 5},
        spacing="md",
        children=[
            _kpi("Datastore", f"{len(datastores):,}", _DC_ICONS["storage_systems"], color="indigo", stagger=1),
            _kpi("Toplam Kapasite", smart_storage(total_cap / _DS_GiB), _DC_ICONS["total_capacity"], color="grape", is_text=True, stagger=2),
            _kpi("Kullanılan", f"{smart_storage(total_used / _DS_GiB)}  ·  {overall_pct:.0f}%", _DC_ICONS["used_capacity"], color=used_color, is_text=True, stagger=3),
            _kpi("Boş", smart_storage(total_free / _DS_GiB), _DC_ICONS["storage"], color="teal", is_text=True, stagger=4),
            _kpi("Bağlı Host", f"{len(host_set):,}", _DC_ICONS["total_devices"], color="cyan", stagger=5,
                 tooltip=f"{total_vms:,} VM · {inaccessible_mounts} erişilemeyen mount" if inaccessible_mounts else f"{total_vms:,} VM"),
        ],
    )

    # ── Capacity by vDC ────────────────────────────────────────────────────
    def _vdc_row(name: str, g: dict):
        cap, used, count = g["cap"], g["used"], g["count"]
        pct = (used / cap * 100) if cap > 0 else 0.0
        _, pct_color = _ds_usage_palette(pct)
        return html.Div(
            style={"background": "#FAFBFF", "border": "1px solid #E9EDF7", "borderRadius": "12px", "padding": "16px 18px"},
            children=[
                # Row 1: badge + datastore count (left) · usage % (right, short → never wraps)
                html.Div(
                    style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "8px", "marginBottom": "10px"},
                    children=[
                        html.Div(
                            style={"display": "flex", "alignItems": "center", "gap": "8px", "minWidth": 0},
                            children=[_ds_vdc_badge(name), html.Span(f"{count} datastore", style={"fontSize": "0.74rem", "color": "#A3AED0", "fontFamily": "DM Sans", "fontWeight": 600, "whiteSpace": "nowrap"})],
                        ),
                        html.Span(f"{pct:.1f}%", style={"fontSize": "0.95rem", "color": pct_color, "fontFamily": "DM Sans", "fontWeight": 800, "flexShrink": 0}),
                    ],
                ),
                # Row 2: used / total — always its own line so all cards align identically
                html.Div(
                    f"{smart_storage(used / _DS_GiB)} / {smart_storage(cap / _DS_GiB)}",
                    style={"fontSize": "0.82rem", "color": "#2B3674", "fontFamily": "DM Sans", "fontWeight": 700, "fontVariantNumeric": "tabular-nums", "marginBottom": "10px"},
                ),
                _ds_usage_bar(pct, height="20px", show_label=False),
            ],
        )

    vdc_sorted = sorted(vdc_groups.items(), key=lambda kv: kv[1]["cap"], reverse=True)
    type_chips = dmc.Group(
        gap="xs",
        children=[
            dmc.Badge(f"{t} · {c}", color=("grape" if t.upper().startswith("VMFS") else "cyan" if t.upper() in ("NFS", "NAS", "NFS41") else "gray"),
                      variant="dot", size="sm", radius="sm")
            for t, c in sorted(type_counts.items(), key=lambda kv: kv[1], reverse=True)
        ],
    )
    vdc_card = html.Div(
        className="nexus-card",
        style={"padding": "20px"},
        children=[
            html.Div(
                style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "12px", "flexWrap": "wrap", "marginBottom": "14px"},
                children=[_section_title("Kapasite Dağılımı", "vCenter datacenter (vDC) bazında kullanım"), type_chips],
            ),
            dmc.SimpleGrid(cols={"base": 1, "md": min(3, len(vdc_sorted)) or 1}, spacing="md", children=[_vdc_row(n, g) for n, g in vdc_sorted]),
        ],
    )

    # ── Fullest datastores (highlight) ─────────────────────────────────────
    fullest = sorted(
        [ds for ds in datastores if (ds.get("capacity_bytes") or 0) > 0],
        key=lambda ds: float(ds.get("used_percent") or 0),
        reverse=True,
    )[:6]

    def _highlight_card(ds: dict):
        pct = float(ds.get("used_percent") or 0)
        _, color = _ds_usage_palette(pct)
        cap = (ds.get("capacity_bytes") or 0) / _DS_GiB
        used = (ds.get("used_bytes") or 0) / _DS_GiB
        free = (ds.get("free_bytes") or 0) / _DS_GiB
        return html.Div(
            style={"background": "#FAFBFF", "border": "1px solid #E9EDF7", "borderRadius": "12px", "padding": "16px 18px"},
            children=[
                html.Div(
                    style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "8px", "marginBottom": "12px"},
                    children=[
                        html.Div(
                            style={"display": "flex", "alignItems": "center", "gap": "8px", "minWidth": 0},
                            children=[
                                html.Div(style={"width": "8px", "height": "8px", "borderRadius": "50%", "background": color, "flexShrink": 0}),
                                html.Span(
                                    ds.get("datastore_name") or "Unknown",
                                    style={"fontWeight": 700, "fontSize": "0.86rem", "color": "#2B3674", "fontFamily": "DM Sans",
                                           "whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis"},
                                    title=ds.get("datastore_name") or "",
                                ),
                            ],
                        ),
                        html.Div(style={"display": "flex", "gap": "4px", "flexShrink": 0}, children=[_ds_backing_badge(ds.get("backing")), _ds_type_badge(ds.get("type")), _ds_vdc_badge(ds.get("datacenter_name"))]),
                    ],
                ),
                _ds_usage_bar(pct, height="30px"),
                html.Div(
                    style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "marginTop": "10px"},
                    children=[
                        html.Span(f"Kullanılan {smart_storage(used)}", style={"fontSize": "0.76rem", "color": color, "fontFamily": "DM Sans", "fontWeight": 700}),
                        html.Span(f"Boş {smart_storage(free)}", style={"fontSize": "0.76rem", "color": "#05CD99", "fontFamily": "DM Sans", "fontWeight": 600}),
                        html.Span(f"Σ {smart_storage(cap)}", style={"fontSize": "0.74rem", "color": "#A3AED0", "fontFamily": "DM Sans"}),
                    ],
                ),
                html.Div(
                    style={"display": "flex", "gap": "6px", "marginTop": "10px"},
                    children=[
                        dmc.Badge(f"{int(ds.get('host_count') or 0)} host", color="gray", variant="light", size="xs", radius="sm"),
                        dmc.Badge(f"{int(ds.get('vm_count') or 0)} VM", color="gray", variant="light", size="xs", radius="sm"),
                    ],
                ),
            ],
        )

    fullest_card = html.Div(
        className="nexus-card",
        style={"padding": "20px"},
        children=[
            _section_title("En Dolu Datastore'lar", "Kullanım oranına göre ilk 6"),
            dmc.SimpleGrid(cols={"base": 1, "sm": 2, "lg": 3}, spacing="md", style={"marginTop": "4px"}, children=[_highlight_card(ds) for ds in fullest]),
        ],
    )

    # ── Full datastore table (with usage data-bars) ────────────────────────
    summary_rows = []
    mount_rows = []
    for ds in datastores:
        ds_name = ds.get("datastore_name") or "Unknown"
        nas_target = f"{ds.get('nas_remote_host')}:{ds.get('nas_remote_path') or ''}" if ds.get("nas_remote_host") else "—"
        summary_rows.append({
            "datastore": ds_name,
            "vdc": _ds_vdc_label(ds.get("datacenter_name")),
            "backing": (ds.get("backing") or "intel").upper(),
            "type": ds.get("type") or "—",
            "capacity_gb": round((ds.get("capacity_bytes") or 0) / _DS_GiB, 1),
            "used_gb": round((ds.get("used_bytes") or 0) / _DS_GiB, 1),
            "free_gb": round((ds.get("free_bytes") or 0) / _DS_GiB, 1),
            "used_pct": round(float(ds.get("used_percent") or 0), 1),
            "host_count": int(ds.get("host_count") or 0),
            "vm_count": int(ds.get("vm_count") or 0),
            "vmfs_version": ds.get("vmfs_version") or "—",
            "nas_target": nas_target,
            "status": ds.get("status") or "—",
        })
        for h in ds.get("hosts") or []:
            mount_rows.append({
                "datastore": ds_name,
                "host": h.get("host_name") or "Unknown",
                "mount_path": h.get("mount_path") or "—",
                "access_mode": h.get("access_mode") or "—",
                "mounted": "✓" if h.get("mounted") else "✗",
                "accessible": "✓" if h.get("accessible") else "✗",
            })

    _header_style = {
        "fontWeight": 700, "backgroundColor": "#F4F7FE", "color": "#707EAE",
        "textTransform": "uppercase", "fontSize": "0.68rem", "letterSpacing": "0.04em",
        "border": "none", "padding": "12px",
    }
    _cell_style = {"fontFamily": "DM Sans", "fontSize": "0.82rem", "padding": "10px 12px", "color": "#2B3674", "border": "none"}
    _table_style = {"overflowX": "auto", "marginTop": "10px", "borderRadius": "12px"}
    _hover_css = [{"selector": "tr:hover td", "rule": "background-color: #F4F7FE !important;"}]

    summary_table = dash_table.DataTable(
        id="datastore-summary-table",
        columns=[
            {"name": "Datastore", "id": "datastore"},
            {"name": "vDC", "id": "vdc"},
            {"name": "Backing", "id": "backing"},
            {"name": "Tip", "id": "type"},
            {"name": "Kapasite (GB)", "id": "capacity_gb", "type": "numeric"},
            {"name": "Kullanılan (GB)", "id": "used_gb", "type": "numeric"},
            {"name": "Boş (GB)", "id": "free_gb", "type": "numeric"},
            {"name": "Kullanım %", "id": "used_pct", "type": "numeric"},
            {"name": "Host", "id": "host_count", "type": "numeric"},
            {"name": "VM", "id": "vm_count", "type": "numeric"},
            {"name": "VMFS", "id": "vmfs_version"},
            {"name": "NAS Hedef", "id": "nas_target"},
            {"name": "Durum", "id": "status"},
        ],
        data=summary_rows,
        page_size=15,
        sort_action="native",
        filter_action="native",
        sort_by=[{"column_id": "used_pct", "direction": "desc"}],
        style_table=_table_style,
        style_cell=_cell_style,
        style_header=_header_style,
        style_data={"borderBottom": "1px solid #F0F2F8"},
        style_cell_conditional=[
            {"if": {"column_id": "datastore"}, "textAlign": "left", "fontWeight": 600, "minWidth": "200px", "maxWidth": "320px"},
            {"if": {"column_id": "nas_target"}, "textAlign": "left", "maxWidth": "240px", "overflow": "hidden", "textOverflow": "ellipsis"},
        ],
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": "#FBFCFF"},
            {"if": {"filter_query": "{used_pct} >= 90", "column_id": "used_pct"}, "color": "#EE5D50", "fontWeight": 800},
            {"if": {"filter_query": "{used_pct} >= 75 && {used_pct} < 90", "column_id": "used_pct"}, "color": "#FFB547", "fontWeight": 800},
            {"if": {"filter_query": "{used_pct} < 75", "column_id": "used_pct"}, "color": "#05CD99", "fontWeight": 700},
            {"if": {"filter_query": '{status} = "active"', "column_id": "status"}, "color": "#05CD99", "fontWeight": 700},
            {"if": {"filter_query": '{status} = "passive"', "column_id": "status"}, "color": "#A3AED0"},
            {"if": {"filter_query": '{backing} = "IBM"', "column_id": "backing"}, "color": "#4318FF", "fontWeight": 800},
            {"if": {"filter_query": '{backing} = "INTEL"', "column_id": "backing"}, "color": "#00B5D8", "fontWeight": 700},
        ],
        css=_hover_css,
        tooltip_data=[{"datastore": {"value": r["datastore"], "type": "text"}, "nas_target": {"value": r["nas_target"], "type": "text"}} for r in summary_rows],
        tooltip_duration=None,
    )

    mount_table = dash_table.DataTable(
        id="datastore-host-mount-table",
        columns=[
            {"name": "Datastore", "id": "datastore"},
            {"name": "Host", "id": "host"},
            {"name": "Mount Path", "id": "mount_path"},
            {"name": "Access", "id": "access_mode"},
            {"name": "Mounted", "id": "mounted"},
            {"name": "Accessible", "id": "accessible"},
        ],
        data=mount_rows,
        page_size=15,
        sort_action="native",
        filter_action="native",
        style_table=_table_style,
        style_cell=_cell_style,
        style_header=_header_style,
        style_data={"borderBottom": "1px solid #F0F2F8"},
        style_cell_conditional=[
            {"if": {"column_id": "datastore"}, "textAlign": "left", "fontWeight": 600},
            {"if": {"column_id": "mount_path"}, "textAlign": "left", "maxWidth": "320px", "overflow": "hidden", "textOverflow": "ellipsis"},
            *[{"if": {"column_id": c}, "textAlign": "center"} for c in ("mounted", "accessible")],
        ],
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": "#FBFCFF"},
            {"if": {"filter_query": '{mounted} = "✓"', "column_id": "mounted"}, "color": "#05CD99", "fontWeight": 800},
            {"if": {"filter_query": '{mounted} = "✗"', "column_id": "mounted"}, "color": "#EE5D50", "fontWeight": 800},
            {"if": {"filter_query": '{accessible} = "✓"', "column_id": "accessible"}, "color": "#05CD99", "fontWeight": 800},
            {"if": {"filter_query": '{accessible} = "✗"', "column_id": "accessible"}, "color": "#EE5D50", "fontWeight": 800},
        ],
        css=_hover_css,
    )

    return dmc.Stack(
        gap="lg",
        children=[
            kpi_strip,
            vdc_card,
            fullest_card,
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title(f"Tüm Datastore'lar ({len(summary_rows)})", "Kapasite, kullanım ve VMFS/NAS envanteri — sıralanabilir & filtrelenebilir"),
                    summary_table,
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title(f"Host Eşleştirme ({len(mount_rows)})", "Her datastore'un mount edildiği host kayıtları"),
                    mount_table,
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

    # Capacity info card (replaces gauge — total is not a ratio)
    _bar_w = f"{min(used_pct, 100):.1f}%"
    _bar_color = "#FFB547" if used_pct < 75 else "#EE5D50" if used_pct >= 90 else "#FF8C00"
    total_capacity_card = html.Div(
        className="nexus-card dc-chart-card",
        style={
            "padding": "24px 28px",
            "height": "300px",
            "display": "flex",
            "flexDirection": "column",
            "justifyContent": "center",
            "gap": "16px",
            "overflow": "hidden",
            "boxSizing": "border-box",
        },
        children=[
            # Header row
            html.Div(
                style={"display": "flex", "alignItems": "center", "gap": "10px"},
                children=[
                    html.Div(
                        style={
                            "width": "36px", "height": "36px", "borderRadius": "10px",
                            "background": "rgba(255,181,71,0.12)",
                            "display": "flex", "alignItems": "center", "justifyContent": "center",
                            "flexShrink": 0,
                        },
                        children=DashIconify(icon="solar:database-bold-duotone", width=20, color="#FFB547"),
                    ),
                    html.Div([
                        html.Div("TOTAL CAPACITY", style={
                            "fontSize": "0.62rem", "fontWeight": 700, "color": "#A3AED0",
                            "letterSpacing": "0.08em", "marginBottom": "2px",
                        }),
                        html.Div(smart_storage(total_gb), style={
                            "fontSize": "1.75rem", "fontWeight": 900, "color": "#2B3674",
                            "letterSpacing": "-0.03em", "lineHeight": 1,
                            "fontVariantNumeric": "tabular-nums",
                        }),
                    ]),
                ],
            ),
            # Usage bar
            html.Div([
                html.Div(
                    style={"display": "flex", "justifyContent": "space-between", "marginBottom": "6px"},
                    children=[
                        html.Span("Utilization", style={"fontSize": "0.68rem", "fontWeight": 600, "color": "#A3AED0"}),
                        html.Span(f"{used_pct:.1f}%", style={"fontSize": "0.68rem", "fontWeight": 800, "color": _bar_color}),
                    ],
                ),
                html.Div(
                    style={"height": "6px", "borderRadius": "4px", "background": "#EEF2FF", "overflow": "hidden"},
                    children=html.Div(style={
                        "width": _bar_w, "height": "100%", "borderRadius": "4px",
                        "background": f"linear-gradient(90deg, #FFB547 0%, {_bar_color} 100%)",
                    }),
                ),
            ]),
            # Used / Free row
            html.Div(
                style={"display": "flex", "gap": "16px"},
                children=[
                    html.Div([
                        html.Div("Used", style={"fontSize": "0.62rem", "fontWeight": 700, "color": "#A3AED0", "letterSpacing": "0.06em"}),
                        html.Div(smart_storage(used_gb), style={"fontSize": "0.95rem", "fontWeight": 800, "color": "#2B3674", "fontVariantNumeric": "tabular-nums"}),
                    ]),
                    html.Div(style={"width": "1px", "background": "rgba(227,234,252,0.8)", "alignSelf": "stretch"}),
                    html.Div([
                        html.Div("Free", style={"fontSize": "0.62rem", "fontWeight": 700, "color": "#A3AED0", "letterSpacing": "0.06em"}),
                        html.Div(smart_storage(free_gb), style={"fontSize": "0.95rem", "fontWeight": 800, "color": "#05CD99", "fontVariantNumeric": "tabular-nums"}),
                    ]),
                ],
            ),
        ],
    )

    # Gauges
    donut_used = create_premium_gauge_chart(used_pct, "Used Capacity", color="#4318FF")
    donut_free = create_premium_gauge_chart(free_pct, "Free Capacity", color="#05CD99")

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
        height=300,
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
            *(
                [dmc.SimpleGrid(
                    cols=_intel_cols,
                    spacing="lg",
                    children=_intel_cards,
                )]
                if (_intel_cards := list(filter(None, [
                    total_capacity_card if total_bytes > 0 else None,
                    _chart_card(html.Div(
                        style={"width": "100%", "aspectRatio": "16 / 11", "maxWidth": "360px", "margin": "0 auto"},
                        children=dcc.Graph(id="intel-donut-used", figure=donut_used, config={"displayModeBar": False, "responsive": True}, style={"height": "100%", "width": "100%"}),
                    )) if used_bytes > 0 else None,
                    _chart_card(html.Div(
                        style={"width": "100%", "aspectRatio": "16 / 11", "maxWidth": "360px", "margin": "0 auto"},
                        children=dcc.Graph(id="intel-donut-free", figure=donut_free, config={"displayModeBar": False, "responsive": True}, style={"height": "100%", "width": "100%"}),
                    )) if (total_bytes - used_bytes) > 0 else None,
                ]))) and (_intel_cols := min(len(_intel_cards), 3)) is not None
                else []
            ),
            html.Div(
                className="nexus-card",
                style={"padding": "20px"},
                children=[
                    _section_title("Capacity Planning", "Capacity utilization over time (downsampled daily)"),
                    _chart_card(dcc.Graph(id="intel-capacity-trend-chart", figure=trend_fig, config={"displayModeBar": False}, style={"height": "300px"})),
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


def _build_ibm_storage_subtab(storage_capacity: dict, storage_performance: dict):
    """IBM Storage subtab — physical vs efficient capacity with topology/layer labels."""
    storage_capacity = storage_capacity or {}
    storage_performance = storage_performance or {}

    systems = storage_capacity.get("systems") or []
    storage_system_count = len(systems)

    caps = aggregate_ibm_storage_capacities(systems, parse_storage_string)
    phys_total_gb = caps["phys_total_gb"]
    phys_used_gb = caps["phys_used_gb"]
    phys_free_gb = caps["phys_free_gb"]
    eff_total_gb = caps["eff_total_gb"]
    eff_used_gb = caps["eff_used_gb"]
    eff_free_gb = caps["eff_free_gb"]
    storage_pct = caps["utilization_pct"]

    def _topology_badge(topology: str | None):
        topo = (topology or "standard").strip().lower()
        if topo == "hyperswap":
            return dmc.Badge("Hyperswap", color="violet", variant="light", size="sm")
        return dmc.Badge("Standard", color="blue", variant="light", size="sm")

    def _layer_badge(layer: str | None):
        lay = (layer or "storage").strip().lower()
        if lay == "replication":
            return dmc.Badge("Replication", color="orange", variant="outline", size="sm")
        return dmc.Badge("Storage", color="gray", variant="outline", size="sm")

    # Storage systems breakdown — physical used/free with topology and layer badges
    def _storage_system_rows():
        rows = []
        for s in systems:
            name = s.get("name") or s.get("storage_ip") or "System"
            sys_caps = compute_system_capacities_gb(s, parse_storage_string)
            used = sys_caps["phys_used_gb"]
            free = sys_caps["phys_free_gb"]
            total = sys_caps["phys_total_gb"]
            eff_total = sys_caps["eff_total_gb"]
            eff_free = sys_caps["eff_free_gb"]
            used_pct = (used / total * 100) if total > 0 else 0
            free_pct = 100 - used_pct
            if used_pct >= 80:
                used_grad = "linear-gradient(90deg, #FF6B6B, #EE5D50)"
                used_color = "#EE5D50"
            elif used_pct >= 60:
                used_grad = "linear-gradient(90deg, #FFD080, #FFB547)"
                used_color = "#FFB547"
            else:
                used_grad = "linear-gradient(90deg, #868CFF, #4318FF)"
                used_color = "#4318FF"

            rows.append(html.Div(
                style={
                    "background": "#FAFBFF",
                    "border": "1px solid #E9EDF7",
                    "borderRadius": "12px",
                    "padding": "16px 20px",
                },
                children=[
                    html.Div(
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "justifyContent": "space-between",
                            "flexWrap": "wrap",
                            "gap": "8px",
                            "marginBottom": "14px",
                        },
                        children=[
                            html.Div(
                                style={"display": "flex", "alignItems": "center", "gap": "8px", "minWidth": 0},
                                children=[
                                    html.Div(style={"width": "8px", "height": "8px", "borderRadius": "50%", "background": used_color, "flexShrink": 0}),
                                    html.Span(name, style={"fontWeight": 700, "fontSize": "0.9rem", "color": "#2B3674", "fontFamily": "DM Sans"}),
                                ],
                            ),
                            html.Div(
                                style={"display": "flex", "alignItems": "center", "gap": "6px", "flexWrap": "wrap"},
                                children=[
                                    _layer_badge(s.get("layer")),
                                    _topology_badge(s.get("topology")),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        style={"display": "flex", "borderRadius": "10px", "overflow": "hidden", "height": "36px", "marginBottom": "12px"},
                        children=[
                            html.Div(
                                style={
                                    "flex": f"{used_pct}",
                                    "background": used_grad,
                                    "display": "flex", "alignItems": "center", "justifyContent": "center",
                                    "minWidth": "48px",
                                },
                                children=html.Span(
                                    f"{used_pct:.1f}%",
                                    style={"color": "white", "fontSize": "0.78rem", "fontWeight": 700, "fontFamily": "DM Sans"},
                                ) if used_pct > 10 else None,
                            ),
                            html.Div(
                                style={
                                    "flex": f"{free_pct}",
                                    "background": "linear-gradient(90deg, #C6F6E2, #A8EDCB)",
                                    "display": "flex", "alignItems": "center", "justifyContent": "center",
                                    "minWidth": "48px",
                                },
                                children=html.Span(
                                    f"{free_pct:.1f}%",
                                    style={"color": "#05CD99", "fontSize": "0.78rem", "fontWeight": 700, "fontFamily": "DM Sans"},
                                ) if free_pct > 10 else None,
                            ),
                        ],
                    ),
                    html.Div(
                        style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"},
                        children=[
                            html.Div(
                                style={"display": "flex", "gap": "16px"},
                                children=[
                                    html.Div(
                                        style={"display": "flex", "alignItems": "center", "gap": "6px"},
                                        children=[
                                            html.Div(style={"width": "10px", "height": "10px", "borderRadius": "3px", "background": used_color}),
                                            html.Span(f"Used  {smart_storage(used)}", style={"fontSize": "0.78rem", "color": "#2B3674", "fontFamily": "DM Sans", "fontWeight": 600}),
                                        ],
                                    ),
                                    html.Div(
                                        style={"display": "flex", "alignItems": "center", "gap": "6px"},
                                        children=[
                                            html.Div(style={"width": "10px", "height": "10px", "borderRadius": "3px", "background": "#05CD99"}),
                                            html.Span(f"Free  {smart_storage(free)}", style={"fontSize": "0.78rem", "color": "#2B3674", "fontFamily": "DM Sans", "fontWeight": 600}),
                                        ],
                                    ),
                                ],
                            ),
                            html.Span(
                                f"Total: {smart_storage(total)}",
                                style={"fontSize": "0.78rem", "color": "#A3AED0", "fontFamily": "DM Sans"},
                            ),
                        ],
                    ),
                    html.Div(
                        f"Efficient: {smart_storage(eff_total)} total / {smart_storage(eff_free)} free",
                        style={
                            "fontSize": "0.72rem",
                            "color": "#15AABF",
                            "fontFamily": "DM Sans",
                            "fontStyle": "italic",
                            "marginTop": "10px",
                            "opacity": 0.85,
                        },
                    ),
                ],
            ))
        return rows

    # Performance cards
    storage_series = storage_performance.get("series") or []
    iops_vals = [float(s.get("iops", 0) or 0) for s in storage_series]
    throughput_vals = [float(s.get("throughput_mb", 0) or 0) for s in storage_series]
    latency_vals = [float(s.get("latency_ms", 0) or 0) for s in storage_series]
    avg_iops = (sum(iops_vals) / len(iops_vals)) if iops_vals else 0.0
    avg_throughput = (sum(throughput_vals) / len(throughput_vals)) if throughput_vals else 0.0
    avg_latency = (sum(latency_vals) / len(latency_vals)) if latency_vals else 0.0

    return dmc.Stack(
        gap="lg",
        children=[
            dmc.Text("Physical Storage", size="xs", c="#A3AED0", fw=600, tt="uppercase", style={"letterSpacing": "0.06em"}),
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 2, "md": 5},
                spacing="lg",
                children=[
                    _kpi("Storage Systems", f"{storage_system_count:,}", _DC_ICONS["storage_systems"], color="grape"),
                    _kpi("Physical Total", smart_storage(phys_total_gb), _DC_ICONS["total_capacity"], color="grape", is_text=True),
                    _kpi("Physical Used", smart_storage(phys_used_gb), _DC_ICONS["used_capacity"], color="grape", is_text=True),
                    _kpi("Physical Free", smart_storage(phys_free_gb), _DC_ICONS["total_capacity"], color="grape", is_text=True, opacity=0.55),
                    _kpi("Utilization", f"{storage_pct:.1f}%", _DC_ICONS["utilization"], color="grape"),
                ],
            ),
            dmc.Stack(
                gap="xs",
                children=[
                    dmc.Text("Efficient Storage", size="xs", c="#15AABF", fw=600, tt="uppercase", style={"letterSpacing": "0.06em", "opacity": 0.9}),
                    dmc.SimpleGrid(
                        cols=4,
                        spacing="lg",
                        children=[
                            _kpi(
                                "Efficient Total",
                                smart_storage(eff_total_gb),
                                _DC_ICONS["total_capacity"],
                                color="cyan",
                                is_text=True,
                                opacity=0.85,
                                background="#F8FBFF",
                            ),
                            _kpi(
                                "Efficient Used",
                                smart_storage(eff_used_gb),
                                _DC_ICONS["used_capacity"],
                                color="cyan",
                                is_text=True,
                                background="#F8FBFF",
                            ),
                            _kpi(
                                "Efficient Free",
                                smart_storage(eff_free_gb),
                                _DC_ICONS["total_capacity"],
                                color="cyan",
                                is_text=True,
                                opacity=0.5,
                                background="#F8FBFF",
                            ),
                        ],
                    ),
                ],
            ),
            dmc.SimpleGrid(
                cols=2,
                spacing="lg",
                children=[
                    # LEFT CARD — Gauge + summary stats
                    html.Div(
                        className="nexus-card",
                        style={"padding": "24px", "display": "flex", "flexDirection": "column", "gap": "16px"},
                        children=[
                            _section_title("Storage Capacity", "Physical utilization"),
                            html.Div(
                                style={"display": "flex", "justifyContent": "center"},
                                children=[_gauge_wrap(
                                    create_gauge_chart(phys_used_gb, phys_total_gb or 1, "", color="#FFB547", height=220),
                                    "Storage Capacity",
                                )] if _has_value(phys_total_gb) else [
                                    html.P("No data available.", style={"color": "#A3AED0", "fontSize": "0.85rem", "textAlign": "center", "paddingTop": "60px"}),
                                ],
                            ),
                            # Summary stats row
                            html.Div(
                                style={"display": "flex", "justifyContent": "space-around", "borderTop": "1px solid #F4F7FE", "paddingTop": "16px"},
                                children=[
                                    html.Div(style={"textAlign": "center"}, children=[
                                        html.Div(smart_storage(phys_total_gb), style={"fontWeight": 800, "fontSize": "1.1rem", "color": "#2B3674", "fontFamily": "DM Sans"}),
                                        html.Div("Physical Total", style={"fontSize": "0.75rem", "color": "#A3AED0", "fontFamily": "DM Sans", "marginTop": "2px"}),
                                    ]),
                                    html.Div(style={"width": "1px", "background": "#F4F7FE"}),
                                    html.Div(style={"textAlign": "center"}, children=[
                                        html.Div(smart_storage(phys_used_gb), style={"fontWeight": 800, "fontSize": "1.1rem", "color": "#FFB547", "fontFamily": "DM Sans"}),
                                        html.Div("Physical Used", style={"fontSize": "0.75rem", "color": "#A3AED0", "fontFamily": "DM Sans", "marginTop": "2px"}),
                                    ]),
                                    html.Div(style={"width": "1px", "background": "#F4F7FE"}),
                                    html.Div(style={"textAlign": "center"}, children=[
                                        html.Div(smart_storage(phys_free_gb), style={"fontWeight": 800, "fontSize": "1.1rem", "color": "#05CD99", "fontFamily": "DM Sans", "opacity": "0.75"}),
                                        html.Div("Physical Free", style={"fontSize": "0.75rem", "color": "#A3AED0", "fontFamily": "DM Sans", "marginTop": "2px"}),
                                    ]),
                                ],
                            ),
                        ],
                    ),
                    # RIGHT CARD — Per-system breakdown
                    html.Div(
                        className="nexus-card",
                        style={"padding": "24px"},
                        children=[
                            _section_title("Systems Breakdown", f"{storage_system_count} storage system{'s' if storage_system_count != 1 else ''} detected"),
                            html.Div(
                                style={"marginTop": "16px", "display": "flex", "flexDirection": "column", "gap": "16px"},
                                children=_storage_system_rows() or [
                                    html.P("No storage systems found.", style={"color": "#A3AED0", "fontSize": "0.85rem"}),
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
        ],
    )

# ---------------------------------------------------------------------------
# Main page builder
# ---------------------------------------------------------------------------

_BUILD_LOG = logging.getLogger(__name__)

_SUMMARY_EAGER_TABS = frozenset({"summary"})
_LAZY_TAB_KEYS: tuple[str, ...] = ("virt", "backup", "storage", "phys-inv", "network", "avail")


def _find_component_by_id(component, target_id: str):
    """Depth-first search for a Dash component by string id."""
    if component is None:
        return None
    cid = getattr(component, "id", None)
    if cid == target_id:
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    if isinstance(children, (list, tuple)):
        for ch in children:
            if ch is None:
                continue
            hit = _find_component_by_id(ch, target_id)
            if hit is not None:
                return hit
    else:
        return _find_component_by_id(children, target_id)
    return None


def _resolve_outer_tab(
    active_outer_tab: str | None,
    tabs_order: list[tuple[str, bool]],
    default_outer_tab: str,
) -> str:
    """Keep user-selected tab when valid; otherwise fall back to first available."""
    if active_outer_tab:
        for tab_key, ok in tabs_order:
            if ok and tab_key == active_outer_tab:
                return active_outer_tab
    return default_outer_tab


def build_dc_lazy_tab_panel(
    dc_id: str,
    tab: str,
    time_range=None,
    visible_sections=None,
):
    """Build inner content for a single lazy tab root (no full page rebuild)."""
    tr = time_range or default_time_range()
    vs = visible_sections
    dc_display, _ = resolve_dc_display_from_summary(str(dc_id), tr)
    page = build_dc_view(
        dc_id,
        tr,
        visible_sections=vs,
        eager_tabs=frozenset({tab}),
    )
    root_id = f"dc-tab-{tab}-root"
    found = _find_component_by_id(page, root_id)
    if found is None:
        return build_dc_tab_loading_shell(tab, dc_display)
    children = getattr(found, "children", None)
    if children is None:
        return build_dc_tab_loading_shell(tab, dc_display)
    return children


def _tab_eager(eager_tabs: frozenset[str] | None, tab: str) -> bool:
    if eager_tabs is None:
        return True
    return tab in eager_tabs


def _tab_lazy_placeholder(tab: str, dc_display: str) -> html.Div:
    return dcc.Loading(
        id=f"dc-tab-{tab}-loading",
        type="circle",
        color="#4318FF",
        delay_show=250,
        overlay_style={"visibility": "visible", "backgroundColor": "rgba(244, 247, 254, 0.6)"},
        children=html.Div(
            id=f"dc-tab-{tab}-root",
            style={"padding": "0 30px", "minHeight": "120px"},
            children=build_dc_tab_loading_shell(tab, dc_display),
        ),
    )


def _log_dc_build_phase(dc_id: str, phase: str, started: float, **extra) -> None:
    ms = round((time.perf_counter() - started) * 1000, 1)
    parts = " ".join(f"{k}={v}" for k, v in extra.items())
    _BUILD_LOG.info("build_dc_view dc=%s phase=%s ms=%s %s", dc_id, phase, ms, parts)


def compute_has_backup(dc_id: str, time_range: dict | None = None) -> bool:
    """DC için Veeam/Zerto/NetBackup'tan herhangi birinde veri var mı?

    Sidebar'daki 'Backup için ekstra' kontrolünün görünürlüğünü belirlemek için
    build_dc_view'dan bağımsız hızlı bir probe. Aynı cache'lenmiş api_client
    wrapper'larını kullanır — DC sayfası açılmışsa hepsi cache hit.
    """
    if not dc_id:
        return False
    tr = time_range or default_time_range()
    try:
        nb = api.get_dc_netbackup_pools(dc_id, tr)
        zerto = api.get_dc_zerto_sites(dc_id, tr)
        veeam = api.get_dc_veeam_repos(dc_id, tr)
    except Exception:
        return False
    return bool((nb or {}).get("pools") or (zerto or {}).get("sites") or (veeam or {}).get("repos"))


def build_dc_view(
    dc_id,
    time_range=None,
    visible_sections=None,
    *,
    eager_tabs: frozenset[str] | None = None,
    active_outer_tab: str | None = None,
):
    """Build DC detail page for the given time range.

    visible_sections: optional set of permission codes (sec:/sub:/action:) the user may see.
    If None, all sections are shown (backward compatible).
    eager_tabs: when set, only fetch/build content for these tab keys (summary, virt, storage, …).
    """
    if not dc_id:
        return html.Div("No Data Center ID provided", style={"padding": "20px"})

    def _sec(code: str) -> bool:
        if visible_sections is None:
            return True
        return code in visible_sections

    tr = time_range or default_time_range()
    t_total = time.perf_counter()
    t_batch1 = time.perf_counter()
    batch1_tasks: dict = {
        "data": lambda: api.get_dc_details(dc_id, tr),
        "sla_by_dc": lambda: api.get_sla_by_dc(tr),
    }
    if _tab_eager(eager_tabs, "virt") or _tab_eager(eager_tabs, "summary"):
        batch1_tasks["classic_clusters"] = lambda: api.get_classic_cluster_list(dc_id, tr)
        batch1_tasks["hyperconv_clusters"] = lambda: api.get_hyperconv_cluster_list(dc_id, tr)
    if _tab_eager(eager_tabs, "storage"):
        batch1_tasks["s3_data"] = lambda: api.get_dc_s3_pools(dc_id, tr)
    if _tab_eager(eager_tabs, "summary"):
        batch1_tasks["sellable_summary"] = lambda: api.get_sellable_summary_light(str(dc_id))
    batch1 = parallel_execute(batch1_tasks)
    _log_dc_build_phase(str(dc_id), "batch1", t_batch1, tasks=len(batch1_tasks))
    data = batch1["data"]
    sla_by_dc = batch1["sla_by_dc"]
    s3_data = batch1.get("s3_data") or {"pools": []}
    classic_clusters = batch1.get("classic_clusters") or []
    hyperconv_clusters = batch1.get("hyperconv_clusters") or []
    sellable_summary = batch1.get("sellable_summary")

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
    dc_loc = data["meta"]["location"]
    dc_desc = (data.get("meta") or {}).get("description") or ""
    dc_display = format_dc_display_name(dc_name, dc_desc)

    need_batch2 = (
        _tab_eager(eager_tabs, "phys-inv")
        or _tab_eager(eager_tabs, "network")
        or _tab_eager(eager_tabs, "avail")
        or _tab_eager(eager_tabs, "storage")
    )
    t_batch2 = time.perf_counter()
    if need_batch2:
        batch2 = parallel_execute(
            {
                "phys_inv": lambda: api.get_physical_inventory_dc(dc_name),
                "san_switches": lambda: api.get_dc_san_switches(dc_id, tr),
                "net_filters": lambda: api.get_dc_network_filters(dc_id, tr),
                "aura_dc": lambda: api.get_dc_availability_sla_item(str(dc_id), dc_name, tr),
            }
        )
        _log_dc_build_phase(str(dc_id), "batch2", t_batch2)
    else:
        batch2 = {}
    aura_dc_item = batch2.get("aura_dc")
    phys_inv = batch2.get("phys_inv") or {"total": 0}
    has_phys_inv = phys_inv.get("total", 0) > 0

    export_group = dmc.Group(
        gap=6,
        align="center",
        children=[
            dmc.Text("Export", size="xs", c="dimmed"),
            dmc.Button("CSV", id="dc-export-csv", size="xs", variant="light", color="gray"),
            dmc.Button("Excel", id="dc-export-xlsx", size="xs", variant="light", color="gray"),
            dmc.Button("PDF", id={"type": "pdf-export-btn", "index": "dc"}, size="xs", variant="light", color="gray"),
        ],
    )
    header_right_extra = list(sla_badges or [])
    if _sec("action:dc_view:export"):
        header_right_extra.append(export_group)

    san_switches = batch2.get("san_switches") or {}
    has_san = _has_san_data(san_switches) if _tab_eager(eager_tabs, "storage") else False
    t_san = time.perf_counter()
    if _tab_eager(eager_tabs, "storage") and has_san:
        san_port_usage = api.get_dc_san_port_usage(dc_id, tr)
        san_health_alerts = api.get_dc_san_health(dc_id, tr)
        san_traffic_trend = api.get_dc_san_traffic_trend(dc_id, tr)
        _log_dc_build_phase(str(dc_id), "san", t_san)
    else:
        san_port_usage = {}
        san_health_alerts = []
        san_traffic_trend = []
    san_ms = round((time.perf_counter() - t_san) * 1000, 1)

    net_filters = batch2.get("net_filters") or {}
    has_network = bool((net_filters or {}).get("manufacturers")) if _tab_eager(eager_tabs, "network") else False
    net_port_summary: dict = {}
    net_percentile: dict = {}
    net_interface_table: dict = {}
    net_interface_export: dict = {}
    net_firewall_data: dict = {}
    net_lb_data: dict = {}
    net_ms = 0.0
    if has_network and _tab_eager(eager_tabs, "network"):
        t_net = time.perf_counter()
        net_batch = parallel_execute(
            {
                "port_summary": lambda: api.get_dc_network_port_summary(dc_id, tr),
                "percentile": lambda: api.get_dc_network_95th_percentile(dc_id, tr, top_n=20),
                "interface_table": lambda: api.get_dc_network_interface_table(
                    dc_id, tr, page=1, page_size=50
                ),
                "interface_export": lambda: api.get_dc_network_interface_export(dc_id, tr),
                "firewall": lambda: api.get_dc_network_firewall_summary(dc_id, tr),
                "load_balancer": lambda: api.get_dc_network_load_balancer_summary(dc_id, tr),
            }
        )
        net_port_summary = net_batch["port_summary"]
        net_percentile = net_batch["percentile"]
        net_interface_table = net_batch["interface_table"]
        net_interface_export = net_batch["interface_export"]
        net_firewall_data = net_batch["firewall"]
        net_lb_data = net_batch["load_balancer"]
        net_ms = round((time.perf_counter() - t_net) * 1000, 1)
        _log_dc_build_phase(str(dc_id), "network", t_net)

    energy    = data.get("energy", {})
    classic   = data.get("classic", {})
    hyperconv = data.get("hyperconv", {})
    power     = data.get("power", {})

    # Backup datasets (per DC)
    t_backup = time.perf_counter()
    if _tab_eager(eager_tabs, "backup"):
        nb_data = api.get_dc_netbackup_pools(dc_id, tr)
        zerto_data = api.get_dc_zerto_sites(dc_id, tr)
        veeam_data = api.get_dc_veeam_repos(dc_id, tr)
        _log_dc_build_phase(str(dc_id), "backup", t_backup)
    else:
        nb_data = {"pools": []}
        zerto_data = {"sites": []}
        veeam_data = {"repos": []}
    backup_ms = round((time.perf_counter() - t_backup) * 1000, 1)

    export_sheets = (
        _build_dc_export_sheets(
            str(dc_id),
            data,
            phys_inv,
            net_interface_export or net_interface_table,
            nb_data,
            zerto_data,
            veeam_data,
        )
        if eager_tabs is None
        else {}
    )

    # Determine which sections actually have data
    has_classic = _has_compute_data(classic)
    has_hyperconv = _has_compute_data(hyperconv)
    has_power = _has_power_data(power)

    storage_capacity = {}
    storage_performance = {}
    san_bottleneck = {}
    _fetch_ibm_storage = _tab_eager(eager_tabs, "virt") or _tab_eager(eager_tabs, "storage")
    if _fetch_ibm_storage:
        t_power_storage = time.perf_counter()
        storage_capacity = api.get_dc_storage_capacity(dc_id, tr)
        storage_performance = api.get_dc_storage_performance(dc_id, tr)
        if _tab_eager(eager_tabs, "virt"):
            san_bottleneck = api.get_dc_san_bottleneck(dc_id, tr)
        power_storage_ms = round((time.perf_counter() - t_power_storage) * 1000, 1)
        _log_dc_build_phase(str(dc_id), "power_storage", t_power_storage)
    else:
        power_storage_ms = 0.0
    has_ibm_storage = bool((storage_capacity.get("systems") or []))

    # Intel Storage (Zabbix)
    if _tab_eager(eager_tabs, "storage"):
        zabbix_storage_capacity = api.get_dc_zabbix_storage_capacity(dc_id, tr)
        has_intel_storage = int(zabbix_storage_capacity.get("storage_device_count", 0) or 0) > 0
        t_intel_storage = time.perf_counter()
        zabbix_storage_devices = api.get_dc_zabbix_storage_devices(dc_id, tr) if has_intel_storage else []
        zabbix_storage_trend = api.get_dc_zabbix_storage_trend(dc_id, tr) if has_intel_storage else {}
        intel_storage_ms = round((time.perf_counter() - t_intel_storage) * 1000, 1)
        _log_dc_build_phase(str(dc_id), "intel_storage", t_intel_storage)
        datastore_mapping = api.get_dc_datastore_mapping(dc_id, tr)
        has_datastore = int(datastore_mapping.get("datastore_count", 0) or 0) > 0
    else:
        zabbix_storage_capacity = {}
        has_intel_storage = False
        zabbix_storage_devices = []
        zabbix_storage_trend = {}
        intel_storage_ms = 0.0
        datastore_mapping = {}
        has_datastore = False

    has_storage = bool(has_intel_storage or has_ibm_storage or has_power or has_s3 or has_san or has_datastore)

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
    has_avail = True

    show_summary = has_summary and _sec("sec:dc_view:summary")
    show_virt = has_virt and _sec("sec:dc_view:virtualization")
    show_storage = has_storage and _sec("sec:dc_view:storage")
    show_backup = has_backup and _sec("sec:dc_view:backup")
    show_phys = has_phys_inv and _sec("sec:dc_view:phys_inv")
    show_network = has_network and _sec("sec:dc_view:network")
    show_avail = has_avail and _sec("sec:dc_view:availability")
    if eager_tabs is not None:
        show_virt = _sec("sec:dc_view:virtualization")
        show_storage = _sec("sec:dc_view:storage")
        show_backup = _sec("sec:dc_view:backup")
        show_phys = _sec("sec:dc_view:phys_inv")
        show_network = _sec("sec:dc_view:network")

    tabs_order = [
        ("summary", show_summary),
        ("virt", show_virt),
        ("storage", show_storage),
        ("backup", show_backup),
        ("phys-inv", show_phys),
        ("network", show_network),
        ("avail", show_avail),
    ]
    default_outer_tab = next((t for t, ok in tabs_order if ok), "summary")
    resolved_outer_tab = _resolve_outer_tab(active_outer_tab, tabs_order, default_outer_tab)

    show_classic = has_classic and _sec("sub:dc_view:virt:classic")
    show_hyperconv = has_hyperconv and _sec("sub:dc_view:virt:hyperconv")
    show_power_inner = has_power and _sec("sub:dc_view:virt:power")
    show_virt_hosts = _sec("sub:dc_view:virt:hosts")
    show_summary_sellable = _sec("sub:dc_view:summary:sellable")
    virt_order = [
        ("classic", show_classic),
        ("hyperconv", show_hyperconv),
        ("power", show_power_inner),
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
                size="md",
                radius="xl",
                style={
                    "minWidth": "260px",
                    "background": "#F8F9FC",
                },
            ),
        )

    page = html.Div([
        dcc.Store(
            id="dc-export-store",
            data={
                "dc_name": dc_name,
                "dc_code": str(dc_id),
                "sheets": export_sheets,
            },
        ),
        dcc.Download(id="dc-export-download"),
        dmc.Tabs(
            id="dc-main-tabs",
            color="indigo",
            variant="pills",
            radius="md",
            value=resolved_outer_tab,
            children=[
                create_detail_header(
                    title=dc_display,
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
                            dmc.TabsTab("Summary", value="summary") if show_summary else None,
                            dmc.TabsTab("Virtualization", value="virt") if show_virt else None,
                            dmc.TabsTab("Storage", value="storage") if show_storage else None,
                            dmc.TabsTab("Backup & Replication", value="backup") if show_backup else None,
                            dmc.TabsTab("Physical Inventory", value="phys-inv") if show_phys else None,
                            dmc.TabsTab("Network", value="network") if show_network else None,
                            dmc.TabsTab("Availability", value="avail") if show_avail else None,
                        ],
                    ),
                ),

                # Summary tab
                dmc.TabsPanel(
                    value="summary",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[_build_summary_tab(
                            data, tr, dc_id=str(dc_id),
                            sellable_summary=sellable_summary if show_summary_sellable else None,
                            show_sellable=show_summary_sellable,
                            classic_clusters=classic_clusters or None,
                            hyperconv_clusters=hyperconv_clusters or None,
                        )],
                    ),
                ) if show_summary else None,

                # Virtualization (nested tabs)
                dmc.TabsPanel(
                    value="virt",
                    children=(
                        _tab_lazy_placeholder("virt", dc_display)
                        if not _tab_eager(eager_tabs, "virt")
                        else html.Div(
                        id="dc-tab-virt-root",
                        style={"padding": "0 30px"},
                        children=[
                            html.Div(id="sellable-virt-total-card"),
                            dmc.Tabs(
                                color="violet",
                                variant="outline",
                                radius="md",
                                value=default_virt_tab,
                                children=[
                                    dmc.TabsList(
                                        children=[
                                            dmc.TabsTab("Klasik Mimari", value="classic") if show_classic else None,
                                            dmc.TabsTab("Hyperconverged Mimari", value="hyperconv") if show_hyperconv else None,
                                            dmc.TabsTab("Power Mimari", value="power") if show_power_inner else None,
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
                                                    children=_build_compute_tab(classic, "Classic Compute", color="blue", slug="classic"),
                                                ),
                                                html.Div(id="sellable-classic-card"),
                                                _build_hosts_panel_shell(
                                                    "classic", "blue",
                                                ) if show_virt_hosts else None,
                                            ],
                                        ),
                                    ) if show_classic else None,
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
                                                    children=_build_compute_tab(hyperconv, "Hyperconverged Compute", color="teal", slug="hyperconv"),
                                                ),
                                                html.Div(id="sellable-hyperconv-card"),
                                                _build_hosts_panel_shell(
                                                    "hyperconv", "teal",
                                                ) if show_virt_hosts else None,
                                            ],
                                        ),
                                    ) if show_hyperconv else None,
                                    dmc.TabsPanel(
                                        value="power",
                                        pt="lg",
                                        children=dmc.Stack(
                                            gap="lg",
                                            children=[
                                                _build_power_tab(
                                                    power,
                                                    energy,
                                                    storage_capacity,
                                                    storage_performance,
                                                    san_bottleneck,
                                                ),
                                                html.Div(id="sellable-power-card"),
                                            ],
                                        ),
                                    ) if show_power_inner else None,
                                ],
                            ),
                        ],
                    )
                    ),
                ) if show_virt else None,

                # Backup (nested tabs)
                dmc.TabsPanel(
                    value="backup",
                    children=(
                        _tab_lazy_placeholder("backup", dc_display)
                        if not _tab_eager(eager_tabs, "backup")
                        else html.Div(
                        id="dc-tab-backup-root",
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
                                        children=dmc.Stack(
                                            gap="lg",
                                            children=[
                                                html.Div(
                                                    id="backup-zerto-panel",
                                                    children=build_zerto_panel(zerto_data, None) if has_zerto else html.Div(),
                                                ),
                                            ],
                                        ),
                                    ) if has_zerto else None,
                                    dmc.TabsPanel(
                                        value="veeam",
                                        pt="lg",
                                        children=dmc.Stack(
                                            gap="lg",
                                            children=[
                                                html.Div(
                                                    id="backup-veeam-panel",
                                                    children=build_veeam_panel(veeam_data, None) if has_veeam else html.Div(),
                                                ),
                                            ],
                                        ),
                                    ) if has_veeam else None,
                                    dmc.TabsPanel(
                                        value="netbackup",
                                        pt="lg",
                                        children=dmc.Stack(
                                            gap="lg",
                                            children=[
                                                html.Div(
                                                    id="backup-netbackup-panel",
                                                    children=build_netbackup_panel(nb_data, None) if has_netbackup else html.Div(),
                                                ),
                                            ],
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
                    )
                    ),
                ) if show_backup else None,

                # Physical Inventory
                dmc.TabsPanel(
                    value="phys-inv",
                    children=(
                        _tab_lazy_placeholder("phys-inv", dc_display)
                        if not _tab_eager(eager_tabs, "phys-inv")
                        else html.Div(
                            id="dc-tab-phys-inv-root",
                            children=dmc.Stack(
                                gap="lg",
                                style={"padding": "0 30px"},
                                children=[_build_physical_inventory_dc_tab(phys_inv)],
                            ),
                        )
                    ),
                ) if show_phys else None,
                # Storage (Intel / IBM / SAN / S3)
                dmc.TabsPanel(
                    value="storage",
                    children=(
                        _tab_lazy_placeholder("storage", dc_display)
                        if not _tab_eager(eager_tabs, "storage")
                        else html.Div(
                            id="dc-tab-storage-root",
                            children=_build_storage_section_with_san(
                        has_intel_storage,
                        has_ibm_storage,
                        has_power,
                        has_s3,
                        has_san,
                        zabbix_storage_devices,
                        zabbix_storage_capacity,
                        zabbix_storage_trend,
                        storage_capacity,
                        storage_performance,
                        dc_name,
                        s3_data,
                        tr,
                        san_port_usage,
                        san_health_alerts,
                        san_traffic_trend,
                        sec_check=_sec,
                        has_datastore=has_datastore,
                        datastore_mapping=datastore_mapping,
                        ),
                        )
                    ),
                ) if show_storage else None,

                # Network (role-based Zabbix scopes)
                dmc.TabsPanel(
                    value="network",
                    pt="lg",
                    children=(
                        _tab_lazy_placeholder("network", dc_display)
                        if not _tab_eager(eager_tabs, "network")
                        else html.Div(
                            id="dc-tab-network-root",
                            children=_build_network_zabbix_section(
                                net_filters,
                                net_port_summary,
                                net_percentile,
                                net_interface_table,
                                net_firewall_data,
                                net_lb_data,
                                sec_check=_sec,
                            ),
                        )
                    ),
                ) if show_network else None,

                dmc.TabsPanel(
                    value="avail",
                    children=(
                        _tab_lazy_placeholder("avail", dc_display)
                        if not _tab_eager(eager_tabs, "avail")
                        else html.Div(
                            id="dc-tab-avail-root",
                            children=dmc.Stack(
                                gap="lg",
                                style={"padding": "0 30px"},
                                children=[build_dc_availability_panel(aura_dc_item, dc_display)],
                            ),
                        )
                    ),
                )
                if show_avail
                else None,
            ],
        )
    ])
    _log_dc_build_phase(
        str(dc_id),
        "total",
        t_total,
        eager=str(eager_tabs) if eager_tabs is not None else "all",
        san_ms=san_ms,
        net_ms=net_ms,
        backup_ms=backup_ms,
    )
    return page


def render_dc_loading_page(
    dc_id: str,
    time_range,
    visible_sections=None,
    *,
    active_outer_tab: str | None = None,
) -> html.Div:
    """Phase A: header + tabs shell with loading skeleton (no blocking API)."""
    tr = time_range or default_time_range()
    dc_display, dc_loc = resolve_dc_display_from_summary(str(dc_id), tr)
    label = dc_display or str(dc_id or "Data Center").strip() or "Data Center"

    def _sec(code: str) -> bool:
        if visible_sections is None:
            return True
        return code in visible_sections

    show_summary = _sec("sec:dc_view:summary")
    tabs_order = [
        ("summary", show_summary),
        ("virt", _sec("sec:dc_view:virtualization")),
        ("storage", _sec("sec:dc_view:storage")),
        ("backup", _sec("sec:dc_view:backup")),
        ("phys-inv", _sec("sec:dc_view:phys_inv")),
        ("network", _sec("sec:dc_view:network")),
        ("avail", _sec("sec:dc_view:availability")),
    ]
    default_tab = "summary" if show_summary else "virt"
    resolved_tab = _resolve_outer_tab(active_outer_tab, tabs_order, default_tab)
    tabs = [
        dmc.TabsTab("Summary", value="summary") if show_summary else None,
        dmc.TabsTab("Virtualization", value="virt") if _sec("sec:dc_view:virtualization") else None,
        dmc.TabsTab("Storage", value="storage") if _sec("sec:dc_view:storage") else None,
        dmc.TabsTab("Backup & Replication", value="backup") if _sec("sec:dc_view:backup") else None,
        dmc.TabsTab("Physical Inventory", value="phys-inv") if _sec("sec:dc_view:phys_inv") else None,
        dmc.TabsTab("Network", value="network") if _sec("sec:dc_view:network") else None,
        dmc.TabsTab("Availability", value="avail") if _sec("sec:dc_view:availability") else None,
    ]
    loc_badge = dc_loc or "Loading…"
    shell_tab = resolved_tab if resolved_tab == "summary" else "summary"
    panels = [
        dmc.TabsPanel(
            value="summary",
            children=dmc.Stack(
                gap="lg",
                style={"padding": "0 30px"},
                children=[build_dc_loading_shell(label, tab=shell_tab)],
            ),
        ) if show_summary else None,
    ]
    for tab_key, ok in tabs_order:
        if not ok or tab_key == "summary":
            continue
        panels.append(
            dmc.TabsPanel(
                value=tab_key,
                children=_tab_lazy_placeholder(tab_key, label),
            )
        )
    return html.Div(
        className="dc-page-enter customer-page-enter",
        children=[
            dmc.Tabs(
                id="dc-main-tabs",
                color="indigo",
                variant="pills",
                radius="md",
                value=resolved_tab,
                children=[
                    create_detail_header(
                        title=label,
                        back_href="/datacenters",
                        back_label="Data Centers",
                        subtitle_badge=loc_badge,
                        subtitle_color="indigo",
                        time_range=tr,
                        icon="solar:server-square-bold-duotone",
                        tabs=dmc.TabsList(style={"paddingTop": "8px"}, children=tabs),
                    ),
                    *panels,
                ],
            ),
        ],
    )


def build_dc_view_layout_shell(dc_id, time_range=None, visible_sections=None):
    """Instant DC layout shell; Phase B callback fills dc-view-page-root."""
    if not dc_id:
        return html.Div("No Data Center ID provided", style={"padding": "20px"})
    tr = time_range or default_time_range()
    vs = visible_sections
    return html.Div(
        children=[
            dcc.Store(
                id="dc-view-visible-sections",
                data=sorted(vs) if vs is not None else None,
            ),
            dcc.Store(id="dc-view-dc-id", data=str(dc_id)),
            dcc.Store(id="dc-view-loaded-tabs", data=["summary"]),
            dcc.Store(id="dc-view-active-tab", data="summary"),
            dcc.Store(id="dc-view-context-store", data={}),
            html.Div(
                id="dc-view-page-root",
                children=render_dc_loading_page(str(dc_id), tr, visible_sections=vs),
            ),
        ],
    )


def layout(dc_id=None):
    return build_dc_view(dc_id, default_time_range())


@callback(
    Output("dc-export-download", "data"),
    Input("dc-export-csv", "n_clicks"),
    Input("dc-export-xlsx", "n_clicks"),
    State("dc-export-store", "data"),
    State("app-time-range", "data"),
    State("net-filters-store", "data"),
    prevent_initial_call=True,
)
def export_dc_detail(nc, nx, store, time_range, net_filters):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    tid = ctx.triggered[0]["prop_id"].split(".")[0]
    fmt_map = {"dc-export-csv": "csv", "dc-export-xlsx": "xlsx"}
    fmt = fmt_map.get(tid)
    if not fmt:
        return dash.no_update
    store = store or {}
    base = str(store.get("dc_name") or "dc_detail")
    extra = {
        "dc_code": store.get("dc_code", ""),
        "network_filters": net_filters,
    }
    sheets_raw = store.get("sheets")
    if not isinstance(sheets_raw, dict):
        sheets_raw = {}
    if not sheets_raw and store.get("rows"):
        sheets_raw = {"Legacy": store.get("rows") or []}

    sheet_order = [
        "Meta",
        "Classic_Metrics",
        "HyperConv_Metrics",
        "Power_Metrics",
        "Energy_Metrics",
        "Intel_Legacy",
        "Physical_Inventory",
        "Network_Interfaces",
        "Backup",
        "Legacy",
    ]
    dfs = {}
    for name in sheet_order:
        recs = sheets_raw.get(name)
        if recs:
            dfs[name] = records_to_dataframe(recs if isinstance(recs, list) else [])
    for name, recs in sheets_raw.items():
        if name not in dfs and isinstance(recs, list):
            dfs[name] = records_to_dataframe(recs)

    if fmt == "xlsx":
        content = dataframes_to_excel_with_meta(dfs, time_range, "DC_Detail", extra)
        return dash_send_excel_workbook(content, base)
    report_info = build_report_info_df(time_range, "DC_Detail", extra)
    sections = [(k, v) for k, v in dfs.items()]
    if not sections:
        sections = [("Data", records_to_dataframe([]))]
    csv_body = csv_bytes_with_report_header(report_info, sections)
    return dash_send_csv_bytes(csv_body, base)


@callback(
    Output({"type": "compute-gauge-util", "slug": MATCH}, "style"),
    Output({"type": "compute-gauge-alloc", "slug": MATCH}, "style"),
    Input({"type": "compute-gauge-mode", "slug": MATCH}, "value"),
)
def _toggle_compute_gauge_mode(mode):
    if mode == "allocation":
        return {"display": "none"}, {"display": "block"}
    return {"display": "block"}, {"display": "none"}
