"""CRM inventory report tables — grouped accordion / flat view for /crm/inventory-overview."""
from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import dash_table, dcc, html

from src.pages import crm_shared as shared

_ISSUE_STATUSES = frozenset({"over", "unsold_usage"})

_REPORT_COLUMNS = [
    {"name": "Service (CRM)", "id": "service_label"},
    {"name": "Unit", "id": "display_unit"},
    {"name": "Utilization", "id": "utilization_fmt"},
    {"name": "Total", "id": "total_fmt"},
    {"name": "CRM Sold", "id": "crm_sold_fmt"},
    {"name": "Used", "id": "used_fmt"},
    {"name": "Free", "id": "free_fmt"},
    {"name": "Sellable", "id": "sellable_fmt"},
    {"name": "Gap", "id": "gap_fmt"},
    {"name": "Status", "id": "status_label"},
    {"name": "Potential TL", "id": "potential_tl_fmt"},
]

_FLAT_EXTRA_COLUMN = {"name": "Family", "id": "family_label"}

_NUMERIC_COLS = {
    "total_fmt", "crm_sold_fmt", "used_fmt", "free_fmt",
    "sellable_fmt", "gap_fmt", "potential_tl_fmt",
}

_UNMAPPED_COLUMNS = [
    {"name": "Product", "id": "product_name"},
    {"name": "Unit", "id": "resource_unit"},
    {"name": "CRM Sold", "id": "entitled_qty"},
    {"name": "Amount TL", "id": "entitled_amount_tl"},
]

_TABLE_STYLE_CELL = {
    "fontSize": "12px",
    "fontFamily": "Inter, system-ui, sans-serif",
    "padding": "8px 10px",
    "textAlign": "left",
    "border": "none",
    "borderBottom": "1px solid #E9EDF7",
}
_TABLE_STYLE_HEADER = {
    "backgroundColor": "#F4F7FE",
    "color": "#2B3674",
    "fontWeight": "700",
    "border": "none",
    "borderBottom": "2px solid #E0E5F2",
    "position": "sticky",
    "top": 0,
    "zIndex": 1,
}
_STATUS_COLORS = {
    "ok": "#12B76A",
    "under": "#F79009",
    "over": "#F04438",
    "unsold_usage": "#F79009",
    "crm_only": "#7C3AED",
    "no_usage": "#98A2B3",
}
_ROW_ISSUE_STYLES = [
    {
        "if": {"filter_query": "{status} = over", "column_id": "status_label"},
        "backgroundColor": "#FFF4F4",
    },
    {
        "if": {"filter_query": "{status} = unsold_usage", "column_id": "status_label"},
        "backgroundColor": "#FFFAEB",
    },
    {
        "if": {"filter_query": "{status} = over"},
        "backgroundColor": "#FFFBFB",
    },
    {
        "if": {"filter_query": "{status} = unsold_usage"},
        "backgroundColor": "#FFFCF5",
    },
    {
        "if": {"filter_query": "{data_quality} = suspect", "column_id": "status_label"},
        "backgroundColor": "#FEF3F2",
        "color": "#B42318",
    },
]


def _fmt_qty(value: Any, unit: str) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.0f} {unit}".strip()
    except (TypeError, ValueError):
        return "—"


def _fmt_gap(delta: Any, unit: str) -> str:
    if delta is None:
        return "—"
    try:
        return f"{float(delta):+,.0f} {unit}".strip()
    except (TypeError, ValueError):
        return "—"


def prepare_service_row(row: dict[str, Any]) -> dict[str, Any]:
    unit = str(row.get("display_unit") or "")
    status = str(row.get("status") or "no_usage")
    data_quality = str(row.get("data_quality") or "")
    status_label = shared.inventory_status_label(status)
    if data_quality == "suspect":
        status_label = f"{status_label} · Check data"
    return {
        "panel_key": row.get("panel_key") or "",
        "service_label": row.get("service_label") or row.get("label") or "",
        "family_label": row.get("family_label") or row.get("family") or "",
        "display_unit": unit,
        "utilization_fmt": shared.utilization_summary(row.get("total"), row.get("used_qty")),
        "total_fmt": _fmt_qty(row.get("total"), unit),
        "crm_sold_fmt": _fmt_qty(row.get("crm_sold_qty"), unit),
        "used_fmt": _fmt_qty(row.get("used_qty"), unit),
        "free_fmt": _fmt_qty(row.get("free_qty"), unit),
        "sellable_fmt": _fmt_qty(row.get("sellable_qty"), unit),
        "gap_fmt": _fmt_gap(row.get("delta_used_vs_crm"), unit),
        "status": status,
        "status_label": status_label,
        "data_quality": data_quality,
        "potential_tl_fmt": shared.fmt_tl(row.get("potential_tl")),
        "crm_products_summary": row.get("crm_products_summary") or "",
        "infra_binding": row.get("infra_binding") or "",
        "has_infra_source": bool(row.get("has_infra_source")),
    }


def filter_service_rows(rows: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    mode = (mode or "all").lower()
    if mode == "infra":
        return [r for r in rows if r.get("has_infra_source")]
    if mode == "crm_only":
        return [r for r in rows if (r.get("infra_binding") or "") == "crm_only"]
    if mode == "issues":
        return [r for r in rows if str(r.get("status") or "") in _ISSUE_STATUSES]
    return list(rows)


def filter_by_search(rows: list[dict[str, Any]], query: str | None) -> list[dict[str, Any]]:
    q = (query or "").strip().lower()
    if not q:
        return list(rows)
    out: list[dict[str, Any]] = []
    for row in rows:
        haystack = " ".join([
            str(row.get("service_label") or ""),
            str(row.get("family_label") or row.get("family") or ""),
            str(row.get("crm_products_summary") or ""),
            str(row.get("panel_key") or ""),
        ]).lower()
        if q in haystack:
            out.append(row)
    return out


def _table_style_data_conditional() -> list[dict[str, Any]]:
    styles: list[dict[str, Any]] = list(_ROW_ISSUE_STYLES)
    for status, color in _STATUS_COLORS.items():
        styles.append({
            "if": {"filter_query": f"{{status}} = {status}", "column_id": "status_label"},
            "color": color,
            "fontWeight": "600",
        })
    for col in _NUMERIC_COLS:
        styles.append({
            "if": {"column_id": col},
            "textAlign": "right",
        })
    styles.append({
        "if": {"column_id": "utilization_fmt"},
        "fontFamily": "ui-monospace, monospace",
        "fontSize": "11px",
        "letterSpacing": "-0.02em",
    })
    return styles


def build_report_table(
    rows: list[dict[str, Any]],
    *,
    table_id: str,
    page_size: int = 15,
    include_family: bool = False,
) -> dash_table.DataTable:
    data = [prepare_service_row(r) for r in rows]
    columns = list(_REPORT_COLUMNS)
    if include_family:
        columns = [_FLAT_EXTRA_COLUMN, *columns]
    return dash_table.DataTable(
        id=table_id,
        data=data,
        columns=columns,
        page_size=page_size,
        filter_action="native",
        sort_action="native",
        sort_mode="multi",
        style_table={"overflowX": "auto", "borderRadius": "8px"},
        style_cell=_TABLE_STYLE_CELL,
        style_header=_TABLE_STYLE_HEADER,
        style_data_conditional=_table_style_data_conditional(),
    )


def build_unmapped_table(rows: list[dict[str, Any]], *, table_id: str) -> dash_table.DataTable:
    data = []
    for r in rows or []:
        data.append({
            "product_name": r.get("product_name") or r.get("productid") or "",
            "resource_unit": r.get("resource_unit") or "",
            "entitled_qty": r.get("entitled_qty"),
            "entitled_amount_tl": r.get("entitled_amount_tl"),
        })
    return dash_table.DataTable(
        id=table_id,
        data=data,
        columns=_UNMAPPED_COLUMNS,
        page_size=15,
        filter_action="native",
        sort_action="native",
        sort_mode="multi",
        style_table={"overflowX": "auto"},
        style_cell=_TABLE_STYLE_CELL,
        style_header=_TABLE_STYLE_HEADER,
    )


def _family_issue_count(panels: list[dict[str, Any]]) -> int:
    return sum(1 for p in panels if str(p.get("status") or "") in _ISSUE_STATUSES)


def _family_potential_tl(panels: list[dict[str, Any]]) -> float:
    return sum(float(p.get("potential_tl") or 0) for p in panels)


def build_family_accordion(
    families: list[dict[str, Any]],
    *,
    filter_mode: str = "all",
    search_query: str | None = None,
    id_prefix: str = "crm-inventory",
) -> dmc.Accordion | None:
    items: list[dmc.AccordionItem] = []
    idx = 0
    for fam in families or []:
        panels = fam.get("panels") or []
        filtered = filter_by_search(filter_service_rows(panels, filter_mode), search_query)
        if not filtered or filter_mode == "crm_only":
            continue
        title = str(fam.get("family_label") or fam.get("label") or fam.get("family") or "Services")
        issues = _family_issue_count(filtered)
        potential = _family_potential_tl(filtered)
        badges = [
            dmc.Badge(f"{len(filtered)} services", color="gray", variant="light", size="sm"),
            dmc.Badge(shared.fmt_tl(potential), color="indigo", variant="light", size="sm"),
        ]
        if issues:
            badges.append(dmc.Badge(f"{issues} issues", color="red", variant="light", size="sm"))
        items.append(
            dmc.AccordionItem(
                value=f"fam-{idx}",
                children=[
                    dmc.AccordionControl(
                        children=dmc.Group(gap="xs", wrap="wrap", children=[
                            dmc.Text(title, fw=600, size="sm"),
                            *badges,
                        ]),
                    ),
                    dmc.AccordionPanel(
                        children=build_report_table(
                            filtered,
                            table_id=f"{id_prefix}-family-{idx}",
                        ),
                    ),
                ],
            )
        )
        idx += 1
    if not items:
        return None
    default_open = [items[0].value] if items else []
    return dmc.Accordion(
        multiple=True,
        variant="separated",
        radius="md",
        value=default_open,
        children=items,
    )


def build_flat_view(
    payload: dict[str, Any],
    *,
    filter_mode: str = "all",
    search_query: str | None = None,
) -> dash_table.DataTable | dmc.Alert:
    rows = payload.get("panels") or []
    filtered = filter_by_search(filter_service_rows(rows, filter_mode), search_query)
    if filter_mode == "crm_only":
        filtered = [r for r in filtered if (r.get("infra_binding") or "") == "crm_only"]
    if not filtered:
        return _empty_alert()
    return build_report_table(
        filtered,
        table_id="crm-inventory-flat-table",
        page_size=25,
        include_family=True,
    )


def _empty_alert() -> dmc.Alert:
    return dmc.Alert(
        title="No rows match this filter",
        color="gray",
        variant="light",
        children=[
            dmc.Text("Try another filter or search term.", size="sm", mb="xs"),
            dmc.Group(gap="md", children=[
                dcc.Link("Infra sources settings", href="/settings/integrations/crm-infra-sources"),
                dcc.Link("CRM service mapping", href="/settings/integrations/crm-service-mapping"),
            ]),
        ],
    )


def build_crm_only_section(
    rows: list[dict[str, Any]],
    *,
    filter_mode: str = "all",
    search_query: str | None = None,
    table_id: str = "crm-inventory-crm-only",
) -> dmc.AccordionItem | None:
    if filter_mode not in ("all", "crm_only"):
        return None
    filtered = filter_service_rows(rows or [], "crm_only" if filter_mode == "crm_only" else "all")
    filtered = [r for r in filtered if (r.get("infra_binding") or "") == "crm_only"]
    filtered = filter_by_search(filtered, search_query)
    if not filtered:
        return None
    return dmc.AccordionItem(
        value="crm-only",
        children=[
            dmc.AccordionControl(
                children=dmc.Group(gap="xs", children=[
                    dmc.Text("CRM-only services", fw=600, size="sm"),
                    dmc.Badge(f"{len(filtered)}", color="grape", variant="light", size="sm"),
                ]),
            ),
            dmc.AccordionPanel(
                children=[
                    dmc.Text(
                        "Mapped CRM sales without infrastructure telemetry binding.",
                        size="xs", c="dimmed", mb="sm",
                    ),
                    build_report_table(filtered, table_id=table_id),
                ],
            ),
        ],
    )


def build_unmapped_section(
    products: list[dict[str, Any]],
    *,
    table_id: str = "crm-inventory-unmapped",
) -> dmc.AccordionItem | None:
    if not products:
        return None
    return dmc.AccordionItem(
        value="unmapped",
        children=[
            dmc.AccordionControl(
                children=dmc.Group(gap="xs", children=[
                    dmc.Text("Unmapped CRM products", fw=600, size="sm"),
                    dmc.Badge(f"{len(products)}", color="orange", variant="light", size="sm"),
                ]),
            ),
            dmc.AccordionPanel(
                children=[
                    dmc.Text(
                        "Entitled sales for catalog SKUs without panel mapping.",
                        size="xs", c="dimmed", mb="sm",
                    ),
                    build_unmapped_table(products, table_id=table_id),
                ],
            ),
        ],
    )


def build_report_body(
    payload: dict[str, Any],
    *,
    filter_mode: str = "all",
    search_query: str | None = None,
    view_mode: str = "grouped",
) -> list[Any]:
    """Assemble full report body from API payload."""
    families = payload.get("families") or []
    crm_only = payload.get("crm_only_panels") or []
    unmapped = payload.get("unmapped_products") or []
    summary = payload.get("summary") or {}
    mode = (filter_mode or "all").lower()
    view = (view_mode or "grouped").lower()

    body: list[Any] = []

    if mode == "issues":
        all_rows = payload.get("panels") or []
        issue_rows = filter_by_search(filter_service_rows(all_rows, "issues"), search_query)
        if issue_rows:
            body.append(
                dmc.Paper(
                    p="md",
                    radius="md",
                    withBorder=True,
                    mb="md",
                    children=[
                        dmc.Title("Compliance issues", order=5, mb="xs"),
                        dmc.Text(
                            f"{len(issue_rows)} service(s) with overage or unsold usage",
                            size="sm", c="dimmed", mb="sm",
                        ),
                        build_report_table(issue_rows, table_id="crm-inventory-issues"),
                    ],
                )
            )
        else:
            body.append(_empty_alert())
        return body

    if view == "flat":
        flat = build_flat_view(payload, filter_mode=mode, search_query=search_query)
        if isinstance(flat, dmc.Alert):
            body.append(flat)
        else:
            body.append(
                dmc.Paper(p="md", radius="md", withBorder=True, mb="md", children=[flat]),
            )
    else:
        accordion_items: list[Any] = []
        fam_accordion = build_family_accordion(
            families,
            filter_mode=mode,
            search_query=search_query,
        )
        if fam_accordion is not None:
            accordion_items.extend(fam_accordion.children or [])
        crm_item = build_crm_only_section(crm_only, filter_mode=mode, search_query=search_query)
        if crm_item is not None:
            accordion_items.append(crm_item)
        if mode == "all":
            unmapped_item = build_unmapped_section(unmapped)
            if unmapped_item is not None:
                accordion_items.append(unmapped_item)
        if accordion_items:
            body.append(
                dmc.Accordion(
                    multiple=True,
                    variant="separated",
                    radius="md",
                    value=[accordion_items[0].value],
                    children=accordion_items,
                )
            )
        else:
            body.append(_empty_alert())

    note = summary.get("note") or ""
    if note:
        body.append(
            dmc.Alert(
                title="Scope note",
                color="blue",
                variant="light",
                mt="md",
                icon=None,
                children=note,
            )
        )

    if not body:
        return [_empty_alert()]

    return body
