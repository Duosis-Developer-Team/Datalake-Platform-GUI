"""Item 1.5: the customer-availability and CRM-sales caches must live in the
shared cache_service backend (so they're shared across pods), not in private
per-process dicts. These tests assert the entries land in cache_service.
"""
import importlib
from unittest.mock import patch

from src.services import api_client

cache_service = importlib.import_module("src.services.cache_service")


def _tr():
    return {"start": "2024-06-01", "end": "2024-06-07", "preset": "7d"}


def test_customer_availability_bundle_stored_in_shared_cache_service():
    cache_service.clear()
    api_client.clear_customer_availability_bundle_cache()
    payload = {
        "service_downtimes": [],
        "vm_downtimes": [],
        "vm_outage_counts": {"vm1": 2},
        "customer_id": 99,
        "customer_ids": [99],
    }
    with patch.object(
        api_client, "_fetch_customer_availability_bundle_uncached", return_value=payload
    ):
        api_client.get_customer_availability_bundle("Acme", _tr())

    key = api_client._customer_availability_cache_key("Acme", _tr())
    entry = cache_service.get(key)
    assert entry is not None, "availability bundle should be in the shared cache_service"
    _fetched_at, data = entry
    assert data["customer_id"] == 99


def test_crm_sales_summary_stored_in_shared_cache_service():
    cache_service.clear()
    with patch.object(api_client, "_get_json", return_value={"total": 5}):
        api_client.get_customer_sales_summary("Acme")

    key = f"api:crm_sales_summary:{api_client.CRM_SALES_CACHE_VERSION}:Acme"
    entry = cache_service.get(key)
    assert entry is not None, "CRM sales summary should be in the shared cache_service"
    _fetched_at, data = entry
    assert data == {"total": 5}
