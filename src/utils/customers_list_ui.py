"""Pure helpers for the /customers CRM catalog page (no Dash imports)."""
from __future__ import annotations

from typing import Any


OVERUSE_LABELS = {
    "pending": "Comparison pending",
    "not_applicable": "N/A",
    "ok": "Within limits",
    "overuse": "Overuse detected",
    "unknown": "Unknown",
}

MAPPING_STATUS_COLORS = {
    "configured": "teal",
    "seed": "blue",
    "empty": "gray",
}


def filter_catalog_rows(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    q = (query or "").strip().casefold()
    if not q:
        return list(rows or [])
    return [
        row
        for row in (rows or [])
        if q in str(row.get("crm_account_name") or "").casefold()
        or q in str(row.get("display_name") or "").casefold()
    ]


def paginate_rows(rows: list[dict[str, Any]], page: int, page_size: int) -> list[dict[str, Any]]:
    if page_size <= 0:
        return list(rows or [])
    start = max(0, int(page or 0)) * page_size
    end = start + page_size
    return list(rows or [])[start:end]


def page_count(total: int, page_size: int) -> int:
    if page_size <= 0 or total <= 0:
        return 1
    return max(1, (total + page_size - 1) // page_size)


def badge_color_for_mapping_status(status: str) -> str:
    return MAPPING_STATUS_COLORS.get(str(status or "").lower(), "gray")


def overuse_badge_props(status: str) -> tuple[str, str]:
    key = str(status or "unknown").lower()
    label = OVERUSE_LABELS.get(key, key.replace("_", " ").title())
    if key == "overuse":
        return label, "red"
    if key == "pending":
        return label, "orange"
    if key == "ok":
        return label, "teal"
    return label, "gray"


def format_revenue(amount: float | int | None, currency: str | None = None) -> str:
    value = float(amount or 0.0)
    cur = (currency or "TL").strip() or "TL"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M {cur}"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K {cur}"
    return f"{value:,.0f} {cur}"


def group_catalog_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    vip: list[dict[str, Any]] = []
    mapped: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    for row in rows or []:
        item = dict(row)
        if item.get("is_vip"):
            item["list_group"] = "vip"
            vip.append(item)
        elif item.get("mapped"):
            item["list_group"] = "mapped"
            mapped.append(item)
        else:
            item["list_group"] = "unmapped"
            unmapped.append(item)
    return {"vip": vip, "mapped": mapped, "unmapped": unmapped}


def apply_vip_toggle_local(store_data: dict[str, Any], account_id: str, is_vip: bool) -> dict[str, Any]:
    """Optimistic catalog store update after VIP toggle (no API round-trip)."""
    data = dict(store_data or {})
    customers = [dict(c) for c in (data.get("customers") or [])]
    overview = dict(data.get("overview") or {})
    target = str(account_id or "")
    for row in customers:
        if str(row.get("crm_accountid") or "") == target:
            row["is_vip"] = bool(is_vip)
            row["cache_pinned"] = bool(is_vip)
            break
    groups = group_catalog_rows(customers)
    overview.update(
        {
            "vip_count": len(groups["vip"]),
            "mapped_count": len(groups["mapped"]),
            "unmapped_count": len(groups["unmapped"]),
        }
    )
    return {
        "customers": customers,
        "groups": groups,
        "overview": overview,
    }
