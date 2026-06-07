"""Customer catalog and overview builders for the /customers GUI page."""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.db.queries import crm_sales as sq
from app.db.queries import customer as cq
from app.db.queries import service_mapping as smq
from app.services import cache_service as cache
from app.utils.service_sales_mapping import map_service_sales_lines
from app.utils.time_range import default_time_range

logger = logging.getLogger(__name__)


def _enabled_mapping_count(source_mappings: list[dict[str, Any]] | None) -> int:
    count = 0
    for row in source_mappings or []:
        if not row.get("enabled", True):
            continue
        if str(row.get("match_value") or "").strip():
            count += 1
    return count


def _mapping_status(source_mappings: list[dict[str, Any]] | None) -> str:
    mappings = source_mappings or []
    if not mappings:
        return "empty"
    if any(str(m.get("source") or "").lower() == "seed" for m in mappings):
        return "seed"
    if _enabled_mapping_count(mappings) > 0:
        return "configured"
    return "empty"


def _is_mapped(source_mappings: list[dict[str, Any]] | None) -> bool:
    return _enabled_mapping_count(source_mappings) > 0


def _real_data_cached(display_name: str) -> bool:
    tr = default_time_range()
    cache_key = f"customer_assets:{display_name}:{tr.get('start', '')}:{tr.get('end', '')}"
    try:
        return cache.get(cache_key) is not None
    except Exception:
        return False


def _overuse_status(*, mapped: bool, is_vip: bool) -> str:
    if not mapped:
        return "not_applicable"
    # Comparison engine not wired yet — surface pending for mapped/VIP rows.
    return "pending"


def build_catalog_row(
    *,
    crm_accountid: str,
    crm_account_name: str,
    source_mappings: list[dict[str, Any]] | None,
    is_vip: bool,
    cache_pinned: bool,
    ytd_revenue: float = 0.0,
    currency: Optional[str] = None,
) -> dict[str, Any]:
    mapped = _is_mapped(source_mappings)
    mapping_count = _enabled_mapping_count(source_mappings)
    status = _mapping_status(source_mappings)
    return {
        "crm_accountid": crm_accountid,
        "crm_account_name": crm_account_name,
        "display_name": crm_account_name,
        "is_vip": bool(is_vip),
        "cache_pinned": bool(cache_pinned),
        "mapped": mapped,
        "mapping_status": status,
        "mapping_count": mapping_count,
        "real_data_cached": _real_data_cached(crm_account_name) if mapped else False,
        "overuse_status": _overuse_status(mapped=mapped, is_vip=is_vip),
        "ytd_revenue": float(ytd_revenue or 0.0),
        "currency": currency,
        "list_group": "vip" if is_vip else ("mapped" if mapped else "unmapped"),
    }


def group_catalog_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    vip: list[dict[str, Any]] = []
    mapped: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    for row in rows:
        if row.get("is_vip"):
            vip.append(row)
        elif row.get("mapped"):
            mapped.append(row)
        else:
            unmapped.append(row)
    return {"vip": vip, "mapped": mapped, "unmapped": unmapped}


def build_overview_payload(
    *,
    catalog_rows: list[dict[str, Any]],
    sales_total: dict[str, Any],
    service_sales: list[dict[str, Any]],
) -> dict[str, Any]:
    groups = group_catalog_rows(catalog_rows)
    overuse_pending = sum(
        1
        for row in catalog_rows
        if row.get("mapped") and row.get("overuse_status") == "pending"
    )
    return {
        "total_customers": len(catalog_rows),
        "vip_count": len(groups["vip"]),
        "mapped_count": len(groups["mapped"]),
        "unmapped_count": len(groups["unmapped"]),
        "total_revenue": float(sales_total.get("total_revenue") or 0.0),
        "currency": sales_total.get("currency"),
        "order_count": int(sales_total.get("order_count") or 0),
        "service_sales": service_sales,
        "overuse_customer_count": overuse_pending,
        "overuse_status": "pending",
    }


def load_project_customer_rows(run_query, run_one) -> list[dict[str, Any]]:
    try:
        rows = run_query(cq.CRM_PROJECT_CUSTOMER_ROWS, ())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load CRM project customer rows: %s", exc)
        rows = []
    boyner = run_one(cq.CRM_BOYNER_ACCOUNT, ())
    if boyner and boyner.get("crm_accountid"):
        account_id = str(boyner["crm_accountid"])
        account_name = str(boyner.get("crm_account_name") or "").strip()
        if account_name and not any(str(r.get("crm_accountid")) == account_id for r in rows):
            rows.append({"crm_accountid": account_id, "crm_account_name": account_name})
    rows.sort(key=lambda r: str(r.get("crm_account_name") or "").casefold())
    return rows
