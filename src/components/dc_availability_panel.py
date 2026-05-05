"""Shared Availability tab UI (AuraNotify + product catalog) for DC detail and annual report."""

from __future__ import annotations

from dash import html
import dash_mantine_components as dmc

from src.services import product_catalog as product_catalog_service


def _aura_notify_raw_categories_table(categories: list) -> html.Table:
    """Fixed column layout so header cells align with body (avoids dmc.Table / thead tbody drift)."""
    border = "1px solid #e9ecef"
    th_style = {
        "padding": "10px 12px",
        "fontWeight": "600",
        "fontSize": "12px",
        "color": "#5c6b7a",
        "borderBottom": border,
        "backgroundColor": "#f8f9fb",
        "textTransform": "uppercase",
        "letterSpacing": "0.04em",
    }
    td_style = {
        "padding": "10px 12px",
        "fontSize": "13px",
        "color": "#2B3674",
        "borderBottom": border,
        "verticalAlign": "middle",
        "wordBreak": "break-word",
    }
    num_td = {**td_style, "fontVariantNumeric": "tabular-nums"}

    body_rows: list = []
    for cat in categories:
        if not isinstance(cat, dict):
            continue
        body_rows.append(
            html.Tr(
                [
                    html.Td(str(cat.get("category") or "-"), style={**td_style, "textAlign": "left"}),
                    html.Td(
                        f"{float(cat.get('availability_pct') or 0):.4f}",
                        style={**num_td, "textAlign": "right"},
                    ),
                    html.Td(str(cat.get("total_downtime_min") or "-"), style={**num_td, "textAlign": "right"}),
                    html.Td(str(cat.get("record_count") or "-"), style={**num_td, "textAlign": "right"}),
                ]
            )
        )

    if not body_rows:
        body_rows = [
            html.Tr(
                html.Td(
                    "No categories",
                    colSpan=4,
                    style={**td_style, "textAlign": "center", "color": "#A3AED0"},
                )
            )
        ]

    return html.Table(
        style={
            "width": "100%",
            "borderCollapse": "collapse",
            "tableLayout": "fixed",
        },
        children=[
            html.Colgroup(
                [
                    html.Col(style={"width": "42%"}),
                    html.Col(style={"width": "18%"}),
                    html.Col(style={"width": "22%"}),
                    html.Col(style={"width": "18%"}),
                ]
            ),
            html.Thead(
                html.Tr(
                    [
                        html.Th("Category", style={**th_style, "textAlign": "left"}),
                        html.Th("Availability %", style={**th_style, "textAlign": "right"}),
                        html.Th("Total downtime (min)", style={**th_style, "textAlign": "right"}),
                        html.Th("Records", style={**th_style, "textAlign": "right"}),
                    ]
                )
            ),
            html.Tbody(body_rows),
        ],
    )


def availability_downtime_table(downtimes: list):
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


def build_dc_availability_panel(
    item: dict | None,
    dc_display_name: str,
    *,
    period_label: str | None = None,
):
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
                                availability_downtime_table(dts),
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

    stack_children: list = [
        dmc.Text(f"DC: {dc_display_name}", size="sm", c="dimmed"),
    ]
    if period_label:
        stack_children.append(dmc.Text(period_label, size="xs", c="dimmed"))
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
                _aura_notify_raw_categories_table(categories),
            ],
        )
    )

    return dmc.Stack(gap="lg", children=stack_children)
