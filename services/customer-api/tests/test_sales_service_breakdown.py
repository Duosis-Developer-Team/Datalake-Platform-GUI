"""SalesService service-breakdown and lifetime summary fields."""
from __future__ import annotations

from app.services.sales_service import SalesService


class _FakeWebuiPool:
    is_available = True

    def run_rows(self, sql: str, params=None):
        if "gui_crm_customer_alias" in sql:
            return [{"crm_accountid": "acct-1"}]
        if "gui_crm_service_mapping" in sql or "FULL JOIN" in sql:
            return [
                {
                    "productid": "prod-1",
                    "category_code": "virt_hyperconverged",
                    "category_label": "Hyperconverged",
                    "gui_tab_binding": "virtualization.hyperconverged",
                    "resource_unit": "Adet",
                    "source": "yaml",
                }
            ]
        return []

    def run_one(self, sql: str, params=None):
        return None


def test_get_sales_summary_includes_lifetime_fields():
    svc = SalesService(None, None, None, get_customer_assets=None, webui=_FakeWebuiPool())

    def _fake_run_one(sql: str, params: tuple):
        return {
            "ytd_revenue_total": 100.0,
            "ytd_order_count": 2,
            "currency": "TRY",
            "lifetime_revenue_total": 500.0,
            "lifetime_order_count": 9,
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
    assert out["lifetime_revenue_total"] == 500.0
    assert out["lifetime_order_count"] == 9


def test_get_service_breakdown_maps_categories():
    svc = SalesService(None, None, None, get_customer_assets=None, webui=_FakeWebuiPool())

    def _fake_run_query(sql: str, params: tuple):
        if "GROUP BY d.productid" in sql:
            return [{"productid": "prod-1", "product_name": "RAM", "amount_tl": 250.0}]
        return []

    svc._run_query = _fake_run_query  # type: ignore[method-assign]
    out = svc.get_service_breakdown("demo")
    assert len(out) == 1
    assert out[0]["service_code"] == "virt_hyperconverged"
    assert out[0]["service_label"] == "Hyperconverged"
    assert out[0]["amount_tl"] == 250.0
