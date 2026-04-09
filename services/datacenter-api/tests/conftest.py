from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

FAKE_DC_SUMMARY = [
    {
        "id": "DC11",
        "name": "DC11",
        "location": "Istanbul",
        "description": "Premier DC",
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
    "meta": {"name": "DC11", "location": "Istanbul", "description": "Premier DC"},
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
    "classic_totals": {
        "cpu_cap": 200.0,
        "cpu_used": 100.0,
        "mem_cap": 1000.0,
        "mem_used": 500.0,
        "stor_cap": 20.0,
        "stor_used": 10.0,
    },
    "hyperconv_totals": {
        "cpu_cap": 100.0,
        "cpu_used": 40.0,
        "mem_cap": 500.0,
        "mem_used": 200.0,
        "stor_cap": 10.0,
        "stor_used": 4.0,
    },
    "ibm_totals": {
        "mem_total": 256.0,
        "mem_assigned": 128.0,
        "cpu_used": 10.0,
        "cpu_assigned": 20.0,
    },
}


@pytest.fixture
def mock_db():
    db = MagicMock()
    db._pool = MagicMock()
    db.get_all_datacenters_summary.return_value = FAKE_DC_SUMMARY
    db.get_dc_details.return_value = FAKE_DC_DETAIL
    db.get_global_dashboard.return_value = FAKE_DASHBOARD
    return db


@pytest.fixture
def client(mock_db):
    mock_scheduler = MagicMock()
    mock_scheduler.running = False
    with patch("app.main.DatabaseService", return_value=mock_db), \
         patch("app.main.start_scheduler", return_value=mock_scheduler):
        with TestClient(app) as c:
            yield c
