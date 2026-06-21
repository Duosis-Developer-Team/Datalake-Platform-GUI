"""PRJ project scope: one catalog row per account, PRJ-only sales aggregation."""
from __future__ import annotations

from app.db.queries import crm_sales, customer as cq
from app.services.sales_service import SalesService


def test_prj_customer_rows_one_row_per_accountid():
    sql = cq.CRM_PROJECT_CUSTOMER_ROWS
    assert "DISTINCT" in sql
    assert "a.accountid AS crm_accountid" in sql
    assert "PRJ-" in sql


def test_sales_summary_filters_prj_orders_only():
    sql = crm_sales.SALES_SUMMARY
    assert sql.count("ordernumber LIKE 'PRJ-%%'") >= 3


def test_catalog_ytd_and_active_filter_prj_orders():
    assert "ordernumber LIKE 'PRJ-%%'" in crm_sales.CRM_PROJECT_SALES_BY_CUSTOMER_YTD
    assert "ordernumber LIKE 'PRJ-%%'" in crm_sales.CRM_PROJECT_ACTIVE_ORDERS_BY_CUSTOMER


def test_sales_lines_by_product_filters_prj_orders():
    assert "ordernumber LIKE 'PRJ-%%'" in crm_sales.SALES_LINES_BY_PRODUCT_FOR_CUSTOMER


def test_entitled_queries_filter_prj_orders():
    assert "ordernumber LIKE 'PRJ-%%'" in crm_sales.SALES_ENTITLED_RAW_BY_PRODUCT
    assert "ordernumber LIKE 'PRJ-%%'" in crm_sales.SALES_ENTITLED_RAW_BY_CUSTOMER_PRODUCT


class _FakeWebui:
    def __init__(self):
        self.is_available = True
        self.executed: list[tuple] = []

    def execute(self, sql, params):
        self.executed.append((sql, params))
        return 1

    def run_rows(self, sql, params=()):
        if "orphan" in sql.lower() or "LEFT JOIN gui_crm_customer_alias" in sql:
            return [
                {
                    "id": 1,
                    "crm_accountid": "old-guid",
                    "crm_account_name": "ACME CORP",
                    "data_source": "virtualization",
                    "match_method": "contains",
                    "match_value": "Acme",
                }
            ]
        return []


def test_resync_skips_name_collision():
    webui = _FakeWebui()
    project_rows = [
        {"crm_accountid": "guid-a", "crm_account_name": "ACME CORP"},
        {"crm_accountid": "guid-b", "crm_account_name": "ACME CORP"},
        {"crm_accountid": "guid-c", "crm_account_name": "UNIQUE CUSTOMER LTD"},
    ]

    def run_rows(sql, params=()):
        if "PRJ-" in sql:
            return project_rows
        return webui.run_rows(sql, params)

    svc = SalesService(
        get_connection=lambda: None,
        run_row=lambda cur, sql, params: None,
        run_rows=run_rows,
        webui=webui,
    )
    svc.seed_boyner_source_mappings = lambda: {"status": "ok", "rows_upserted": 0}

    result = svc.resync_aliases_from_datalake()
    assert result["aliases_upserted"] == 1
    assert "acme corp" in result["name_collisions"]
    assert result["mappings_remapped"] == 0
    assert len(webui.executed) == 1
