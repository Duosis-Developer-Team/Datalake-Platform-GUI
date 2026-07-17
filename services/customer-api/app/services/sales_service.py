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
from app.db.queries import customer as cq
from app.db.queries import service_mapping as smq
from app.services import cache_service as cache
from app.services.crm_account_resolver import (
    make_datalake_account_lookup,
    resolve_crm_account_ids,
)
from app.services.customer_catalog import (
    ALIASES_SNAPSHOT_KEY,
    ALIASES_SNAPSHOT_TTL_SECONDS,
    CATALOG_SNAPSHOT_KEY,
    load_project_customer_rows,
)
from app.utils.service_sales_mapping import map_service_sales_lines
from app.services.customer_mapping_resolver import (
    DATA_SOURCES,
    INTERNAL_ACCOUNT_ID,
    INTERNAL_ACCOUNT_NAME,
    MATCH_METHODS,
    boyner_seed_rows,
    group_mappings_by_account,
)
from app.utils.efficiency_usage import efficiency_status, resolve_used_quantity
from app.utils.usage_comparison import (
    aggregate_entitled_by_category,
    build_virtualization_compliance,
    catalog_product_names_for_compliance,
)
from app.services.crm_config_service import CrmConfigService
from app.services.webui_db import WebuiPool
from app.utils.time_range import default_time_range
from shared.customer.cache_keys import customer_assets_cache_key

logger = logging.getLogger(__name__)

_ACCOUNT_IDS_CACHE_TTL_SEC = 120.0


class SalesService:
    """CRM sales queries spanning datalake + webui DBs."""

    def __init__(
        self,
        get_connection,
        run_row,
        run_rows,
        get_customer_assets=None,
        invalidate_mapping_caches=None,
        plan_mapping_invalidation=None,
        apply_mapping_invalidation=None,
        invalidate_all_mapping_caches=None,
        webui: Optional[WebuiPool] = None,
    ):
        self._get_connection = get_connection
        self._run_row = run_row
        self._run_rows = run_rows
        self._get_customer_assets = get_customer_assets
        self._invalidate_mapping_caches = invalidate_mapping_caches
        self._plan_mapping_invalidation = plan_mapping_invalidation
        self._apply_mapping_invalidation = apply_mapping_invalidation
        self._invalidate_all_mapping_caches = invalidate_all_mapping_caches
        self._webui = webui
        self._config = CrmConfigService(webui) if webui is not None else None
        self._account_ids_cache: Dict[str, tuple[float, List[str]]] = {}
        self._product_mapping_cache: tuple[float, Dict[str, Dict[str, Any]]] | None = None
        self._catalog_price_cache: tuple[float, tuple[Dict[str, float], Dict[str, float], Dict[str, float]]] | None = None

    # ------------------------------------------------------------------
    # Datalake helpers
    # ------------------------------------------------------------------

    def _customer_infra_bundle(
        self,
        customer_name: str,
        time_range: dict | None = None,
    ) -> Dict[str, Any]:
        """Read infra bundle from Redis; on miss optionally load via get_customer_resources."""
        tr = time_range or default_time_range()
        cache_key = customer_assets_cache_key(customer_name, tr.get("start", ""), tr.get("end", ""))
        try:
            hit = cache.get(cache_key)
            if isinstance(hit, dict):
                return hit
        except Exception as exc:  # noqa: BLE001
            logger.debug("customer bundle cache read failed: %s", exc)

        if self._get_customer_assets:
            try:
                bundle = self._get_customer_assets(customer_name, tr)
            except TypeError:
                bundle = self._get_customer_assets(customer_name)
            if isinstance(bundle, dict) and bundle:
                logger.info(
                    "Loaded infra bundle on demand for %s (cache miss: %s)",
                    customer_name,
                    cache_key,
                )
                return bundle
        return {}

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
        """Resolve a customer display name -> list of CRM accountids (alias + display-name fallbacks)."""
        key = (customer_name or "").strip().casefold()
        if key:
            cached = self._account_ids_cache.get(key)
            if cached and (time.perf_counter() - cached[0]) < _ACCOUNT_IDS_CACHE_TTL_SEC:
                return list(cached[1])
        datalake_lookup = None
        if self._get_connection is not None:
            datalake_lookup = make_datalake_account_lookup(self._get_connection, self._run_row)
        account_ids = resolve_crm_account_ids(
            customer_name,
            webui=self._webui,
            datalake_account_lookup=datalake_lookup,
        )
        if key:
            self._account_ids_cache[key] = (time.perf_counter(), list(account_ids))
        return account_ids

    def _load_product_mapping(self) -> Dict[str, Dict[str, Any]]:
        """Return productid -> {category_code, category_label, gui_tab_binding, resource_unit, source}."""
        now = time.perf_counter()
        if self._product_mapping_cache and (now - self._product_mapping_cache[0]) < _ACCOUNT_IDS_CACHE_TTL_SEC:
            return self._product_mapping_cache[1]
        if not self._webui or not self._webui.is_available:
            return {}
        rows = self._webui.run_rows(smq.LIST_SERVICE_MAPPINGS_WEBUI)
        mapping = {str(r["productid"]): r for r in rows if r.get("productid")}
        self._product_mapping_cache = (now, mapping)
        return mapping

    def _load_price_override_dict(self) -> Dict[str, float]:
        if not self._config:
            return {}
        return {str(r["productid"]): float(r["unit_price_tl"]) for r in self._config.list_price_overrides()}

    def _load_catalog_price_indexes(
        self,
    ) -> tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
        """Return (price_overrides, catalog_by_productid, catalog_by_name)."""
        now = time.perf_counter()
        if self._catalog_price_cache and (now - self._catalog_price_cache[0]) < _ACCOUNT_IDS_CACHE_TTL_SEC:
            return self._catalog_price_cache[1]
        price_overrides = self._load_price_override_dict()
        catalog_by_productid: Dict[str, float] = {}
        catalog_by_name: Dict[str, float] = {}
        try:
            for row in self._run_query(sq.SALES_CATALOG_PRICES, ()):
                pid = str(row.get("productid") or "")
                price = row.get("catalog_unit_price")
                if pid and price is not None and pid not in catalog_by_productid:
                    catalog_by_productid[pid] = float(price)
            names = catalog_product_names_for_compliance()
            if names:
                for row in self._run_query(sq.SALES_CATALOG_PRICE_BY_PRODUCT_NAME, (names,)):
                    name = str(row.get("product_name") or "").strip()
                    price = row.get("catalog_unit_price")
                    if name and price is not None and name not in catalog_by_name:
                        catalog_by_name[name] = float(price)
        except Exception as exc:  # noqa: BLE001
            logger.info("Catalog price index unavailable: %s", exc)
        indexes = (price_overrides, catalog_by_productid, catalog_by_name)
        self._catalog_price_cache = (now, indexes)
        return indexes

    def _empty_compliance_summary(self) -> Dict[str, Any]:
        return {
            "total_overage_loss_tl": 0.0,
            "has_overuse": False,
            "overuse_categories": [],
            "overuse_status": "ok",
        }

    # ------------------------------------------------------------------
    # /customers/{name}/sales/summary
    # ------------------------------------------------------------------

    def _empty_summary(self) -> Dict[str, Any]:
        return {
            "ytd_revenue_total": 0.0,
            "invoice_count": 0,
            "ytd_order_count": 0,
            "currency": None,
            "lifetime_revenue_total": 0.0,
            "lifetime_order_count": 0,
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
        row = self._run_one(sq.SALES_SUMMARY, (account_ids, account_ids, account_ids))
        if row is None:
            return self._empty_summary()
        int_keys = {
            "invoice_count",
            "ytd_order_count",
            "lifetime_order_count",
            "opportunity_count",
            "active_order_count",
            "active_contract_count",
        }
        out = {
            k: (
                float(v)
                if v is not None and k not in int_keys and k != "currency"
                else v
            )
            for k, v in row.items()
        }
        if "invoice_count" not in out and out.get("ytd_order_count") is not None:
            out["invoice_count"] = int(out["ytd_order_count"] or 0)
        for key in int_keys:
            if key in out and out[key] is not None:
                out[key] = int(out[key])
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
    # /customers/{name}/sales/active-orders
    # /customers/{name}/sales/active-items
    # ------------------------------------------------------------------

    def get_active_order_headers(self, customer_name: str) -> List[Dict[str, Any]]:
        account_ids = self._resolve_account_ids(customer_name)
        if not account_ids:
            return []
        rows = self._run_query(sq.SALES_ORDER_HEADERS_ACTIVE, (account_ids,))
        out: List[Dict[str, Any]] = []
        for row in rows:
            out.append({
                **row,
                "order_total": float(row["order_total"]) if row.get("order_total") is not None else None,
                "line_count": int(row.get("line_count") or 0),
            })
        return out

    def get_active_sales_items(self, customer_name: str) -> List[Dict[str, Any]]:
        account_ids = self._resolve_account_ids(customer_name)
        if not account_ids:
            return []
        return self._run_query(sq.SALES_ITEMS_ACTIVE, (account_ids,))

    # ------------------------------------------------------------------
    # /customers/{name}/sales/service-breakdown
    # ------------------------------------------------------------------

    def get_service_breakdown(self, customer_name: str) -> List[Dict[str, Any]]:
        account_ids = self._resolve_account_ids(customer_name)
        if not account_ids:
            return []
        raw_lines = self._run_query(sq.SALES_LINES_BY_PRODUCT_FOR_CUSTOMER, (account_ids,))
        mapping = self._load_product_mapping()
        return map_service_sales_lines(raw_lines, mapping)

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

    def get_efficiency_by_category(
        self,
        customer_name: str,
        time_range: dict | None = None,
    ) -> List[Dict[str, Any]]:
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

        bundle = self._customer_infra_bundle(customer_name, time_range)
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
    # /customers/{name}/sales/resource-compliance
    # ------------------------------------------------------------------

    def get_resource_compliance(
        self,
        customer_name: str,
        scope: str = "virtualization",
        time_range: dict | None = None,
    ) -> Dict[str, Any]:
        if scope != "virtualization":
            return {
                "scope": scope,
                "rows": [],
                "summary": self._empty_compliance_summary(),
            }

        account_ids = self._resolve_account_ids(customer_name)
        if not account_ids:
            return {
                "scope": scope,
                "rows": [],
                "summary": self._empty_compliance_summary(),
            }

        entitled_raw = self._run_query(sq.SALES_ENTITLED_RAW_BY_PRODUCT, (account_ids,))
        weighted_rows = self._run_query(sq.SALES_ENTITLED_UNIT_PRICE_BY_PRODUCT, (account_ids,))
        weighted_prices = {
            str(r["productid"]): float(r["weighted_unit_price"])
            for r in weighted_rows
            if r.get("productid") and r.get("weighted_unit_price") is not None
        }

        mapping = self._load_product_mapping()
        price_overrides, catalog_by_productid, catalog_by_name = self._load_catalog_price_indexes()
        entitled_agg = aggregate_entitled_by_category(entitled_raw, mapping)

        bundle = self._customer_infra_bundle(customer_name, time_range)
        if not bundle:
            logger.info(
                "resource_compliance for %s: no infra bundle (mapping or telemetry unavailable)",
                customer_name,
            )

        calc = self._config.get_calc_dict() if self._config else {}
        under_pct = float(calc.get("efficiency.under_pct", 80.0))
        over_pct = float(calc.get("efficiency.over_pct", 110.0))

        rows, summary = build_virtualization_compliance(
            entitled_agg=entitled_agg,
            assets=bundle.get("assets") or {},
            totals=bundle.get("totals") or {},
            weighted_prices=weighted_prices,
            price_overrides=price_overrides,
            catalog_by_productid=catalog_by_productid,
            catalog_by_name=catalog_by_name,
            under_pct=under_pct,
            over_pct=over_pct,
        )
        if not bundle:
            summary = {**summary, "infra_cache_hit": False}
        else:
            summary = {**summary, "infra_cache_hit": True}
        return {"scope": scope, "rows": rows, "summary": summary}

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

    def _load_crm_project_customer_rows(self) -> list[dict[str, Any]]:
        return load_project_customer_rows(self._run_query, self._run_one).rows

    def _load_legacy_alias_index(self) -> dict[str, dict[str, Any]]:
        if not self._webui or not self._webui.is_available:
            return {}
        legacy_rows = self._webui.run_rows(smq.GET_ALL_ALIASES)
        return {str(r.get("crm_accountid")): r for r in legacy_rows if r.get("crm_accountid")}

    def _load_source_mapping_index(self) -> dict[str, list[dict[str, Any]]]:
        if not self._webui or not self._webui.is_available:
            return {}
        rows = self._webui.run_rows(smq.LIST_SOURCE_MAPPINGS)
        return group_mappings_by_account(rows)

    def get_all_aliases(self) -> List[Dict[str, Any]]:
        try:
            cached = cache.get(ALIASES_SNAPSHOT_KEY)
            if isinstance(cached, list) and cached:
                return cached
        except Exception:  # noqa: BLE001
            pass
        project_load = load_project_customer_rows(self._run_query, self._run_one)
        out = self._build_all_aliases()
        if out and not project_load.degraded:
            try:
                cache.set(ALIASES_SNAPSHOT_KEY, out, ttl=ALIASES_SNAPSHOT_TTL_SECONDS)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to cache CRM aliases snapshot: %s", exc)
        return out

    def _build_all_aliases(self) -> list[dict[str, Any]]:
        project_rows = self._load_crm_project_customer_rows()
        legacy_index = self._load_legacy_alias_index()
        mapping_index = self._load_source_mapping_index()

        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in project_rows:
            account_id = str(row.get("crm_accountid") or "").strip()
            account_name = str(row.get("crm_account_name") or "").strip()
            if not account_id:
                continue
            seen.add(account_id.casefold())
            legacy = legacy_index.get(account_id, {})
            mappings = mapping_index.get(account_id, [])
            out.append(
                {
                    "crm_accountid": account_id,
                    "crm_account_name": account_name,
                    "canonical_customer_key": legacy.get("canonical_customer_key"),
                    "netbox_musteri_value": legacy.get("netbox_musteri_value"),
                    "notes": legacy.get("notes"),
                    "source": legacy.get("source") or ("seed" if mappings else "auto"),
                    "source_mappings": mappings,
                }
            )

        for account_id, legacy in legacy_index.items():
            if account_id.casefold() in seen:
                continue
            out.append(
                {
                    "crm_accountid": account_id,
                    "crm_account_name": legacy.get("crm_account_name") or account_id,
                    "canonical_customer_key": legacy.get("canonical_customer_key"),
                    "netbox_musteri_value": legacy.get("netbox_musteri_value"),
                    "notes": legacy.get("notes"),
                    "source": legacy.get("source") or "manual",
                    "source_mappings": mapping_index.get(account_id, []),
                }
            )

        out.sort(key=lambda r: str(r.get("crm_account_name") or "").casefold())
        return out

    def list_source_mappings_for_account(self, crm_accountid: str) -> list[dict[str, Any]]:
        if not self._webui or not self._webui.is_available:
            return []
        return self._webui.run_rows(smq.LIST_SOURCE_MAPPINGS_FOR_ACCOUNT, (crm_accountid,))

    def get_internal_alias(self) -> dict[str, Any]:
        """Return the reserved Internal (Bulutistan) pseudo-account with its source mappings.

        Mirrors a single customer-alias entry so the Internal aliases page can reuse
        the same editor. Backed by gui_crm_customer_source_mapping under crm_accountid
        = INTERNAL; not present in gui_crm_customer_alias so it never leaks into the
        CRM customer list.
        """
        mappings = self.list_source_mappings_for_account(INTERNAL_ACCOUNT_ID)
        notes = next(
            (str(m.get("notes")) for m in mappings if str(m.get("notes") or "").strip()),
            None,
        )
        return {
            "crm_accountid": INTERNAL_ACCOUNT_ID,
            "crm_account_name": INTERNAL_ACCOUNT_NAME,
            "canonical_customer_key": None,
            "netbox_musteri_value": None,
            "notes": notes,
            "source": "internal",
            "source_mappings": mappings,
        }

    def _invalidate_for(self, account_ids: set[str]) -> str | None:
        """Drop cached views for these accounts. Returns a warning, or None.

        Resolves and deletes in one go, so it is only correct for writes the
        resolver cannot see — i.e. writes to gui_crm_customer_source_mapping,
        which it never reads. Anything that writes gui_crm_customer_alias must
        use _plan_invalidation_for / _apply_invalidation instead.

        Injected from main.py rather than imported, so SalesService never has to
        know about CustomerService.
        """
        if self._invalidate_mapping_caches is None:
            return None
        return self._invalidate_mapping_caches(account_ids)

    def _plan_invalidation_for(self, account_ids: set[str]):
        """Resolve, but do not yet delete, the cached views these accounts own.

        Call before a write to gui_crm_customer_alias. The resolver reads that
        table, so a name resolved afterwards can come back None (or point
        somewhere else) and its keys would be skipped as already-correct and
        left stale — the bug this whole path exists to kill. The returned plan
        is opaque here; only _apply_invalidation consumes it.
        """
        if self._plan_mapping_invalidation is None:
            return None
        return self._plan_mapping_invalidation(account_ids)

    def _apply_invalidation(self, plan) -> str | None:
        """Delete the keys a plan doomed. Must run after the write commits:
        deleting earlier would let a concurrent reader refill the cache from
        pre-write rows."""
        if plan is None or self._apply_mapping_invalidation is None:
            return None
        return self._apply_mapping_invalidation(plan)

    def _invalidate_all(self) -> str | None:
        """Drop every cached customer view, for bulk writes whose account set is
        every customer anyway. Resolver-free, so no plan/apply split is needed —
        but it still has to run after the writes commit."""
        if self._invalidate_all_mapping_caches is None:
            return None
        return self._invalidate_all_mapping_caches()

    def save_source_mappings(
        self,
        crm_accountid: str,
        *,
        crm_account_name: str,
        mappings: list[dict[str, Any]],
        notes: Optional[str] = None,
    ) -> dict[str, Any]:
        if not self._webui:
            raise RuntimeError("WebUI pool not configured")
        if not crm_accountid.strip():
            raise ValueError("crm_accountid is required")

        allowed_sources = set(DATA_SOURCES)
        allowed_methods = set(MATCH_METHODS)
        cleaned_name = (crm_account_name or crm_accountid).strip()

        statements: list[tuple[str, tuple[Any, ...]]] = [
            (smq.DELETE_SOURCE_MAPPINGS_FOR_ACCOUNT, (crm_accountid,))
        ]
        for entry in mappings or []:
            data_source = str(entry.get("data_source") or "").strip()
            match_method = str(entry.get("match_method") or "").strip()
            match_value = str(entry.get("match_value") or "").strip()
            if not data_source or not match_method or not match_value:
                continue
            if data_source not in allowed_sources:
                raise ValueError(f"Unsupported data_source: {data_source}")
            if match_method not in allowed_methods:
                raise ValueError(f"Unsupported match_method: {match_method}")
            statements.append(
                (
                    smq.UPSERT_SOURCE_MAPPING,
                    (
                        crm_accountid,
                        cleaned_name,
                        data_source,
                        match_method,
                        match_value,
                        entry.get("display_label"),
                        int(entry.get("priority") or 100),
                        bool(entry.get("enabled", True)),
                        entry.get("notes") or notes,
                        "manual",
                    ),
                )
            )
        # Validation happens while building, so a bad row aborts before the
        # DELETE is ever sent — previously the DELETE was already committed.
        self._webui.execute_all(statements)
        try:
            cache.delete(ALIASES_SNAPSHOT_KEY)
            cache.delete(CATALOG_SNAPSHOT_KEY)
        except Exception:  # noqa: BLE001
            pass
        cache_warning = self._invalidate_for({crm_accountid})
        return {
            "mappings": self.list_source_mappings_for_account(crm_accountid),
            "cache_warning": cache_warning,
        }

    def seed_boyner_source_mappings(self) -> dict[str, Any]:
        if not self._webui:
            raise RuntimeError("WebUI pool not configured")
        boyner = self._run_one(cq.CRM_BOYNER_ACCOUNT, ())
        if not boyner or not boyner.get("crm_accountid"):
            raise ValueError("Boyner CRM account not found in datalake DB")
        account_id = str(boyner["crm_accountid"])
        account_name = str(boyner.get("crm_account_name") or "Boyner").strip()
        rows = boyner_seed_rows(account_id, account_name)
        inserted = 0
        for row in rows:
            self._webui.execute(
                smq.UPSERT_SOURCE_MAPPING,
                (
                    row["crm_accountid"],
                    row["crm_account_name"],
                    row["data_source"],
                    row["match_method"],
                    row["match_value"],
                    row.get("display_label"),
                    row.get("priority", 100),
                    row.get("enabled", True),
                    row.get("notes"),
                    row.get("source", "seed"),
                ),
            )
            inserted += 1
        try:
            cache.delete(ALIASES_SNAPSHOT_KEY)
            cache.delete(CATALOG_SNAPSHOT_KEY)
        except Exception:  # noqa: BLE001
            pass
        self._invalidate_for({account_id})
        return {
            "status": "ok",
            "crm_accountid": account_id,
            "crm_account_name": account_name,
            "rows_upserted": inserted,
        }

    def resync_aliases_from_datalake(self) -> dict[str, Any]:
        """Reconcile WebUI aliases and orphan source mappings with datalake CRM accounts."""
        if not self._webui:
            raise RuntimeError("WebUI pool not configured")

        project_rows = self._load_crm_project_customer_rows()
        name_to_ids: dict[str, set[str]] = {}
        for row in project_rows or []:
            if isinstance(row, dict):
                account_id = str(row.get("crm_accountid") or "").strip()
                account_name = str(row.get("crm_account_name") or "").strip()
            else:
                account_id = str(row[0]).strip()
                account_name = str(row[1]).strip()
            if not account_id or not account_name:
                continue
            name_to_ids.setdefault(account_name.casefold(), set()).add(account_id)

        collision_names = {name for name, ids in name_to_ids.items() if len(ids) > 1}
        name_to_id = {
            name: next(iter(ids))
            for name, ids in name_to_ids.items()
            if len(ids) == 1
        }
        if collision_names:
            logger.warning(
                "CRM alias resync skipped %d display-name collision(s): %s",
                len(collision_names),
                sorted(collision_names)[:10],
            )

        aliases_upserted = 0
        for row in project_rows or []:
            if isinstance(row, dict):
                account_id = str(row.get("crm_accountid") or "").strip()
                account_name = str(row.get("crm_account_name") or "").strip()
            else:
                account_id = str(row[0]).strip()
                account_name = str(row[1]).strip()
            if not account_id or not account_name:
                continue
            if account_name.casefold() in collision_names:
                continue
            self._webui.execute(
                smq.UPSERT_ALIAS_AUTO,
                (account_id, account_name, account_name),
            )
            aliases_upserted += 1

        orphans = self._webui.run_rows(smq.LIST_ORPHAN_SOURCE_MAPPINGS, ())
        mappings_remapped = 0
        seen_names: set[str] = set()
        for row in orphans or []:
            mapping_id = row.get("id")
            old_account_id = str(row.get("crm_accountid") or "").strip()
            account_name = str(row.get("crm_account_name") or "").strip()
            if mapping_id is None or not account_name:
                continue
            if account_name.casefold() in collision_names:
                logger.warning(
                    "Skipping orphan remap for ambiguous display name: %s",
                    account_name,
                )
                continue
            new_account_id = name_to_id.get(account_name.casefold())
            if not new_account_id:
                resolved = self._run_one(
                    cq.CRM_ACCOUNT_BY_DISPLAY_NAME,
                    (account_name, account_name),
                )
                if resolved:
                    if isinstance(resolved, dict):
                        new_account_id = str(resolved.get("crm_accountid") or "").strip()
                    else:
                        new_account_id = str(resolved[0]).strip()
            if not new_account_id or new_account_id == old_account_id:
                continue
            self._webui.execute(
                smq.UPDATE_SOURCE_MAPPING_ACCOUNT,
                (new_account_id, account_name, mapping_id),
            )
            mappings_remapped += 1
            if account_name.casefold() not in seen_names:
                self._webui.execute(
                    smq.UPSERT_ALIAS_AUTO,
                    (new_account_id, account_name, account_name),
                )
                seen_names.add(account_name.casefold())

        self._account_ids_cache.clear()
        boyner_result: dict[str, Any] | None = None
        try:
            boyner_result = self.seed_boyner_source_mappings()
        except Exception as exc:
            logger.warning("Boyner seed during CRM resync failed: %s", exc)

        # Everything, not a targeted set — for two reasons.
        #
        # It cannot be targeted correctly: a targeted plan has to resolve names
        # to accounts *before* the first write, because both loops above write
        # gui_crm_customer_alias, which the resolver reads. But half the account
        # set (the remap ends) is derived from LIST_ORPHAN_SOURCE_MAPPINGS,
        # which finds mappings whose account has no alias row — a question that
        # only answers correctly *after* the alias upserts have run. The set is
        # unknowable at the only moment resolution is still valid.
        #
        # And targeting buys nothing here anyway: the accounts reconciled from
        # the project rows are every project customer, i.e. every customer that
        # can hold a cached view at all. A targeted plan would delete the same
        # keys — minus the ones whose name stopped resolving across the very
        # renames this method performs, which are precisely the stale ones.
        #
        # Cost is bounded by what is actually cached (the warm set), and the
        # names dropped are re-warmed. Correctness never depends on it: an
        # over-eager drop only costs a read-through recompute.
        self._invalidate_all()

        return {
            "status": "ok",
            "aliases_upserted": aliases_upserted,
            "mappings_remapped": mappings_remapped,
            "orphan_mappings_remaining": max(0, len(orphans or []) - mappings_remapped),
            "name_collisions": sorted(collision_names),
            "boyner_seed": boyner_result,
        }

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
        # Plan before the write: UPSERT_ALIAS overwrites canonical_customer_key
        # outright (no COALESCE), so a name that resolved only through the old
        # canonical key stops resolving the moment this statement commits.
        plan = self._plan_invalidation_for({crm_accountid})
        self._webui.execute(
            smq.UPSERT_ALIAS,
            (crm_accountid, crm_account_name, canonical_key, netbox_value, notes),
        )
        self._apply_invalidation(plan)

    def delete_alias(self, crm_accountid: str) -> int:
        if not self._webui:
            raise RuntimeError("WebUI pool not configured")
        # Plan before the write, or this invalidation is a no-op for exactly the
        # keys it exists to catch: once the alias row is gone, a name that
        # matched only via its crm_account_name (RESOLVE_ALIAS_BY_NAME's ILIKE
        # '%name%') resolves to None — CRM_ACCOUNT_BY_DISPLAY_NAME is an exact
        # match and will not stand in for it — and the key is skipped as
        # already-correct, leaving a stale primary and a zombie :last_good.
        plan = self._plan_invalidation_for({crm_accountid})
        deleted = self._webui.execute(smq.DELETE_ALIAS, (crm_accountid,))
        self._apply_invalidation(plan)
        return deleted

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
