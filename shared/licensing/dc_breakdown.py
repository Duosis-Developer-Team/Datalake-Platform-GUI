"""Per-DC licensed-OS breakdown, split by virtualization architecture.

Pure — takes rows, returns a dict. DC View needs this split because a DC owner
sells capacity per architecture ("Classic is nearly full, Hyperconverged has
room"); Customer View deliberately does not split (see
services/customer-api/app/utils/licensed_os.py).

Pure Nutanix is modelled as a *gap*, not a tally. Its guests genuinely have no
guest-OS record anywhere in the datalake — nutanix_vm_metrics.guest_os is NULL
across all 371M rows and NetBox names 48 of 1,531 AHV VMs (2026-07-27). Reporting
them as ``unknown`` alongside classified guests would read as "we looked and could
not tell"; they were never observed at all. So the bucket carries a count and no
family breakdown, and the UI can say so plainly.
"""
from __future__ import annotations

from typing import Any, Iterable

from .os_classifier import LICENSED_FAMILIES, classify
from .os_source import (
    ARCH_CLASSIC,
    ARCH_HYPERCONVERGED,
    ARCH_POWER,
    ARCH_PURE_NUTANIX,
    arch_bucket,
    empty_tally,
)


#: Cap on the manual-review list. It exists to be read by a human deciding which
#: rule to add next, so it is a sample, not a dump.
_MAX_UNKNOWN_SAMPLES = 50


#: States that count as "this guest is live right now". Anything else — including
#: a missing value — is not treated as running: absent state is not evidence.
_RUNNING_STATES = frozenset({"poweredon", "running"})


def _is_running(state: str | None) -> bool:
    return (state or "").strip().lower() in _RUNNING_STATES


def _add(
    tally: dict[str, int],
    raw: str | None,
    unknown: dict[str, None],
    running_tally: dict[str, int] | None = None,
    state: str | None = None,
) -> None:
    fam = classify(raw).family
    tally[fam] = tally.get(fam, 0) + 1
    if running_tally is not None and _is_running(state):
        running_tally[fam] = running_tally.get(fam, 0) + 1
    if fam == "unknown":
        label = (raw or "").strip()
        # A blank is missing telemetry, not an unrecognised string — there is
        # nothing for a human to classify, so it is not worth reviewing.
        if label and len(unknown) < _MAX_UNKNOWN_SAMPLES:
            unknown.setdefault(label, None)


def build_dc_breakdown(
    vm_rows: Iterable[tuple] | None,
    power_rows: Iterable[tuple] | None,
    ahv_vm_count: int = 0,
) -> dict[str, Any]:
    """Assemble the DC card payload.

    vm_rows:    (cluster, vmname, guest_os) — VMware/Nutanix-on-VMware guests.
    power_rows: (lparname, ostype)          — IBM Power LPARs, HMC's own OS label.
    ahv_vm_count: pure-Nutanix guests in this DC (no OS telemetry exists for them).
    """
    buckets: dict[str, dict[str, int]] = {
        ARCH_CLASSIC: empty_tally(),
        ARCH_HYPERCONVERGED: empty_tally(),
        ARCH_POWER: empty_tally(),
    }
    running: dict[str, dict[str, int]] = {
        ARCH_CLASSIC: empty_tally(),
        ARCH_HYPERCONVERGED: empty_tally(),
        ARCH_POWER: empty_tally(),
    }
    counts: dict[str, int] = {ARCH_CLASSIC: 0, ARCH_HYPERCONVERGED: 0, ARCH_POWER: 0}
    # dict-as-ordered-set: keeps first-seen order so the review list is stable.
    unknown: dict[str, None] = {}

    for row in vm_rows or ():
        cluster, _vmname, guest_os = row[0], row[1], row[2]
        state = row[3] if len(row) > 3 else None
        bucket = arch_bucket(cluster)
        # A KM/non-KM VM can never be pure-Nutanix: vm_metrics only sees what
        # vCenter manages. Guard anyway so a stray AHV-named cluster cannot
        # silently create a fourth tally the UI does not render.
        if bucket == ARCH_PURE_NUTANIX:
            bucket = ARCH_HYPERCONVERGED
        counts[bucket] += 1
        _add(buckets[bucket], guest_os, unknown, running[bucket], state)

    for row in power_rows or ():
        ostype = row[1] if len(row) > 1 else None
        state = row[2] if len(row) > 2 else None
        counts[ARCH_POWER] += 1
        _add(buckets[ARCH_POWER], ostype, unknown, running[ARCH_POWER], state)

    totals, totals_running = empty_tally(), empty_tally()
    for tally in buckets.values():
        for fam, n in tally.items():
            totals[fam] = totals.get(fam, 0) + n
    for tally in running.values():
        for fam, n in tally.items():
            totals_running[fam] = totals_running.get(fam, 0) + n

    ahv = max(int(ahv_vm_count or 0), 0)
    return _breakdown_payload(buckets, running, counts, totals, totals_running, ahv, list(unknown))


def attribute_licences_to_dc(
    dc_vm_counts: dict[str, int] | None,
    total_vm_counts: dict[str, int] | None,
    sold_by_tenant: dict[str, dict[str, float]] | None,
) -> dict[str, int]:
    """Split each customer's CRM licence quantity across the DCs they occupy.

    CRM sells to a customer, not to a DC. A customer with guests in two DCs holds
    one quantity, so a DC-level "sold vs detected" line is only meaningful once
    that quantity is divided. The share is VM footprint in this DC over footprint
    everywhere — which makes the per-DC numbers add back up to the company total
    instead of counting the same licence once per DC.

    This is an allocation, not a fact recorded anywhere; callers must label it.
    """
    dc_counts = {str(k or "").strip().lower(): int(v or 0) for k, v in (dc_vm_counts or {}).items()}
    all_counts = {str(k or "").strip().lower(): int(v or 0) for k, v in (total_vm_counts or {}).items()}

    out: dict[str, float] = {"windows": 0.0, "rhel": 0.0, "suse": 0.0}
    for tenant, families in (sold_by_tenant or {}).items():
        key = str(tenant or "").strip().lower()
        here = dc_counts.get(key, 0)
        if here <= 0:
            continue
        everywhere = all_counts.get(key, 0)
        if everywhere <= 0:
            # No footprint recorded at all — allocating would invent a number.
            continue
        share = min(here / everywhere, 1.0)
        for fam, qty in (families or {}).items():
            if fam in out:
                out[fam] += float(qty or 0) * share

    return {fam: int(round(v)) for fam, v in out.items()}


def _breakdown_payload(buckets, running, counts, totals, totals_running, ahv, unknown_samples) -> dict[str, Any]:
    return {
        "architectures": {
            ARCH_CLASSIC: {
                "instances": counts[ARCH_CLASSIC],
                "families": buckets[ARCH_CLASSIC],
                "families_running": running[ARCH_CLASSIC],
            },
            ARCH_HYPERCONVERGED: {
                "instances": counts[ARCH_HYPERCONVERGED],
                "families": buckets[ARCH_HYPERCONVERGED],
                "families_running": running[ARCH_HYPERCONVERGED],
            },
            ARCH_PURE_NUTANIX: {"instances": ahv, "no_os_telemetry": ahv},
            ARCH_POWER: {
                "instances": counts[ARCH_POWER],
                "families": buckets[ARCH_POWER],
                "families_running": running[ARCH_POWER],
            },
        },
        "totals": {
            "families": totals,
            "families_running": totals_running,
            "licensed": sum(totals.get(f, 0) for f in LICENSED_FAMILIES),
            "instances": sum(counts.values()),
            "no_os_telemetry": ahv,
        },
        "unknown_samples": unknown_samples,
    }
