"""
CRM entitlement vs infrastructure usage comparison for virtualization services.

Entitlement baseline: active (statecode 0/1) + invoiced (3/4) order line quantities.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.utils.efficiency_usage import efficiency_status, resolve_used_quantity

# Phase 1 virtualization categories (page_key registry).
VIRT_COMPARISON_CATEGORIES: List[Dict[str, str]] = [
    {
        "category_code": "virt_hyperconverged_cpu",
        "category_label": "Hyperconverged Mimari — CPU",
        "resource_unit": "vCPU",
        "gui_tab_binding": "virtualization.hyperconverged",
        "catalog_product_name": "Hyperconverged Mimari Intel CPU",
    },
    {
        "category_code": "virt_hyperconverged_ram",
        "category_label": "Hyperconverged Mimari — RAM",
        "resource_unit": "GB",
        "gui_tab_binding": "virtualization.hyperconverged",
        "catalog_product_name": "Hyperconverged Mimari Intel RAM",
    },
    {
        "category_code": "virt_hyperconverged_storage",
        "category_label": "Hyperconverged Mimari — Storage",
        "resource_unit": "GB",
        "gui_tab_binding": "virtualization.hyperconverged",
        "catalog_product_name": "Hyperconverged Mimari Intel Disk - SSD Hybrid",
    },
    {
        "category_code": "virt_classic_cpu",
        "category_label": "Klasik Mimari (KM) — CPU",
        "resource_unit": "vCPU",
        "gui_tab_binding": "virtualization.classic",
        "catalog_product_name": "Klasik Mimari Intel CPU",
    },
    {
        "category_code": "virt_classic_ram",
        "category_label": "Klasik Mimari (KM) — RAM",
        "resource_unit": "GB",
        "gui_tab_binding": "virtualization.classic",
        "catalog_product_name": "Klasik Mimari Intel RAM",
    },
    {
        "category_code": "virt_classic_storage",
        "category_label": "Klasik Mimari (KM) — Storage",
        "resource_unit": "GB",
        "gui_tab_binding": "virtualization.classic",
        "catalog_product_name": "Klasik Mimari Intel Disk - SSD",
    },
]

_CATALOG_PRODUCT_NAMES = sorted(
    {str(c["catalog_product_name"]) for c in VIRT_COMPARISON_CATEGORIES}
)


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def normalize_entitled_qty(
    qty: float,
    uomid_name: str | None,
    target_unit: str,
) -> float:
    """Normalize CRM line quantity to the infra metric unit (GB or vCPU/Core)."""
    u = _norm(uomid_name)
    target = _norm(target_unit)
    value = float(qty or 0)

    if "tb" in u or "tib" in u:
        if target in ("gb", "gib"):
            return value * 1024.0
        return value

    if "mb" in u or "mib" in u:
        if target in ("gb", "gib"):
            return value / 1024.0
        return value

    return value


def _category_index() -> Dict[str, Dict[str, str]]:
    return {c["category_code"]: c for c in VIRT_COMPARISON_CATEGORIES}


def aggregate_entitled_by_category(
    entitled_raw: List[Dict[str, Any]],
    product_mapping: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Sum entitled quantities per virtualization page_key."""
    idx = _category_index()
    agg: Dict[str, Dict[str, Any]] = {}

    for row in entitled_raw or []:
        pid = str(row.get("productid") or "")
        m = product_mapping.get(pid) or {}
        cat_code = (m.get("category_code") if m else None) or ""
        if cat_code not in idx:
            continue

        meta = idx[cat_code]
        target_unit = meta["resource_unit"]
        ru = row.get("resource_unit") or m.get("resource_unit") or target_unit
        raw_qty = float(row.get("entitled_qty") or 0)
        norm_qty = normalize_entitled_qty(raw_qty, ru, target_unit)

        bucket = agg.setdefault(
            cat_code,
            {
                "category_code": cat_code,
                "category_label": meta["category_label"],
                "gui_tab_binding": meta["gui_tab_binding"],
                "resource_unit": target_unit,
                "entitled_qty": 0.0,
                "entitled_amount_tl": 0.0,
                "product_ids": set(),
            },
        )
        bucket["entitled_qty"] += norm_qty
        bucket["entitled_amount_tl"] += float(row.get("entitled_amount_tl") or 0)
        if pid:
            bucket["product_ids"].add(pid)

    for bucket in agg.values():
        bucket["product_ids"] = list(bucket["product_ids"])
    return agg


def aggregate_entitled_by_panel_key(
    entitled_raw: List[Dict[str, Any]],
    product_mapping: Dict[str, Dict[str, Any]],
    panel_units: Dict[str, str] | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Sum entitled quantities per panel_key (service mapping page_key)."""
    panel_units = panel_units or {}
    agg: Dict[str, Dict[str, Any]] = {}

    for row in entitled_raw or []:
        pid = str(row.get("productid") or "")
        m = product_mapping.get(pid) or {}
        if (m.get("source") or "") == "unmatched":
            continue
        panel_key = str((m.get("category_code") if m else None) or "").strip()
        if not panel_key:
            continue

        target_unit = (
            panel_units.get(panel_key)
            or m.get("resource_unit")
            or row.get("resource_unit")
            or "Adet"
        )
        ru = row.get("resource_unit") or m.get("resource_unit") or target_unit
        norm_qty = normalize_entitled_qty(
            float(row.get("entitled_qty") or 0),
            str(ru) if ru is not None else None,
            str(target_unit),
        )

        bucket = agg.setdefault(
            panel_key,
            {
                "panel_key": panel_key,
                "category_label": m.get("category_label") or panel_key,
                "resource_unit": str(target_unit),
                "entitled_qty": 0.0,
                "entitled_amount_tl": 0.0,
                "product_ids": set(),
                "product_names": set(),
            },
        )
        bucket["entitled_qty"] += norm_qty
        bucket["entitled_amount_tl"] += float(row.get("entitled_amount_tl") or 0)
        if pid:
            bucket["product_ids"].add(pid)
        pname = str(row.get("product_name") or "").strip()
        if pname:
            bucket["product_names"].add(pname)

    for bucket in agg.values():
        bucket["product_ids"] = list(bucket["product_ids"])
        bucket["product_names"] = sorted(bucket["product_names"])
    return agg


def resolve_unit_price_tl(
    *,
    category_code: str,
    product_ids: List[str],
    weighted_prices: Dict[str, float],
    price_overrides: Dict[str, float],
    catalog_by_productid: Dict[str, float],
    catalog_by_name: Dict[str, float],
) -> Tuple[float, str]:
    """Return (unit_price_tl, price_source)."""
    for pid in product_ids or []:
        if pid in weighted_prices and weighted_prices[pid]:
            return float(weighted_prices[pid]), "order_weighted"
        if pid in price_overrides:
            return float(price_overrides[pid]), "override"

    for pid in product_ids or []:
        if pid in catalog_by_productid and catalog_by_productid[pid]:
            return float(catalog_by_productid[pid]), "catalog"

    meta = _category_index().get(category_code) or {}
    name = meta.get("catalog_product_name") or ""
    if name and name in catalog_by_name:
        return float(catalog_by_name[name]), "catalog_name"

    return 0.0, "none"


def compliance_row_status(
    *,
    entitled_qty: float,
    used_qty: float,
    overage_qty: float,
    efficiency_pct: float | None,
    under_pct: float,
    over_pct: float,
) -> str:
    if entitled_qty <= 0 and used_qty > 0:
        return "unsold_usage"
    if entitled_qty <= 0 and used_qty <= 0:
        return "no_usage"
    if overage_qty > 0:
        return "over"
    return efficiency_status(
        efficiency_pct,
        entitled_qty,
        under_pct=under_pct,
        over_pct=over_pct,
        used_qty=used_qty,
    )


def panel_inventory_status_virt(
    *,
    crm_sold_qty: float,
    total_qty: float | None,
    has_infra_source: bool,
    under_pct: float = 80.0,
    over_pct: float = 110.0,
) -> str:
    """Inventory status for virtualization families (no infra Used column)."""
    if not has_infra_source and crm_sold_qty > 0:
        return "crm_only"
    if crm_sold_qty <= 0:
        return "no_usage"
    cap = float(total_qty or 0.0)
    if cap <= 0:
        return "no_usage"
    overage_qty = max(0.0, crm_sold_qty - cap)
    eff_pct = round((crm_sold_qty / cap) * 100.0, 2)
    return compliance_row_status(
        entitled_qty=cap,
        used_qty=crm_sold_qty,
        overage_qty=overage_qty,
        efficiency_pct=eff_pct,
        under_pct=under_pct,
        over_pct=over_pct,
    )


def panel_inventory_status(
    *,
    crm_sold_qty: float,
    used_qty: float,
    has_infra_source: bool,
    under_pct: float = 80.0,
    over_pct: float = 110.0,
) -> str:
    """Derive inventory overview status for one panel row."""
    if not has_infra_source and crm_sold_qty > 0:
        return "crm_only"
    if crm_sold_qty <= 0 and used_qty > 0:
        return "unsold_usage"
    eff_pct: float | None
    if crm_sold_qty > 0:
        eff_pct = round((used_qty / crm_sold_qty) * 100.0, 2)
    else:
        eff_pct = None
    overage_qty = max(0.0, used_qty - crm_sold_qty)
    return compliance_row_status(
        entitled_qty=crm_sold_qty,
        used_qty=used_qty,
        overage_qty=overage_qty,
        efficiency_pct=eff_pct,
        under_pct=under_pct,
        over_pct=over_pct,
    )


def build_virtualization_compliance(
    *,
    entitled_agg: Dict[str, Dict[str, Any]],
    assets: Dict[str, Any],
    totals: Dict[str, Any],
    weighted_prices: Dict[str, float],
    price_overrides: Dict[str, float],
    catalog_by_productid: Dict[str, float],
    catalog_by_name: Dict[str, float],
    under_pct: float = 80.0,
    over_pct: float = 110.0,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Build compliance rows for all phase-1 virtualization categories."""
    rows: List[Dict[str, Any]] = []

    for meta in VIRT_COMPARISON_CATEGORIES:
        cat_code = meta["category_code"]
        entitled_bucket = entitled_agg.get(cat_code) or {}
        entitled_qty = float(entitled_bucket.get("entitled_qty") or 0)
        product_ids = list(entitled_bucket.get("product_ids") or [])

        used_qty, note = resolve_used_quantity(
            category_code=cat_code,
            resource_unit=meta["resource_unit"],
            assets=assets,
            totals=totals,
        )
        used_qty = float(used_qty or 0)

        overage_qty = max(0.0, used_qty - entitled_qty)
        eff_pct: float | None
        if entitled_qty > 0:
            eff_pct = round((used_qty / entitled_qty) * 100.0, 2)
        else:
            eff_pct = None

        unit_price, price_source = resolve_unit_price_tl(
            category_code=cat_code,
            product_ids=product_ids,
            weighted_prices=weighted_prices,
            price_overrides=price_overrides,
            catalog_by_productid=catalog_by_productid,
            catalog_by_name=catalog_by_name,
        )
        overage_loss_tl = round(overage_qty * unit_price, 2)

        status = compliance_row_status(
            entitled_qty=entitled_qty,
            used_qty=used_qty,
            overage_qty=overage_qty,
            efficiency_pct=eff_pct,
            under_pct=under_pct,
            over_pct=over_pct,
        )

        rows.append({
            "category_code": cat_code,
            "category_label": entitled_bucket.get("category_label") or meta["category_label"],
            "gui_tab_binding": meta["gui_tab_binding"],
            "resource_unit": meta["resource_unit"],
            "entitled_qty": round(entitled_qty, 4),
            "entitled_amount_tl": round(float(entitled_bucket.get("entitled_amount_tl") or 0), 2),
            "used_qty": round(used_qty, 4),
            "overage_qty": round(overage_qty, 4),
            "unit_price_tl": round(unit_price, 4),
            "price_source": price_source,
            "overage_loss_tl": overage_loss_tl,
            "efficiency_pct": eff_pct,
            "status": status,
            "usage_note": note,
        })

    summary = summarize_compliance(rows)
    return rows, summary


def summarize_compliance(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    overuse_categories = [
        r["category_code"]
        for r in rows
        if r.get("status") in ("over", "unsold_usage")
    ]
    total_loss = round(sum(float(r.get("overage_loss_tl") or 0) for r in rows), 2)
    has_overuse = bool(overuse_categories)
    return {
        "total_overage_loss_tl": total_loss,
        "has_overuse": has_overuse,
        "overuse_categories": overuse_categories,
        "overuse_status": "overuse" if has_overuse else "ok",
    }


def derive_catalog_overuse_status(
    *,
    mapped: bool,
    has_infra_cache: bool,
    compliance_summary: Dict[str, Any] | None,
) -> str:
    if not mapped:
        return "not_applicable"
    if not has_infra_cache or compliance_summary is None:
        return "pending"
    return str(compliance_summary.get("overuse_status") or "ok")


def catalog_product_names_for_compliance() -> List[str]:
    return list(_CATALOG_PRODUCT_NAMES)


def group_entitled_by_customer(
    rows: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows or []:
        aid = str(row.get("crm_accountid") or "").strip()
        if not aid:
            continue
        out.setdefault(aid, []).append(row)
    return out


def group_weighted_prices_by_customer(
    rows: List[Dict[str, Any]],
) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for row in rows or []:
        aid = str(row.get("crm_accountid") or "").strip()
        pid = str(row.get("productid") or "")
        price = row.get("weighted_unit_price")
        if not aid or not pid or price is None:
            continue
        out.setdefault(aid, {})[pid] = float(price)
    return out


def build_catalog_price_by_name(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for row in rows or []:
        name = str(row.get("product_name") or "").strip()
        price = row.get("catalog_unit_price")
        if name and price is not None and name not in out:
            out[name] = float(price)
    return out


def build_lightweight_compliance_from_bundle(
    *,
    entitled_raw: List[Dict[str, Any]],
    product_mapping: Dict[str, Dict[str, Any]],
    assets: Dict[str, Any],
    totals: Dict[str, Any],
    weighted_prices: Dict[str, float],
    price_overrides: Dict[str, float],
    catalog_by_productid: Dict[str, float],
    catalog_by_name: Dict[str, float],
    under_pct: float = 80.0,
    over_pct: float = 110.0,
) -> Dict[str, Any]:
    """Single-customer compliance summary for catalog badge (cache-backed)."""
    entitled_agg = aggregate_entitled_by_category(entitled_raw, product_mapping)
    _, summary = build_virtualization_compliance(
        entitled_agg=entitled_agg,
        assets=assets or {},
        totals=totals or {},
        weighted_prices=weighted_prices,
        price_overrides=price_overrides,
        catalog_by_productid=catalog_by_productid,
        catalog_by_name=catalog_by_name,
        under_pct=under_pct,
        over_pct=over_pct,
    )
    return summary
