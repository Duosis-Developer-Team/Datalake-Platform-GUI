"""CRM Inventory Overview: the "Os" rows must carry real telemetry.

Before this, every licence and OS-management panel rendered as
"(CRM entitled — infra telemetry pending)" with dashes in the Total/Used columns,
because no gui_panel_infra_source row bound them to anything. There is a source
now — the detected guest-OS tally — so they are computed like any other panel.

Selling more licences than there are guests is a legitimate business state
(over-licensing), not a data fault, so these panels are exempt from the
"CRM sold exceeds infra total (check units)" suspicion.
"""
from __future__ import annotations

from app.utils.licensed_os_inventory import (
    LICENCE_OS_PANEL_FAMILIES,
    detected_total_for_panel,
)


_TALLY = {"windows": 8057, "rhel": 523, "suse": 800, "free": 5813, "unknown": 4965}
_POWER = {"suse": 300, "aix": 14, "other": 41}


def test_windows_licence_panel_totals_the_detected_windows_guests():
    assert detected_total_for_panel("license_windows_os", _TALLY, _POWER) == 8057


def test_redhat_and_suse_licence_panels_use_their_own_families():
    assert detected_total_for_panel("license_redhat", _TALLY, _POWER) == 523
    assert detected_total_for_panel("license_suse", _TALLY, _POWER) == 800


def test_windows_management_service_tracks_windows_guests():
    assert detected_total_for_panel("mgmt_os_windows", _TALLY, _POWER) == 8057


def test_linux_management_service_covers_every_linux_guest():
    """"Linux İşletim Sistemi Yönetimi" is billed per managed Linux VM, whatever
    the distribution — the free ones included."""
    assert detected_total_for_panel("mgmt_os_linux", _TALLY, _POWER) == 523 + 800 + 5813


def test_sap_hana_management_tracks_suse_on_power():
    """"SUSE for SAP HANA Yönetimi" is a Power service — 300 LPARs report
    'Linux - SUSE' on 2026-07-27."""
    assert detected_total_for_panel("mgmt_os_sap", _TALLY, _POWER) == 300


def test_unix_management_tracks_aix_lpars():
    assert detected_total_for_panel("mgmt_os_unix", _TALLY, _POWER) == 14


def test_unrelated_panel_gets_no_total():
    assert detected_total_for_panel("virt_classic_cpu", _TALLY, _POWER) is None
    assert detected_total_for_panel("license_veeam", _TALLY, _POWER) is None


def test_missing_tallies_yield_zero_not_none_for_a_bound_panel():
    """A bound panel with no detections must show 0, not fall back to
    'telemetry pending' — the telemetry ran and found nothing."""
    assert detected_total_for_panel("license_windows_os", {}, {}) == 0


def test_power_ostype_buckets_use_the_hmc_vocabulary():
    from app.utils.licensed_os_inventory import power_os_tally

    # The exact value distribution seen live 2026-07-27.
    out = power_os_tally(
        ["Linux - SUSE"] * 300 + ["Linux"] * 21 + ["Unknown"] * 20
        + ["AIX"] * 14 + ["AIX/Linux"] * 3
    )
    assert out["suse"] == 300
    # AIX/Linux is dual-boot capable; counted on the licensable side.
    assert out["aix"] == 17
    assert out["other"] == 41


def test_power_ostype_tally_ignores_blanks():
    from app.utils.licensed_os_inventory import power_os_tally

    assert power_os_tally([None, "", "   "]) == {"suse": 0, "aix": 0, "other": 3}


def test_every_bound_panel_is_declared_in_the_family_set():
    for panel in (
        "license_windows_os", "license_redhat", "license_suse",
        "mgmt_os_windows", "mgmt_os_linux", "mgmt_os_sap", "mgmt_os_unix",
    ):
        assert panel in LICENCE_OS_PANEL_FAMILIES
