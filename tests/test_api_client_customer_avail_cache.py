"""Unit tests for customer availability bundle TTL cache in api_client."""

from unittest.mock import patch

from src.services import api_client


def _sample_tr():
    return {"start": "2024-06-01", "end": "2024-06-07", "preset": "7d"}


def test_get_customer_availability_bundle_second_call_uses_cache():
    api_client.clear_customer_availability_bundle_cache()
    payload = {
        "service_downtimes": [],
        "vm_downtimes": [],
        "vm_outage_counts": {"vm1": 2},
        "customer_id": 99,
        "customer_ids": [99],
    }
    with patch.object(
        api_client,
        "_fetch_customer_availability_bundle_uncached",
        return_value=payload,
    ) as fetch:
        r1 = api_client.get_customer_availability_bundle("Acme", _sample_tr())
        r2 = api_client.get_customer_availability_bundle("Acme", _sample_tr())
        assert fetch.call_count == 1
    assert r1 == r2
    assert r1["customer_id"] == 99


def test_get_customer_availability_bundle_force_refresh_bypasses_cache():
    api_client.clear_customer_availability_bundle_cache()
    payload = {"service_downtimes": [], "vm_downtimes": [], "vm_outage_counts": {}, "customer_id": 1, "customer_ids": []}
    with patch.object(
        api_client,
        "_fetch_customer_availability_bundle_uncached",
        return_value=payload,
    ) as fetch:
        api_client.get_customer_availability_bundle("Acme", _sample_tr())
        api_client.get_customer_availability_bundle("Acme", _sample_tr(), force_refresh=True)
        assert fetch.call_count == 2


def test_get_customer_availability_bundle_expired_ttl_refetches():
    api_client.clear_customer_availability_bundle_cache()
    payload = {"service_downtimes": [], "vm_downtimes": [], "vm_outage_counts": {}, "customer_id": None, "customer_ids": []}
    t0 = 1000.0
    t1 = t0 + api_client.CUSTOMER_AVAIL_TTL_SECONDS + 1.0
    times = [t0, t1]
    with patch.object(
        api_client,
        "_fetch_customer_availability_bundle_uncached",
        return_value=payload,
    ) as fetch, patch("src.services.api_client.time.time", side_effect=times):
        api_client.get_customer_availability_bundle("Acme", _sample_tr())
        api_client.get_customer_availability_bundle("Acme", _sample_tr())
        assert fetch.call_count == 2
