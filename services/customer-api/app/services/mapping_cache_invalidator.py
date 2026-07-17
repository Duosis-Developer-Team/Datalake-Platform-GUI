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


from typing import Callable, Iterable


class ResolutionError(Exception):
    """A display name could not be resolved to an account.

    Distinct from resolving to None. None means "this name belongs to no
    account" — a clean answer we can act on. This exception means "we could not
    tell", and we must never treat that as None: skipping a key we were unsure
    about is precisely how a mapping stays silently stale.
    """


@dataclass(frozen=True)
class InvalidationResult:
    deleted_count: int
    matched_names: tuple[str, ...]
    scanned_count: int


def invalidate_for_accounts(
    account_ids: set[str],
    *,
    resolve_account_id: Callable[[str], str | None],
    scan_keys: Callable[[str], Iterable[str]],
    delete_keys: Callable[[list[str]], None],
) -> InvalidationResult:
    """Delete every customer_assets key owned by any of account_ids.

    Names are read out of the cache and resolved with the read path's own
    resolver, so "which keys does this account own" is answered by the same code
    that answers "which rules build this view". They cannot drift apart.

    Raises ResolutionError if any name cannot be resolved.
    """
    if not account_ids:
        return InvalidationResult(deleted_count=0, matched_names=(), scanned_count=0)

    targets = {a for a in account_ids if a}
    resolved: dict[str, str | None] = {}
    doomed: list[str] = []
    matched: list[str] = []
    scanned = 0

    for key in scan_keys(CUSTOMER_ASSETS_SCAN_PREFIX):
        scanned += 1
        parsed = parse_customer_assets_key(key)
        if parsed is None:
            continue
        name = parsed.name
        if name not in resolved:
            resolved[name] = resolve_account_id(name)  # may raise ResolutionError
        account_id = resolved[name]
        if account_id is not None and account_id in targets:
            doomed.append(key)
            if name not in matched:
                matched.append(name)

    if doomed:
        delete_keys(doomed)

    return InvalidationResult(
        deleted_count=len(doomed),
        matched_names=tuple(matched),
        scanned_count=scanned,
    )
