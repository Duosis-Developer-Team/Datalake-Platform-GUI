"""Pure, DB-free helpers for Nutanix snapshot rows.

Customer/retention parsing, IP↔uuid resolution, row enrichment, and KPI
aggregation. Imported by the datacenter-api fetch layer and unit-tested
directly (no live DB required).
"""
from __future__ import annotations

import re

# Generic-schedule prefixes like "1Days_10RP", "1Day7RP", "2Hours-360RP" — a
# leading integer immediately followed by a time unit means "no customer".
_GENERIC_SCHEDULE_RE = re.compile(
    r"^\d+\s*(day|days|hour|hours|min|mins|week|weeks|month|months)",
    re.IGNORECASE,
)
_RP_RE = re.compile(r"(\d+)\s*RP", re.IGNORECASE)


def _looks_like_customer(prefix: str | None) -> bool:
    if not prefix:
        return False
    if _GENERIC_SCHEDULE_RE.match(prefix):
        return False
    return True


def parse_customer(protection_domain_name: str | None, vm_names: str | None = None) -> str | None:
    """Customer = token before the first '-' (customer names use '_').

    Try the protection-domain name first, then the first vm_names entry. Returns
    None if neither yields a plausible customer (these become 'Missing Entities').
    """
    for source in (protection_domain_name, vm_names):
        if not source:
            continue
        first = str(source).split(",")[0].strip()
        if "-" not in first:
            continue
        prefix = first.split("-", 1)[0].strip()
        if _looks_like_customer(prefix):
            return prefix
    return None


def parse_retention(schedule_local_max_snapshots, protection_domain_name: str | None = None) -> int | None:
    """Retention count: prefer schedule_local_max_snapshots, else parse '<n>RP'
    from the protection-domain name (e.g. '1Day_7RP' -> 7)."""
    if schedule_local_max_snapshots not in (None, 0, ""):
        try:
            return int(schedule_local_max_snapshots)
        except (TypeError, ValueError):
            pass
    if protection_domain_name:
        m = _RP_RE.search(str(protection_domain_name))
        if m:
            return int(m.group(1))
    return None


def ip_to_nutanix_uuid(ip: str | None) -> str | None:
    return f"nutanix-{ip}" if ip else None


def uuid_to_ip(nutanix_uuid: str | None) -> str | None:
    if not nutanix_uuid:
        return None
    s = str(nutanix_uuid)
    prefix = "nutanix-"
    return s[len(prefix):] if s.startswith(prefix) else s


def split_vms(vm_names: str | None) -> list[str]:
    if not vm_names:
        return []
    return [v.strip() for v in str(vm_names).split(",") if v.strip()]


def _iso(value) -> str:
    """Datetime → ISO string; passthrough for strings; '' for None."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


# Column order produced by SNAPSHOTS_BY_IPS_LATEST / SNAPSHOTS_BY_CUSTOMER_LATEST.
_SNAPSHOT_COLS = (
    "nutanix_ip", "protection_domain_name", "state", "vm_names",
    "missing_entities_entity_name", "missing_entities_entity_type",
    "schedule_type", "schedule_local_max_snapshots", "size_in_bytes",
    "start_time", "create_time", "expiry_time", "snapshot_id",
)


def enrich_snapshot_rows(raw_rows, ip_to_cluster: dict | None = None) -> tuple[list[dict], str]:
    """Turn raw SQL tuples into enriched row dicts + the latest create_time (as_of).

    Shared by the DC-scoped and customer-scoped fetchers so the enrichment lives
    in one place. `ip_to_cluster` supplies the "Cluster" column for the DC path;
    the customer path passes None (cluster left blank).
    """
    ip_to_cluster = ip_to_cluster or {}
    rows_out: list[dict] = []
    as_of = ""
    for r in raw_rows or []:
        (ip, pd_name, state, vm_names, miss_name, miss_type, sched_type,
         max_snaps, size, start_time, create_time, expiry_time, snapshot_id) = r
        create_iso = _iso(create_time)
        if create_iso > as_of:
            as_of = create_iso
        rows_out.append({
            "nutanix_ip": ip,
            "cluster": ip_to_cluster.get(ip, ""),
            "customer": parse_customer(pd_name, vm_names),
            "protection_domain_name": pd_name,
            "vm_names": vm_names,
            "state": state,
            "entity_type": miss_type,
            "missing_entity": miss_name,
            "schedule_type": sched_type,
            "retention": parse_retention(max_snaps, pd_name),
            "size_in_bytes": int(size or 0),
            "start_time": _iso(start_time),
            "create_time": create_iso,
            "expiry_time": _iso(expiry_time),
            "snapshot_id": snapshot_id,
        })
    return rows_out, as_of


def aggregate_snapshots(rows: list[dict]) -> dict:
    """KPIs + breakdowns over already-deduped latest-per-snapshot rows."""
    total_size = 0
    vm_set: set[str] = set()
    missing = 0
    sched: dict[str, int] = {}
    state: dict[str, int] = {}
    for r in rows:
        total_size += int(r.get("size_in_bytes") or 0)
        for vm in split_vms(r.get("vm_names")):
            vm_set.add(vm)
        if r.get("missing_entity"):
            missing += 1
        st = str(r.get("schedule_type") or "Unknown")
        sched[st] = sched.get(st, 0) + 1
        stt = str(r.get("state") or "Unknown")
        state[stt] = state.get(stt, 0) + 1
    return {
        "total_snapshots": len(rows),
        "total_size_bytes": total_size,
        "protected_vms": len(vm_set),
        "missing_entities": missing,
        "schedule_type_breakdown": sched,
        "state_breakdown": state,
    }
