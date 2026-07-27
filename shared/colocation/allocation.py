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
from typing import Any

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
