"""Unit tests for host-level compute aggregation helpers."""
from __future__ import annotations

from shared.sellable.host_aggregate import (
    aggregate_hosts_compute,
    build_deduped_storage_pools,
    finalize_host_payload,
)


def _sample_host(**overrides):
    base = {
        "host": "hv1",
        "cluster": "CLS-1",
        "vm_count": 5,
        "cpu_cap_ghz": 100.0,
        "cpu_used_ghz": 20.0,
        "cpu_used_pct": 20.0,
        "cpu_alloc_ghz": 40.0,
        "cpu_alloc_ghz_physical": 80.0,
        "mem_cap_gb": 512.0,
        "mem_used_gb": 128.0,
        "mem_alloc_gb": 256.0,
        "mem_used_gb_peak": 200.0,
        "mem_peak_util_pct": 39.0,
        "stor_cap_gb": 2048.0,
        "stor_provisioned_gb": 1024.0,
        "stor_used_gb": 512.0,
        "stor_free_gb": 1536.0,
        "datastore_mounts": [
            {
                "datastore_moid": "ds-1",
                "name": "DS1",
                "backing": "intel",
                "cap_gb": 1024.0,
                "free_gb": 512.0,
                "used_gb": 512.0,
                "used_pct": 50.0,
                "shared": True,
            },
            {
                "datastore_moid": "ds-2",
                "name": "DS2",
                "backing": "intel",
                "cap_gb": 1024.0,
                "free_gb": 1024.0,
                "used_gb": 0.0,
                "used_pct": 0.0,
                "shared": False,
            },
        ],
    }
    base.update(overrides)
    return base


def test_aggregate_hosts_compute_sums_capacity_fields():
    hosts = [_sample_host(), _sample_host(host="hv2", cpu_cap_ghz=50.0, vm_count=3)]
    summary = aggregate_hosts_compute(hosts)
    assert summary["hosts"] == 2
    assert summary["vms"] == 8
    assert summary["cpu_cap"] == 150.0
    assert summary["cpu_alloc_ghz_vm"] == 80.0
    assert summary["mem_cap"] == 1024.0
    assert summary["stor_cap_gb"] == 4096.0


def test_aggregate_hosts_compute_empty_returns_zeros():
    summary = aggregate_hosts_compute([])
    assert summary["hosts"] == 0
    assert summary["cpu_cap"] == 0.0
    assert summary["stor_free_gb"] == 0.0


def test_build_deduped_storage_pools_dedupes_by_moid():
    hosts = [
        _sample_host(),
        _sample_host(
            host="hv2",
            datastore_mounts=[
                {
                    "datastore_moid": "ds-1",
                    "name": "DS1-copy",
                    "free_gb": 100.0,
                    "shared": True,
                },
                {
                    "datastore_moid": "ds-3",
                    "name": "DS3",
                    "free_gb": 256.0,
                    "shared": False,
                },
            ],
        ),
    ]
    pools = build_deduped_storage_pools(hosts)
    moids = {p["datastore_moid"] for p in pools}
    assert moids == {"ds-1", "ds-2", "ds-3"}
    ds1 = next(p for p in pools if p["datastore_moid"] == "ds-1")
    assert ds1["name"] == "DS1"


def test_aggregate_hosts_compute_dedupes_nutanix_cluster_storage():
    pool_host = {
        "cluster": "HC-CLS",
        "cpu_cap_ghz": 100.0,
        "cpu_used_ghz": 10.0,
        "cpu_alloc_ghz": 20.0,
        "mem_cap_gb": 512.0,
        "mem_used_gb": 100.0,
        "mem_alloc_gb": 200.0,
        "stor_cap_gb": 5000.0,
        "stor_provisioned_gb": 1000.0,
        "stor_used_gb": 2000.0,
        "stor_free_gb": 3000.0,
    }
    hosts = [pool_host, {**pool_host, "host": "hv2"}]
    summed = aggregate_hosts_compute(hosts)
    deduped = aggregate_hosts_compute(hosts, dedupe_cluster_storage=True)
    assert summed["stor_cap_gb"] == 10000.0
    assert deduped["stor_cap_gb"] == 5000.0
    assert deduped["cpu_cap"] == 200.0


def test_finalize_host_payload_attaches_summary_and_pools():
    payload = finalize_host_payload({"hosts": [_sample_host()], "host_count": 1})
    assert "summary" in payload
    assert payload["summary"]["hosts"] == 1
    assert len(payload["storage_pools"]) == 2
