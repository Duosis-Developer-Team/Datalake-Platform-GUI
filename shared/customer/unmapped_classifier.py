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

from shared.customer import match as alias_match

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

    ``kind`` is one of ``shared.customer.match.ALL_METHODS``. The semantics live
    in that module so this path and the SQL path cannot drift apart; it is
    applied case-insensitively to the raw name (like ILIKE), NOT the folded key.
    """

    owner: str
    kind: str
    value: str

    def matches(self, name_lower: str) -> bool:
        return alias_match.predicate(self.kind, self.value)(name_lower)


@dataclass(frozen=True)
class UnmappedRow:
    name: str
    guessed_owner: str | None
    reason: str  # 'alias_gap' | 'orphan'
    guessed_owner_id: str | None = None
    suggested_alias: str | None = None


def is_system_vm(name: str, system_prefixes: Sequence[str] = DEFAULT_SYSTEM_PREFIXES) -> bool:
    nl = name.strip().lower()
    return any(nl.startswith(p) for p in system_prefixes)


def guess_owner_key(name: str, account_keys: Mapping[str, str]) -> str | None:
    """Best-effort *account key* for an unmatched name.

    1. Exact key match on the prefix before the first '-' (strong: the
       ``<Customer>-<VMname>`` convention).
    2. Fallback for dash-less names: the longest account key that the folded
       full name starts with (handles ``Deneme_Kredi_LOG_Server``).

    Returns the folded key, or ``None``. The *key* is returned rather than the
    display name because callers need it to look up the CRM account id too;
    the display name is one lookup away via ``account_keys[key]``.
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
        return pkey

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
    return best_key or None


def alias_suggestion(name: str) -> str | None:
    """The alias value the one-click action writes: the prefix before the first '-'.

    Deliberately narrow. Widening it to the *matched account key* would bind
    machines the operator cannot see on screen; widening a rule later from the
    aliases page is cheaper than discovering an over-claiming one.

    A dash-less name yields the whole name, so the rule binds exactly that one
    machine — better than inventing a cut point.
    """
    raw = (name or "").strip()
    if not raw:
        return None
    return raw.split("-", 1)[0] if "-" in raw else raw


# data_source keys whose rules claim VM names (Phase 1 scope).
VM_OWNER_SOURCES: tuple[str, ...] = ("virtualization", "netbox_vm_customer")

# data_source keys whose rules claim backup policy names. A policy claimed by
# any of them is somebody's, regardless of which backup product it was written
# for, so all three gate the worklist.
BACKUP_OWNER_SOURCES: tuple[str, ...] = (
    "backup_netbackup", "backup_veeam", "backup_zerto",
)


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
        source = str(row.get("data_source") or "")
        method = str(row.get("match_method") or alias_match.DEFAULT_METHOD).strip().lower()
        if not alias_match.is_allowed(source, method):
            # An id_exact rule on a name source claims nothing — mirroring the
            # SQL side, which drops it. Silently rewriting it to `contains` made
            # every name containing the id vanish from Unmapped while the
            # customer view showed none of them either.
            continue
        owner = str(row.get("crm_account_name") or row.get("crm_accountid") or "")
        matchers.append(OwnerMatcher(owner=owner, kind=method, value=value))
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


def account_ids_from_rows(rows: Iterable[Mapping[str, object]]) -> dict[str, str]:
    """norm(account_name) -> crm accountid, first-writer-wins.

    Kept parallel to account_keys_from_names() rather than merged into it: the
    22 existing classifier tests build key maps from bare name lists, and the
    SQL path has callers that never select accountid.
    """
    ids: dict[str, str] = {}
    for row in rows:
        name = str(row.get("name") or "").strip()
        accountid = str(row.get("accountid") or "").strip()
        if not name or not accountid:
            continue
        k = norm(name)
        if k and k not in ids:
            ids[k] = accountid
    return ids


_REASON_ORDER = {"alias_gap": 0, "ambiguous": 1, "orphan": 2}


def build_unmapped_payload(
    names_with_platform: Iterable[tuple[str, str]],
    owners: Sequence[OwnerMatcher],
    account_keys: Mapping[str, str],
    system_prefixes: Sequence[str] = DEFAULT_SYSTEM_PREFIXES,
    account_ids: Mapping[str, str] | None = None,
    policies: Iterable[str] | None = None,
    policy_index: Mapping[str, list[tuple[str, str]]] | None = None,
    backup_owners: Sequence[OwnerMatcher] | None = None,
) -> dict[str, object]:
    """Full response payload: sorted rows (+platform) and reason counts.

    alias_gap rows sort first (they are the actionable worklist), then
    ambiguous (resolved by hand), then orphan (nothing to resolve), then by
    guessed owner, then name.
    """
    name_platform: dict[str, str] = {}
    for name, platform in names_with_platform:
        if name and name not in name_platform:
            name_platform[name] = platform or ""

    classified = classify_unmapped(
        name_platform.keys(), owners, account_keys, system_prefixes, account_ids
    )
    rows = [
        {
            "name": r.name,
            "platform": name_platform.get(r.name, ""),
            "guessed_owner": r.guessed_owner,
            "guessed_owner_id": r.guessed_owner_id,
            "suggested_alias": r.suggested_alias,
            "suggested_method": "prefix" if r.suggested_alias else None,
            "reason": r.reason,
            "kind": "vm",
        }
        for r in classified
    ]
    if policies is not None and policy_index is not None:
        rows.extend(classify_unmapped_policies(
            policies,
            backup_owners if backup_owners is not None else owners,
            policy_index,
        ))
    rows.sort(key=lambda d: (
        _REASON_ORDER.get(str(d["reason"]), 9),
        (d.get("guessed_owner") or "").casefold(),
        str(d["name"]).casefold(),
    ))
    return {
        "rows": rows,
        "total": len(rows),
        "alias_gap_count": sum(1 for d in rows if d["reason"] == "alias_gap"),
        "orphan_count": sum(1 for d in rows if d["reason"] == "orphan"),
        "ambiguous_count": sum(1 for d in rows if d["reason"] == "ambiguous"),
    }


def classify_unmapped(
    names: Iterable[str],
    owners: Sequence[OwnerMatcher],
    account_keys: Mapping[str, str],
    system_prefixes: Sequence[str] = DEFAULT_SYSTEM_PREFIXES,
    account_ids: Mapping[str, str] | None = None,
) -> list[UnmappedRow]:
    """Return one row per name owned by nobody (system VMs excluded, not returned).

    Order preserved; duplicates preserved (caller de-dupes names upstream).
    """
    ids = account_ids or {}
    rows: list[UnmappedRow] = []
    for name in names:
        if not name or not name.strip() or not norm(name):
            continue  # skip empties and punctuation-only junk ('-', '---')
        if is_system_vm(name, system_prefixes):
            continue
        name_lower = name.strip().lower()
        if any(m.matches(name_lower) for m in owners):
            continue
        key = guess_owner_key(name, account_keys)
        rows.append(UnmappedRow(
            name=name,
            guessed_owner=account_keys[key] if key else None,
            reason="alias_gap" if key else "orphan",
            guessed_owner_id=ids.get(key) if key else None,
            suggested_alias=alias_suggestion(name) if key else None,
        ))
    return rows


def classify_unmapped_policies(
    policies: Iterable[str],
    owners: Sequence[OwnerMatcher],
    policy_index: Mapping[str, list[tuple[str, str]]],
) -> list[dict[str, object]]:
    """Backup policies owned by nobody, split into gap / ambiguous / orphan.

    ``ambiguous`` is a third outcome the VM path does not have: a 4-char token
    can address two customers (``avro`` → AVROMED and AVRORA LLC), and 27% of
    live policies do. Those rows name no owner and offer no action — binding
    backup capacity to the wrong customer reaches billing and capacity
    reports, which is worse than leaving the row unresolved.
    """
    from shared.customer.backup_policy import guess_policy_owner

    rows: list[dict[str, object]] = []
    for policy in policies:
        name = (policy or "").strip()
        if not name or not norm(name):
            continue
        name_lower = name.lower()
        if any(m.matches(name_lower) for m in owners):
            continue

        hit = guess_policy_owner(name, policy_index)
        token, candidates = hit if hit else (None, [])

        if len(candidates) == 1:
            owner, accountid = candidates[0]
            reason, suggested = "alias_gap", token
        elif len(candidates) > 1:
            owner, accountid = None, None
            reason, suggested = "ambiguous", None
        else:
            owner, accountid = None, None
            reason, suggested = "orphan", None

        rows.append({
            "name": name,
            "platform": "netbackup",
            "guessed_owner": owner,
            "guessed_owner_id": accountid,
            "suggested_alias": suggested,
            "suggested_method": "prefix" if suggested else None,
            "reason": reason,
            "kind": "backup",
            "candidate_count": len(candidates),
        })
    return rows
