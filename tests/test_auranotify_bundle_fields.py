"""AuraNotify bundle reads all downtime categories from a no-source call."""
from __future__ import annotations

from unittest.mock import patch

from src.services import auranotify_client as aura


def _body(datacenter=None, vm=None, service=None, dedicated=None):
    return {
        "datacenter_downtimes": datacenter or [],
        "dedicated_downtimes": dedicated or [],
        "service_downtimes": service or [],
        "vm_downtimes": vm or [],
    }


def test_bundle_merges_service_categories_and_vm_counts():
    dc = [{"category": "DR", "group_name": "DC13", "duration_minutes": 60}]
    ded = [{"category": "Ded", "group_name": "DC16", "duration_minutes": 5}]
    vm = [
        {"vm_name": "web-01", "cluster": "CLS1", "duration_minutes": 30},
        {"vm_name": "web-01", "cluster": "CLS1", "duration_minutes": 10},
    ]
    with patch.object(aura, "get_customer_downtimes", return_value=_body(dc, vm, dedicated=ded)) as gcd:
        out = aura.get_availability_bundle_for_ids([1498], "2024-01-01")
    # one no-source call per id
    gcd.assert_called_once_with(1498, "2024-01-01")
    assert out["service_downtimes"] == dc + ded  # datacenter + dedicated + service(empty)
    assert out["vm_downtimes"] == vm
    assert out["vm_outage_counts"] == {"web-01": 2}
    assert out["customer_id"] == 1498
    assert out["customer_ids"] == [1498]


def test_bundle_empty_when_no_ids():
    out = aura.get_availability_bundle_for_ids([], "2024-01-01")
    assert out == {
        "service_downtimes": [], "vm_downtimes": [], "vm_outage_counts": {},
        "customer_id": None, "customer_ids": [],
    }


def test_get_customer_downtimes_omits_source_when_none():
    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"datacenter_downtimes": []}

    class _Client:
        def __init__(self): self.params = None
        def get(self, path, params=None, headers=None):
            self.params = params
            return _Resp()

    client = _Client()
    with patch.object(aura, "AURANOTIFY_KEY", "k"), patch.object(aura, "_get_client", return_value=client):
        aura.get_customer_downtimes(1498, "2024-01-01")
    assert "source" not in client.params
    assert client.params["start_date"] == "2024-01-01"
