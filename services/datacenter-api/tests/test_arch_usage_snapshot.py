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


def test_hyperconv_live_uses_merged_row_when_nutanix_fallback_applied():
    # AZ11-like: merge query fills hyperconv_row from Nutanix when VMware is empty.
    # CPU 50/200 = 25%; RAM 5120/10240 = 50%.
    result = _agg(
        nutanix_host_count=9,
        nutanix_cpu=(200.0, 50.0),
        nutanix_mem=(10.0, 5.0),
        hyperconv_row=(0, 0, 200.0, 50.0, 10240.0, 5120.0, 0.0, 0.0),
    )
    hyperconv = result["hyperconv"]
    assert hyperconv["cpu_cap"] == 200.0
    assert hyperconv["cpu_pct_live"] == 25.0
    assert hyperconv["ram_pct_live"] == 50.0


def test_hyperconv_live_uses_merged_row_without_dc_wide_nutanix_double_count():
    # Per-cluster merge already folded Nutanix into hyperconv_row; intel nutanix_* must not be added again.
    result = _agg(
        hyperconv_row=(3, 50, 100.0, 20.0, 400.0, 100.0, 0.0, 0.0),
        nutanix_cpu=(100.0, 80.0),
        nutanix_mem=(10.0, 5.0),
    )
    hyperconv = result["hyperconv"]
    assert hyperconv["cpu_pct_live"] == 20.0
    assert hyperconv["ram_pct_live"] == 25.0


def test_live_fields_are_zero_when_no_capacity():
    result = _agg()
    assert result["classic"]["cpu_pct_live"] == 0.0
    assert result["classic"]["ram_pct_live"] == 0.0
    assert result["hyperconv"]["cpu_pct_live"] == 0.0
    assert result["hyperconv"]["ram_pct_live"] == 0.0
