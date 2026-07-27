"""Resolve a NetBox tenant string to a CRM account.

The authoritative link is the operator-maintained
``gui_crm_customer_alias.netbox_musteri_value``. It is filled by hand — the
automatic resync writes NULL there — so most customers have none, and a DC-level
"sold vs detected" line built on aliases alone would be blank for nearly everyone.

So an unaliased tenant falls back to name matching, the same heuristic Customer
View already uses in production. That is a guess, and the result records which
route produced it so the UI can say so rather than presenting a guess as a fact.

Ambiguity is resolved by refusing: if a token matches two customers, neither is
chosen. Attributing someone's licences to the wrong company is worse than leaving
the cell empty.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable

MATCH_ALIAS = "alias"
MATCH_NAME = "name"

#: Legal-form and filler words that carry no identity. Dropping them lets
#: "GAMA ENERJİ A.Ş." and a "gama_enerji" tenant meet in the middle.
_NOISE_WORDS = frozenset({
    "anonim", "sirketi", "sirket", "limited", "ltd", "sti", "as", "a", "s",
    "sanayi", "san", "ticaret", "tic", "ve", "holding", "grup", "group",
})

#: A token this short is not evidence of anything — "as", "tic" match half the
#: registry.
_MIN_TOKEN_LEN = 4


def _fold(value: str | None) -> str:
    """Lower-case, de-accent, and strip separators. Turkish dotted/dotless i is
    mapped before NFKD so 'İ' does not decompose into something unmatchable."""
    s = (value or "").replace("ı", "i").replace("İ", "i").replace("I", "i")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _tokens(value: str | None) -> list[str]:
    return [t for t in _fold(value).split() if t and t not in _NOISE_WORDS]


def _key(value: str | None) -> str:
    return "".join(_tokens(value))


def match_tenants_to_accounts(
    tenants: Iterable[str] | None,
    accounts: Iterable[tuple[str, str]] | None,
    alias_by_tenant: dict[str, str] | None,
) -> dict[str, tuple[str, str]]:
    """Return ``{tenant: (crm_accountid, how)}`` where ``how`` is alias | name.

    accounts: iterable of ``(crm_accountid, crm_account_name)``.
    Tenants that resolve to nothing are simply absent from the result.
    """
    acc_list = [(str(a or ""), str(n or "")) for a, n in (accounts or ()) if a]
    by_key: dict[str, set[str]] = {}
    by_token: dict[str, set[str]] = {}
    for aid, name in acc_list:
        k = _key(name)
        if k:
            by_key.setdefault(k, set()).add(aid)
        toks = _tokens(name)
        if toks and len(toks[0]) >= _MIN_TOKEN_LEN:
            by_token.setdefault(toks[0], set()).add(aid)

    aliases = {str(k or "").strip().lower(): v for k, v in (alias_by_tenant or {}).items()}

    out: dict[str, tuple[str, str]] = {}
    for tenant in tenants or ():
        t = str(tenant or "")
        aliased = aliases.get(t.strip().lower())
        if aliased:
            out[t] = (str(aliased), MATCH_ALIAS)
            continue

        k = _key(t)
        hit = by_key.get(k)
        if hit is None:
            toks = _tokens(t)
            if toks and len(toks[0]) >= _MIN_TOKEN_LEN:
                hit = by_token.get(toks[0])
        # Exactly one candidate, or nothing. An ambiguous token names two
        # different companies; picking either would be a coin flip with someone
        # else's licence bill.
        if hit and len(hit) == 1:
            out[t] = (next(iter(hit)), MATCH_NAME)
    return out
