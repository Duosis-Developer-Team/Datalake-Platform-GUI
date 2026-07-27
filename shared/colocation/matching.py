"""Resolve rack-installed device tenants to CRM customers → per-customer
colocation footprint. Device tenant_name is the only reliable physical→customer
signal (rack.tenant_name is ~4% populated); Bulutistan-internal tenants are
excluded via occupancy.is_internal_tenant."""
from __future__ import annotations

from typing import Sequence

from shared.colocation.occupancy import is_internal_tenant


def build_customer_footprint(
    tenant_rows: Sequence[dict],
    alias_by_key: dict[str, dict],
    internal_prefixes=None,
) -> list[dict]:
    """Group EXACT per-(rack, tenant) U rows into per-customer footprints.

    tenant_rows: rows from ``occupancy.tenant_occupancy_rows`` — one per
    ``(dc, rack_name, tenant_name)`` carrying an exact per-tenant ``used_u``
    (COUNT DISTINCT U-slot). alias_by_key: {lowercased tenant string ->
    {crm_accountid, crm_account_name}}. Bulutistan-internal tenants excluded.
    internal_prefixes: forwarded to ``is_internal_tenant``; ``None`` means the
    built-in tuple, anything else REPLACES it (see is_internal_tenant).

    ``used_u`` is exact and additive: a rack shared by two external tenants
    contributes each tenant's own U (not the whole rack to both), so the
    per-customer totals sum correctly. Untagged devices carry no tenant, so the
    (large) share of physical used-U with no owner in NetBox is intentionally
    absent here — this is per-customer occupancy, not a rack total.
    """
    by_tenant: dict[str, dict] = {}
    for row in tenant_rows or []:
        tenant = row.get("tenant_name")
        if not tenant or is_internal_tenant(tenant, internal_prefixes):
            continue
        dc = row.get("dc")
        rack_name = row.get("rack_name")
        used = int(row.get("used_u") or 0)
        entry = by_tenant.get(tenant)
        if entry is None:
            alias = alias_by_key.get(tenant.strip().lower()) or {}
            entry = {
                "tenant": tenant,
                "crm_accountid": alias.get("crm_accountid"),
                "crm_account_name": alias.get("crm_account_name"),
                "match_status": "matched" if alias.get("crm_accountid") else "unmatched",
                "racks": [],
                "used_u": 0,
                "dc": dc,
            }
            by_tenant[tenant] = entry
        if rack_name and rack_name not in entry["racks"]:
            entry["racks"].append(rack_name)
        entry["used_u"] += max(used, 0)
    return sorted(by_tenant.values(), key=lambda e: (-e["used_u"], e["tenant"]))


def build_internal_footprint(tenant_rows: Sequence[dict], internal_prefixes=None) -> list[dict]:
    """Group EXACT per-(rack, tenant) U rows for Bulutistan-INTERNAL tenants into
    per-resource footprints. Mirror of build_customer_footprint but keeps only
    internal tenants (is_internal_tenant) and carries no CRM columns — internal
    gear does not map to a CRM account. Untagged/blank tenants are excluded.
    internal_prefixes: forwarded to ``is_internal_tenant``; ``None`` means the
    built-in tuple, anything else REPLACES it (see is_internal_tenant).
    """
    by_tenant: dict[str, dict] = {}
    for row in tenant_rows or []:
        tenant = row.get("tenant_name")
        if not tenant or not is_internal_tenant(tenant, internal_prefixes):
            continue
        rack_name = row.get("rack_name")
        used = int(row.get("used_u") or 0)
        entry = by_tenant.get(tenant)
        if entry is None:
            entry = {"tenant": tenant, "racks": [], "used_u": 0, "dc": row.get("dc")}
            by_tenant[tenant] = entry
        if rack_name and rack_name not in entry["racks"]:
            entry["racks"].append(rack_name)
        entry["used_u"] += max(used, 0)
    return sorted(by_tenant.values(), key=lambda e: (-e["used_u"], e["tenant"]))
