"""SalesService — YTD order count exposed as invoice_count for API compatibility."""
from __future__ import annotations

from app.services.sales_service import SalesService


class _FakeWebuiPool:
    """Stand-in for WebuiPool.

    Returns a single CRM accountid for any customer name so the alias resolver
    behaves as if webui-db is reachable, without touching a real DB.
    """

    is_available = True

    def run_rows(self, sql: str, params=None):
        if "gui_crm_customer_alias" in sql:
            return [{"crm_accountid": "fake-1"}]
        return []

    def run_one(self, sql: str, params=None):  # pragma: no cover - unused here
        return None

    def execute(self, sql: str, params=None):  # pragma: no cover - unused here
        return 0


def test_get_sales_summary_maps_ytd_order_count_to_invoice_count():
    svc = SalesService(None, None, None, get_customer_assets=None, webui=_FakeWebuiPool())

    def _fake_run_one(sql: str, params: tuple):
        return {
            "ytd_revenue_total": 100.0,
            "ytd_order_count": 7,
            "currency": "TRY",
            "pipeline_value": 0.0,
            "opportunity_count": 0,
            "active_order_count": 1,
            "active_order_value": 10.0,
            "active_contract_count": 0,
            "total_contract_value": 0.0,
            "estimated_mrr": 0.0,
        }

    svc._run_one = _fake_run_one  # type: ignore[method-assign]

    out = svc.get_sales_summary("demo")
    assert out["invoice_count"] == 7
