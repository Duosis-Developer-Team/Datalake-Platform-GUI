"""Classify infra resource names that belong to NO customer (pure, no DB).

The platform has no ``customer_id`` on infra tables; ownership is decided at
query time by name matching (``vmname ILIKE '%customer%'``). This module answers
the inverse question the platform cannot ask today — *"which resources match no
customer at all?"* — and splits the remainder into an actionable worklist:

  * ``alias_gap`` — the name's prefix loosely matches a real CRM account, but no
    mapping rule connects them yet (operator should add an alias).
  * ``orphan``    — no recognizable owner at all.

System infrastructure VMs (Nutanix CVM/PCVM, vSphere vCLS, Nutanix Svm) are not
customer resources and are excluded entirely rather than reported.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

# Nutanix Controller/Prism VMs, vSphere cluster-services VMs, Nutanix service VMs.
# Matched case-insensitively against the start of the name. Grounded in live data
# (NTNX-*-CVM, NTNX-*-PCVM, vCLS-*, Svm_*). Callers may extend this list.
DEFAULT_SYSTEM_PREFIXES: tuple[str, ...] = ("ntnx", "vcls", "svm")

# Shortest account key we trust for a no-dash startswith guess (avoids matching a
# 2-3 char account against an unrelated name).
_MIN_STARTSWITH_KEY = 4

_TR_FOLD = str.maketrans({
    "ı": "i", "İ": "i", "I": "i",
    "ş": "s", "Ş": "s",
    "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u",
    "ö": "o", "Ö": "o",
    "ç": "c", "Ç": "c",
})
_NON_ALNUM = re.compile(r"[^a-z0-9]")


def norm(s: str | None) -> str:
    """Loose key: lowercase, Turkish-fold, drop every non-alphanumeric char."""
    if not s:
        return ""
    folded = s.translate(_TR_FOLD).lower()
    return _NON_ALNUM.sub("", folded)


@dataclass(frozen=True)
class OwnerMatcher:
    """One ownership predicate mirroring a mapping rule / display-name fallback.

    ``kind`` mirrors ``sql_pattern_for_match``: contains/prefix/suffix/exact,
    applied case-insensitively to the raw name (like ILIKE), NOT the folded key.
    """

    owner: str
    kind: str
    value: str

    def matches(self, name_lower: str) -> bool:
        v = self.value.strip().lower()
        if not v:
            return False
        if self.kind == "prefix":
            return name_lower.startswith(v)
        if self.kind == "suffix":
            return name_lower.endswith(v)
        if self.kind == "exact":
            return name_lower == v
        return v in name_lower  # 'contains' (default)


@dataclass(frozen=True)
class UnmappedRow:
    name: str
    guessed_owner: str | None
    reason: str  # 'alias_gap' | 'orphan'


def is_system_vm(name: str, system_prefixes: Sequence[str] = DEFAULT_SYSTEM_PREFIXES) -> bool:
    nl = name.strip().lower()
    return any(nl.startswith(p) for p in system_prefixes)


def guess_owner(name: str, account_keys: Mapping[str, str]) -> str | None:
    """Best-effort owner for an unmatched name, using fuzzy account-name keys.

    1. Exact key match on the prefix before the first '-' (strong: the
       ``<Customer>-<VMname>`` convention).
    2. Fallback for dash-less names: the longest account key that the folded
       full name starts with (handles ``Deneme_Kredi_LOG_Server``).
    Returns the account display name, or ``None`` if nothing plausible.
    """
    raw = (name or "").strip()
    if not raw:
        return None

    prefix = raw.split("-", 1)[0] if "-" in raw else raw
    pkey = norm(prefix)
    full = norm(raw)
    if not pkey and not full:
        return None
    if pkey and pkey in account_keys:  # strong: exact <Customer>-... convention
        return account_keys[pkey]

    # Fuzzy, longest-key-wins, in both directions:
    #   dir A: account key sits at the start of the VM name  (Deneme_Kredi_LOG_Server)
    #   dir B: VM prefix is a short form of a longer legal name (Deneme_Ltd -> DENEME LTD SAN. VE TİC. A.Ş.)
    best_key = ""
    pkey_usable = len(pkey) >= _MIN_STARTSWITH_KEY
    for k in account_keys:
        if len(k) < _MIN_STARTSWITH_KEY or len(k) <= len(best_key):
            continue
        if full.startswith(k) or (pkey_usable and k.startswith(pkey)):
            best_key = k
    return account_keys[best_key] if best_key else None


# data_source keys whose rules claim VM names (Phase 1 scope).
VM_OWNER_SOURCES: tuple[str, ...] = ("virtualization", "netbox_vm_customer")


def owner_matchers_from_mappings(
    mapping_rows: Iterable[Mapping[str, object]],
    display_names: Iterable[str] = (),
    sources: Sequence[str] = VM_OWNER_SOURCES,
) -> list[OwnerMatcher]:
    """Build the ownership predicate set from webui mapping rows + display names.

    Over-claiming is the safe direction here: a resource claimable by *any*
    customer must not fall into Unmapped, so we union explicit VM rules with each
    customer's display-name fallback.
    """
    matchers: list[OwnerMatcher] = []
    for row in mapping_rows:
        if str(row.get("data_source") or "") not in sources:
            continue
        value = str(row.get("match_value") or "").strip()
        if not value:
            continue
        method = str(row.get("match_method") or "contains").strip().lower()
        kind = method if method in ("prefix", "suffix", "exact", "contains") else "contains"
        owner = str(row.get("crm_account_name") or row.get("crm_accountid") or "")
        matchers.append(OwnerMatcher(owner=owner, kind=kind, value=value))
    for name in display_names:
        n = (name or "").strip()
        if n:
            matchers.append(OwnerMatcher(owner=n, kind="contains", value=n))
    return matchers


def account_keys_from_names(names: Iterable[str]) -> dict[str, str]:
    """norm(account_name) -> display name, first-writer-wins."""
    keys: dict[str, str] = {}
    for a in names:
        k = norm(a)
        if k and k not in keys:
            keys[k] = a
    return keys


def build_unmapped_payload(
    names_with_platform: Iterable[tuple[str, str]],
    owners: Sequence[OwnerMatcher],
    account_keys: Mapping[str, str],
    system_prefixes: Sequence[str] = DEFAULT_SYSTEM_PREFIXES,
) -> dict[str, object]:
    """Full response payload: sorted rows (+platform) and reason counts.

    alias_gap rows sort first (they are the actionable worklist), then by guessed
    owner, then name.
    """
    name_platform: dict[str, str] = {}
    for name, platform in names_with_platform:
        if name and name not in name_platform:
            name_platform[name] = platform or ""

    classified = classify_unmapped(name_platform.keys(), owners, account_keys, system_prefixes)
    rows = [
        {
            "name": r.name,
            "platform": name_platform.get(r.name, ""),
            "guessed_owner": r.guessed_owner,
            "reason": r.reason,
        }
        for r in classified
    ]
    rows.sort(key=lambda d: (
        d["reason"] != "alias_gap",
        (d["guessed_owner"] or "").casefold(),
        d["name"].casefold(),
    ))
    return {
        "rows": rows,
        "total": len(rows),
        "alias_gap_count": sum(1 for d in rows if d["reason"] == "alias_gap"),
        "orphan_count": sum(1 for d in rows if d["reason"] == "orphan"),
    }


def classify_unmapped(
    names: Iterable[str],
    owners: Sequence[OwnerMatcher],
    account_keys: Mapping[str, str],
    system_prefixes: Sequence[str] = DEFAULT_SYSTEM_PREFIXES,
) -> list[UnmappedRow]:
    """Return one row per name owned by nobody (system VMs excluded, not returned).

    Order preserved; duplicates preserved (caller de-dupes names upstream).
    """
    rows: list[UnmappedRow] = []
    for name in names:
        if not name or not name.strip() or not norm(name):
            continue  # skip empties and punctuation-only junk ('-', '---')
        if is_system_vm(name, system_prefixes):
            continue
        name_lower = name.strip().lower()
        if any(m.matches(name_lower) for m in owners):
            continue
        owner = guess_owner(name, account_keys)
        rows.append(UnmappedRow(
            name=name,
            guessed_owner=owner,
            reason="alias_gap" if owner else "orphan",
        ))
    return rows
