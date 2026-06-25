"""CRM inventory report tables — grouped family sections for /crm/inventory-overview."""
from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import dash_table, html

from src.pages import crm_shared as shared

_ISSUE_STATUSES = frozenset({"over", "unsold_usage"})

_REPORT_COLUMNS = [
    {"name": "Service (CRM)", "id": "service_label"},
    {"name": "Unit", "id": "display_unit"},
    {"name": "Total", "id": "total_fmt"},
    {"name": "CRM Sold", "id": "crm_sold_fmt"},
    {"name": "Used", "id": "used_fmt"},
    {"name": "Free", "id": "free_fmt"},
    {"name": "Sellable", "id": "sellable_fmt"},
    {"name": "Gap", "id": "gap_fmt"},
    {"name": "Status", "id": "status"},
    {"name": "Potential TL", "id": "potential_tl_fmt"},
]

_UNMAPPED_COLUMNS = [
    {"name": "Product", "id": "product_name"},
    {"name": "Unit", "id": "resource_unit"},
    {"name": "CRM Sold", "id": "entitled_qty"},
    {"name": "Amount TL", "id": "entitled_amount_tl"},
]

_TABLE_STYLE_CELL = {
    "fontSize": "12px",
    "fontFamily": "Inter, system-ui, sans-serif",
    "padding": "6px 8px",
    "textAlign": "left",
}
_TABLE_STYLE_HEADER = {
    "backgroundColor": "#F4F7FE",
    "color": "#2B3674",
    "fontWeight": "700",
    "border": "none",
}
_STATUS_COLORS = {
    "ok": "#12B76A",
    "under": "#F79009",
    "over": "#F04438",
    "unsold_usage": "#F79009",
    "crm_only": "#7C3AED",
    "no_usage": "#98A2B3",
}


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
    return {
        "panel_key": row.get("panel_key") or "",
        "service_label": row.get("service_label") or row.get("label") or "",
        "family_label": row.get("family_label") or row.get("family") or "",
        "display_unit": unit,
        "total_fmt": _fmt_qty(row.get("total"), unit),
        "crm_sold_fmt": _fmt_qty(row.get("crm_sold_qty"), unit),
        "used_fmt": _fmt_qty(row.get("used_qty"), unit),
        "free_fmt": _fmt_qty(row.get("free_qty"), unit),
        "sellable_fmt": _fmt_qty(row.get("sellable_qty"), unit),
        "gap_fmt": _fmt_gap(row.get("delta_used_vs_crm"), unit),
        "status": str(row.get("status") or "no_usage"),
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


def build_report_table(
    rows: list[dict[str, Any]],
    *,
    table_id: str,
    page_size: int = 15,
) -> dash_table.DataTable:
    data = [prepare_service_row(r) for r in rows]
    return dash_table.DataTable(
        id=table_id,
        data=data,
        columns=_REPORT_COLUMNS,
        page_size=page_size,
        filter_action="native",
        sort_action="native",
        sort_mode="multi",
        style_table={"overflowX": "auto"},
        style_cell=_TABLE_STYLE_CELL,
        style_header=_TABLE_STYLE_HEADER,
        style_data_conditional=[
            {
                "if": {"filter_query": f"{{status}} = {status}", "column_id": "status"},
                "color": color,
                "fontWeight": "600",
            }
            for status, color in _STATUS_COLORS.items()
        ],
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


def section_header(title: str, subtitle: str | None = None) -> html.Div:
    return html.Div([
        dmc.Title(title, order=4, mb="xs"),
        dmc.Text(subtitle or "", size="sm", c="dimmed", mb="sm") if subtitle else None,
    ])


def build_family_sections(
    families: list[dict[str, Any]],
    *,
    filter_mode: str = "all",
    id_prefix: str = "crm-inventory",
) -> list[Any]:
    """Render family-grouped report sections (no cards)."""
    sections: list[Any] = []
    idx = 0
    for fam in families or []:
        panels = fam.get("panels") or []
        filtered = filter_service_rows(panels, filter_mode)
        if not filtered:
            continue
        if filter_mode == "crm_only":
            continue
        title = str(fam.get("family_label") or fam.get("label") or fam.get("family") or "Services")
        subtitle = f"{len(filtered)} service(s)"
        if fam.get("has_infra"):
            subtitle += " · infrastructure bound"
        sections.append(
            dmc.Paper(
                p="md",
                radius="md",
                withBorder=True,
                mb="md",
                children=[
                    section_header(title, subtitle),
                    build_report_table(filtered, table_id=f"{id_prefix}-family-{idx}"),
                ],
            )
        )
        idx += 1
    return sections


def build_crm_only_section(
    rows: list[dict[str, Any]],
    *,
    filter_mode: str = "all",
    table_id: str = "crm-inventory-crm-only",
) -> html.Div | None:
    if filter_mode not in ("all", "crm_only"):
        return None
    filtered = filter_service_rows(rows or [], "crm_only" if filter_mode == "crm_only" else "all")
    filtered = [r for r in filtered if (r.get("infra_binding") or "") == "crm_only"]
    if not filtered:
        return None
    return dmc.Paper(
        p="md",
        radius="md",
        withBorder=True,
        mb="md",
        children=[
            section_header(
                "CRM-only services",
                "Mapped CRM sales without infrastructure telemetry binding.",
            ),
            build_report_table(filtered, table_id=table_id),
        ],
    )


def build_unmapped_section(
    products: list[dict[str, Any]],
    *,
    table_id: str = "crm-inventory-unmapped",
) -> html.Div | None:
    if not products:
        return None
    return dmc.Paper(
        p="md",
        radius="md",
        withBorder=True,
        mb="md",
        children=[
            section_header(
                "Unmapped CRM products",
                "Entitled sales for catalog SKUs without panel mapping.",
            ),
            build_unmapped_table(products, table_id=table_id),
        ],
    )


def build_report_body(
    payload: dict[str, Any],
    *,
    filter_mode: str = "all",
) -> list[Any]:
    """Assemble full report body from API payload."""
    families = payload.get("families") or []
    crm_only = payload.get("crm_only_panels") or []
    unmapped = payload.get("unmapped_products") or []
    mode = (filter_mode or "all").lower()

    body: list[Any] = []
    if mode == "issues":
        all_rows = payload.get("panels") or []
        issue_rows = filter_service_rows(all_rows, "issues")
        if issue_rows:
            body.append(
                dmc.Paper(
                    p="md",
                    radius="md",
                    withBorder=True,
                    mb="md",
                    children=[
                        section_header("Compliance issues", f"{len(issue_rows)} service(s) with overage or unsold usage"),
                        build_report_table(issue_rows, table_id="crm-inventory-issues"),
                    ],
                )
            )
        return body

    body.extend(build_family_sections(families, filter_mode=mode))
    crm_sec = build_crm_only_section(crm_only, filter_mode=mode)
    if crm_sec is not None:
        body.append(crm_sec)
    if mode == "all":
        unmapped_sec = build_unmapped_section(unmapped)
        if unmapped_sec is not None:
            body.append(unmapped_sec)
    if not body:
        body.append(
            dmc.Alert(
                title="No rows match this filter",
                color="gray",
                variant="light",
                children="Try another filter or verify CRM mappings and infra bindings.",
            )
        )
    return body
