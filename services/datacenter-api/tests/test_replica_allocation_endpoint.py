"""replica-allocation endpoint wiring."""
from __future__ import annotations


def test_replica_allocation_route_delegates(client, mock_db):
    expected = {"cpu_vcpu": 12.0, "ram_gb": 64.0, "vm_count": 3, "architecture": "classic"}
    mock_db.get_replica_allocation_offset.return_value = expected
    r = client.get("/api/v1/datacenters/DC13/compute/replica-allocation?architecture=classic")
    assert r.status_code == 200
    assert r.json()["cpu_vcpu"] == 12.0
    mock_db.get_replica_allocation_offset.assert_called_once()
    kwargs = mock_db.get_replica_allocation_offset.call_args.kwargs
    assert kwargs.get("architecture") == "classic"
