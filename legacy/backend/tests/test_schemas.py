import pytest
from pydantic import ValidationError

from app.models.schemas import (
    CustomerResources,
    DataCenterDetail,
    DataCenterSummary,
    DCEnergy,
    DCIntel,
    DCMeta,
    DCPlatforms,
    DCPower,
    DCStats,
    EnergyBreakdown,
    GlobalOverview,
    GlobalStats,
    IBMPlatform,
    NutanixPlatform,
    QueryResult,
    VMwarePlatform,
)


def _valid_dc_stats():
    return DCStats(
        total_cpu="100 / 200 GHz",
        used_cpu_pct=50.0,
        total_ram="500 / 1000 GB",
        used_ram_pct=50.0,
        total_storage="10 / 20 TB",
        used_storage_pct=50.0,
        last_updated="Live",
        total_energy_kw=100.0,
        ibm_kw=50.0,
        vcenter_kw=50.0,
    )


def _valid_platforms():
    return DCPlatforms(
        nutanix=NutanixPlatform(hosts=5, vms=25),
        vmware=VMwarePlatform(clusters=3, hosts=5, vms=25),
        ibm=IBMPlatform(hosts=0, vios=0, lpars=0),
    )


def test_dc_stats_accepts_valid_data():
    stats = _valid_dc_stats()
    assert stats.total_cpu == "100 / 200 GHz"
    assert stats.used_cpu_pct == 50.0


def test_dc_stats_rejects_missing_total_cpu():
    with pytest.raises(ValidationError):
        DCStats(
            used_cpu_pct=50.0,
            total_ram="x",
            used_ram_pct=0.0,
            total_storage="x",
            used_storage_pct=0.0,
            last_updated="Live",
            total_energy_kw=0.0,
            ibm_kw=0.0,
            vcenter_kw=0.0,
        )


def test_datacenter_summary_accepts_valid_data():
    s = DataCenterSummary(
        id="DC11",
        name="DC11",
        location="Istanbul",
        status="Healthy",
        platform_count=2,
        cluster_count=3,
        host_count=10,
        vm_count=50,
        stats=_valid_dc_stats(),
    )
    assert s.id == "DC11"
    assert s.host_count == 10


def test_datacenter_summary_rejects_missing_id():
    with pytest.raises(ValidationError):
        DataCenterSummary(
            name="DC11",
            location="Istanbul",
            status="Healthy",
            platform_count=0,
            cluster_count=0,
            host_count=0,
            vm_count=0,
            stats=_valid_dc_stats(),
        )


def test_dc_power_cpu_and_ram_default_to_zero_when_not_provided():
    p = DCPower(
        hosts=2,
        vms=5,
        vios=1,
        lpar_count=5,
        cpu_used=1.0,
        cpu_assigned=2.0,
        memory_total=100.0,
        memory_assigned=50.0,
    )
    assert p.cpu == 0
    assert p.ram == 0


def test_global_stats_accepts_all_required_fields():
    gs = GlobalStats(
        dc_count=1,
        total_hosts=10,
        total_vms=50,
        total_platforms=2,
        total_energy_kw=100.0,
        total_cpu_cap=200.0,
        total_cpu_used=100.0,
        total_ram_cap=1000.0,
        total_ram_used=500.0,
        total_storage_cap=20.0,
        total_storage_used=10.0,
    )
    assert gs.dc_count == 1


def test_global_overview_assembles_correctly():
    go = GlobalOverview(
        overview=GlobalStats(
            dc_count=1, total_hosts=10, total_vms=50, total_platforms=2,
            total_energy_kw=100.0, total_cpu_cap=200.0, total_cpu_used=100.0,
            total_ram_cap=1000.0, total_ram_used=500.0, total_storage_cap=20.0,
            total_storage_used=10.0,
        ),
        platforms=_valid_platforms(),
        energy_breakdown=EnergyBreakdown(ibm_kw=50.0, vcenter_kw=50.0),
    )
    assert go.overview.dc_count == 1
    assert go.energy_breakdown.ibm_kw == 50.0


def test_query_result_all_optional_fields_default_to_none():
    qr = QueryResult()
    assert qr.result_type is None
    assert qr.value is None
    assert qr.columns is None
    assert qr.data is None
    assert qr.error is None


def test_query_result_accepts_value_type():
    qr = QueryResult(result_type="value", value=42)
    assert qr.result_type == "value"
    assert qr.value == 42


def test_query_result_accepts_rows_type_with_columns_and_data():
    qr = QueryResult(
        result_type="rows",
        columns=["col1", "col2"],
        data=[[1, "a"], [2, "b"]],
    )
    assert len(qr.columns) == 2
    assert len(qr.data) == 2


def test_query_result_accepts_error_field():
    qr = QueryResult(error="Unknown query key")
    assert qr.error == "Unknown query key"
    assert qr.result_type is None


def test_customer_resources_accepts_arbitrary_nested_data():
    cr = CustomerResources(
        totals={"vms_total": 10, "cpu_total": 20.0},
        assets={"intel": {"vmware_vms": 7}, "power": {}},
    )
    assert cr.totals["vms_total"] == 10


def test_nutanix_platform_stores_hosts_and_vms():
    p = NutanixPlatform(hosts=5, vms=25)
    assert p.hosts == 5
    assert p.vms == 25


def test_vmware_platform_stores_clusters_hosts_vms():
    p = VMwarePlatform(clusters=3, hosts=5, vms=25)
    assert p.clusters == 3


def test_ibm_platform_stores_hosts_vios_lpars():
    p = IBMPlatform(hosts=2, vios=1, lpars=8)
    assert p.lpars == 8
