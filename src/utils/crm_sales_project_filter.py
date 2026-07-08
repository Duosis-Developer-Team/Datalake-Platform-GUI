"""Pure helpers for project (PRJ-*) scoping of Customer View CRM sales data.

A customer's CRM sales orders each carry a project reference (`reference_number`,
e.g. "PRJ-01227-R1M9G0"). These helpers let the Customer View filter the whole
CRM sales set — summary, active orders, line items — to a single project, fully
client-side (the sales payloads already carry reference_number + date + amounts,
so no backend/query change is needed).
"""
from __future__ import annotations

from typing import Any

ALL_PROJECTS = "__all__"


def _ref(row: dict[str, Any]) -> str:
    return str((row or {}).get("reference_number") or "").strip()


def _is_all(project: str | None) -> bool:
    return not project or project == ALL_PROJECTS


def project_select_options(*row_lists: list[dict] | None) -> list[dict[str, str]]:
    """Build dropdown options from every reference_number seen across the payloads.

    Returns [{"All projects"}, {ref}, ...] with refs sorted ascending.
    """
    refs: set[str] = set()
    for rows in row_lists:
        for row in rows or []:
            ref = _ref(row)
            if ref:
                refs.add(ref)
    options = [{"label": "All projects", "value": ALL_PROJECTS}]
    options.extend({"label": ref, "value": ref} for ref in sorted(refs))
    return options


def filter_by_project(rows: list[dict] | None, project: str | None) -> list[dict]:
    """Rows whose reference_number matches the project; all rows when ALL/empty."""
    if _is_all(project):
        return list(rows or [])
    return [row for row in (rows or []) if _ref(row) == project]


def _sum(rows: list[dict], key: str) -> float:
    total = 0.0
    for row in rows:
        try:
            total += float(row.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return total


def _year(row: dict[str, Any]) -> str:
    return str(row.get("date") or "")[:4]


def recompute_summary_for_project(
    base_summary: dict | None,
    *,
    active_orders: list[dict] | None,
    sales_items: list[dict] | None,
    project: str | None,
    current_year: int,
) -> dict[str, Any]:
    """Return a sales-summary dict scoped to one project.

    ALL/empty project returns the base summary unchanged. For a concrete project,
    revenue/order/value fields are recomputed from the project's own active order
    headers (order_total) and realized line items (line_total). List-derived
    counts (service categories, line-item counts) are handled by the caller
    passing already-filtered lists to the panel builder.
    """
    base = dict(base_summary or {})
    if _is_all(project):
        return base

    year = str(current_year)
    proj_active_orders = filter_by_project(active_orders, project)
    proj_realized = filter_by_project(sales_items, project)
    ytd_realized = [r for r in proj_realized if _year(r) == year]

    base["ytd_revenue_total"] = _sum(ytd_realized, "line_total")
    base["lifetime_revenue_total"] = _sum(proj_realized, "line_total")
    base["invoice_count"] = len({_ref(r) for r in ytd_realized if _ref(r)})
    base["lifetime_order_count"] = len({_ref(r) for r in proj_realized if _ref(r)})
    base["active_order_count"] = len({_ref(r) for r in proj_active_orders if _ref(r)})
    base["active_order_value"] = _sum(proj_active_orders, "order_total")
    return base
