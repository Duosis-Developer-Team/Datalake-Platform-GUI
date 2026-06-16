"""Unit tests for host-level compute rows (Hosts panel + host-based sellable)
and the datastore visualization filters (KM-only, NBU/Veeam exclusion, backing).
"""
from __future__ import annotations

from app.db.queries import nutanix as nq
from app.db.queries import vmware as vq
from app.db.queries import vmware_datastore as vdq
from app.services.dc_service import DatabaseService


# ----------------------------------------------------------- payload helpers


def test_host_row_payload_percentages_and_sales_allocation():
    payload = DatabaseService._host_row_payload(
        host="hv1dc13.blt.vc",
        cluster="DC13-KM-CLS-1",
        cpu_cap_ghz=200.0,
        cpu_used_ghz=50.0,
        mem_cap_gb=1024.0,
        mem_used_gb=512.0,
        alloc={"vm_count": 12, "vcpu_total": 80.0, "mem_alloc_gb": 640.0,
               "stor_provisioned_gb": 4096.0, "stor_used_gb": 2048.0},
        ghz_per_core=2.5,
    )
    assert payload["cpu_used_pct"] == 25.0
    assert payload["mem_used_pct"] == 50.0
    # Sales CPU rule: 1 vCPU = 1 GHz.
    assert payload["cpu_alloc_ghz"] == 80.0
    assert payload["cpu_alloc_ghz_physical"] == 200.0  # 80 vCPU × 2.5 GHz
    assert payload["ghz_per_core"] == 2.5
    assert payload["cpu_cap_cores"] == 80.0
    assert payload["cpu_alloc_pct"] == 40.0
    assert payload["mem_alloc_pct"] == 62.5
    assert payload["vm_count"] == 12


def test_host_row_payload_zero_capacity_no_division_error():
    payload = DatabaseService._host_row_payload(
        host="hv2",
        cluster="X",
        cpu_cap_ghz=0.0,
        cpu_used_ghz=0.0,
        mem_cap_gb=0.0,
        mem_used_gb=0.0,
        alloc=None,
    )
    assert payload["cpu_used_pct"] == 0.0
    assert payload["mem_alloc_pct"] == 0.0
    assert payload["vm_count"] == 0


def test_host_alloc_map_normalizes_hostnames():
    """vm_metrics.vmhost may be FQDN or short — both must hit the same key."""
    rows = [
        ("HV1DC13.blt.vc", 5, 40.0, 320.0, 1000.0, 500.0),
        ("hv2dc13", 3, 16.0, 128.0, 400.0, 200.0),
    ]
    out = DatabaseService._host_alloc_map(rows)
    assert "hv1dc13" in out and "hv2dc13" in out
    assert out["hv1dc13"]["vcpu_total"] == 40.0
    assert out["hv2dc13"]["vm_count"] == 3


# ------------------------------------------------------------- SQL contracts


def test_classic_host_rows_sql_scopes_km_clusters():
    assert "vmhost_metrics" in vq.CLASSIC_HOST_ROWS
    assert "ILIKE '%%KM%%'" in vq.CLASSIC_HOST_ROWS
    assert "cardinality(%s::text[])" in vq.CLASSIC_HOST_ROWS


def test_classic_host_mem_peak_sql_exists():
    assert "memory_used_gb" in vq.CLASSIC_HOST_MEM_PEAK
    assert "vmhost_metrics" in vq.CLASSIC_HOST_MEM_PEAK


def test_nutanix_host_mem_peak_sql_exists():
    assert "nutanix_host_metrics" in nq.NUTANIX_HOST_MEM_PEAK


def test_apply_km_storage_to_host_sets_mount_fields():
    ctx = {
        "host_mounts": {
            "hv1": [
                {
                    "datastore_moid": "ds-1",
                    "name": "DS1",
                    "cap_gb": 1000.0,
                    "used_gb": 400.0,
                    "free_gb": 600.0,
                    "used_pct": 40.0,
                    "shared": True,
                },
                {
                    "datastore_moid": "ds-2",
                    "name": "DS2",
                    "cap_gb": 500.0,
                    "used_gb": 100.0,
                    "free_gb": 400.0,
                    "used_pct": 20.0,
                    "shared": False,
                },
            ],
        },
    }
    payload = {"host": "hv1.dc.example"}
    out = DatabaseService._apply_km_storage_to_host(payload, ctx)
    assert out["stor_cap_gb"] == 1500.0
    assert out["stor_exclusive_free_gb"] == 400.0
    assert out["stor_free_gb"] == 1000.0
    assert len(out["datastore_mounts"]) == 2


def test_apply_host_mem_peak_attaches_peak_fields():
    payload = {"host": "hv1", "mem_cap_gb": 512.0}
    out = DatabaseService._apply_host_mem_peak(payload, (256.0, 512.0, 50.0))
    assert out["mem_used_gb_peak"] == 256.0
    assert out["mem_cap_gb_at_peak"] == 512.0
    assert out["mem_peak_util_pct"] == 50.0


def test_classic_host_vm_allocation_groups_by_host():
    assert "GROUP BY vmhost" in vq.CLASSIC_HOST_VM_ALLOCATION
    assert "cluster ILIKE '%%KM%%'" in vq.CLASSIC_HOST_VM_ALLOCATION


def test_nutanix_host_rows_joins_cluster_names():
    assert "nutanix_host_metrics" in nq.NUTANIX_HOST_ROWS
    assert "nutanix_cluster_metrics" in nq.NUTANIX_HOST_ROWS
    assert "cluster_name = ANY(%s::text[])" in nq.NUTANIX_HOST_ROWS


def test_nutanix_host_vm_allocation_groups_by_host():
    assert "GROUP BY host_name" in nq.NUTANIX_HOST_VM_ALLOCATION
    assert "nutanix_vm_metrics" in nq.NUTANIX_HOST_VM_ALLOCATION


# -------------------------------------------------- datastore filter contracts


def test_datastore_metrics_excludes_backup_datastores():
    """NBU / Veeam datastores must not be visualized or sold (KM-only stays)."""
    assert "NOT ILIKE '%%NBU%%'" in vdq.DATASTORE_METRICS
    assert "NOT ILIKE '%%veeam%%'" in vdq.DATASTORE_METRICS
    assert "ILIKE '%%KM%%'" in vdq.DATASTORE_METRICS


def test_datastore_host_mounts_scope_matches_metrics_filter():
    assert "NOT ILIKE '%%NBU%%'" in vdq.DATASTORE_HOST_MOUNTS
    assert "NOT ILIKE '%%veeam%%'" in vdq.DATASTORE_HOST_MOUNTS


def test_datastore_backing_classification_rule():
    """Backing rule mirrored from get_datastore_mapping: IBM in name = ibm."""
    for name, expected in (
        ("IBMR2_Retail_KM_Datastore_108", "ibm"),
        ("ibmr1_retail_km3_datastore_100", "ibm"),
        ("G30STR1DC13_OS1", "intel"),
        ("DC13STRPRM1_OS5", "intel"),
    ):
        backing = "ibm" if "ibm" in name.lower() else "intel"
        assert backing == expected
