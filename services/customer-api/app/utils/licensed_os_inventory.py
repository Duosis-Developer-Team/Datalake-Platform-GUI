"""Which detected guest-OS count backs each licence / OS-management panel.

CRM Inventory Overview rendered every one of these rows as "(CRM entitled — infra
telemetry pending)" because nothing was bound to them. The guest-OS tally is that
missing telemetry.

Each panel maps to the guests it is billed against:

    license_windows_os  Windows guests            the OS licence itself
    license_redhat      RHEL guests
    license_suse        SUSE guests
    mgmt_os_windows     Windows guests            management service, same estate
    mgmt_os_linux       every Linux guest         billed per managed Linux VM,
                                                  distribution irrelevant
    mgmt_os_sap         SUSE LPARs on Power       "SUSE for SAP HANA Yönetimi"
    mgmt_os_unix        AIX LPARs

Selling more licences than there are guests is over-licensing — a real commercial
state, not a data fault. Callers must not flag these panels as suspect on
`crm_sold > total`.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

# Panel key -> how to read its detected count out of (vm tally, power tally).
_PANEL_SOURCES: dict[str, Callable[[Mapping[str, Any], Mapping[str, Any]], int]] = {
    "license_windows_os": lambda vm, pw: _n(vm, "windows"),
    "license_redhat":     lambda vm, pw: _n(vm, "rhel"),
    "license_suse":       lambda vm, pw: _n(vm, "suse"),
    "mgmt_os_windows":    lambda vm, pw: _n(vm, "windows"),
    "mgmt_os_linux":      lambda vm, pw: _n(vm, "rhel") + _n(vm, "suse") + _n(vm, "free"),
    "mgmt_os_sap":        lambda vm, pw: _n(pw, "suse"),
    "mgmt_os_unix":       lambda vm, pw: _n(pw, "aix"),
}

#: Panels backed by guest-OS telemetry. Exported so the inventory service can
#: exempt them from unit-mismatch suspicion.
LICENCE_OS_PANEL_FAMILIES: frozenset[str] = frozenset(_PANEL_SOURCES)


def power_os_tally(ostypes: Any) -> dict[str, int]:
    """Bucket HMC ostype strings into {suse, aix, other}.

    Power's label is its own vocabulary — 'Linux - SUSE', 'AIX', 'AIX/Linux',
    'Linux', 'Unknown' — so it is read directly rather than through the guest-OS
    classifier. 'AIX/Linux' is dual-boot capable and counted as AIX, the licensable
    side. Anything unrecognised lands in `other` and is never billed.
    """
    out = {"suse": 0, "aix": 0, "other": 0}
    for raw in ostypes or ():
        s = (raw or "").strip().lower()
        if "suse" in s or "sles" in s:
            out["suse"] += 1
        elif "aix" in s:
            out["aix"] += 1
        else:
            out["other"] += 1
    return out


def _n(tally: Mapping[str, Any] | None, key: str) -> int:
    try:
        return int((tally or {}).get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def detected_total_for_panel(
    panel_key: str,
    vm_tally: Mapping[str, Any] | None,
    power_tally: Mapping[str, Any] | None,
) -> int | None:
    """Detected guest count backing ``panel_key``, or None if it is not an OS panel.

    A bound panel with no detections returns 0, not None: the telemetry ran and
    found nothing, which is a different statement from "no telemetry exists".
    """
    fn = _PANEL_SOURCES.get(panel_key)
    if fn is None:
        return None
    return fn(vm_tally or {}, power_tally or {})
