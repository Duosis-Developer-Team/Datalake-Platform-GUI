"""SalesService — YTD order count exposed as invoice_count for API compatibility."""
from __future__ import annotations

from app.services.sales_service import SalesService


def test_get_sales_summary_maps_ytd_order_count_to_invoice_count():
    svc = SalesService(None, None, None, get_customer_assets=None)

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
