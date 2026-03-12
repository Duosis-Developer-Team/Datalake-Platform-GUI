import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app


FAKE_CUSTOMER_LIST = ["Boyner"]

FAKE_CUSTOMER_RESOURCES = {
    "totals": {
        "vms_total": 10,
        "intel_vms_total": 8,
        "power_lpar_total": 2,
        "cpu_total": 32.0,
        "intel_cpu_total": 24.0,
        "power_cpu_total": 8.0,
        "backup": {
            "veeam_defined_sessions": 5,
            "zerto_protected_vms": 3,
            "storage_volume_gb": 1024.0,
            "netbackup_pre_dedup_gib": 500.0,
            "netbackup_post_dedup_gib": 100.0,
            "zerto_provisioned_gib": 2048.0,
        },
    },
    "assets": {
        "intel": {
            "vms": {"vmware": 5, "nutanix": 3, "total": 8},
            "cpu": {"vmware": 16.0, "nutanix": 8.0, "total": 24.0},
            "memory_gb": {"vmware": 64.0, "nutanix": 32.0, "total": 96.0},
            "disk_gb": {"vmware": 500.0, "nutanix": 200.0, "total": 700.0},
            "vm_list": [],
        },
        "power": {
            "cpu_total": 8.0,
            "lpar_count": 2,
            "memory_total_gb": 16.0,
            "vm_list": [],
        },
        "backup": {
            "veeam": {"defined_sessions": 5, "session_types": [], "platforms": []},
            "zerto": {"protected_total_vms": 3, "provisioned_storage_gib_total": 2048.0, "vpgs": []},
            "storage": {"total_volume_capacity_gb": 1024.0},
            "netbackup": {
                "pre_dedup_size_gib": 500.0,
                "post_dedup_size_gib": 100.0,
                "deduplication_factor": "5x",
            },
        },
    },
}


@pytest.fixture
def mock_customer_service():
    mock_svc = MagicMock()
    mock_svc._pool = MagicMock()
    mock_svc.get_customer_list.return_value = FAKE_CUSTOMER_LIST
    mock_svc.get_customer_resources.return_value = FAKE_CUSTOMER_RESOURCES
    with patch("app.main.CustomerService", return_value=mock_svc), \
         patch("app.main.init_redis_pool"), \
         patch("app.main.close_redis_pool"):
        with TestClient(app) as client:
            yield client, mock_svc
