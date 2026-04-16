from __future__ import annotations
# DC Detail view - Capacity Planning
# Tab hierarchy: Summary | Virtualization (Classic / Hyperconverged / Power) | Backup | Physical Inventory
import json
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
    create_premium_gauge_chart,
    create_premium_gauge_with_avg,
    create_dual_line_chart,
    create_sparkline_chart,
)
from src.components.charts import create_horizontal_bar_chart, create_premium_horizontal_bar_chart, create_capacity_area_chart, create_grouped_bar_chart
from src.components.header import create_detail_header
from src.components.s3_panel import build_dc_s3_panel
from src.components.backup_panel import (
    build_netbackup_panel,
    build_zerto_panel,
    build_veeam_panel,
)
from src.services import sla_service
from src.services import product_catalog as product_catalog_service
from src.utils.dc_display import format_dc_display_name
from src.utils.export_helpers import (
    records_to_dataframe,
    build_report_info_df,
    dataframes_to_excel_with_meta,
    csv_bytes_with_report_header,
    dash_send_excel_workbook,
    dash_send_csv_bytes,
)


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


def _availability_downtime_table(downtimes: list):
    """Table for AuraNotify downtime dict rows."""
    rows_dt = []
    for d in downtimes or []:
        if not isinstance(d, dict):
            continue
        rows_dt.append(
            html.Tr(
                [
                    html.Td(str(d.get("start_time") or "-")),
                    html.Td(str(d.get("end_time") or "-")),
                    html.Td(str(d.get("duration_minutes") or "-")),
                    html.Td(str(d.get("reason") or "-")),
                    html.Td(str(d.get("senaryo") or "-")),
                    html.Td(str(d.get("outage_status") or "-")),
                    html.Td(str(d.get("service_impact") or "-")),
                    html.Td(str(d.get("dc_impact") or "-")),
                ]
            )
        )
    if not rows_dt:
        return dmc.Text("No rows", size="xs", c="dimmed")
    return dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=True,
        withColumnBorders=True,
        children=[
            html.Thead(
                html.Tr(
                    [
                        html.Th("Start"),
                        html.Th("End"),
                        html.Th("Duration (min)"),
                        html.Th("Reason"),
                        html.Th("Senaryo"),
                        html.Th("Outage"),
                        html.Th("Service impact"),
                        html.Th("DC impact"),
                    ]
                )
            ),
            html.Tbody(rows_dt),
        ],
    )


def _build_dc_availability_tab(item: dict | None, dc_display_name: str):
    """
    AuraNotify datacenter-services SLA plus full product-catalog service tree.

    Every Excel service is listed under its hierarchy; availability comes from the
    best-matching AuraNotify category, or 100%% when there is no match/outage data.
    """
    hierarchy = product_catalog_service.load_service_hierarchy()
    tree = product_catalog_service.nest_service_catalog(hierarchy)
    categories = (item.get("categories") or []) if item else []

    alerts = []
    if not item:
        alerts.append(
            dmc.Alert(
                "No matching AuraNotify datacenter group for this DC. "
                "Set AURANOTIFY_API_KEY or ANOTIFY_API_KEY and ensure `group_name` matches the DC name or code. "
                "Services below show 100% until a match exists.",
                color="yellow",
            )
        )
    if not hierarchy:
        alerts.append(
            dmc.Alert(
                "Product catalog not loaded (expected data/product_catalog.xlsx, sheet Ana Servis Kategorileri).",
                color="orange",
            )
        )

    pct = float(item.get("availability_pct") or 0.0) if item else 0.0
    period_min = item.get("period_min") if item else None
    total_dm = item.get("total_downtime_min") if item else None
    group_name = (item.get("group_name") or "—") if item else "—"

    main_items = []
    for mi, (main_title, subs) in enumerate(tree.items()):
        sub_acc_items = []
        for sj, (sub_title, services) in enumerate(subs.items()):
            service_blocks = []
            for svc_name in services:
                av_pct, matched = product_catalog_service.service_availability_pct(svc_name, categories)
                dts = (matched or {}).get("downtimes") or [] if matched else []
                matched_cat = (matched or {}).get("category") if matched else None
                downtime_min = (matched or {}).get("total_downtime_min") if matched else None
                badge_color = "teal" if av_pct >= 99.999 else "yellow" if av_pct >= 99.9 else "red"
                detail = []
                if matched_cat:
                    detail.append(
                        dmc.Text(f"AuraNotify category: {matched_cat}", size="xs", c="dimmed"),
                    )
                if dts:
                    detail.append(
                        dmc.Stack(
                            gap="xs",
                            mt="xs",
                            children=[
                                dmc.Text("Downtime records", size="xs", fw=600, c="#2B3674"),
                                _availability_downtime_table(dts),
                            ],
                        )
                    )
                paper_children = [
                    dmc.Group(
                        justify="space-between",
                        align="flex-start",
                        wrap="wrap",
                        children=[
                            dmc.Text(svc_name, size="sm", fw=600, style={"flex": "1 1 200px"}),
                            dmc.Group(
                                gap="xs",
                                align="center",
                                children=[
                                    dmc.Badge(f"{av_pct:.4f} %", color=badge_color, variant="light"),
                                    dmc.Text(
                                        f"{downtime_min} min" if downtime_min is not None else "—",
                                        size="xs",
                                        c="dimmed",
                                    ),
                                ],
                            ),
                        ],
                    ),
                ]
                if detail:
                    paper_children.append(dmc.Stack(gap=4, mt="xs", children=detail))
                service_blocks.append(
                    dmc.Paper(
                        withBorder=True,
                        p="sm",
                        radius="md",
                        mb="xs",
                        children=paper_children,
                    )
                )
            sub_acc_items.append(
                dmc.AccordionItem(
                    value=f"avail-m{mi}-s{sj}",
                    children=[
                        dmc.AccordionControl(
                            dmc.Text(sub_title, fw=600, size="sm", c="#2B3674"),
                        ),
                        dmc.AccordionPanel(
                            p="sm",
                            children=[dmc.Stack(gap="xs", children=service_blocks)],
                        ),
                    ],
                )
            )
        inner = (
            dmc.Accordion(
                multiple=True,
                variant="separated",
                radius="md",
                chevronPosition="right",
                children=sub_acc_items,
            )
            if sub_acc_items
            else dmc.Text("No sub-categories", size="sm", c="dimmed")
        )
        main_items.append(
            dmc.AccordionItem(
                value=f"avail-main-{mi}",
                children=[
                    dmc.AccordionControl(
                        dmc.Text(main_title, fw=700, size="sm", c="#2B3674"),
                    ),
                    dmc.AccordionPanel(p="sm", children=[inner]),
                ],
            )
        )

    hierarchy_section = html.Div(
        className="nexus-card",
        style={"padding": "24px", "overflowX": "auto"},
        children=[
            dmc.Text("Service availability (product catalog)", fw=700, size="lg", c="#2B3674", mb="xs"),
            dmc.Text(
                "All services from the product list hierarchy; values merge from AuraNotify when a category matches.",
                size="xs",
                c="dimmed",
                mb="md",
            ),
            dmc.Accordion(
                multiple=True,
                variant="separated",
                radius="md",
                chevronPosition="right",
                children=main_items,
            )
            if main_items
            else dmc.Text("No catalog entries.", c="dimmed"),
        ],
    )

    cat_rows = []
    for cat in categories:
        if not isinstance(cat, dict):
            continue
        cat_rows.append(
            html.Tr(
                [
                    html.Td(str(cat.get("category") or "-")),
                    html.Td(f"{float(cat.get('availability_pct') or 0):.4f}"),
                    html.Td(str(cat.get("total_downtime_min") or "-")),
                    html.Td(str(cat.get("record_count") or "-")),
                ]
            )
        )

    stack_children: list = [
        dmc.Text(f"DC: {dc_display_name}", size="sm", c="dimmed"),
    ]
    stack_children.extend(alerts)
    stack_children.append(
        dmc.SimpleGrid(
            cols=3,
            spacing="lg",
            children=[
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    radius="md",
                    children=[
                        dmc.Text("Overall availability", size="xs", c="dimmed", tt="uppercase"),
                        dmc.Text(f"{pct:.4f} %" if item else "—", fw=800, size="xl", c="#2B3674"),
                        dmc.Text(str(group_name), size="sm", c="dimmed"),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    radius="md",
                    children=[
                        dmc.Text("Period (minutes)", size="xs", c="dimmed"),
                        dmc.Text(str(period_min if period_min is not None else "—"), fw=700, size="lg"),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    radius="md",
                    children=[
                        dmc.Text("Total downtime (min)", size="xs", c="dimmed"),
                        dmc.Text(str(total_dm if total_dm is not None else "—"), fw=700, size="lg"),
                    ],
                ),
            ],
        )
    )
    stack_children.append(hierarchy_section)
    stack_children.append(
        html.Div(
            className="nexus-card nexus-table",
            style={"padding": "24px", "overflowX": "auto"},
            children=[
                dmc.Text("AuraNotify categories (raw)", fw=700, size="lg", c="#2B3674", mb="xs"),
                dmc.Table(
                    striped=True,
                    highlightOnHover=True,
                    children=[
                        html.Thead(
                            html.Tr(
                                [
                                    html.Th("Category"),
                                    html.Th("Availability %"),
                                    html.Th("Total downtime (min)"),
                                    html.Th("Records"),
                                ]
                            )
                        ),
                        html.Tbody(
                            cat_rows
                            if cat_rows
                            else [html.Tr([html.Td("No categories", colSpan=4)])],
                        ),
                    ],
                ),
            ],
        )
    )

    return dmc.Stack(gap="lg", children=stack_children)


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


def _kpi(title: str, value, icon: str, color: str = "indigo", is_text: bool = False, stagger: int = 1):
    """Standard KPI card used across all tabs."""
    return html.Div(
        className=f"nexus-card dc-kpi-card dc-stagger-{stagger}",
        style={
            "padding": "20px",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "space-between",
        },
        children=[
            html.Div([
                html.Span(
                    title,
                    style={
                        "color": "#A3AED0",
                        "fontSize": "0.82rem",
                        "fontWeight": 500,
                        "letterSpacing": "0.02em",
                        "textTransform": "uppercase",
                    },
                ),
                html.H3(
                    str(value),
                    style={
                        "color": "#2B3674",
                        "fontSize": "1.1rem" if is_text else "1.6rem",
                        "fontWeight": 900,
                        "margin": "6px 0 0 0",
                        "letterSpacing": "-0.02em",
                    },
                ),
            ]),
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


def _chart_card(graph_component):
    return html.Div(
        className="nexus-card dc-chart-card",
        style={
            "padding": "16px",
            "height": "250px",
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "justifyContent": "center",
            "overflow": "hidden",
        },
        children=graph_component,
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


def _capacity_metric_row(label: str, cap_val, used_val, pct: float, unit_fn=None):
    """Renders a capacity / allocated / utilisation trio inside a card row."""
    cap_str  = unit_fn(cap_val)  if unit_fn else str(cap_val)
    used_str = unit_fn(used_val) if unit_fn else str(used_val)
    pct_color = "#05CD99" if pct < 60 else "#FFB547" if pct < 80 else "#EE5D50"
    return html.Div(
        className="dc-capacity-row",
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "borderBottom": "1px solid #F4F7FE",
        },
        children=[
            html.Span(
                label,
                style={
                    "color": "#2B3674",
                    "fontWeight": 700,
                    "fontSize": "0.85rem",
                    "minWidth": "120px",
                },
            ),
            html.Span(f"Capacity: {cap_str}", style={"color": "#A3AED0", "fontSize": "0.8rem"}),
            html.Span(
                f"Allocated: {used_str}",
                style={"color": "#4318FF", "fontSize": "0.8rem", "fontWeight": 600},
            ),
            dmc.Badge(
                f"{pct:.1f}%",
                color="indigo" if pct < 60 else "yellow" if pct < 80 else "red",
                variant="light",
                size="sm",
                style={"minWidth": "60px", "textAlign": "center"},
            ),
            html.Div(
                style={
                    "width": "80px",
                    "height": "6px",
                    "borderRadius": "3px",
                    "background": "#EEF2FF",
                    "overflow": "hidden",
                    "marginLeft": "8px",
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
                        create_premium_gauge_with_avg(cpu_pct, cpu_pct_max, "CPU Usage (peak)", color="#4318FF")
                        if cpu_pct_max > 0
                        else create_premium_gauge_chart(cpu_pct, "CPU Usage", color="#4318FF")
                    ),
                    config={"displayModeBar": False},
                    style={"height": "100%", "width": "100%"},
                )),
                _chart_card(dcc.Graph(
                    figure=(
                        create_premium_gauge_with_avg(mem_pct, mem_pct_max, "RAM Usage (peak)", color="#05CD99")
                        if mem_pct_max > 0
                        else create_premium_gauge_chart(mem_pct, "RAM Usage", color="#05CD99")
                    ),
                    config={"displayModeBar": False},
                    style={"height": "100%", "width": "100%"},
                )),
                _chart_card(dcc.Graph(
                    figure=create_premium_gauge_chart(stor_pct, "Storage Usage", color="#FFB547"),
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
                                            figure=create_premium_gauge_chart(licensed_pct, "Pod License ROI", color="#4318FF"),
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
                                            figure=create_premium_gauge_chart(active_pct, "Active vs Licensed", color="#05CD99"),
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
                                            figure=create_premium_gauge_chart(available_pct, "Port Availability", color="#FFB547"),
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
                            figure=create_premium_gauge_chart(cpu_pct, "CPU Usage", color="#4318FF"),
                            config={"displayModeBar": False},
                            style={"height": "100%", "width": "100%"},
                        )),
                        _chart_card(dcc.Graph(
                            figure=create_premium_gauge_chart(mem_pct, "RAM Usage", color="#05CD99"),
                            config={"displayModeBar": False},
                            style={"height": "100%", "width": "100%"},
                        )),
                        _chart_card(dcc.Graph(
                            figure=create_premium_gauge_chart(stor_pct, "Storage Usage", color="#FFB547"),
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
                style={
                    "padding": "20px",
                    "background": "linear-gradient(135deg, rgba(139, 92, 246, 0.03) 0%, rgba(67, 24, 255, 0.03) 100%)",
                },
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
                        _kpi("IBM Power",  f"{energy.get('ibm_kw', 0):.1f} kW",      "material-symbols:power-rounded", color="orange", stagger=1),
                        _kpi("vCenter",    f"{energy.get('vcenter_kw', 0):.1f} kW",   "material-symbols:cloud", color="orange", stagger=2),
                        _kpi("Total",      f"{energy.get('total_kw', 0):.1f} kW",     "material-symbols:flash-on", color="orange", stagger=3),
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
                        _kpi("Total Devices", f"{total:,}", "solar:server-bold-duotone", color="indigo", stagger=1),
                        _kpi("Device Roles", f"{len(by_role):,}", "solar:widget-4-bold-duotone", color="violet", stagger=2),
                        _kpi("Top Role", title_case(by_role[0]["role"]) if by_role else "—", "solar:crown-bold-duotone", color="grape", is_text=True, stagger=3),
                        _kpi("Manufacturers", f"{len(set(r['manufacturer'] for r in by_rm)) if by_rm else 0}", "solar:buildings-bold-duotone", color="teal", stagger=4),
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
            _kpi("Total Devices", f"{device_count:,}", "solar:server-bold-duotone", color="indigo", stagger=1),
            _kpi("Active Ports", f"{active_ports:,}", "solar:signal-bold-duotone", color="indigo", stagger=2),
            _kpi("Total Ports", f"{total_ports:,}", "solar:port-bold-duotone", color="indigo", stagger=3),
            _kpi("Port Availability", f"{port_availability_pct:.1f}%", "solar:graph-bold-duotone", color="indigo", stagger=4),
        ],
    )

    # Donut charts (initial)
    donut_active = create_premium_gauge_chart(port_availability_pct, "Port Availability", color="#FFB547")
    donut_util = create_premium_gauge_chart(overall_util_pct, "Port Utilization", color="#05CD99")
    donut_icmp = create_premium_gauge_chart(icmp_availability_pct, "ICMP Availability", color="#4318FF")

    top_interfaces = percentile_data.get("top_interfaces") or []
    bar_labels = [(t.get("interface_name") or "").strip() or "Unknown" for t in top_interfaces]
    bar_values = [_bps_to_gbps(t.get("p95_total_bps")) for t in top_interfaces]
    bar_fig = create_premium_horizontal_bar_chart(
        labels=bar_labels,
        values=bar_values,
        title="Top 95th Percentile Interfaces (Gbps)",
        unit_suffix="Gbps",
        height=360,
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
        style_data_conditional=[
            {
                "if": {"state": "active"},
                "backgroundColor": "rgba(67, 24, 255, 0.04)",
                "border": "1px solid rgba(67, 24, 255, 0.1)",
            },
        ],
    )

    return dmc.Stack(
        gap="lg",
        children=[
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
                            style={"height": "100%", "width": "100%"},
                        )
                    ),
                    _chart_card(
                        dcc.Graph(
                            id="net-donut-utilization",
                            figure=donut_util,
                            config={"displayModeBar": False},
                            style={"height": "100%", "width": "100%"},
                        )
                    ),
                    _chart_card(
                        dcc.Graph(
                            id="net-donut-icmp",
                            figure=donut_icmp,
                            config={"displayModeBar": False},
                            style={"height": "100%", "width": "100%"},
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
    donut_total = create_premium_gauge_chart(100.0, f"Total {smart_storage(total_gb)}", color="#FFB547")
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

def build_dc_view(dc_id, time_range=None, visible_sections=None):
    """Build DC detail page for the given time range.

    visible_sections: optional set of permission codes (sec:/sub:/action:) the user may see.
    If None, all sections are shown (backward compatible).
    """
    if not dc_id:
        return html.Div("No Data Center ID provided", style={"padding": "20px"})

    def _sec(code: str) -> bool:
        if visible_sections is None:
            return True
        return code in visible_sections

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
    dc_loc = data["meta"]["location"]
    dc_desc = (data.get("meta") or {}).get("description") or ""
    dc_display = format_dc_display_name(dc_name, dc_desc)

    batch2 = parallel_execute(
        {
            "phys_inv": lambda: api.get_physical_inventory_dc(dc_name),
            "san_switches": lambda: api.get_dc_san_switches(dc_id, tr),
            "net_filters": lambda: api.get_dc_network_filters(dc_id, tr),
            "aura_dc": lambda: api.get_dc_availability_sla_item(str(dc_id), dc_name, tr),
        }
    )
    aura_dc_item = batch2.get("aura_dc")
    phys_inv = batch2["phys_inv"]
    has_phys_inv = phys_inv.get("total", 0) > 0

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
    header_right_extra = list(sla_badges or [])
    if _sec("action:dc_view:export"):
        header_right_extra.append(export_group)

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

    export_sheets = _build_dc_export_sheets(
        str(dc_id),
        data,
        phys_inv,
        net_interface_table,
        nb_data,
        zerto_data,
        veeam_data,
    )

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
    has_avail = True

    show_summary = has_summary and _sec("sec:dc_view:summary")
    show_virt = has_virt and _sec("sec:dc_view:virtualization")
    show_storage = has_storage and _sec("sec:dc_view:storage")
    show_backup = has_backup and _sec("sec:dc_view:backup")
    show_phys = has_phys_inv and _sec("sec:dc_view:phys_inv")
    show_network = (has_network or has_san) and _sec("sec:dc_view:network")
    show_avail = has_avail and _sec("sec:dc_view:availability")

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

    show_classic = has_classic and _sec("sub:dc_view:virt:classic")
    show_hyperconv = has_hyperconv and _sec("sub:dc_view:virt:hyperconv")
    show_power_inner = has_power and _sec("sub:dc_view:virt:power")
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

    return dcc.Loading(
        id="dc-view-page-loading",
        type="circle",
        color="#4318FF",
        delay_show=200,
        overlay_style={"visibility": "visible", "backgroundColor": "rgba(244, 247, 254, 0.75)"},
        children=html.Div([
        dcc.Store(id="net-filters-store", data=net_filters or {}),
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
            color="indigo",
            variant="pills",
            radius="md",
            value=default_outer_tab,
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
                        children=[_build_summary_tab(data, tr)],
                    ),
                ) if show_summary else None,

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
                                                    children=_build_compute_tab(classic, "Classic Compute", color="blue"),
                                                ),
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
                                                    children=_build_compute_tab(hyperconv, "Hyperconverged Compute", color="teal"),
                                                ),
                                            ],
                                        ),
                                    ) if show_hyperconv else None,
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
                                    ) if show_power_inner else None,
                                ],
                            ),
                        ],
                    ),
                ) if show_virt else None,

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
                ) if show_backup else None,

                # Physical Inventory
                dmc.TabsPanel(
                    value="phys-inv",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[_build_physical_inventory_dc_tab(phys_inv)],
                    ),
                ) if show_phys else None,
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
                ) if show_storage else None,

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
                ) if show_network else None,

                dmc.TabsPanel(
                    value="avail",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[_build_dc_availability_tab(aura_dc_item, dc_display)],
                    ),
                )
                if show_avail
                else None,
            ],
        )
    ]),
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
