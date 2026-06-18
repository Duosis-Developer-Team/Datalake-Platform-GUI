"""API client — customers list page data and CRM aliases cache guards."""
from __future__ import annotations

from unittest.mock import patch

from src.services import api_client as api
from src.services import cache_service


def test_crm_aliases_response_not_cacheable_for_boyner_only():
    assert api._crm_aliases_response_cacheable(
        [{"crm_accountid": "b1", "crm_account_name": "Boyner Holding"}]
    ) is False
    assert api._crm_aliases_response_cacheable(
        [
            {"crm_accountid": "b1", "crm_account_name": "Boyner Holding"},
            {"crm_accountid": "a1", "crm_account_name": "Alpha Corp"},
        ]
    ) is True
    assert api._crm_aliases_response_cacheable([]) is False


def test_get_customers_page_data_uses_embedded_catalog():
    cache_service.clear()
    overview = {
        "total_customers": 2,
        "catalog": {
            "customers": [{"crm_accountid": "a1", "crm_account_name": "Alpha"}],
            "groups": {"vip": [], "mapped": [], "unmapped": []},
            "degraded": False,
        },
    }
    with patch.object(api, "get_customer_overview", return_value=overview):
        with patch.object(api, "get_customer_catalog") as mock_catalog:
            data = api.get_customers_page_data()
    mock_catalog.assert_not_called()
    assert len(data["customers"]) == 1
    assert data["load_error"] is False
    assert data["degraded"] is False


def test_get_customers_page_data_flags_degraded_prj_failure():
    cache_service.clear()
    overview = {
        "total_customers": 1,
        "catalog": {
            "customers": [{"crm_accountid": "b1", "crm_account_name": "Boyner"}],
            "groups": {"vip": [], "mapped": [], "unmapped": []},
            "degraded": True,
            "prj_query_failed": True,
        },
    }
    with patch.object(api, "get_customer_overview", return_value=overview):
        data = api.get_customers_page_data()
    assert data["degraded"] is True
