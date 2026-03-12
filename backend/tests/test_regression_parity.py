from unittest.mock import MagicMock, patch

from app.services.db_service import DatabaseService


def _make_mock_db():
    db = MagicMock(spec=DatabaseService)
    db._pool = MagicMock()
    db.get_dc_details.return_value = {
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
            "cpu_used": 0.0,
            "cpu_assigned": 0.0,
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
    db.get_all_datacenters_summary.return_value = [
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
    return db


def test_get_dc_details_returns_required_top_level_keys():
    db = _make_mock_db()
    result = db.get_dc_details("DC11")
    assert "meta" in result
    assert "intel" in result
    assert "power" in result
    assert "energy" in result
    assert "platforms" in result


def test_get_dc_details_meta_has_name_and_location():
    db = _make_mock_db()
    result = db.get_dc_details("DC11")
    assert result["meta"]["name"] == "DC11"
    assert result["meta"]["location"] == "Istanbul"


def test_get_dc_details_intel_has_all_fields():
    db = _make_mock_db()
    result = db.get_dc_details("DC11")
    intel = result["intel"]
    for field in ("clusters", "hosts", "vms", "cpu_cap", "cpu_used", "ram_cap", "ram_used", "storage_cap", "storage_used"):
        assert field in intel


def test_get_dc_details_platforms_has_nutanix_vmware_ibm():
    db = _make_mock_db()
    result = db.get_dc_details("DC11")
    platforms = result["platforms"]
    assert "nutanix" in platforms
    assert "vmware" in platforms
    assert "ibm" in platforms


def test_get_all_datacenters_summary_returns_list():
    db = _make_mock_db()
    result = db.get_all_datacenters_summary()
    assert isinstance(result, list)


def test_get_all_datacenters_summary_item_has_required_keys():
    db = _make_mock_db()
    result = db.get_all_datacenters_summary()
    assert len(result) >= 1
    item = result[0]
    for key in ("id", "name", "location", "status", "host_count", "vm_count", "stats"):
        assert key in item


def test_get_all_datacenters_summary_stats_has_energy():
    db = _make_mock_db()
    result = db.get_all_datacenters_summary()
    stats = result[0]["stats"]
    assert "total_energy_kw" in stats
