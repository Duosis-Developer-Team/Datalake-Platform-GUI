"""NetBackup policy name → CRM account, via the naming standard (pure, no DB).

Derived from ``backup-musteri-isim.xlsx`` (sheet AD-KARŞILIĞI: 189 customers,
233 policy tokens) and validated against 1,294 live policy names:

    <first4(word1)>[-<first4(word2)>]-<workload>-<env>-<type>

Turkish-folded, lowercase. 215 of the sheet's 233 tokens (92%) follow it;
the rest are consonant squeezes (``trkn`` ← Turkon) or unrelated codes
(``visa01``), which no rule derives — the spreadsheet is the authority there
and is loaded separately as a seed.

The standard alone is NOT sufficient to assign an owner: matching all 1,294
live policies against 2,668 CRM accounts leaves 27% matching more than one
account (``avro`` → AVROMED and AVRORA LLC). guess_policy_owner() therefore
returns *every* candidate and refuses to choose; callers surface the ambiguity
rather than guessing.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable, Mapping

from shared.customer.unmapped_classifier import norm

# Legal-form and generic words that are not part of the trading name and never
# contribute a policy token. Folded (norm()) before comparison.
_NAME_STOPWORDS: frozenset[str] = frozenset({
    "anonim", "sirketi", "sirket", "limited", "ltd", "sti",
    "as", "ve", "tic", "ticaret", "san", "sanayi",
})

_WORD_SPLIT = re.compile(r"[^0-9A-Za-zçğıöşüÇĞİÖŞÜ]+")

# Token length the standard uses per word.
_TOKEN_LEN = 4

# Shortest token trusted on its own. Below this a token claims far too much.
_MIN_TOKEN = 3


def _name_words(name: str) -> list[str]:
    """Folded, stopword-free words of an account name, in order."""
    words = [norm(w) for w in _WORD_SPLIT.split(name or "")]
    return [w for w in words if w and w not in _NAME_STOPWORDS]


def policy_tokens_for_account(name: str) -> set[str]:
    """Every policy prefix this account plausibly owns under the standard."""
    words = _name_words(name)
    if not words:
        return set()

    tokens: set[str] = set()
    head = words[0][:_TOKEN_LEN]

    if len(words) > 1:
        tail = words[1][:_TOKEN_LEN]
        if len(head) >= _MIN_TOKEN and tail:
            tokens.add(f"{head}-{tail}")
    if len(head) >= _TOKEN_LEN:
        tokens.add(head)
    # 'Aksular' appears in live data both as 'aksu' and in full.
    if len(words[0]) > _TOKEN_LEN:
        tokens.add(words[0])
    return tokens


def build_policy_index(
    accounts: Iterable[Mapping[str, object]],
) -> dict[str, list[tuple[str, str]]]:
    """token -> [(display_name, accountid)], each list sorted by display name.

    Sorted so an ambiguous match reports its candidates in the same order on
    every run; dict iteration order would otherwise leak into the UI.
    """
    index: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in accounts:
        name = str(row.get("name") or "").strip()
        accountid = str(row.get("accountid") or "").strip()
        if not name or not accountid:
            continue
        for token in policy_tokens_for_account(name):
            index[token].add((name, accountid))
    return {t: sorted(v) for t, v in index.items()}


def guess_policy_owner(
    policy: str,
    index: Mapping[str, list[tuple[str, str]]],
) -> tuple[str, list[tuple[str, str]]] | None:
    """(matched_token, candidates) for a policy name, or None.

    Tries the two-segment token first (``abc-dete``), then the single segment
    (``avro``): the longer prefix is the more specific claim. Matching is on
    whole dash-separated segments, so ``abc`` never claims ``abcdef-prd``.

    Returns every candidate for the winning token. A caller that picks one
    when there are several will bind backup capacity to the wrong customer,
    which reaches billing — the ambiguity is surfaced instead.
    """
    cleaned = (policy or "").strip().lower()
    if not cleaned:
        return None

    segments = cleaned.split("-")
    candidates_by_length = []
    if len(segments) >= 2:
        candidates_by_length.append("-".join(segments[:2]))
    candidates_by_length.append(segments[0])

    for token in candidates_by_length:
        owners = index.get(token)
        if owners:
            return token, list(owners)
    return None
