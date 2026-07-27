"""Per-customer licensed-OS tally, derived from the rendered VM lists.

Customer View does NOT split by virtualization type here (unlike DC View): a
customer's Windows licence count is one number across Classic, Hyperconverged and
Power. What it must never do is count a VM twice — Pure Nutanix is a *subset* of
Hyperconverged (the hyperconverged query unions every nutanix_vm_metrics row for
the customer; the pure-Nutanix query filters that same set down to AHV-only
clusters), so adding both buckets would inflate the used side.
"""
from __future__ import annotations

from app.utils.licensed_os import customer_os_tally


def _vm(name, family):
    return {"name": name, "os_family": family}


def test_tally_spans_classic_hyperconv_and_power():
    assets = {
        "classic": {"vm_list": [_vm("km-1", "windows"), _vm("km-2", "rhel")]},
        "hyperconv": {"vm_list": [_vm("hc-1", "windows")]},
        "power": {"vm_list": [_vm("lpar-1", "suse")]},
    }
    assert customer_os_tally(assets) == {
        "rhel": 1, "suse": 1, "windows": 2, "free": 0, "unknown": 0,
    }


def test_pure_nutanix_is_not_added_on_top_of_hyperconverged():
    """pure_nutanix ⊆ hyperconv — counting both double counts the same guest."""
    shared_vm = _vm("ahv-1", "windows")
    assets = {
        "classic": {"vm_list": []},
        "hyperconv": {"vm_list": [shared_vm, _vm("hc-2", "windows")]},
        "pure_nutanix": {"vm_list": [shared_vm]},
        "power": {"vm_list": []},
    }
    assert customer_os_tally(assets)["windows"] == 2


def test_same_vm_name_in_two_buckets_counts_once():
    assets = {
        "classic": {"vm_list": [_vm("Acme-SRV01", "windows")]},
        "hyperconv": {"vm_list": [_vm("acme-srv01", "windows")]},
    }
    assert customer_os_tally(assets)["windows"] == 1


def test_missing_or_empty_assets_are_safe():
    assert customer_os_tally(None) == {
        "rhel": 0, "suse": 0, "windows": 0, "free": 0, "unknown": 0,
    }
    assert customer_os_tally({})["windows"] == 0
    assert customer_os_tally({"classic": {}})["windows"] == 0


def test_vms_without_a_signal_land_in_unknown_not_a_licence_family():
    assets = {"hyperconv": {"vm_list": [{"name": "ahv-x", "guest_os": None}]}}
    tally = customer_os_tally(assets)
    assert tally["unknown"] == 1
    assert tally["windows"] == 0
