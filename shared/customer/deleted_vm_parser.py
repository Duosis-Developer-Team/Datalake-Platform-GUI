"""Parse deletion metadata out of a deleted-VM name (pure, no DB).

Convention (live-verified 2026-07-16): an operator renames a VM to be removed with
a leading underscore and a trailing planned-deletion date:

    _<Customer>-<VMname>_Silinecek_DD_MM_YYYY

The keyword ("Silinecek") is written inconsistently (Silenecek, Sİlineek, Slinecek,
…), so we anchor on the **trailing** date, never the word. Some names carry a
second (restore) date mid-string — the trailing one is the deletion date.

Derived dates:
  * planned_date = the date in the name (scheduled deletion)
  * request_date = planned_date − 14 days (the name encodes request + 2 weeks)
  * actual deletion is observed elsewhere (when metrics stop) — not derivable here.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

# Trailing DD_MM_YYYY with any of _ - . : as separators (all seen in the wild).
_TRAILING_DATE = re.compile(r"[_\-.:](\d{1,2})[_\-.:](\d{1,2})[_\-.:](\d{4})\s*$")

_REQUEST_LEAD_DAYS = 14


@dataclass(frozen=True)
class DeletedVmInfo:
    customer: str | None
    planned_date: dt.date
    request_date: dt.date


def parse_deleted_vm(name: str | None) -> DeletedVmInfo | None:
    """Return deletion dates for a '_'-prefixed VM name, or None if not parseable.

    Only names starting with '_' are deletion-marked; a normal live VM that merely
    ends in a date is not one.
    """
    raw = (name or "").strip()
    if not raw.startswith("_") or not raw.strip("_"):
        return None

    m = _TRAILING_DATE.search(raw)
    if not m:
        return None
    day, month, year = (int(g) for g in m.groups())
    try:
        planned = dt.date(year, month, day)
    except ValueError:
        return None
    request = planned - dt.timedelta(days=_REQUEST_LEAD_DAYS)

    return DeletedVmInfo(
        customer=_extract_customer(raw),
        planned_date=planned,
        request_date=request,
    )


def _extract_customer(raw: str) -> str | None:
    """`_<Customer>-<rest>` → Customer (before the first '-'); None if no '-'."""
    body = raw.lstrip("_")
    if "-" not in body:
        return None
    prefix = body.split("-", 1)[0].strip()
    return prefix or None


# A deleted VM is considered "actually gone" once it has emitted no metrics for
# this many days (last_seen becomes the actual deletion date). Below the floor it
# is still running (planned but not yet deleted -> actual_delete_date NULL).
REGISTRY_STALE_DAYS = 3


def build_registry_row(
    platform: str,
    name: str,
    first_seen: dt.date | None,
    last_seen: dt.date | None,
    today: dt.date,
    stale_days: int = REGISTRY_STALE_DAYS,
) -> dict | None:
    """Registry upsert row for one deletion-marked VM, or None if unparseable.

    actual_delete_date = last_seen once the VM has stopped emitting for
    `stale_days`; otherwise NULL (planned but still running — the overdue case).
    """
    info = parse_deleted_vm(name)
    if info is None:
        return None
    still_emitting = last_seen is not None and (today - last_seen).days <= stale_days
    actual = None if still_emitting else last_seen
    return {
        "platform": platform,
        "vm_name": name,
        "customer": info.customer,
        "request_date": info.request_date,
        "planned_date": info.planned_date,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "actual_delete_date": actual,
    }
