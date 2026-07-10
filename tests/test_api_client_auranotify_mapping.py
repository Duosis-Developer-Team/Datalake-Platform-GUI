"""Explicit AuraNotify id mapping resolution and fetch precedence."""
from __future__ import annotations

from unittest.mock import patch

from src.services import api_client


_ALIASES = [
    {
        "crm_accountid": "acc-4a",
        "crm_account_name": "4a_Kozmetik",
        "source_mappings": [
            {"data_source": "virtualization", "match_method": "contains", "match_value": "4a", "enabled": True},
            {"data_source": "auranotify", "match_method": "id_exact", "match_value": "1498", "enabled": True},
            {"data_source": "auranotify", "match_method": "id_exact", "match_value": "3787", "enabled": True},
            {"data_source": "auranotify", "match_method": "id_exact", "match_value": "999", "enabled": False},
            {"data_source": "auranotify", "match_method": "id_exact", "match_value": "notanint", "enabled": True},
        ],
    },
]


def test_ids_for_customer_returns_enabled_numeric_only():
    with patch.object(api_client, "get_crm_aliases", return_value=_ALIASES):
        assert api_client.get_auranotify_ids_for_customer("4a_Kozmetik") == [1498, 3787]


def test_ids_for_customer_case_insensitive_and_empty_when_unmapped():
    with patch.object(api_client, "get_crm_aliases", return_value=_ALIASES):
        assert api_client.get_auranotify_ids_for_customer("4A_KOZMETIK".lower()) == [1498, 3787]
        assert api_client.get_auranotify_ids_for_customer("Unknown Co") == []


def test_fetch_prefers_explicit_mapping():
    tr = {"start": "2024-01-01", "end": "2024-06-07"}
    with patch.object(api_client, "get_auranotify_ids_for_customer", return_value=[1498, 3787]), \
         patch("src.services.auranotify_client.get_availability_bundle_for_ids", return_value={"customer_ids": [1498, 3787]}) as by_ids, \
         patch("src.services.auranotify_client.get_customer_availability_bundle") as by_name:
        out = api_client._fetch_customer_availability_bundle_uncached("4a_Kozmetik", tr)
    by_ids.assert_called_once()
    by_name.assert_not_called()
    assert out["customer_ids"] == [1498, 3787]


def test_fetch_falls_back_to_name_when_unmapped():
    tr = {"start": "2024-01-01", "end": "2024-06-07"}
    with patch.object(api_client, "get_auranotify_ids_for_customer", return_value=[]), \
         patch("src.services.auranotify_client.get_availability_bundle_for_ids") as by_ids, \
         patch("src.services.auranotify_client.get_customer_availability_bundle", return_value={"customer_ids": [7]}) as by_name:
        out = api_client._fetch_customer_availability_bundle_uncached("Unknown Co", tr)
    by_name.assert_called_once()
    by_ids.assert_not_called()
    assert out["customer_ids"] == [7]


def test_customer_options_shape():
    fake_list = [{"id": 1498, "name": "4a_Kozmetik"}, {"id": 1495, "name": "12mtech"}]
    api_client._api_response_cache.delete("api:auranotify_customer_options")
    with patch("src.services.auranotify_client.get_customer_list_aura", return_value=fake_list):
        opts = api_client.get_auranotify_customer_options()
    assert {"label": "4a_Kozmetik · id 1498", "value": "1498"} in opts
    assert all(set(o) == {"label", "value"} for o in opts)
