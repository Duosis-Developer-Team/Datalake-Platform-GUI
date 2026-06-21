"""Tests for CRM alias resync from datalake."""
from __future__ import annotations

from app.services.sales_service import SalesService


class _FakeWebui:
    def __init__(self):
        self.is_available = True
        self.executed: list[tuple] = []
        self._orphans = [
            {
                "id": 1,
                "crm_accountid": "old-guid",
                "crm_account_name": "BOYNER BUYUK MAGAZACILIK A.S.",
                "data_source": "virtualization",
                "match_method": "contains",
                "match_value": "Boyner",
            }
        ]

    def execute(self, sql, params):
        self.executed.append((sql, params))
        return 1

    def run_rows(self, sql, params=()):
        if "orphan" in sql.lower() or "LEFT JOIN gui_crm_customer_alias" in sql:
            return list(self._orphans)
        return []


def test_resync_aliases_from_datalake_remaps_orphans():
    webui = _FakeWebui()

    def run_rows(sql, params=()):
        if "PRJ-" in sql:
            return [{"crm_accountid": "new-guid", "crm_account_name": "BOYNER BUYUK MAGAZACILIK A.S."}]
        return webui.run_rows(sql, params)

    svc = SalesService(
        get_connection=lambda: None,
        run_row=lambda cur, sql, params: None,
        run_rows=run_rows,
        webui=webui,
    )
    svc.seed_boyner_source_mappings = lambda: {"status": "ok", "rows_upserted": 1}

    result = svc.resync_aliases_from_datalake()
    assert result["aliases_upserted"] == 1
    assert result["mappings_remapped"] == 1
