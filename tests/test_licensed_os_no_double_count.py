"""Regression: one VM's Windows licence must never be counted twice.

Live CRM reality (2026-07-27): 88 of 218 customers buy BOTH `MS Windows Lisans` and
`Standart Windows İşletim Sistemi Yönetim Hizmeti`, in identical quantities
(44/44, 29/29, 21/21, 19/19, 18/18, 17/17). Summing both panels doubled the "sold"
side and hid real overusage. Sold Windows = the OS licence SKU only.
"""
from __future__ import annotations

from shared.licensing.reconcile import FAMILY_TO_SOLD_CATEGORIES, reconcile


def _sold(page_key, qty):
    return {"page_key": page_key, "entitled_qty": qty}


def test_management_service_does_not_inflate_windows_sold():
    # ANKUTSAN-shaped: 44 OS licences + 44 management services for the same 44 VMs.
    detected = {"rhel": 0, "suse": 0, "windows": 50}
    rows = {
        r["family"]: r
        for r in reconcile(detected, [_sold("license_windows_os", 44), _sold("mgmt_os_windows", 44)])
    }
    assert rows["windows"]["sold"] == 44
    assert rows["windows"]["delta"] == 6


def test_spla_core_and_cal_do_not_inflate_windows_sold():
    detected = {"rhel": 0, "suse": 0, "windows": 10}
    rows = {
        r["family"]: r
        for r in reconcile(
            detected,
            [
                _sold("license_windows_os", 4),
                _sold("license_microsoft_spla", 204),   # SQL Server 2-core packs
                _sold("license_microsoft_csp", 91),     # M365 per-user seats
            ],
        )
    }
    assert rows["windows"]["sold"] == 4
    assert rows["windows"]["delta"] == 6


def test_suse_sold_is_the_licence_sku_only():
    rows = {
        r["family"]: r
        for r in reconcile(
            {"suse": 300},
            [_sold("license_suse", 6), _sold("mgmt_os_sap", 39)],
        )
    }
    assert rows["suse"]["sold"] == 6
    assert rows["suse"]["delta"] == 294


def test_family_map_points_at_os_licence_skus():
    assert FAMILY_TO_SOLD_CATEGORIES["windows"] == ("license_windows_os",)
    assert FAMILY_TO_SOLD_CATEGORIES["suse"] == ("license_suse",)
    assert FAMILY_TO_SOLD_CATEGORIES["rhel"] == ("license_redhat",)
