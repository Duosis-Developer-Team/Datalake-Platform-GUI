"""
Sales data service — queries discovery_crm_* tables via customer_service DB pool.
All methods return plain dicts/lists; pydantic validation happens in the router layer.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.db.queries import crm_sales as sq
from app.utils.efficiency_usage import efficiency_status, resolve_used_quantity

logger = logging.getLogger(__name__)


class SalesService:
    """Wraps CRM sales queries using the shared CustomerService connection pool infrastructure."""

    def __init__(self, get_connection, run_row, run_rows, get_customer_assets=None):
        self._get_connection = get_connection
        self._run_row = run_row
        self._run_rows = run_rows
        self._get_customer_assets = get_customer_assets

    def _run_query(self, sql: str, params: tuple) -> List[Dict[str, Any]]:
        """Execute a SELECT and return list of column-name dicts."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                t0 = time.perf_counter()
                cur.execute(sql, params)
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                elapsed = (time.perf_counter() - t0) * 1000
                logger.info("CRM sales SQL (%.0fms): %s rows", elapsed, len(rows))
                return [dict(zip(cols, row)) for row in rows]

    def _run_one(self, sql: str, params: tuple) -> Optional[Dict[str, Any]]:
        rows = self._run_query(sql, params)
        return rows[0] if rows else None

    def _customer_params(self, customer_name: str) -> tuple:
        """Return (exact, ilike) param tuple for alias resolution."""
        return (customer_name, f"%{customer_name}%")

    # ------------------------------------------------------------------
    # /customers/{name}/sales/summary
    # ------------------------------------------------------------------

    def get_sales_summary(self, customer_name: str) -> Dict[str, Any]:
        params = self._customer_params(customer_name) * 1
        row = self._run_one(sq.SALES_SUMMARY, params)
        if row is None:
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
        # API schema field name (realized sales orders)
        if "invoice_count" not in out and out.get("ytd_order_count") is not None:
            out["invoice_count"] = int(out["ytd_order_count"] or 0)
        if "invoice_count" in out and out["invoice_count"] is not None:
            out["invoice_count"] = int(out["invoice_count"])
        return out

    # ------------------------------------------------------------------
    # /customers/{name}/sales/items
    # ------------------------------------------------------------------

    def get_sales_items(self, customer_name: str) -> List[Dict[str, Any]]:
        p = self._customer_params(customer_name)
        params = p + p  # two UNION ALL branches, each needs (name, ilike)
        return self._run_query(sq.SALES_ITEMS, params)

    # ------------------------------------------------------------------
    # /customers/{name}/sales/efficiency
    # ------------------------------------------------------------------

    def get_sales_efficiency(self, customer_name: str) -> List[Dict[str, Any]]:
        p = self._customer_params(customer_name)
        return self._run_query(sq.SALES_EFFICIENCY, p)

    # ------------------------------------------------------------------
    # /customers/{name}/sales/efficiency-by-category
    # ------------------------------------------------------------------

    def get_efficiency_by_category(self, customer_name: str) -> List[Dict[str, Any]]:
        """Sold vs used per CRM category row (usage from live customer assets bundle when available)."""
        p = self._customer_params(customer_name)
        sold_rows = self._run_query(sq.SALES_SOLD_BY_CATEGORY, p)
        bundle: Dict[str, Any] = {}
        if self._get_customer_assets:
            try:
                bundle = self._get_customer_assets(customer_name) or {}
            except Exception as exc:  # noqa: BLE001
                logger.warning("get_customer_assets failed for efficiency-by-category: %s", exc)
                bundle = {}
        assets = bundle.get("assets") or {}
        totals = bundle.get("totals") or {}

        out: List[Dict[str, Any]] = []
        for r in sold_rows:
            cat = r.get("category_code")
            ru = r.get("resource_unit")
            sold_qty = float(r.get("sold_qty") or 0)
            sold_amt = float(r.get("sold_amount_tl") or 0)
            used_qty, note = resolve_used_quantity(
                category_code=cat, resource_unit=ru, assets=assets, totals=totals
            )
            eff_pct: float | None
            if sold_qty > 0:
                eff_pct = round((used_qty / sold_qty) * 100.0, 2)
            else:
                eff_pct = None
            alloc_pct: float | None
            if sold_qty > 0:
                alloc_pct = round(min(150.0, (used_qty / sold_qty) * 100.0), 2)
            else:
                alloc_pct = None
            out.append(
                {
                    "category_code": cat,
                    "category_label": r.get("category_label"),
                    "gui_tab_binding": r.get("gui_tab_binding"),
                    "resource_unit": ru,
                    "sold_qty": sold_qty,
                    "sold_amount_tl": sold_amt,
                    "used_qty": used_qty,
                    "efficiency_pct": eff_pct,
                    "allocated_vs_sold_pct": alloc_pct,
                    "delta_qty": (used_qty - sold_qty) if sold_qty or used_qty else 0.0,
                    "status": efficiency_status(eff_pct, sold_qty),
                    "usage_note": note,
                }
            )
        return out

    # ------------------------------------------------------------------
    # /customers/{name}/sales/catalog-valuation
    # ------------------------------------------------------------------

    def get_catalog_valuation(self, customer_name: str) -> List[Dict[str, Any]]:
        p = self._customer_params(customer_name)
        return self._run_query(sq.CATALOG_VALUATION, p)

    # ------------------------------------------------------------------
    # Customer alias management
    # ------------------------------------------------------------------

    def get_all_aliases(self) -> List[Dict[str, Any]]:
        return self._run_query(sq.GET_ALL_ALIASES, ())

    def upsert_alias(self, crm_accountid: str, crm_account_name: str,
                     canonical_key: Optional[str], netbox_value: Optional[str],
                     notes: Optional[str]) -> None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sq.UPSERT_ALIAS, (
                    crm_accountid, crm_account_name,
                    canonical_key, netbox_value, notes,
                ))
                conn.commit()

    # ------------------------------------------------------------------
    # Product category alias (discovery_crm_product_category_alias)
    # ------------------------------------------------------------------

    def list_product_category_aliases(self) -> List[Dict[str, Any]]:
        return self._run_query(sq.LIST_PRODUCT_CATEGORY_ALIASES, ())

    def update_product_category_alias(
        self,
        productid: str,
        *,
        category_code: str,
        category_label: str,
        gui_tab_binding: str,
        resource_unit: str,
        notes: Optional[str],
    ) -> int:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sq.UPDATE_PRODUCT_CATEGORY_ALIAS,
                    (category_code, category_label, gui_tab_binding, resource_unit, notes, productid),
                )
                conn.commit()
                return int(cur.rowcount or 0)
