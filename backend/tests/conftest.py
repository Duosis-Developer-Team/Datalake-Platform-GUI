from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

FAKE_DC_SUMMARY = [
    {
        "id": "DC11",
        "name": "DC11",
        "location": "Istanbul",
        "status": "Healthy",
        "platform_count": 2,
        "cluster_count": 3,
        "host_count": 10,
        "vm_count": 50,
        "stats": {
            "total_cpu": "100 / 200 GHz",
            "used_cpu_pct": 50.0,
            "total_ram": "500 / 1000 GB",
            "used_ram_pct": 50.0,
            "total_storage": "10 / 20 TB",
            "used_storage_pct": 50.0,
            "last_updated": "Live",
            "total_energy_kw": 100.0,
            "ibm_kw": 50.0,
            "vcenter_kw": 50.0,
        },
    }
]

FAKE_DC_DETAIL = {
    "meta": {"name": "DC11", "location": "Istanbul"},
    "intel": {
        "clusters": 3,
        "hosts": 10,
        "vms": 50,
        "cpu_cap": 200.0,
        "cpu_used": 100.0,
        "ram_cap": 1000.0,
        "ram_used": 500.0,
        "storage_cap": 20.0,
        "storage_used": 10.0,
    },
    "power": {
        "hosts": 0,
        "vms": 0,
        "vios": 0,
        "lpar_count": 0,
        "cpu": 0,
        "cpu_used": 0.0,
        "cpu_assigned": 0.0,
        "ram": 0,
        "memory_total": 0.0,
        "memory_assigned": 0.0,
    },
    "energy": {
        "total_kw": 100.0,
        "ibm_kw": 50.0,
        "vcenter_kw": 50.0,
        "total_kwh": 1000.0,
        "ibm_kwh": 500.0,
        "vcenter_kwh": 500.0,
    },
    "platforms": {
        "nutanix": {"hosts": 5, "vms": 25},
        "vmware": {"clusters": 3, "hosts": 5, "vms": 25},
        "ibm": {"hosts": 0, "vios": 0, "lpars": 0},
    },
}

FAKE_DASHBOARD = {
    "overview": {
        "dc_count": 1,
        "total_hosts": 10,
        "total_vms": 50,
        "total_platforms": 2,
        "total_energy_kw": 100.0,
        "total_cpu_cap": 200.0,
        "total_cpu_used": 100.0,
        "total_ram_cap": 1000.0,
        "total_ram_used": 500.0,
        "total_storage_cap": 20.0,
        "total_storage_used": 10.0,
    },
    "platforms": {
        "nutanix": {"hosts": 5, "vms": 25},
        "vmware": {"clusters": 3, "hosts": 5, "vms": 25},
        "ibm": {"hosts": 0, "vios": 0, "lpars": 0},
    },
    "energy_breakdown": {"ibm_kw": 50.0, "vcenter_kw": 50.0},
}

FAKE_CUSTOMER_RESOURCES = {
    "totals": {
        "vms_total": 10,
        "intel_vms_total": 10,
        "power_lpar_total": 0,
        "cpu_total": 20.0,
        "intel_cpu_total": 20.0,
        "power_cpu_total": 0.0,
        "backup": {
            "veeam_defined_sessions": 5,
            "zerto_protected_vms": 3,
            "storage_volume_gb": 100.0,
            "netbackup_pre_dedup_gib": 50.0,
            "netbackup_post_dedup_gib": 10.0,
            "zerto_provisioned_gib": 20.0,
        },
    },
    "assets": {
        "intel": {
            "vmware_vms": 7,
            "nutanix_vms": 3,
            "total_vms": 10,
            "cpu": {"vmware": 14.0, "nutanix": 6.0, "total": 20.0},
            "memory": {"vmware": 70.0, "nutanix": 30.0, "total": 100.0},
        },
        "power": {"lpars": 0, "cpu": 0.0, "memory": 0.0},
        "backup": {
            "veeam": {"defined_sessions": 5, "session_types": [], "platforms": []},
            "zerto": {"protected_total_vms": 3, "provisioned_storage_gib_total": 20.0, "vpgs": 2},
            "storage": {"total_volume_capacity_gb": 100.0},
            "netbackup": {"pre_dedup_size_gib": 50.0, "post_dedup_size_gib": 10.0, "deduplication_factor": 5.0},
        },
    },
}

FAKE_QUERY_RESULT = {"result_type": "value", "value": 42}


@pytest.fixture
def mock_db():
    db = MagicMock()
    db._pool = MagicMock()
    db.get_all_datacenters_summary.return_value = FAKE_DC_SUMMARY
    db.get_dc_details.return_value = FAKE_DC_DETAIL
    db.get_global_dashboard.return_value = FAKE_DASHBOARD
    db.get_customer_resources.return_value = FAKE_CUSTOMER_RESOURCES
    db.get_customer_list.return_value = ["Boyner"]
    db.execute_registered_query.return_value = FAKE_QUERY_RESULT
    return db


@pytest.fixture
def client(mock_db):
    mock_scheduler = MagicMock()
    mock_scheduler.running = False
    with patch("app.main.DatabaseService", return_value=mock_db), \
         patch("app.main.start_scheduler", return_value=mock_scheduler):
        with TestClient(app) as c:
            yield c
