"""Rack-to-colocation-customer allocation — pure functions, no DB access.

Phase 1 (occupancy.py / matching.py) derived the customer view from
``discovery_netbox_inventory_device.tenant_name``, populated on ~4% of
racks. Phase 2's measured finding (bulutlake prod, 2026-07-27) is that the
real colocation estate is a *rack* property: ``discovery_loki_rack.role_id``
names the rack's role via ``loki_racks.role_name`` (1=NETWORK RACK,
2=HOST RACK, 3=NON-STANDART RACK, 4=CUSTOMER RACK), and the customer name
lives in one of three different fields depending on the rack. Reading only
tenant_name is why Sabancı DX and Aksigorta -- two of the three largest
colocation customers -- were invisible.

See docs/superpowers/specs/2026-07-27-colocation-allocation-model-design.md
sections 1-2 and Testing for the full measured reality and rule set this
module implements.
"""
from __future__ import annotations

import json
import re
from typing import Any, Sequence

# Rack roles that mean "this rack belongs to a colocation customer", per
# loki_racks.role_name verified against prod bulutlake on 2026-07-27:
#   role_id 1 = NETWORK RACK
#   role_id 2 = HOST RACK
#   role_id 3 = NON-STANDART RACK   <- colocation
#   role_id 4 = CUSTOMER RACK        <- colocation
# discovery_loki_rack.role_id is a VARCHAR column, not an int, so role ids
# are compared as STRINGS throughout this module -- do not coerce to int
# upstream and compare numerically, the column itself never guarantees that.
COLOCATION_ROLE_IDS = frozenset({"3", "4"})

# Roles whose free U is NOT sellable inventory. Customer request 2026-08-04:
# "kabinlerde customer cabinetler U hesaplamasında dışarda tutulmalı" +
# "network kabinide aynı şekilde". Colocation racks (3/4) belong to a
# customer, so their free U is theirs; a NETWORK rack (1) holds switching
# gear the platform can never rent out. Measured against prod bulutlake
# 2026-08-04 over 188 de-duplicated racks / 8,603 U: excluding role 1 as well
# moves sellable free U from 4,477 to 3,611.
#
# This is deliberately a SEPARATE set from COLOCATION_ROLE_IDS, not a widening
# of it. The two answer different questions -- "allocated to which customer"
# vs "can this space be sold" -- and a network rack answers the second without
# answering the first. Merging them would file network racks under an
# Unattributed colocation customer and invent an allocation that does not
# exist.
NETWORK_ROLE_IDS = frozenset({"1"})
NON_SELLABLE_ROLE_IDS = COLOCATION_ROLE_IDS | NETWORK_ROLE_IDS

# loki_racks.role_name, for display only — the breakdown the page shows when
# someone asks why sellable free U is smaller than total free U.
ROLE_NAMES: dict[str, str] = {
    "1": "NETWORK",
    "2": "HOST",
    "3": "NON-STANDART",
    "4": "CUSTOMER",
}

# Bucket for a colocation-role rack whose customer name resolves to nothing
# in any of tenant_name / tags / description. 6 such racks exist in prod
# today (2026-07-27, per the design doc); they must be counted here -- never
# dropped from totals, never guessed at from partial data.
UNATTRIBUTED = "Unattributed"

# Matches "CO LOCATION" (any run of whitespace, including none, between the
# two words) or "COLOCATION" case-insensitively, ANCHORED to the end of the
# string (trailing whitespace tolerated). Because \s* already matches zero
# whitespace characters, "CO\s*LOCATION" alone matches "COLOCATION" too; the
# explicit alternation mirrors the spec's stated pattern for clarity.
#
# The trailing anchor is load-bearing, not decorative: an earlier unanchored
# version stripped the FIRST occurrence of the marker anywhere in the string,
# which mangled names where the marker isn't a suffix --
# "COLOCATION EXPRESS" became "EXPRESS" (silently discarding "COLOCATION "
# instead of rejecting the tag), and "SABANCI CO LOCATION DX" became
# "SABANCI  DX" (a double space from splicing the two remaining halves back
# together). Anchoring means a tag only ever contributes a name when the
# marker is genuinely a suffix, matching the spec's literal wording ("with
# that marker stripped from the end") and every prod tag seen to date
# (`SABANCI DX CO LOCATION`, `BOYNER CO LOCATION`); a non-suffix match now
# simply fails to match, so that tag is skipped (falls through) rather than
# producing a mangled name.
_TAG_MARKER_RE = re.compile(r"(?:CO\s*LOCATION|COLOCATION)\s*$", re.IGNORECASE)


def is_colocation_rack(role_id: Any) -> bool:
    """True when ``role_id`` names a colocation rack (NON-STANDART RACK or
    CUSTOMER RACK -- role 3 or 4).

    ``role_id`` is compared as a trimmed string against COLOCATION_ROLE_IDS
    regardless of whether the caller passes the raw varchar, an int, or a
    padded string -- discovery_loki_rack.role_id is a varchar column, so no
    assumption is made that it always arrives pre-coerced.
    """
    if role_id is None:
        return False
    return str(role_id).strip() in COLOCATION_ROLE_IDS


def is_network_rack(role_id: Any) -> bool:
    """True when ``role_id`` names a NETWORK RACK (role 1)."""
    if role_id is None:
        return False
    return str(role_id).strip() in NETWORK_ROLE_IDS


def is_sellable_rack(role_id: Any) -> bool:
    """True when free U in this rack can be sold to a new customer.

    False for roles 1/3/4 (see NON_SELLABLE_ROLE_IDS). An absent or
    unrecognised role is treated as SELLABLE, not as network: role_id is 100%
    populated in discovery_loki_rack, so the only callers that reach here
    without one are the informational aggregates that carry no role data at
    all (the Floor Map occupancy summary). Defaulting those to non-sellable
    would silently zero their free U instead of leaving it unclassified.
    """
    if role_id is None:
        return True
    return str(role_id).strip() not in NON_SELLABLE_ROLE_IDS


def sellable_rack_totals(rows: Sequence[dict]) -> tuple[float, float]:
    """``(capacity_u, used_u)`` summed over sellable racks only.

    This is the pair the sellable engine prices for ``dc_hosting_u``. Both
    sides drop non-sellable racks: leaving their capacity in ``total`` while
    counting their occupancy in ``allocated`` would inflate the CRM threshold
    budget (``total × 80% − allocated``) with space that can never be sold,
    which produces a *different* answer than simply not offering it. Measured
    2026-08-04: all-racks 8,603/2,712 yields 4,170.4 sellable U, sellable-only
    4,894/1,283 yields 2,632.2 U.
    """
    capacity = 0
    used = 0
    for row in rows or []:
        if not is_sellable_rack(row.get("role_id")):
            continue
        capacity += int(row.get("capacity_u") or 0)
        used += int(row.get("used_u") or 0)
    return float(capacity), float(used)


def _parse_tags(tags: Any) -> list[dict]:
    """Defensively parse the ``tags`` JSON value into a list of tag dicts.

    ``tags`` arrives as a JSON list already deserialized by the DB driver at
    some call sites, and as a raw JSON string at others. Anything that is
    not eventually a list of dicts -- unparseable JSON, JSON that decodes to
    something other than a list, a non-dict list element -- is treated as
    absent (empty list) rather than raised, per the spec's "parse
    defensively... treat anything malformed as absent" instruction.
    """
    if tags is None:
        return []
    if isinstance(tags, (list, tuple)):
        parsed: Any = tags
    elif isinstance(tags, str):
        try:
            parsed = json.loads(tags)
        except (ValueError, TypeError):
            return []
    else:
        return []
    if not isinstance(parsed, (list, tuple)):
        return []
    return [t for t in parsed if isinstance(t, dict)]


def _tag_customer_name(tags: Any) -> str | None:
    """First ``tags[].name`` ending in the CO LOCATION marker, with that
    trailing marker stripped, e.g. "SABANCI DX CO LOCATION" -> "SABANCI DX".
    A tag where the marker is not a trailing suffix (e.g. "COLOCATION
    EXPRESS" or "SABANCI CO LOCATION DX") does not match at all -- it is
    skipped, exactly like a tag that never mentions the marker (a bare
    "CUSTOMER" tag) -- rather than being partially stripped, which would
    either discard a legitimate leading word or splice a mid-string removal
    back together. A match that strips to nothing is likewise skipped in
    favour of the next tag in the list.
    """
    for tag in _parse_tags(tags):
        name = tag.get("name")
        if not isinstance(name, str):
            continue
        match = _TAG_MARKER_RE.search(name)
        if not match:
            continue
        remainder = name[: match.start()].strip()
        if remainder:
            return remainder
    return None


def resolve_rack_customer(
    tenant_name: str | None, tags: Any, description: str | None
) -> str | None:
    """Resolve a colocation rack's customer name. First hit wins:

    1. ``tenant_name``, trimmed
    2. a ``tags[].name`` matching the CO LOCATION marker, with that marker
       stripped from the end (see ``_tag_customer_name``)
    3. ``description``, trimmed

    Returns ``None`` when none of the three resolve to a non-blank value --
    the caller then attributes the rack to ``UNATTRIBUTED`` rather than
    dropping it or guessing a name.
    """
    if isinstance(tenant_name, str):
        stripped = tenant_name.strip()
        if stripped:
            return stripped

    tag_name = _tag_customer_name(tags)
    if tag_name:
        return tag_name

    if isinstance(description, str):
        stripped = description.strip()
        if stripped:
            return stripped

    return None


def normalize_customer_name(name: str) -> str:
    """Canonical grouping/display key for a resolved customer name, so
    "TURKONAY" and "Turkonay" collapse to one customer.

    Rule (deterministic, independent of row order): trim, collapse any run
    of internal whitespace to a single space, then upper-case. Upper-casing
    is chosen over e.g. "first name encountered wins" because the latter
    makes the displayed casing depend on which row a caller happens to
    process first -- an arbitrary, order-dependent outcome for what should
    be a stable customer label.
    """
    collapsed = re.sub(r"\s+", " ", (name or "").strip())
    return collapsed.upper()


def resolve_rack_customer_label(
    tenant_name: str | None, tags: Any, description: str | None
) -> str:
    """The single, documented way to turn a rack's raw name-bearing fields
    into its final customer label. This is the function callers (e.g. the
    allocation grouping in phase 2 Task B) should use -- not
    ``resolve_rack_customer`` and ``normalize_customer_name`` composed by
    hand.

    Resolves via ``resolve_rack_customer``, then:
      * if a name resolved, returns ``normalize_customer_name(resolved)``;
      * if nothing resolved, returns ``UNATTRIBUTED`` UNTOUCHED (not passed
        through normalisation).

    That second rule is the whole reason this function exists: writing
    ``normalize_customer_name(resolve_rack_customer(...) or UNATTRIBUTED)``
    looks correct but silently upper-cases the sentinel to "UNATTRIBUTED",
    a string that no longer equals this module's ``UNATTRIBUTED`` constant
    (``"Unattributed"``) -- every unattributed rack would then group under
    a value the caller can no longer compare against the constant, quietly
    splitting the bucket in two. This function returns the constant object
    itself in that case, so ``resolve_rack_customer_label(...) == UNATTRIBUTED``
    (and ``is UNATTRIBUTED``) always holds.
    """
    resolved = resolve_rack_customer(tenant_name, tags, description)
    if resolved is None:
        return UNATTRIBUTED
    return normalize_customer_name(resolved)


def aggregate_rack_allocations(rows: Sequence[dict]) -> dict:
    """Group occupancy rows (role_id/tags/description/tenant_name-carrying,
    per ``occupancy.occupancy_rows``) into per-colocation-customer allocation
    totals, plus the sellable-free-U base for the rest of the platform.

    Per customer (``resolve_rack_customer_label``'s output, including the
    ``UNATTRIBUTED`` bucket -- a colocation-role rack with no resolvable name
    is counted there, never dropped):

      * ``allocated_u`` -- total capacity (Σ capacity_u) of every rack
        assigned to that customer (Boyner: 312).
      * ``used_u`` -- front-face U-slots their devices occupy (Boyner: 87).
        Same per-rack ``used_u`` occupancy.py already computes; this simply
        sums it over the customer's own racks rather than by device tenant.
      * ``rack_count`` / ``racks`` -- how many/which physical racks.

    Also returns the two platform-level numbers design section 3 needs:

      * ``colocation_allocated_u`` -- Σ capacity_u over every colocation-role
        rack (named + Unattributed), i.e. the whole colocation estate.
      * ``sellable_free_u`` -- Σ free_u over racks that are SELLABLE
        (``is_sellable_rack``): not colocation-role and not NETWORK. Free U
        *inside* a colocation-role rack belongs to whichever customer holds
        that rack; free U in a network rack is switching space nobody can
        rent. Separate from ``free_u`` (unchanged, still the total across all
        racks).
      * ``sellable_capacity_u`` / ``sellable_used_u`` -- the same subset's
        capacity and occupancy, for callers that price headroom rather than
        free space (see ``sellable_rack_totals``).
      * ``network_free_u`` / ``network_capacity_u`` / ``network_rack_count``
        -- the NETWORK slice, broken out so the page can show what it removed
        instead of silently shrinking a number.
      * ``role_breakdown`` -- one entry per role actually present, each with
        role_id/role_name/sellable/rack_count/capacity_u/used_u/free_u.
        Accounts for every rack, sellable or not.

    A rack that is not colocation-role is never named or bucketed by
    customer; it contributes only to the platform-level totals above. In
    particular a NETWORK rack is non-sellable WITHOUT belonging to anyone, so
    it must not reach the per-customer view.
    """
    by_customer: dict[str, dict] = {}
    colocation_allocated_u = 0
    sellable_free_u = 0
    sellable_capacity_u = 0
    sellable_used_u = 0
    network_free_u = 0
    network_capacity_u = 0
    network_rack_count = 0
    by_role: dict[str, dict] = {}
    for row in rows or []:
        role_id = row.get("role_id")
        capacity = int(row.get("capacity_u") or 0)
        used = int(row.get("used_u") or 0)
        free = int(row.get("free_u") or 0)

        role_key = "" if role_id is None else str(role_id).strip()
        bucket = by_role.get(role_key)
        if bucket is None:
            bucket = {
                "role_id": role_key,
                "role_name": ROLE_NAMES.get(role_key, "UNKNOWN"),
                "sellable": is_sellable_rack(role_id),
                "rack_count": 0, "capacity_u": 0, "used_u": 0, "free_u": 0,
            }
            by_role[role_key] = bucket
        bucket["rack_count"] += 1
        bucket["capacity_u"] += capacity
        bucket["used_u"] += used
        bucket["free_u"] += free

        if is_sellable_rack(role_id):
            sellable_free_u += free
            sellable_capacity_u += capacity
            sellable_used_u += used
        elif is_network_rack(role_id):
            network_free_u += free
            network_capacity_u += capacity
            network_rack_count += 1

        if not is_colocation_rack(role_id):
            continue

        colocation_allocated_u += capacity

        label = resolve_rack_customer_label(
            row.get("tenant_name"), row.get("tags"), row.get("description")
        )
        entry = by_customer.get(label)
        if entry is None:
            entry = {
                "customer": label, "allocated_u": 0, "used_u": 0,
                "rack_count": 0, "racks": [],
            }
            by_customer[label] = entry
        entry["allocated_u"] += capacity
        entry["used_u"] += used
        entry["rack_count"] += 1
        rack_name = row.get("rack_name")
        if rack_name and rack_name not in entry["racks"]:
            entry["racks"].append(rack_name)

    customers = sorted(
        by_customer.values(), key=lambda e: (-e["allocated_u"], e["customer"])
    )
    # Sellable first, then by size: the page reads this top-down as "here is
    # what you can sell, here is what was taken out and why".
    role_breakdown = sorted(
        by_role.values(), key=lambda r: (not r["sellable"], -r["free_u"], r["role_id"])
    )
    return {
        "customers": customers,
        "colocation_allocated_u": colocation_allocated_u,
        "sellable_free_u": sellable_free_u,
        "sellable_capacity_u": sellable_capacity_u,
        "sellable_used_u": sellable_used_u,
        "network_free_u": network_free_u,
        "network_capacity_u": network_capacity_u,
        "network_rack_count": network_rack_count,
        "role_breakdown": role_breakdown,
    }
