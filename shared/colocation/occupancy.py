"""Canonical colocation rack-occupancy computation — the single source of truth.

Imported by datacenter-api (endpoints) and customer-api (dc_hosting_u sellable)
so "used vs free U" can never diverge.

Verified read-only against bulutlake 2026-07-23: over_capacity = 0 across 234
racks (total 10,745 U / used 3,998 / free 6,747).

Data model (see the TASK-62 spec §5):
  * CURRENT tables only. The legacy loki_devices/loki_racks timeseries are stale
    (last collected 2026-04-12); discovery_* is the live snapshot.
  * device->rack scoped by (rack_name, site_name): rack names are non-unique
    (182 names / 234 racks) and the two NetBox snapshots use disjoint rack_id
    spaces (0 matches), so neither rack_id nor rack_name-alone is a safe key.
  * used_u = count of distinct FRONT-face U-slots occupied. A device at U=p with
    height h occupies [p .. p+h-1]; COUNT(DISTINCT u) over generate_series caps
    at capacity and absorbs chassis-child overlaps.
"""
from __future__ import annotations

import logging
from typing import Any, Sequence

from shared.colocation.allocation import (
    NETWORK_ROLE_IDS,
    ROLE_NAMES,
    is_colocation_rack,
    resolve_rack_customer_label,
)

logger = logging.getLogger(__name__)

# One row per rack. %(dc_pattern)s: a str glob (e.g. '%DC13%') or None for all.
#
# role_id / tags / description / tenant_name (phase 2 Task B): scalar per-row
# facts straight off discovery_loki_rack, added for the allocation model (see
# shared/colocation/allocation.py). They are NOT aggregated -- each duplicate
# discovery_loki_rack row for the same physical rack carries its own values,
# and _dedupe_physical_racks below resolves the ambiguity when duplicates
# disagree (a physical rack cannot simultaneously be a generic HOST rack and
# a customer's colocation cage).
OCCUPANCY_SQL = """
WITH dev_slots AS (
    SELECT d.rack_name,
           d.site_name,
           generate_series(
               floor(d.position)::int,
               floor(d.position)::int
                   + GREATEST(COALESCE(NULLIF(dt.u_height, 0), 1), 1)::int - 1
           ) AS u,
           d.tenant_name
    FROM discovery_netbox_inventory_device d
    JOIN loki_device_types dt ON dt.id = d.device_type_id
    WHERE d.position IS NOT NULL
      AND lower(coalesce(d.face_value, 'front')) IN ('front', '')
),
rack AS (
    SELECT r.id            AS rack_id,
           r.name          AS rack_name,
           r.u_height::int AS capacity_u,
           l.site_name     AS site_name,
           l.name          AS hall,
           COALESCE(l.parent_name, l.name) AS dc,
           r.role_id       AS role_id,
           r.tags          AS tags,
           r.description   AS description,
           r.tenant_name   AS tenant_name
    FROM discovery_loki_rack r
    LEFT JOIN discovery_loki_location l ON l.id::varchar = r.location_id
)
SELECT r.rack_id,
       r.rack_name,
       r.dc,
       r.hall,
       r.capacity_u,
       COUNT(DISTINCT s.u) FILTER (WHERE s.u BETWEEN 1 AND r.capacity_u) AS used_u,
       GREATEST(
           r.capacity_u
           - COUNT(DISTINCT s.u) FILTER (WHERE s.u BETWEEN 1 AND r.capacity_u),
           0
       ) AS free_u,
       ARRAY_AGG(DISTINCT s.tenant_name)
           FILTER (WHERE s.tenant_name IS NOT NULL AND btrim(s.tenant_name) <> ''
                   AND s.u BETWEEN 1 AND r.capacity_u) AS tenants,
       r.site_name,
       r.role_id,
       r.tags,
       r.description,
       r.tenant_name
FROM rack r
LEFT JOIN dev_slots s
    ON s.rack_name = r.rack_name
   AND COALESCE(s.site_name, '') = COALESCE(r.site_name, '')
WHERE (%(dc_pattern)s IS NULL OR COALESCE(r.dc, '') ILIKE %(dc_pattern)s)
GROUP BY r.rack_id, r.rack_name, r.dc, r.hall, r.capacity_u, r.site_name,
         r.role_id, r.tags, r.description, r.tenant_name
ORDER BY r.dc, r.rack_name
"""

OCCUPANCY_COLUMNS = (
    "rack_id", "rack_name", "dc", "hall", "capacity_u", "used_u", "free_u", "tenants",
    "site_name",
    # Appended (phase 2 Task B) -- order is load-bearing, existing callers
    # index by name via row_to_dict, not position, but the SQL SELECT list
    # above must match this order 1:1.
    "role_id", "tags", "description", "tenant_name",
)

# Tenants that are Bulutistan's own infrastructure, not external colocation
# customers. Matched case-insensitively as a prefix. (Verified prod tenants:
# the "Bulutistan - *" buckets, "Bulut Broker", "CPE-Tenant", switch fabrics.)
INTERNAL_TENANT_PREFIXES = (
    "bulutistan", "bulut broker", "cpe-tenant", "dc11 arista",
)


def row_to_dict(row: Sequence[Any]) -> dict:
    """Map one OCCUPANCY_SQL row tuple to a dict with coerced numeric fields."""
    d = {col: (row[i] if i < len(row) else None) for i, col in enumerate(OCCUPANCY_COLUMNS)}
    d["capacity_u"] = int(d.get("capacity_u") or 0)
    d["used_u"] = int(d.get("used_u") or 0)
    d["free_u"] = int(d.get("free_u") or 0)
    d["tenants"] = list(d.get("tenants") or [])
    return d


def _resolve_colocation_identity(rack_name: Any, site_name: Any, colo_rows: list[dict]) -> dict:
    """Pick role_id/tags/description/tenant_name for a physical rack from its
    colocation-role (3/4) duplicate rows -- called only when ``colo_rows`` is
    non-empty.

    * Exactly one colocation-role duplicate: unambiguous, use it verbatim.
    * Two or more, all resolving (via ``resolve_rack_customer_label``) to the
      SAME customer: use any one of them (they agree; e.g. capacity or hall
      may differ but the identity does not).
    * Two or more resolving to DIFFERENT customers: a genuine conflict --
      verified against prod 2026-07-27, 4 racks ("112", "114", "116", "306")
      have duplicate colocation-role rows naming different customers (e.g.
      rack "306": a CUSTOMER-role row naming TURKONAY vs a NON-STANDART-role
      row naming SABANCI DX; rack "112": two CUSTOMER-role rows, one naming
      AKSIGORTA via description, one naming AytemizBank via tenant_name).
      There is no principled way to pick a winner from the data available --
      an ordering signal like ``first_observed`` only reflects which record
      the collector happened to paginate first within one sweep (sub-second
      apart on these rows), not which registration is authoritative. Per the
      design doc's own rule for unresolvable racks ("never dropped, never
      guessed"), a conflict resolves to UNATTRIBUTED, not to either
      candidate, and is logged with the competing values so it can be
      corrected in NetBox.

    This function decides IDENTITY ONLY. capacity_u/used_u/free_u are never
    touched here -- they keep the pure max-merge every duplicate has always
    used (see _dedupe_physical_racks), regardless of which row (if any) wins
    the colocation identity.
    """
    labels = {
        resolve_rack_customer_label(r.get("tenant_name"), r.get("tags"), r.get("description"))
        for r in colo_rows
    }
    if len(labels) > 1:
        logger.warning(
            "colocation identity conflict for rack %r/%r: %d colocation-role "
            "duplicates disagree on customer (%s) -- resolving to Unattributed. "
            "Competing rows: %s",
            rack_name, site_name, len(colo_rows), sorted(labels),
            [
                {
                    "role_id": r.get("role_id"), "tenant_name": r.get("tenant_name"),
                    "tags": r.get("tags"), "description": r.get("description"),
                }
                for r in colo_rows
            ],
        )
        return {
            "role_id": colo_rows[0].get("role_id"),
            "tags": [], "description": "", "tenant_name": None,
        }
    winner = colo_rows[0]
    return {
        "role_id": winner.get("role_id"),
        "tags": winner.get("tags"),
        "description": winner.get("description"),
        "tenant_name": winner.get("tenant_name"),
    }


def _resolve_non_colocation_role(rack_name: Any, site_name: Any, group: list[dict]) -> Any:
    """Pick ``role_id`` for a physical rack whose duplicates hold no
    colocation role -- i.e. the NETWORK/HOST split that
    ``_resolve_colocation_identity`` never sees.

    Unanimous (the overwhelming majority): that role, verbatim.

    Split: the most restrictive role wins, which here means NETWORK over
    HOST. Same reasoning as the colocation branch -- there is no authority
    signal in the data, ``first_observed`` only says which record the
    collector paginated first within one sub-second sweep -- but the
    conclusion differs because the question differs. Identity cannot be
    guessed (so a conflict becomes Unattributed), while sellability has a
    safe side: 24 racks carry conflicting role_id in prod (2026-08-04), and
    the defect being corrected is OVERstating sellable U, so a tie breaks
    toward not selling. Logged either way so NetBox can be cleaned up; the
    ambiguity is a data problem this rule contains, not one it fixes.
    """
    roles = {
        str(r.get("role_id")).strip()
        for r in group
        if r.get("role_id") is not None and str(r.get("role_id")).strip()
    }
    if len(roles) <= 1:
        return next(iter(roles), group[0].get("role_id"))

    winner = "1" if roles & NETWORK_ROLE_IDS else sorted(roles)[0]
    logger.warning(
        "rack role conflict for rack %r/%r: %d duplicates disagree on role_id "
        "(%s) -- resolving to %r (most restrictive wins; correct in NetBox).",
        rack_name, site_name, len(group), sorted(roles), winner,
    )
    return winner


def _dedupe_physical_racks(rows: Sequence[dict]) -> list[dict]:
    """Collapse duplicate ``discovery_loki_rack`` entries for the same physical
    rack so used/free U are not inflated.

    The rack table holds several rows for one physical rack — 234 rows for 188
    distinct (rack_name, site_name). Because a device joins to a rack by
    (rack_name, site_name) only (device.rack_id can't join rack.id — the two
    snapshots use disjoint id spaces), every duplicate row re-counts the *same*
    devices, so summing per rack triple-counts capacity/used/free (verified:
    "102"/ISTANBUL had 3 rows each reporting used_u=36 → 108U instead of 36U).

    We keep one row per (rack_name, site_name); a same-name rack at a different
    site is a genuinely different rack and stays separate. When duplicates
    disagree we take the max capacity + max used (the most complete count),
    recompute free, union the tenant lists, and pick the most-common dc
    (tie-break: smallest) since a name+site that spans DC labels is ambiguous.
    This max/union/vote merge is UNCHANGED by colocation identity (phase 2
    Task B) -- capacity_u/used_u/free_u/tenants/dc never depend on which
    duplicate (if any) is colocation-role. Only role_id/tags/description/
    tenant_name are resolved separately, via ``_resolve_colocation_identity``
    for the subset of duplicates that are colocation-role (3/4), and via
    ``_resolve_non_colocation_role`` for the rest.

    role_id is ALWAYS resolved by rule, never left to row order. It used to
    fall out of ``base = dict(group[0])`` for racks with no colocation-role
    duplicate, which was safe only while ``is_colocation_rack`` gated every
    read of it. It no longer is: NETWORK racks (role 1) are excluded from
    sellable U as of 2026-08-04, so an arbitrary pick between a NETWORK and a
    HOST duplicate would change the priced number between two runs over
    identical data. tags/description/tenant_name stay first-encountered for
    non-colocation racks -- those genuinely are never read outside the
    colocation branch.
    """
    groups: dict[tuple, list[dict]] = {}
    order: list[tuple] = []
    for r in rows:
        key = (r.get("rack_name"), (r.get("site_name") or ""))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)

    out = []
    for key in order:
        group = groups[key]
        base = dict(group[0])

        cap = 0
        used = 0
        tenants: list = []
        dc_votes: dict = {}
        for r in group:
            cap = max(cap, int(r.get("capacity_u") or 0))
            used = max(used, int(r.get("used_u") or 0))
            for t in (r.get("tenants") or []):
                if t not in tenants:
                    tenants.append(t)
            dc = r.get("dc")
            if dc:
                dc_votes[dc] = dc_votes.get(dc, 0) + 1
        base["capacity_u"] = cap
        base["used_u"] = used
        base["free_u"] = max(cap - used, 0)
        base["tenants"] = tenants
        if dc_votes:
            base["dc"] = min(dc_votes, key=lambda d: (-dc_votes[d], d))  # most-common, tie -> smallest

        colo_rows = [r for r in group if is_colocation_rack(r.get("role_id"))]
        if colo_rows:
            base.update(_resolve_colocation_identity(key[0], key[1], colo_rows))
        else:
            base["role_id"] = _resolve_non_colocation_role(key[0], key[1], group)

        out.append(base)
    return out


def occupancy_rows(cursor, dc_pattern: str | None = None) -> list[dict]:
    """Execute OCCUPANCY_SQL and return de-duplicated per-physical-rack dicts."""
    cursor.execute(OCCUPANCY_SQL, {"dc_pattern": dc_pattern})
    return _dedupe_physical_racks([row_to_dict(r) for r in (cursor.fetchall() or [])])


def aggregate_by_dc(rows: Sequence[dict]) -> dict:
    """Roll per-rack rows up to per-DC totals."""
    out: dict = {}
    for r in rows:
        dc = r.get("dc") or "UNKNOWN"
        agg = out.setdefault(dc, {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0})
        agg["total_u"] += int(r.get("capacity_u") or 0)
        agg["used_u"] += int(r.get("used_u") or 0)
        agg["free_u"] += int(r.get("free_u") or 0)
        agg["rack_count"] += 1
    return out


def is_internal_tenant(name: str, prefixes: Sequence[str] | None = None) -> bool:
    """True when the tenant is Bulutistan-internal (excluded from the customer view).

    `prefixes` REPLACES the built-in tuple rather than extending it — the caller
    owns the union, because the caller is the one that knows whether the
    Administration mapping table was reachable. Passing an empty sequence
    deliberately classifies nothing as internal.
    """
    active = INTERNAL_TENANT_PREFIXES if prefixes is None else prefixes
    key = (name or "").strip().lower()
    return any(key.startswith(p) for p in active)


# --- EXACT per-(rack, tenant) occupancy -------------------------------------
# OCCUPANCY_SQL rolls a rack up with ARRAY_AGG(DISTINCT tenant_name) — it keeps
# *which* tenants share a rack but discards *how many U each* holds, so the
# customer footprint could only approximate per-tenant U by the whole rack.
# This query keeps that per-U granularity: COUNT(DISTINCT front-face U-slot) per
# tenant, so a rack shared by several tenants splits into exact per-tenant U
# (additive, never exceeding the rack's real used-U). Untagged devices carry no
# tenant and are excluded at source, so they never inflate any customer (they
# also mean a large share of physical used-U is unattributable — a NetBox
# data-entry gap, not something this query can recover).
#
# FAN-OUT GUARD (why this does NOT reuse OCCUPANCY_SQL's rack join): the rack
# table's (rack_name, site_name) is NOT unique — e.g. "102"/ISTANBUL exists as
# 3 rows (discovery_loki_rack has 234 rows for 188 distinct name+site). Joining
# devices straight onto that multiplies a device's U by the number of matching
# rack rows (A101's real 16U became 32U across two DC labels). device.rack_id
# cannot join to rack.id (disjoint id spaces), so (rack_name, site_name) is the
# only link. We therefore aggregate per-tenant U at the DEVICE side first
# (tenant_rack), which has no rack fan-out, and only THEN attach a de-duplicated
# rack (one row per name+site via GROUP BY) for the capacity cap and a DC label.
# When a name+site legitimately spans DCs the DC label is ambiguous; we pick
# MIN(dc) deterministically (the per-U count stays exact regardless).
TENANT_OCCUPANCY_SQL = """
WITH dev_slots AS (
    SELECT d.rack_name,
           d.site_name,
           generate_series(
               floor(d.position)::int,
               floor(d.position)::int
                   + GREATEST(COALESCE(NULLIF(dt.u_height, 0), 1), 1)::int - 1
           ) AS u,
           d.tenant_name
    FROM discovery_netbox_inventory_device d
    JOIN loki_device_types dt ON dt.id = d.device_type_id
    WHERE d.position IS NOT NULL
      AND lower(coalesce(d.face_value, 'front')) IN ('front', '')
      AND d.tenant_name IS NOT NULL
      AND btrim(d.tenant_name) <> ''
),
tenant_rack AS (
    -- exact device-side per-tenant U per physical rack name+site (NO rack join,
    -- so no fan-out): COUNT(DISTINCT u) collapses chassis-child overlaps.
    SELECT rack_name,
           site_name,
           tenant_name,
           COUNT(DISTINCT u) AS used_u
    FROM dev_slots
    GROUP BY rack_name, site_name, tenant_name
),
rack_cap AS (
    -- one row per (rack_name, site_name): de-duplicates the multiple rack rows
    -- so the join below is 1:1 and cannot inflate used_u.
    SELECT rack_name,
           site_name,
           MAX(capacity_u) AS capacity_u,
           MIN(dc)         AS dc
    FROM (
        SELECT r.name          AS rack_name,
               l.site_name     AS site_name,
               r.u_height::int AS capacity_u,
               COALESCE(l.parent_name, l.name) AS dc
        FROM discovery_loki_rack r
        LEFT JOIN discovery_loki_location l ON l.id::varchar = r.location_id
    ) x
    GROUP BY rack_name, site_name
)
SELECT COALESCE(rc.dc, '')                                   AS dc,
       tr.rack_name,
       tr.tenant_name,
       LEAST(tr.used_u, COALESCE(rc.capacity_u, tr.used_u))  AS used_u
FROM tenant_rack tr
LEFT JOIN rack_cap rc
    ON rc.rack_name = tr.rack_name
   AND COALESCE(rc.site_name, '') = COALESCE(tr.site_name, '')
WHERE (%(dc_pattern)s IS NULL OR COALESCE(rc.dc, '') ILIKE %(dc_pattern)s)
ORDER BY dc, tr.rack_name, tr.tenant_name
"""

TENANT_OCCUPANCY_COLUMNS = ("dc", "rack_name", "tenant_name", "used_u")


def tenant_row_to_dict(row: Sequence[Any]) -> dict:
    """Map one TENANT_OCCUPANCY_SQL row tuple to a dict with coerced used_u."""
    d = {col: (row[i] if i < len(row) else None) for i, col in enumerate(TENANT_OCCUPANCY_COLUMNS)}
    d["used_u"] = int(d.get("used_u") or 0)
    return d


def tenant_occupancy_rows(cursor, dc_pattern: str | None = None) -> list[dict]:
    """Execute TENANT_OCCUPANCY_SQL and return exact per-(rack, tenant) dicts."""
    cursor.execute(TENANT_OCCUPANCY_SQL, {"dc_pattern": dc_pattern})
    return [tenant_row_to_dict(r) for r in (cursor.fetchall() or [])]


# --- Used-U breakdown: External / Internal / Untagged partition --------------
# Answers "where does the DC's used rack-U go?": each occupied front-face U-slot
# is assigned to exactly ONE group (external customer > internal Bulutistan >
# untagged) so the three counts sum to the de-duplicated used_u. Feeds the
# colocation summary bar in the DC Colocation tab and the Floor Map.
#
# Per-slot source rows (rack_name, site_name, u, tenant_name), DC-filtered and
# capacity-capped. Joins to a de-duplicated rack (one row per name+site) so the
# non-unique rack table cannot fan out a device's U (same guard as
# _dedupe_physical_racks / TENANT_OCCUPANCY_SQL).
USED_U_BREAKDOWN_SQL = """
WITH dev_slots AS (
    SELECT d.rack_name,
           d.site_name,
           generate_series(
               floor(d.position)::int,
               floor(d.position)::int
                   + GREATEST(COALESCE(NULLIF(dt.u_height, 0), 1), 1)::int - 1
           ) AS u,
           d.tenant_name
    FROM discovery_netbox_inventory_device d
    JOIN loki_device_types dt ON dt.id = d.device_type_id
    WHERE d.position IS NOT NULL
      AND lower(coalesce(d.face_value, 'front')) IN ('front', '')
),
rack_cap AS (
    SELECT rack_name,
           site_name,
           MAX(capacity_u) AS capacity_u,
           MIN(dc)         AS dc
    FROM (
        SELECT r.name          AS rack_name,
               l.site_name     AS site_name,
               r.u_height::int AS capacity_u,
               COALESCE(l.parent_name, l.name) AS dc
        FROM discovery_loki_rack r
        LEFT JOIN discovery_loki_location l ON l.id::varchar = r.location_id
    ) x
    GROUP BY rack_name, site_name
)
SELECT s.rack_name, s.site_name, s.u, s.tenant_name
FROM dev_slots s
JOIN rack_cap rc
    ON rc.rack_name = s.rack_name
   AND COALESCE(rc.site_name, '') = COALESCE(s.site_name, '')
WHERE (%(dc_pattern)s IS NULL OR COALESCE(rc.dc, '') ILIKE %(dc_pattern)s)
  AND s.u BETWEEN 1 AND rc.capacity_u
"""


def _classify_slots(rows, internal_prefixes: Sequence[str] | None = None) -> dict:
    """Partition occupied front-face U-slots into external/internal/untagged.

    rows: iterable of (rack_name, site_name, u, tenant_name). Each distinct
    (rack_name, site_name, u) slot is counted once and assigned to the
    highest-priority tenant occupying it: external (2) > internal (1) >
    untagged (0). Returns U counts per group + distinct external tenant count.

    internal_prefixes: forwarded to ``is_internal_tenant``; ``None`` means the
    built-in tuple, anything else REPLACES it (see is_internal_tenant) — same
    replace-not-extend semantics as the rest of this module.
    """
    best: dict[tuple, int] = {}
    external_names: set[str] = set()
    for rack_name, site_name, u, tenant in rows:
        key = (rack_name, site_name or "", u)
        t = (tenant or "").strip()
        if not t:
            rank = 0
        elif is_internal_tenant(t, internal_prefixes):
            rank = 1
        else:
            rank = 2
            external_names.add(t)
        if key not in best or rank > best[key]:
            best[key] = rank
    return {
        "external_u": sum(1 for r in best.values() if r == 2),
        "internal_u": sum(1 for r in best.values() if r == 1),
        "untagged_u": sum(1 for r in best.values() if r == 0),
        "external_customer_count": len(external_names),
    }


def used_u_breakdown(
    cursor, dc_pattern: str | None = None, internal_prefixes: Sequence[str] | None = None
) -> dict:
    """Execute USED_U_BREAKDOWN_SQL and return the external/internal/untagged
    used-U split (sums to the de-duplicated used_u) + external customer count.

    internal_prefixes is forwarded to ``_classify_slots`` untouched — this
    module never queries for prefixes itself, it only accepts them as an
    argument (shared/colocation stays database-free).
    """
    cursor.execute(USED_U_BREAKDOWN_SQL, {"dc_pattern": dc_pattern})
    return _classify_slots(cursor.fetchall() or [], internal_prefixes)


# --- Loki rack role catalogue ------------------------------------------------
# The Colocation Configuration screen lists the roles that actually exist in the
# live data, so a 5th role added in Loki shows up on the screen by itself
# instead of silently joining the sellable pool as an unconfigured role.
#
# Source is discovery_loki_rack, NOT loki_racks: the loki_* timeseries stopped
# collecting on 2026-04-12 (see this module's docstring) and would show a role
# set that is nearly four months stale. discovery_loki_rack carries no
# role_name, so the display name comes from allocation.ROLE_NAMES and unknown
# ids fall back to "UNKNOWN" -- which is exactly the signal the operator needs.
ROLE_CATALOG_SQL = """
SELECT role_id::text AS role_id,
       COUNT(*)      AS rack_rows
FROM   discovery_loki_rack
WHERE  role_id IS NOT NULL
GROUP BY role_id
ORDER BY role_id
"""


def role_catalog(cursor) -> list[dict]:
    """``[{role_id, role_name, rack_rows}]`` for every role present in the data.

    role_id is cast to text for the same reason allocation.py compares it as a
    string: discovery_loki_rack.role_id is a varchar and the two sides must
    agree, or a rule keyed "4" never matches a catalogue entry of 4.

    ``rack_rows`` counts RAW rows, not de-duplicated physical racks -- it is
    only here so a role with zero live racks is visibly distinguishable from
    one that carries inventory. Do not display it as a rack count; the screen
    takes its rack/capacity/free numbers from the aggregate's role_breakdown,
    which is post-dedupe.

    Builds its dicts inline rather than through row_to_dict(): that helper maps
    tuples POSITIONALLY onto OCCUPANCY_COLUMNS, so a two-column result would
    come back labelled rack_id/rack_name.
    """
    cursor.execute(ROLE_CATALOG_SQL)
    out: list[dict] = []
    for row in cursor.fetchall() or []:
        role_key = str(row[0] or "").strip()
        if not role_key:
            continue
        out.append({
            "role_id": role_key,
            "role_name": ROLE_NAMES.get(role_key, "UNKNOWN"),
            "rack_rows": int(row[1] or 0),
        })
    return out
