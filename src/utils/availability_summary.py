"""Pure helpers to summarise AuraNotify outage records for the availability tab."""
from __future__ import annotations


def _duration(rec: dict) -> int:
    try:
        return int(rec.get("duration_minutes") or 0)
    except (TypeError, ValueError):
        return 0


def _is_unplanned(rec: dict) -> bool:
    return "plansız" in str(rec.get("type") or "").casefold()


def summarize_outages(service_downtimes: list, vm_downtimes: list) -> dict:
    svc = [r for r in (service_downtimes or []) if isinstance(r, dict)]
    vm = [r for r in (vm_downtimes or []) if isinstance(r, dict)]
    events = svc + vm
    unplanned = sum(1 for r in events if _is_unplanned(r))
    planned = sum(
        1 for r in events if str(r.get("type") or "").strip() and not _is_unplanned(r)
    )
    locations = sorted(
        {
            str(r.get("group_name") or r.get("cluster") or "").strip()
            for r in events
            if str(r.get("group_name") or r.get("cluster") or "").strip()
        }
    )
    return {
        "total_outages": len(events),
        "service_outages": len(svc),
        "vm_outages": len(vm),
        "total_downtime_min": sum(_duration(r) for r in events),
        "unplanned_count": unplanned,
        "planned_count": planned,
        "longest": max(events, key=_duration) if events else None,
        "locations": locations,
    }


def format_downtime(minutes) -> str:
    if minutes is None:
        return "-"
    try:
        m = int(minutes)
    except (TypeError, ValueError):
        return "-"
    if m < 60:
        return f"{m} dk"
    if m < 1440:
        return f"{m / 60:.1f} sa".replace(".", ",")
    return f"{m / 1440:.1f} gün".replace(".", ",")
