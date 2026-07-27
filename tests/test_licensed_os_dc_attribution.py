"""Attributing a customer's CRM licences to the DC their guests run in.

CRM sells to a customer, not to a datacenter. A customer whose guests span two DCs
holds one licence quantity that has to be divided before a DC-level "sold vs
detected" comparison means anything. The share is the customer's VM footprint in
that DC over their footprint everywhere, so the per-DC figures add back up to the
company total instead of counting the same licence once per DC.

This is an estimate and the UI labels it as one.
"""
from __future__ import annotations

from shared.licensing.dc_breakdown import attribute_licences_to_dc


def test_customer_entirely_in_one_dc_keeps_their_whole_quantity():
    out = attribute_licences_to_dc(
        dc_vm_counts={"acme": 10},
        total_vm_counts={"acme": 10},
        sold_by_tenant={"acme": {"windows": 8.0}},
    )
    assert out["windows"] == 8


def test_customer_split_across_dcs_is_divided_by_footprint():
    out = attribute_licences_to_dc(
        dc_vm_counts={"acme": 30},
        total_vm_counts={"acme": 100},
        sold_by_tenant={"acme": {"windows": 10.0}},
    )
    assert out["windows"] == 3


def test_shares_across_dcs_add_back_up_to_the_company_total():
    sold = {"acme": {"windows": 10.0}}
    totals = {"acme": 100}
    dc_a = attribute_licences_to_dc({"acme": 30}, totals, sold)
    dc_b = attribute_licences_to_dc({"acme": 70}, totals, sold)
    assert dc_a["windows"] + dc_b["windows"] == 10


def test_multiple_customers_are_summed():
    out = attribute_licences_to_dc(
        dc_vm_counts={"acme": 10, "globex": 5},
        total_vm_counts={"acme": 10, "globex": 10},
        sold_by_tenant={"acme": {"windows": 4.0}, "globex": {"windows": 8.0, "suse": 2.0}},
    )
    assert out["windows"] == 8    # 4 + 4
    assert out["suse"] == 1


def test_customer_with_no_vms_anywhere_contributes_nothing():
    """Guard against a divide-by-zero turning into a fabricated licence count."""
    out = attribute_licences_to_dc(
        dc_vm_counts={"ghost": 0},
        total_vm_counts={"ghost": 0},
        sold_by_tenant={"ghost": {"windows": 50.0}},
    )
    assert out["windows"] == 0


def test_customer_absent_from_this_dc_is_ignored():
    out = attribute_licences_to_dc(
        dc_vm_counts={"acme": 10},
        total_vm_counts={"acme": 10, "globex": 10},
        sold_by_tenant={"acme": {"windows": 4.0}, "globex": {"windows": 99.0}},
    )
    assert out["windows"] == 4


def test_tenant_names_match_case_insensitively():
    out = attribute_licences_to_dc(
        dc_vm_counts={"ACME": 10},
        total_vm_counts={"acme": 10},
        sold_by_tenant={"Acme": {"windows": 6.0}},
    )
    assert out["windows"] == 6


def test_result_always_carries_every_licence_family():
    out = attribute_licences_to_dc({}, {}, {})
    assert out == {"windows": 0, "rhel": 0, "suse": 0}
