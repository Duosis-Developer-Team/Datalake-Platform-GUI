"""
Sales data service — bridges datalake DB (raw CRM rows) and webui DB (operator
configuration). Replaces the previous single-DB design that required cross-DB
joins on `discovery_crm_customer_alias` and `v_gui_crm_product_mapping`.

Flow:
    1. Resolve customer name -> CRM accountid list via webui-db (gui_crm_customer_alias).
    2. Load product->page mapping dict from webui-db (cached).
    3. Run datalake-side aggregation queries with `customerid = ANY(%s)`.
    4. Enrich rows in Python using the mapping and price-override dicts.

All methods return plain dicts/lists; pydantic validation happens at the router layer.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.db.queries import crm_sales as sq
from app.db.queries import service_mapping as smq
from app.utils.efficiency_usage import efficiency_status, resolve_used_quantity
from app.services.crm_config_service import CrmConfigService
from app.services.webui_db import WebuiPool

logger = logging.getLogger(__name__)


class SalesService:
    """CRM sales queries spanning datalake + webui DBs."""

    def __init__(
        self,
        get_connection,
        run_row,
        run_rows,
        get_customer_assets=None,
        webui: Optional[WebuiPool] = None,
    ):
        self._get_connection = get_connection
        self._run_row = run_row
        self._run_rows = run_rows
        self._get_customer_assets = get_customer_assets
        self._webui = webui
        self._config = CrmConfigService(webui) if webui is not None else None

    # ------------------------------------------------------------------
    # Datalake helpers
    # ------------------------------------------------------------------

    def _run_query(self, sql: str, params: tuple) -> List[Dict[str, Any]]:
        """Execute a SELECT against the datalake DB and return list of column-name dicts."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                t0 = time.perf_counter()
                cur.execute(sql, params)
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                elapsed = (time.perf_counter() - t0) * 1000
                logger.info("CRM datalake SQL (%.0fms): %s rows", elapsed, len(rows))
                return [dict(zip(cols, row)) for row in rows]

    def _run_one(self, sql: str, params: tuple) -> Optional[Dict[str, Any]]:
        rows = self._run_query(sql, params)
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # Webui-side helpers (alias resolution and mapping cache)
    # ------------------------------------------------------------------

    def _resolve_account_ids(self, customer_name: str) -> List[str]:
        """Resolve a customer display name -> list of CRM accountids via webui alias table."""
        if not self._webui or not self._webui.is_available:
            logger.warning("WebUI pool unavailable; alias resolution returns empty list.")
            return []
        rows = self._webui.run_rows(
            smq.RESOLVE_ALIAS_BY_NAME,
            (customer_name, f"%{customer_name}%"),
        )
        return [str(r["crm_accountid"]) for r in rows if r.get("crm_accountid")]

    def _load_product_mapping(self) -> Dict[str, Dict[str, Any]]:
        """Return productid -> {category_code, category_label, gui_tab_binding, resource_unit, source}."""
        if not self._webui or not self._webui.is_available:
            return {}
        rows = self._webui.run_rows(smq.LIST_SERVICE_MAPPINGS_WEBUI)
        return {str(r["productid"]): r for r in rows if r.get("productid")}

    def _load_price_override_dict(self) -> Dict[str, float]:
        if not self._config:
            return {}
        return {str(r["productid"]): float(r["unit_price_tl"]) for r in self._config.list_price_overrides()}

    # ------------------------------------------------------------------
    # /customers/{name}/sales/summary
    # ------------------------------------------------------------------

    def _empty_summary(self) -> Dict[str, Any]:
        return {
            "ytd_revenue_total": 0.0,
            "invoice_count": 0,
            "ytd_order_count": 0,
            "currency": None,
            "pipeline_value": 0.0,
            "opportunity_count": 0,
            "active_order_count": 0,
            "active_order_value": 0.0,
            "active_contract_count": 0,
            "total_contract_value": 0.0,
            "estimated_mrr": 0.0,
        }

    def get_sales_summary(self, customer_name: str) -> Dict[str, Any]:
        account_ids = self._resolve_account_ids(customer_name)
        if not account_ids:
            return self._empty_summary()
        row = self._run_one(sq.SALES_SUMMARY, (account_ids, account_ids))
        if row is None:
            return self._empty_summary()
        out = {
            k: (
                float(v)
                if v is not None
                and k
                not in (
                    "currency",
                    "invoice_count",
                    "ytd_order_count",
                    "opportunity_count",
                    "active_order_count",
                    "active_contract_count",
                )
                else v
            )
            for k, v in row.items()
        }
        if "invoice_count" not in out and out.get("ytd_order_count") is not None:
            out["invoice_count"] = int(out["ytd_order_count"] or 0)
        if "invoice_count" in out and out["invoice_count"] is not None:
            out["invoice_count"] = int(out["invoice_count"])
        return out

    # ------------------------------------------------------------------
    # /customers/{name}/sales/items
    # ------------------------------------------------------------------

    def get_sales_items(self, customer_name: str) -> List[Dict[str, Any]]:
        account_ids = self._resolve_account_ids(customer_name)
        if not account_ids:
            return []
        return self._run_query(sq.SALES_ITEMS, (account_ids,))

    # ------------------------------------------------------------------
    # /customers/{name}/sales/efficiency
    # ------------------------------------------------------------------

    def get_sales_efficiency(self, customer_name: str) -> List[Dict[str, Any]]:
        account_ids = self._resolve_account_ids(customer_name)
        if not account_ids:
            return []
        billed = self._run_query(sq.SALES_EFFICIENCY_BILLED, (account_ids,))
        price_overrides = self._load_price_override_dict()
        # Catalog fallback (often empty in production until productpricelevels lands).
        catalog: Dict[str, Dict[str, Any]] = {}
        try:
            for row in self._run_query(sq.SALES_CATALOG_PRICES, ()):
                key = str(row.get("productid"))
                if key and key not in catalog:
                    catalog[key] = row
        except Exception as exc:  # noqa: BLE001
            logger.info("Catalog price fallback unavailable: %s", exc)
        out: List[Dict[str, Any]] = []
        for r in billed:
            pid = str(r.get("productid"))
            override = price_overrides.get(pid)
            cat_row = catalog.get(pid) or {}
            unit_price = override if override is not None else cat_row.get("catalog_unit_price")
            qty = float(r.get("total_billed_qty") or 0)
            amt = float(r.get("total_billed_amount") or 0)
            coverage = None
            if unit_price and qty > 0:
                coverage = round((amt / (qty * float(unit_price)) * 100.0), 2)
            out.append({
                "product_name": r.get("product_name"),
                "unit": r.get("unit"),
                "total_billed_qty": qty,
                "total_billed_amount": amt,
                "currency": r.get("currency"),
                "catalog_unit_price": float(unit_price) if unit_price is not None else None,
                "price_list": "override" if override is not None else cat_row.get("price_list"),
                "catalog_coverage_pct": coverage,
            })
        return out

    # ------------------------------------------------------------------
    # /customers/{name}/sales/efficiency-by-category
    # ------------------------------------------------------------------

    def get_efficiency_by_category(self, customer_name: str) -> List[Dict[str, Any]]:
        account_ids = self._resolve_account_ids(customer_name)
        if not account_ids:
            return []

        sold_raw = self._run_query(sq.SALES_SOLD_RAW_BY_PRODUCT, (account_ids,))
        mapping = self._load_product_mapping()
        calc = self._config.get_calc_dict() if self._config else {}
        under_pct = float(calc.get("efficiency.under_pct", 80.0))
        over_pct = float(calc.get("efficiency.over_pct", 110.0))
        alloc_cap = float(calc.get("efficiency.alloc_cap_pct", 150.0))

        # Aggregate datalake rows by mapped category_code/resource_unit.
        # Products without a seed/override row (or with NULL page_key after the LEFT JOIN
        # in LIST_SERVICE_MAPPINGS_WEBUI) are bucketed under 'unmatched' so the operator
        # UI can highlight pending mappings without losing revenue figures.
        agg: Dict[tuple, Dict[str, Any]] = {}
        for row in sold_raw:
            pid = str(row.get("productid") or "")
            m = mapping.get(pid)
            cat_code = (m.get("category_code") if m else None) or "unmatched"
            cat_label = (m.get("category_label") if m else None) or "Unmatched"
            tab = (m.get("gui_tab_binding") if m else None) or "unmatched"
            ru = row.get("resource_unit") or (m.get("resource_unit") if m else None) or "Adet"
            key = (cat_code, ru)
            bucket = agg.setdefault(key, {
                "category_code": cat_code,
                "category_label": cat_label,
                "gui_tab_binding": tab,
                "resource_unit": ru,
                "sold_qty": 0.0,
                "sold_amount_tl": 0.0,
            })
            bucket["sold_qty"] += float(row.get("sold_qty") or 0)
            bucket["sold_amount_tl"] += float(row.get("sold_amount_tl") or 0)

        # Pull live usage bundle
        bundle: Dict[str, Any] = {}
        if self._get_customer_assets:
            try:
                bundle = self._get_customer_assets(customer_name) or {}
            except Exception as exc:  # noqa: BLE001
                logger.warning("get_customer_assets failed: %s", exc)
                bundle = {}
        assets = bundle.get("assets") or {}
        totals = bundle.get("totals") or {}

        out: List[Dict[str, Any]] = []
        for r in sorted(agg.values(), key=lambda x: -x["sold_amount_tl"]):
            sold_qty = r["sold_qty"]
            used_qty, note = resolve_used_quantity(
                category_code=r["category_code"],
                resource_unit=r["resource_unit"],
                assets=assets,
                totals=totals,
            )
            eff_pct: float | None
            if sold_qty > 0:
                eff_pct = round((used_qty / sold_qty) * 100.0, 2)
            else:
                eff_pct = None
            alloc_pct: float | None
            if sold_qty > 0:
                alloc_pct = round(min(alloc_cap, (used_qty / sold_qty) * 100.0), 2)
            else:
                alloc_pct = None
            out.append({
                "category_code": r["category_code"],
                "category_label": r["category_label"],
                "gui_tab_binding": r["gui_tab_binding"],
                "resource_unit": r["resource_unit"],
                "sold_qty": sold_qty,
                "sold_amount_tl": r["sold_amount_tl"],
                "used_qty": used_qty,
                "efficiency_pct": eff_pct,
                "allocated_vs_sold_pct": alloc_pct,
                "delta_qty": (used_qty - sold_qty) if sold_qty or used_qty else 0.0,
                "status": efficiency_status(eff_pct, sold_qty, under_pct=under_pct, over_pct=over_pct),
                "usage_note": note,
            })
        return out

    # ------------------------------------------------------------------
    # /customers/{name}/sales/catalog-valuation — gui_crm_price_override + catalog
    # ------------------------------------------------------------------

    def get_catalog_valuation(self, customer_name: str) -> List[Dict[str, Any]]:
        # We no longer scope by customer alias here: catalog is global. The customer_name
        # argument is preserved for backward compatibility and reserved for future
        # tenant-specific price lists.
        del customer_name
        overrides = self._config.list_price_overrides() if self._config else []
        rows: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for r in overrides:
            pid = str(r.get("productid"))
            seen.add(pid)
            rows.append({
                "product_name": r.get("product_name"),
                "unit": r.get("resource_unit"),
                "unit_price_tl": float(r.get("unit_price_tl") or 0),
                "valuation_type": "override",
            })
        # Fallback to discovery_crm_productpricelevels for any product without an override
        try:
            for r in self._run_query(sq.SALES_CATALOG_PRICES, ()):
                pid = str(r.get("productid"))
                if pid in seen:
                    continue
                if not r.get("price_list") or "TL" not in str(r.get("price_list")).upper():
                    continue
                rows.append({
                    "product_name": r.get("product_name"),
                    "unit": r.get("unit"),
                    "unit_price_tl": float(r.get("catalog_unit_price") or 0),
                    "valuation_type": "catalog",
                })
        except Exception as exc:  # noqa: BLE001
            logger.info("Catalog price fallback skipped: %s", exc)
        rows.sort(key=lambda x: (x.get("product_name") or "").lower())
        return rows

    # ------------------------------------------------------------------
    # Customer alias management (now backed by webui-db)
    # ------------------------------------------------------------------

    def get_all_aliases(self) -> List[Dict[str, Any]]:
        if not self._webui or not self._webui.is_available:
            return []
        return self._webui.run_rows(smq.GET_ALL_ALIASES)

    def upsert_alias(
        self,
        crm_accountid: str,
        crm_account_name: str,
        canonical_key: Optional[str],
        netbox_value: Optional[str],
        notes: Optional[str],
    ) -> None:
        if not self._webui:
            raise RuntimeError("WebUI pool not configured")
        self._webui.execute(
            smq.UPSERT_ALIAS,
            (crm_accountid, crm_account_name, canonical_key, netbox_value, notes),
        )

    def delete_alias(self, crm_accountid: str) -> int:
        if not self._webui:
            raise RuntimeError("WebUI pool not configured")
        return self._webui.execute(smq.DELETE_ALIAS, (crm_accountid,))

    # ------------------------------------------------------------------
    # CRM service mapping (gui_crm_service_pages + seed + override in webui-db)
    # ------------------------------------------------------------------

    def list_service_pages(self) -> List[Dict[str, Any]]:
        if not self._webui or not self._webui.is_available:
            return []
        return self._webui.run_rows(smq.LIST_SERVICE_PAGES)

    def list_service_mappings(self) -> List[Dict[str, Any]]:
        """Return rows enriched with product display names from datalake.

        Webui rows are keyed by productid; we left-join against discovery_crm_products
        in Python to preserve the read-only contract on the datalake DB.
        """
        webui_rows = self._load_product_mapping()
        if not webui_rows:
            return []
        try:
            products = self._run_query(sq.ALL_PRODUCTS, ())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not enrich mapping rows with product metadata: %s", exc)
            products = []
        product_index = {str(p.get("productid")): p for p in products}
        out: List[Dict[str, Any]] = []
        for pid, row in webui_rows.items():
            prod = product_index.get(pid, {})
            out.append({
                "productid": pid,
                "product_name": prod.get("product_name"),
                "product_number": prod.get("product_number"),
                "category_code": row.get("category_code"),
                "category_label": row.get("category_label"),
                "gui_tab_binding": row.get("gui_tab_binding"),
                "resource_unit": row.get("resource_unit"),
                "source": row.get("source"),
            })
        # Surface products that exist in datalake but have neither seed nor override yet.
        # They are explicitly marked as 'unmatched' (not silently bucketed into 'other')
        # so the operator UI can highlight them and let admins assign a granular page_key.
        for pid, prod in product_index.items():
            if pid in webui_rows:
                continue
            out.append({
                "productid": pid,
                "product_name": prod.get("product_name"),
                "product_number": prod.get("product_number"),
                "category_code": None,
                "category_label": None,
                "gui_tab_binding": None,
                "resource_unit": prod.get("default_unit"),
                "source": "unmatched",
            })
        out.sort(key=lambda r: ((r.get("product_name") or "").lower(), r.get("productid") or ""))
        return out

    def upsert_service_mapping_override(
        self,
        productid: str,
        *,
        page_key: str,
        notes: Optional[str],
        updated_by: Optional[str],
    ) -> int:
        if not self._webui:
            raise RuntimeError("WebUI pool not configured")
        chk = self._webui.run_one(smq.VALIDATE_PAGE_KEY, (page_key,))
        if not chk:
            raise ValueError(f"Unknown page_key: {page_key}")
        return self._webui.execute(
            smq.UPSERT_SERVICE_MAPPING_OVERRIDE,
            (productid, page_key, notes, updated_by or "api"),
        )

    def delete_service_mapping_override(self, productid: str) -> int:
        if not self._webui:
            raise RuntimeError("WebUI pool not configured")
        return self._webui.execute(smq.DELETE_SERVICE_MAPPING_OVERRIDE, (productid,))
