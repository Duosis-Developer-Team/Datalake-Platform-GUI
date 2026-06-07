"""SalesService active order headers and line items (statecode 0, 1)."""
from __future__ import annotations

from app.services.sales_service import SalesService


class _FakeWebuiPool:
    is_available = True

    def run_rows(self, sql: str, params=None):
        if "gui_crm_customer_alias" in sql:
            return [{"crm_accountid": "acct-1"}]
        return []

    def run_one(self, sql: str, params=None):
        return None


def test_get_active_order_headers_returns_normalized_rows():
    svc = SalesService(None, None, None, get_customer_assets=None, webui=_FakeWebuiPool())
    captured: list[tuple] = []

    def _fake_run_query(sql: str, params: tuple):
        captured.append((sql, params))
        if "GROUP BY so.salesorderid" in sql:
            return [
                {
                    "source_type": "salesorder",
                    "reference_number": "PRJ-01093-D7Y5J5",
                    "date": "2026-01-15",
                    "status": "Active",
                    "order_total": 3788.42,
                    "line_count": 10,
                    "currency": "TRY",
                }
            ]
        return []

    svc._run_query = _fake_run_query  # type: ignore[method-assign]
    out = svc.get_active_order_headers("3S Sigorta")
    assert len(out) == 1
    assert out[0]["reference_number"] == "PRJ-01093-D7Y5J5"
    assert out[0]["order_total"] == 3788.42
    assert out[0]["line_count"] == 10
    assert captured[0][1] == (["acct-1"],)


def test_get_active_sales_items_uses_statecode_filter():
    svc = SalesService(None, None, None, get_customer_assets=None, webui=_FakeWebuiPool())
    captured_sql: list[str] = []

    def _fake_run_query(sql: str, params: tuple):
        captured_sql.append(sql)
        if "statecode IN (0, 1)" in sql:
            return [
                {
                    "source_type": "salesorder",
                    "reference_number": "PRJ-01093-D7Y5J5",
                    "date": "2026-01-15",
                    "status": "Active",
                    "product_name": "Managed RAM",
                    "quantity": 4.0,
                    "line_total": 500.0,
                    "currency": "TRY",
                }
            ]
        return []

    svc._run_query = _fake_run_query  # type: ignore[method-assign]
    out = svc.get_active_sales_items("3S Sigorta")
    assert len(out) == 1
    assert out[0]["product_name"] == "Managed RAM"
    assert any("statecode IN (0, 1)" in sql for sql in captured_sql)


def test_get_active_orders_empty_when_no_alias():
    svc = SalesService(None, None, None, get_customer_assets=None, webui=None)
    assert svc.get_active_order_headers("unknown") == []
    assert svc.get_active_sales_items("unknown") == []
