#!/usr/bin/env python3
"""Unit tests for CRM source mapping sales service methods."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.db.queries import customer as cq
from app.db.queries import service_mapping as smq
from app.services.sales_service import SalesService


def _service_with_webui(webui: MagicMock) -> SalesService:
    svc = SalesService(
        get_connection=MagicMock(),
        run_row=MagicMock(),
        run_rows=MagicMock(),
        webui=webui,
    )
    return svc


def test_get_all_aliases_merges_project_customers_and_mappings():
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.side_effect = lambda sql, params=None: {
        smq.GET_ALL_ALIASES: [],
        smq.LIST_SOURCE_MAPPINGS: [
            {
                "crm_accountid": "acc-1",
                "crm_account_name": "Acme Corp",
                "data_source": "virtualization",
                "match_method": "contains",
                "match_value": "Acme",
                "enabled": True,
                "priority": 10,
                "source": "manual",
            }
        ],
    }.get(sql, [])

    svc = _service_with_webui(webui)
    with patch.object(
        svc,
        "_run_query",
        side_effect=lambda sql, params=None: [
            {"crm_accountid": "acc-1", "crm_account_name": "Acme Corp"},
        ]
        if sql == cq.CRM_PROJECT_CUSTOMER_ROWS
        else None,
    ), patch.object(svc, "_run_one", return_value=None):
        rows = svc.get_all_aliases()

    assert len(rows) == 1
    assert rows[0]["crm_accountid"] == "acc-1"
    assert rows[0]["source_mappings"][0]["match_value"] == "Acme"


def test_get_all_aliases_skips_snapshot_cache_when_prj_degraded():
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.return_value = []

    svc = _service_with_webui(webui)

    def _fail_prj(sql, params=None):
        if sql == cq.CRM_PROJECT_CUSTOMER_ROWS:
            raise RuntimeError("timeout")
        return []

    with patch.object(svc, "_run_query", side_effect=_fail_prj), patch.object(
        svc,
        "_run_one",
        return_value={"crm_accountid": "b1", "crm_account_name": "Boyner Holding"},
    ), patch("app.services.sales_service.cache") as mock_cache:
        mock_cache.get.return_value = None
        rows = svc.get_all_aliases()

    assert len(rows) == 1
    mock_cache.set.assert_not_called()


def test_save_source_mappings_replaces_account_rows():
    webui = MagicMock()
    webui.is_available = True
    webui.execute.return_value = 1
    webui.run_rows.return_value = [{"crm_accountid": "acc-1", "match_value": "Boyner"}]

    svc = _service_with_webui(webui)
    saved = svc.save_source_mappings(
        "acc-1",
        crm_account_name="Boyner CRM",
        mappings=[
            {
                "data_source": "virtualization",
                "match_method": "contains",
                "match_value": "Boyner",
                "enabled": True,
            }
        ],
    )

    assert webui.execute.call_args_list[0].args[0] == smq.DELETE_SOURCE_MAPPINGS_FOR_ACCOUNT
    assert saved[0]["match_value"] == "Boyner"


def test_seed_boyner_source_mappings_is_idempotent_upsert():
    webui = MagicMock()
    webui.is_available = True
    webui.execute.return_value = 1

    svc = _service_with_webui(webui)
    with patch.object(
        svc,
        "_run_one",
        return_value={"crm_accountid": "boyner-id", "crm_account_name": "BOYNER BUYUK MAGAZACILIK A.S."},
    ):
        result = svc.seed_boyner_source_mappings()

    assert result["crm_accountid"] == "boyner-id"
    assert result["rows_upserted"] > 0
    assert any(call.args[0] == smq.UPSERT_SOURCE_MAPPING for call in webui.execute.call_args_list)
