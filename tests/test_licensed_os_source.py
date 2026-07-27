"""Guest-OS source precedence and virtualization-architecture bucketing."""
from __future__ import annotations

import pytest

from shared.licensing.os_source import (
    ARCH_CLASSIC,
    ARCH_HYPERCONVERGED,
    ARCH_POWER,
    ARCH_PURE_NUTANIX,
    arch_bucket,
    empty_tally,
    resolve_guest_os,
    tally_families,
)


@pytest.mark.parametrize("cluster,expected", [
    # Live cluster names, 2026-07-27.
    ("DC13-KM-vDC", ARCH_CLASSIC),
    ("DC13-KM-SSD-vDC", ARCH_CLASSIC),
    ("AZ11-KM-vDC", ARCH_CLASSIC),
    ("dc13-km-cls", ARCH_CLASSIC),
    ("DC13-G1-AHV-CLS", ARCH_PURE_NUTANIX),
    ("DC13-G1-AHV-HYBRID", ARCH_PURE_NUTANIX),
    ("DC13-G16-CLS-HYBRID", ARCH_HYPERCONVERGED),
    ("DC13-Nutanix-vDC", ARCH_HYPERCONVERGED),
    ("LONDON-ICT21", ARCH_HYPERCONVERGED),
])
def test_arch_bucket_from_cluster_name(cluster, expected):
    assert arch_bucket(cluster) == expected


def test_arch_bucket_km_wins_over_ahv_when_both_present():
    """A KM cluster is Classic even if the name also carries AHV — Classic is the
    billing-side split the DC view already uses (cluster ILIKE '%KM%')."""
    assert arch_bucket("DC13-KM-AHV-CLS") == ARCH_CLASSIC


def test_arch_bucket_unknown_cluster_is_hyperconverged():
    # Matches the existing DC split: anything not KM is counted as hyperconverged.
    assert arch_bucket(None) == ARCH_HYPERCONVERGED
    assert arch_bucket("") == ARCH_HYPERCONVERGED


def test_resolve_guest_os_prefers_first_non_empty():
    assert resolve_guest_os(None, "  ", "Microsoft Windows Server 2022 (64-bit)") == (
        "Microsoft Windows Server 2022 (64-bit)"
    )


def test_resolve_guest_os_returns_none_when_no_signal():
    assert resolve_guest_os(None, "", "   ") is None


def test_tally_families_counts_by_licence_family():
    rows = [
        "Microsoft Windows Server 2022 (64-bit)",
        "Microsoft Windows Server 2016 (64-bit)",
        "Red Hat Enterprise Linux 9 (64-bit)",
        "SUSE Linux Enterprise 15 (64-bit)",
        "Ubuntu Linux (64-bit)",
        "Other Linux (64-bit)",
        None,
    ]
    assert tally_families(rows) == {
        "windows": 2, "rhel": 1, "suse": 1, "free": 1, "unknown": 2,
    }


def test_empty_tally_has_every_family_at_zero():
    assert empty_tally() == {"rhel": 0, "suse": 0, "windows": 0, "free": 0, "unknown": 0}
    # Fresh dict each call — callers mutate these.
    a, b = empty_tally(), empty_tally()
    a["windows"] += 1
    assert b["windows"] == 0


def test_with_os_family_stamps_the_family_and_returns_the_same_dict():
    from shared.licensing.os_source import with_os_family

    vm = {"name": "acme-srv01", "guest_os": "Microsoft Windows Server 2019 (64-bit)"}
    out = with_os_family(vm)
    assert out is vm
    assert vm["os_family"] == "windows"


def test_with_os_family_never_guesses_when_there_is_no_signal():
    from shared.licensing.os_source import with_os_family

    assert with_os_family({"name": "ahv-vm", "guest_os": None})["os_family"] == "unknown"


def test_tally_vm_list_counts_the_rows_the_table_renders():
    from shared.licensing.os_source import tally_vm_list

    vms = [
        {"guest_os": "Microsoft Windows Server 2022 (64-bit)"},
        {"os_family": "windows"},
        {"guest_os": "SUSE Linux Enterprise 15 (64-bit)"},
        {"guest_os": None},
    ]
    assert tally_vm_list(vms) == {"rhel": 0, "suse": 1, "windows": 2, "free": 0, "unknown": 1}


def test_tally_vm_list_handles_empty_input():
    from shared.licensing.os_source import tally_vm_list

    assert tally_vm_list(None) == empty_tally()


def test_power_is_its_own_bucket_constant():
    # Power LPARs never carry a VMware/Nutanix cluster name; the bucket is assigned
    # by the caller, so it just has to be a distinct value.
    assert ARCH_POWER not in (ARCH_CLASSIC, ARCH_HYPERCONVERGED, ARCH_PURE_NUTANIX)
