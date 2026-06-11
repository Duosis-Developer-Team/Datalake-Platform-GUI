"""Tests for live-snapshot, Nutanix-inclusive architecture utilisation.

Background: the Overview (home) DC Summary table read ``arch_usage`` which was
built from period AVERAGES of VMware cluster_metrics only — Nutanix CPU/RAM was
omitted entirely. The Datacenters cards read ``used_cpu_pct`` (a live, combined
Nutanix+VMware snapshot). The two never matched.

These tests pin the fix: ``_aggregate_dc`` must expose ``cpu_pct_live`` /
``ram_pct_live`` on each compute section, computed as a capacity-weighted
*current snapshot* (not a period average), with the Hyperconverged section
folding in Nutanix CPU/RAM so it reconciles with the combined Intel gauge.
"""

from app.services.dc_service import DatabaseService


def _agg(**overrides):
    """Call _aggregate_dc with safe zero defaults, applying overrides."""
    base = dict(
        dc_code="TEST",
        nutanix_host_count=0,
        nutanix_vms=0,
        nutanix_mem=(0, 0),
        nutanix_storage=(0, 0),
        nutanix_cpu=(0, 0),
        vmware_counts=(0, 0, 0),
        vmware_mem=(0, 0),
        vmware_storage=(0, 0),
        vmware_cpu=(0, 0),
        power_hosts=0,
        power_vios=0,
        power_lpar_count=0,
        power_mem=(0, 0, 0),
        power_cpu=(0, 0, 0, 0),
        ibm_w=0,
        vcenter_w=0,
        classic_row=(0,) * 8,
        classic_avg30=None,
        hyperconv_row=(0,) * 8,
        hyperconv_avg30=None,
    )
    base.update(overrides)
    return DatabaseService._aggregate_dc(**base)


def test_classic_cpu_pct_live_is_snapshot_ratio_not_period_average():
    # classic_row snapshot: cpu_used 30 / cpu_cap 100 = 30%.
    # classic_avg30 says the period AVERAGE cpu was 99% — must be ignored by *_live.
    result = _agg(
        classic_row=(2, 10, 100.0, 30.0, 200.0, 80.0, 0.0, 0.0),
        classic_avg30=(99.0, 99.0, 100.0, 100.0, 1.0, 1.0),
    )
    classic = result["classic"]
    assert classic["cpu_pct_live"] == 30.0
    assert classic["ram_pct_live"] == 40.0  # 80/200


def test_hyperconv_live_folds_in_nutanix_cpu_and_ram_when_no_vmware():
    # AZ11-like: no non-KM VMware (hyperconv_row all zero), but Nutanix present.
    # Nutanix CPU (cap,used) GHz = (200, 50) -> 25%.
    # Nutanix mem (cap,used) where mem_gb = value*1024 -> (10,5) => 10240/5120 = 50%.
    result = _agg(
        nutanix_host_count=9,
        nutanix_cpu=(200.0, 50.0),
        nutanix_mem=(10.0, 5.0),
    )
    hyperconv = result["hyperconv"]
    assert hyperconv["cpu_pct_live"] == 25.0
    assert hyperconv["ram_pct_live"] == 50.0


def test_hyperconv_live_capacity_weights_vmware_plus_nutanix():
    # non-KM VMware snapshot: cpu cap 100 used 20 ; mem cap 400 used 100
    # Nutanix: cpu (100,80) GHz ; mem (10,5) -> 10240/5120 GB
    # Combined cpu = (20+80)/(100+100) = 50%
    # Combined mem = (100+5120)/(400+10240) = 5220/10640 = 49.06 -> 49.1
    result = _agg(
        hyperconv_row=(3, 50, 100.0, 20.0, 400.0, 100.0, 0.0, 0.0),
        nutanix_cpu=(100.0, 80.0),
        nutanix_mem=(10.0, 5.0),
    )
    hyperconv = result["hyperconv"]
    assert hyperconv["cpu_pct_live"] == 50.0
    assert hyperconv["ram_pct_live"] == 49.1


def test_live_fields_are_zero_when_no_capacity():
    result = _agg()
    assert result["classic"]["cpu_pct_live"] == 0.0
    assert result["classic"]["ram_pct_live"] == 0.0
    assert result["hyperconv"]["cpu_pct_live"] == 0.0
    assert result["hyperconv"]["ram_pct_live"] == 0.0
