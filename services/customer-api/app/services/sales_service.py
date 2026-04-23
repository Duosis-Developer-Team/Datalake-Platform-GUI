"""
Sales data service — queries discovery_crm_* tables via customer_service DB pool.
All methods return plain dicts/lists; pydantic validation happens in the router layer.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.db.queries import crm_sales as sq

logger = logging.getLogger(__name__)


class SalesService:
    """Wraps CRM sales queries using the shared CustomerService connection pool infrastructure."""

    def __init__(self, get_connection, run_row, run_rows):
        self._get_connection = get_connection
        self._run_row = run_row
        self._run_rows = run_rows

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
                "currency": None,
                "pipeline_value": 0.0,
                "opportunity_count": 0,
                "active_order_count": 0,
                "active_order_value": 0.0,
                "active_contract_count": 0,
                "total_contract_value": 0.0,
                "estimated_mrr": 0.0,
            }
        return {k: (float(v) if v is not None and k not in ("currency", "invoice_count", "opportunity_count", "active_order_count", "active_contract_count") else v)
                for k, v in row.items()}

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
