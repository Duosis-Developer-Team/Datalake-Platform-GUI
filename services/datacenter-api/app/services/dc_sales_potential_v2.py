"""
Datacenter sales potential v2 — sellable-ceiling vs realized CRM sales (ADR-0010).

Sources:
  - Datalake DB: nutanix_cluster_metrics (capacity), discovery_crm_salesorder*
                  (sold quantities by raw productid), legacy
                  discovery_crm_productpricelevels (catalog fallback).
  - WebUI DB:    gui_crm_threshold_config (per-resource sellable ceiling),
                  gui_crm_customer_alias (NetBox tenant -> CRM accountid),
                  gui_crm_service_mapping_seed/override + service_pages
                  (productid -> category mapping),
                  gui_crm_price_override (operator-managed unit prices).

Application-layer joins replace the legacy v_gui_crm_product_mapping view.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from app.db.queries import crm_potential as crm_q

logger = logging.getLogger(__name__)

DEFAULT_SELLABLE_LIMIT_PCT = 80.0


def _get_threshold_dict(webui) -> Dict[str, float]:
    """Return {resource_type: sellable_limit_pct} from webui-db (fallback to defaults)."""
    if webui is None or not webui.is_available:
        return {}
    try:
        rows = webui.run_rows(
            """SELECT resource_type, sellable_limit_pct
               FROM   gui_crm_threshold_config
               WHERE  dc_code = '*'"""
        )
        return {r["resource_type"]: float(r["sellable_limit_pct"]) for r in rows}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load thresholds from webui-db: %s", exc)
        return {}


def _get_threshold_for(thresholds: Dict[str, float], resource_type: str) -> float:
    return float(thresholds.get(resource_type, DEFAULT_SELLABLE_LIMIT_PCT))


def _resource_view(total: float, sold: float, unit_price: float, ceiling_pct: float) -> Dict[str, Any]:
    if total and total > 0:
        sold_pct = min(100.0, max(0.0, sold / total * 100.0))
        rem_pct = max(0.0, ceiling_pct - sold_pct)
        rem_qty = rem_pct / 100.0 * total
    else:
        if sold > 0:
            sold_pct = 100.0
            rem_pct = 0.0
            rem_qty = 0.0
        else:
            sold_pct = 0.0
            rem_pct = ceiling_pct
            rem_qty = 0.0
    pot = rem_qty * float(unit_price or 0.0)
    return {
        "total_capacity": float(total or 0.0),
        "sold_qty": float(sold or 0.0),
        "sold_pct_of_ceiling": round(sold_pct, 2),
        "remaining_sellable_pct": round(rem_pct, 2),
        "remaining_sellable_qty": round(rem_qty, 4),
        "catalog_unit_price_tl": float(unit_price or 0.0),
        "potential_revenue_tl": round(pot, 2),
        "ceiling_pct": round(ceiling_pct, 2),
    }


def _resolve_account_ids_for_dc(cur, webui, dc_pattern: str) -> List[str]:
    """Resolve CRM accountids that map to NetBox tenants in this DC.

    Tenant values come from datalake (NetBox VMs); the lookup runs against the
    webui alias table. Cross-DB join is performed in Python.
    """
    cur.execute(crm_q.DC_TENANT_VALUES, (dc_pattern,))
    tenant_values = [(row[0] or "").strip().lower() for row in cur.fetchall() if row and row[0]]
    if not tenant_values or webui is None or not webui.is_available:
        return []
    try:
        rows = webui.run_rows(crm_q.WEBUI_ALIAS_ACCOUNTIDS_FOR_TENANTS, (tenant_values,))
        return [str(r["crm_accountid"]) for r in rows if r.get("crm_accountid")]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to resolve aliases from webui-db: %s", exc)
        return []


def _load_product_mapping(webui) -> Dict[str, Dict[str, Any]]:
    if webui is None or not webui.is_available:
        return {}
    try:
        rows = webui.run_rows(
            """SELECT
                   COALESCE(o.productid, s.productid) AS productid,
                   COALESCE(o.page_key, s.page_key, 'other') AS category_code,
                   pg.category_label,
                   pg.gui_tab_binding,
                   COALESCE(NULLIF(TRIM(pg.resource_unit), ''), 'Adet') AS resource_unit
               FROM       gui_crm_service_mapping_seed s
               FULL JOIN  gui_crm_service_mapping_override o ON o.productid = s.productid
               JOIN       gui_crm_service_pages pg
                      ON pg.page_key = COALESCE(o.page_key, s.page_key, 'other')"""
        )
        return {str(r["productid"]): r for r in rows if r.get("productid")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load product mapping from webui-db: %s", exc)
        return {}


def _load_price_overrides(webui) -> Dict[str, float]:
    if webui is None or not webui.is_available:
        return {}
    try:
        rows = webui.run_rows("SELECT productid, unit_price_tl FROM gui_crm_price_override")
        return {str(r["productid"]): float(r["unit_price_tl"] or 0) for r in rows}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load price overrides: %s", exc)
        return {}


def _resource_kind_from_unit(unit: Optional[str]) -> str:
    u = (unit or "").lower()
    if "vcpu" in u or u in ("core", "vcore", "cpu"):
        return "cpu"
    if "gb" in u or "ram" in u or "memory" in u or "tb" in u:
        return "ram"
    return "other"


def compute_sales_potential_v2(cur, dc_code: str, *, webui=None) -> Dict[str, Any]:
    """Compute v2 sales potential combining datalake + webui sources.

    Parameters
    ----------
    cur : datalake DB cursor
    dc_code : DC code (used as ILIKE pattern)
    webui : WebuiPool (datacenter-api). Falls back to defaults when absent.
    """
    dc_pattern = f"%{dc_code}%"

    thresholds = _get_threshold_dict(webui)
    cpu_ceil = _get_threshold_for(thresholds, "cpu")
    ram_ceil = _get_threshold_for(thresholds, "ram")
    storage_ceil = _get_threshold_for(thresholds, "storage")
    backup_ceil = _get_threshold_for(thresholds, "backup")
    rack_ceil = _get_threshold_for(thresholds, "rack_u")
    power_ceil = _get_threshold_for(thresholds, "power_kw")

    # Datalake-side capacity proxy
    cur.execute(crm_q.DC_NUTANIX_CLUSTER_CAPACITY, (dc_pattern,))
    cap = cur.fetchone() or (0.0, 0.0)
    total_cpu = float(cap[0] or 0.0)
    total_ram_gb = float(cap[1] or 0.0)

    # Resolve customer accountids in this DC via webui alias
    account_ids = _resolve_account_ids_for_dc(cur, webui, dc_pattern)

    # Sold totals — raw productid rows; mapping merged in Python below
    sold_rows: List[Dict[str, Any]] = []
    if account_ids:
        cur.execute(crm_q.DC_SOLD_RAW_BY_PRODUCT_FOR_DC, (account_ids,))
        cols = [d[0] for d in cur.description]
        sold_rows = [dict(zip(cols, row)) for row in cur.fetchall() or []]

    mapping = _load_product_mapping(webui)
    price_overrides = _load_price_overrides(webui)

    # Aggregate sold by category
    by_cat: Dict[tuple, Dict[str, Any]] = {}
    sold_vcpu = 0.0
    sold_ram_gb = 0.0
    for r in sold_rows:
        pid = str(r.get("productid") or "")
        m = mapping.get(pid)
        cat_code = m["category_code"] if m else "other"
        cat_label = m["category_label"] if m else "Other"
        tab = m["gui_tab_binding"] if m else "other"
        ru = r.get("resource_unit") or (m["resource_unit"] if m else "Adet")
        qty = float(r.get("sold_qty") or 0)
        amt = float(r.get("sold_amount_tl") or 0)
        # Track virt totals for capacity comparison
        kind = _resource_kind_from_unit(ru)
        if str(cat_code).startswith("virt"):
            if kind == "cpu":
                sold_vcpu += qty
            elif kind == "ram":
                sold_ram_gb += qty
        key = (cat_code, ru)
        bucket = by_cat.setdefault(key, {
            "category_code": cat_code,
            "category_label": cat_label,
            "gui_tab_binding": tab,
            "resource_unit": ru,
            "sold_qty": 0.0,
            "sold_amount_tl": 0.0,
        })
        bucket["sold_qty"] += qty
        bucket["sold_amount_tl"] += amt

    # Catalog unit prices: webui price_override > datalake catalog avg
    def _avg_for(unit_pattern: str) -> float:
        try:
            cur.execute(crm_q.DC_CATALOG_AVG_UNIT_PRICE, (unit_pattern,))
            row = cur.fetchone()
            return float((row or (0.0,))[0] or 0.0)
        except Exception:
            return 0.0

    # Pick a representative override: average of overrides whose product maps to virt + cpu/ram
    def _override_avg(kind: str) -> float:
        vals: list[float] = []
        for pid, price in price_overrides.items():
            m = mapping.get(pid)
            if not m:
                continue
            if not str(m.get("category_code") or "").startswith("virt"):
                continue
            ru_kind = _resource_kind_from_unit(m.get("resource_unit"))
            if ru_kind == kind:
                vals.append(float(price))
        return sum(vals) / len(vals) if vals else 0.0

    pr_cpu = _override_avg("cpu") or _avg_for("%vcpu%")
    pr_ram = _override_avg("ram") or _avg_for("%gb%")

    cpu_block = _resource_view(total_cpu, sold_vcpu, pr_cpu, cpu_ceil)
    ram_block = _resource_view(total_ram_gb, sold_ram_gb, pr_ram, ram_ceil)

    rem_cpu = cpu_block["remaining_sellable_pct"]
    rem_ram = ram_block["remaining_sellable_pct"]
    if total_cpu > 0 and total_ram_gb > 0:
        general_remaining_pct = round(min(rem_cpu, rem_ram), 2)
    elif total_cpu > 0:
        general_remaining_pct = round(rem_cpu, 2)
    elif total_ram_gb > 0:
        general_remaining_pct = round(rem_ram, 2)
    else:
        general_remaining_pct = round(min(rem_cpu, rem_ram), 2)

    total_potential_tl = float(cpu_block["potential_revenue_tl"]) + float(ram_block["potential_revenue_tl"])

    per_category: List[Dict[str, Any]] = []
    for rec in sorted(by_cat.values(), key=lambda x: -x["sold_amount_tl"]):
        cc = str(rec.get("category_code") or "").lower()
        rec["remaining_sellable_pct"] = general_remaining_pct if cc.startswith("virt") else None
        per_category.append(rec)

    return {
        "dc_code": dc_code,
        "sellable_limit_pct": cpu_ceil,  # primary headline ceiling
        "general_remaining_pct": general_remaining_pct,
        "potential_revenue_tl": round(total_potential_tl, 2),
        "thresholds": {
            "cpu": cpu_ceil,
            "ram": ram_ceil,
            "storage": storage_ceil,
            "backup": backup_ceil,
            "rack_u": rack_ceil,
            "power_kw": power_ceil,
        },
        "per_resource": {
            "cpu": cpu_block,
            "ram": ram_block,
            "storage": {
                "total_capacity": 0.0,
                "sold_qty": 0.0,
                "remaining_sellable_pct": None,
                "catalog_unit_price_tl": 0.0,
                "potential_revenue_tl": 0.0,
                "ceiling_pct": storage_ceil,
            },
            "backup_gb": {
                "total_capacity": 0.0,
                "sold_qty": 0.0,
                "remaining_sellable_pct": None,
                "catalog_unit_price_tl": 0.0,
                "potential_revenue_tl": 0.0,
                "ceiling_pct": backup_ceil,
            },
            "rack_u": {
                "total_capacity": 0.0,
                "sold_qty": 0.0,
                "remaining_sellable_pct": None,
                "catalog_unit_price_tl": 0.0,
                "potential_revenue_tl": 0.0,
                "ceiling_pct": rack_ceil,
            },
            "power_kw": {
                "total_capacity": 0.0,
                "sold_qty": 0.0,
                "remaining_sellable_pct": None,
                "catalog_unit_price_tl": 0.0,
                "potential_revenue_tl": 0.0,
                "ceiling_pct": power_ceil,
            },
        },
        "per_category": per_category,
        "resolved_account_ids": account_ids,
    }


def compute_dc_summary(cur, dc_code: str, account_ids: Iterable[str]) -> Dict[str, Any]:
    """Datalake-side YTD billing summary for a DC's resolved customers."""
    dc_pattern = f"%{dc_code}%"  # noqa: F841 — kept for parity with v1 caller signature
    ids = list(account_ids)
    cur.execute(crm_q.DC_POTENTIAL_SUMMARY, (ids, dc_code, ids))
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    return dict(zip(cols, row)) if row else {}
