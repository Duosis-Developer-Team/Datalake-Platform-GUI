import pytest

from app.services.db_service import DatabaseService


def _agg(**kwargs):
    defaults = dict(
        dc_code="DC11",
        nutanix_host_count=0,
        nutanix_vms=0,
        nutanix_mem=None,
        nutanix_storage=None,
        nutanix_cpu=None,
        vmware_counts=None,
        vmware_mem=None,
        vmware_storage=None,
        vmware_cpu=None,
        power_hosts=0,
        power_vios=0,
        power_lpar_count=0,
        power_mem=None,
        power_cpu=None,
        ibm_w=0,
        vcenter_w=0,
    )
    defaults.update(kwargs)
    return DatabaseService._aggregate_dc(**defaults)


def test_nutanix_memory_tib_converted_to_gb():
    result = _agg(nutanix_mem=(1.0, 0.5))
    assert result["intel"]["ram_cap"] == pytest.approx(1024.0)
    assert result["intel"]["ram_used"] == pytest.approx(512.0)


def test_vmware_memory_bytes_converted_to_gb():
    bytes_in_one_gb = 1024 ** 3
    result = _agg(vmware_mem=(float(bytes_in_one_gb), float(bytes_in_one_gb) * 0.5))
    assert result["intel"]["ram_cap"] == pytest.approx(1.0)
    assert result["intel"]["ram_used"] == pytest.approx(0.5)


def test_vmware_storage_bytes_converted_to_tb():
    bytes_in_one_tb = 1024 ** 4
    result = _agg(vmware_storage=(float(bytes_in_one_tb), float(bytes_in_one_tb) * 0.25))
    assert result["intel"]["storage_cap"] == pytest.approx(1.0)
    assert result["intel"]["storage_used"] == pytest.approx(0.25)


def test_vmware_cpu_hz_converted_to_ghz():
    hz_2ghz = 2_000_000_000.0
    result = _agg(vmware_cpu=(hz_2ghz, hz_2ghz * 0.6))
    assert result["intel"]["cpu_cap"] == pytest.approx(2.0)
    assert result["intel"]["cpu_used"] == pytest.approx(1.2)


def test_energy_watts_to_kw_conversion():
    result = _agg(ibm_w=3000.0, vcenter_w=2000.0)
    assert result["energy"]["total_kw"] == pytest.approx(5.0)
    assert result["energy"]["ibm_kw"] == pytest.approx(3.0)
    assert result["energy"]["vcenter_kw"] == pytest.approx(2.0)


def test_aggregate_dc_combines_nutanix_and_vmware_memory():
    bytes_in_1gb = 1024 ** 3
    result = _agg(
        nutanix_mem=(1.0, 0.0),
        vmware_mem=(float(bytes_in_1gb), 0.0),
    )
    assert result["intel"]["ram_cap"] == pytest.approx(1024.0 + 1.0)


def test_aggregate_dc_combines_nutanix_and_vmware_cpu():
    hz_1ghz = 1_000_000_000.0
    result = _agg(
        nutanix_cpu=(2.0, 1.0),
        vmware_cpu=(hz_1ghz, 0.5 * hz_1ghz),
    )
    assert result["intel"]["cpu_cap"] == pytest.approx(3.0)
    assert result["intel"]["cpu_used"] == pytest.approx(1.5)


def test_aggregate_dc_combines_nutanix_and_vmware_storage():
    bytes_in_1tb = 1024 ** 4
    result = _agg(
        nutanix_storage=(2.0, 1.0),
        vmware_storage=(float(bytes_in_1tb), float(bytes_in_1tb) * 0.5),
    )
    assert result["intel"]["storage_cap"] == pytest.approx(3.0)
    assert result["intel"]["storage_used"] == pytest.approx(1.5)


def test_aggregate_dc_counts_nutanix_and_vmware_hosts():
    result = _agg(
        nutanix_host_count=5,
        vmware_counts=(3, 4, 20),
    )
    assert result["intel"]["hosts"] == 9
    assert result["intel"]["clusters"] == 3
    assert result["intel"]["vms"] == 20


def test_aggregate_dc_meta_contains_correct_dc_location():
    result = _agg(dc_code="DC12")
    assert result["meta"]["name"] == "DC12"
    assert result["meta"]["location"] == "İzmir"


def test_aggregate_dc_meta_unknown_dc_falls_back_gracefully():
    result = _agg(dc_code="DC99")
    assert result["meta"]["location"] == "Unknown Data Center"


def test_aggregate_dc_kwh_stored_directly_without_conversion():
    result = _agg(ibm_kwh=100.0, vcenter_kwh=50.0)
    assert result["energy"]["total_kwh"] == pytest.approx(150.0)
    assert result["energy"]["ibm_kwh"] == pytest.approx(100.0)
    assert result["energy"]["vcenter_kwh"] == pytest.approx(50.0)
