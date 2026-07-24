"""Resolve rack-installed device tenants to CRM customers → per-customer
colocation footprint. Device tenant_name is the only reliable physical→customer
signal (rack.tenant_name is ~4% populated); Bulutistan-internal tenants are
excluded via occupancy.is_internal_tenant."""
from __future__ import annotations

from typing import Sequence

from shared.colocation.occupancy import is_internal_tenant


def build_customer_footprint(
    occupancy_rows: Sequence[dict],
    alias_by_key: dict[str, dict],
) -> list[dict]:
    """Group external device tenants across racks into per-customer footprints.

    alias_by_key: {lowercased tenant string -> {crm_accountid, crm_account_name}}.

    Approximation (disclosed, deliberate): per-customer ``used_u`` is the sum of
    the *whole rack's* used-U for every rack the tenant appears in, not an
    exact per-tenant U measurement. A rack shared by N external tenants has
    its used-U counted once per tenant (so the totals are not additive across
    tenants sharing a rack), and any co-located Bulutistan-internal gear in
    that rack is included in the figure too. This is a footprint overview for
    identifying who occupies which racks, not a precise per-tenant U billing
    number.
    """
    by_tenant: dict[str, dict] = {}
    for rack in occupancy_rows or []:
        rack_name = rack.get("rack_name")
        dc = rack.get("dc")
        used = int(rack.get("capacity_u") or 0) - int(rack.get("free_u") or 0)
        for tenant in rack.get("tenants") or []:
            if not tenant or is_internal_tenant(tenant):
                continue
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
