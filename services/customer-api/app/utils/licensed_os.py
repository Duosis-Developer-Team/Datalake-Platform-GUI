"""Per-customer licensed-OS tally.

Counted from the VM lists Customer View actually renders, so the number in the
Resource Overusage row and the VM table a customer can scroll through can never
disagree.

Two things this must get right:

* **No virtualization split.** DC View breaks licences down by Classic /
  Hyperconverged / Power because a DC owner sells capacity per architecture. A
  customer just has N Windows guests; where they run is not their licence
  question.
* **No double counting.** ``pure_nutanix`` is a subset of ``hyperconv`` — the
  hyperconverged query unions every ``nutanix_vm_metrics`` row for the customer
  and the pure-Nutanix query filters that same set down to AHV-only clusters. The
  buckets are therefore merged by VM name, not summed.
"""
from __future__ import annotations

from typing import Any

from shared.licensing.os_source import empty_tally, tally_vm_list

#: Asset buckets that hold licensable guests. Order is irrelevant — names are
#: deduped — but pure_nutanix is listed for the case where a VM somehow appears
#: there and nowhere else.
_GUEST_BUCKETS: tuple[str, ...] = ("classic", "hyperconv", "pure_nutanix", "power")


def customer_os_tally(assets: dict[str, Any] | None) -> dict[str, int]:
    """Licence-family counts across every licensable guest the customer owns."""
    if not assets:
        return empty_tally()

    seen: set[str] = set()
    unique: list[dict] = []
    for bucket in _GUEST_BUCKETS:
        block = assets.get(bucket) or {}
        for vm in (block.get("vm_list") or []):
            if not isinstance(vm, dict):
                continue
            key = str(vm.get("name") or "").strip().lower()
            # A VM with no name cannot be deduped; keep it rather than drop it, so
            # the count never silently shrinks.
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            unique.append(vm)
    return tally_vm_list(unique)
