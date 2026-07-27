"""The Windows OS license SKU must be its own panel, split from the SPLA bucket.

Live CRM reality (2026-07-27): `SPLA -` prefixed products include SQL Server core
licenses (204 qty) and RDS User CALs (612 qty) — neither is a Windows *OS* license.
Folding them into the same panel as `MS Windows Lisans` (1294 qty, per VM) makes the
"sold Windows OS licenses" number meaningless. So `MS Windows Lisans` gets its own
panel key and the reconciliation counts only that.
"""
from __future__ import annotations

from shared.sellable.panel_mapping import classify


def test_ms_windows_lisans_is_its_own_os_panel():
    assert classify("MS Windows Lisans") == "license_windows_os"


def test_spla_core_and_cal_products_stay_out_of_the_os_panel():
    for name in (
        "SPLA - MS SQL Server Standart Edition 2 Core Lisans (SQL Server Standard)",
        "SPLA - RDP Kullanıcı Lisans - RDS User CAL (Win Remote Desktop)",
        "SPLA - MS Windows Server Datacenter Editon 2 Core Lisans (Win DC 2 Core)",
        "SPLA - MS Windows Server Standard Editon 2 Core Lisans (Win Std 2 Core)",
    ):
        assert classify(name) == "license_microsoft_spla", name


def test_windows_management_service_is_not_an_os_license():
    assert classify("Standart Windows İşletim Sistemi Yönetim Hizmeti") == "mgmt_os_windows"
    assert classify("Windows İşletim Sistemi Yönetimi") == "mgmt_os_windows"


def test_unrelated_license_panels_unchanged():
    assert classify("SUSE Lisans Bedeli") == "license_suse"
    assert classify("CCSP-RH02823 Red Hat Enterprise Linux Server, Full Support") == "license_redhat"
    assert classify("CSP - Microsoft 365 Business Standard") == "license_microsoft_csp"
