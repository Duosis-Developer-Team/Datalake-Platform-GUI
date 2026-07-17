"""Pure mapping-cache invalidation logic.

Deliberately free of Redis, DB and FastAPI imports: every side effect is
injected, so this module is unit-testable on its own. See
docs/superpowers/specs/2026-07-17-mapping-save-invalidation-warm-design.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Key shape: customer_assets:{version}:{name}:{start}:{end}[:last_good]
#
# The name is matched greedily and the two date fields are anchored to the tail,
# because names legitimately contain colons (and spaces, dots, Turkish chars),
# and the 1h preset's timestamps contain colons too. split(":") cannot do this.
#
# The version is matched as [^:]+ rather than pinned to
# CUSTOMER_ASSETS_CACHE_VERSION: a bump to netbackup-policy-v4 is already in
# flight, and pinning would make invalidation silently match nothing after it
# lands — reintroducing the exact bug this module fixes. Matching any version
# also cleans up orphaned keys left behind by a bump.
_DATE = r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}Z)?"
KEY_RE = re.compile(
    r"^customer_assets:"
    r"(?P<version>[^:]+):"
    r"(?P<name>.+):"
    rf"(?P<start>{_DATE}):"
    rf"(?P<end>{_DATE})"
    r"(?P<shadow>:last_good)?$"
)

CUSTOMER_ASSETS_SCAN_PREFIX = "customer_assets:"


@dataclass(frozen=True)
class ParsedKey:
    version: str
    name: str
    start: str
    end: str
    is_shadow: bool


def parse_customer_assets_key(key: str) -> ParsedKey | None:
    """Split a customer_assets cache key, or return None if it is not one."""
    if not key:
        return None
    match = KEY_RE.match(key)
    if not match:
        return None
    return ParsedKey(
        version=match.group("version"),
        name=match.group("name"),
        start=match.group("start"),
        end=match.group("end"),
        is_shadow=bool(match.group("shadow")),
    )
