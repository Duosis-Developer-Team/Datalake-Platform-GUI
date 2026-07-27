"""Guest-OS source precedence + virtualization-architecture bucketing.

One place decides two things that DC View and Customer View must agree on:

1. **Which raw guest-OS string wins** when a VM appears in more than one source.
   Live coverage measured 2026-07-27 (deduped by VM identity, vCLS excluded):

       KM (classic)          2,749 VMs   100% have a guest OS
       non-KM (hyperconv)   15,878 VMs    96%  (630 without)
       AHV (pure Nutanix)    1,531 VMs     3%  (1,483 without)

   ``vm_metrics.guest_os`` is the strongest signal for anything VMware sees:
   fresh (written every 15 min) and 100% populated. NetBox
   ``custom_fields_guest_os`` covers Nutanix-on-VMware too but is a daily
   snapshot with ~8% gaps. ``discovery_nutanix_inventory_vm.guest_os`` carries
   guestId enums (``windows9Server64Guest``) which ``os_classifier`` reads fine,
   but it rescues only a few dozen VMs in practice.

   Pure-Nutanix (AHV) VMs have no guest-OS signal in any source —
   ``nutanix_vm_metrics.guest_os`` is NULL across all 371M rows. Those VMs stay
   unknown; nothing here invents a family for them.

2. **Which architecture bucket a VM belongs to**, using the same cluster-name
   rule the DC and Customer queries already bill on (``cluster ILIKE '%KM%'``).
"""
from __future__ import annotations

from typing import Iterable

from .os_classifier import classify

ARCH_CLASSIC = "classic"
ARCH_HYPERCONVERGED = "hyperconverged"
ARCH_PURE_NUTANIX = "pure_nutanix"
ARCH_POWER = "power"

#: Buckets that come from a VMware/Nutanix cluster name, in UI display order.
VIRT_ARCHITECTURES: tuple[str, ...] = (
    ARCH_CLASSIC,
    ARCH_HYPERCONVERGED,
    ARCH_PURE_NUTANIX,
    ARCH_POWER,
)

_FAMILIES: tuple[str, ...] = ("rhel", "suse", "windows", "free", "unknown")


def empty_tally() -> dict[str, int]:
    """A fresh zeroed family tally. Callers mutate the result, so never share one."""
    return {f: 0 for f in _FAMILIES}


def arch_bucket(cluster_name: str | None) -> str:
    """Map a cluster name to its architecture bucket.

    ``KM`` is checked before ``AHV`` on purpose: the Classic/Hyperconverged split
    the platform bills on is ``cluster ILIKE '%KM%'``, so a KM cluster stays
    Classic whatever else its name says. Anything without a cluster name falls to
    hyperconverged, mirroring the existing ``NOT ILIKE '%KM%'`` queries.
    """
    name = (cluster_name or "").strip().lower()
    if "km" in name:
        return ARCH_CLASSIC
    if "ahv" in name:
        return ARCH_PURE_NUTANIX
    return ARCH_HYPERCONVERGED


def resolve_guest_os(*candidates: str | None) -> str | None:
    """First non-blank guest-OS string, in the caller's precedence order."""
    for c in candidates:
        s = (c or "").strip()
        if s:
            return s
    return None


def tally_families(raw_os_values: Iterable[str | None]) -> dict[str, int]:
    """Count licence families over raw guest-OS strings."""
    out = empty_tally()
    for raw in raw_os_values or ():
        fam = classify(raw).family
        out[fam] = out.get(fam, 0) + 1
    return out


def with_os_family(vm: dict, *, key: str = "guest_os") -> dict:
    """Stamp ``os_family`` onto a VM dict from its raw guest-OS string.

    Mutates and returns the same dict so it can wrap a list comprehension. A VM
    with no OS signal gets ``unknown`` — never a guess.
    """
    vm["os_family"] = classify(vm.get(key)).family
    return vm


def tally_vm_list(vm_list: Iterable[dict] | None) -> dict[str, int]:
    """Family tally over VM dicts that already carry ``os_family`` (or ``guest_os``).

    This is what Customer View counts on: the tally is derived from the very rows
    rendered in the VM table, so the number in the overusage row and the list a
    customer can scroll through can never disagree.
    """
    out = empty_tally()
    for vm in vm_list or ():
        fam = vm.get("os_family") or classify(vm.get("guest_os")).family
        out[fam] = out.get(fam, 0) + 1
    return out
