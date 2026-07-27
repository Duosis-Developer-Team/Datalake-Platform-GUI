"""NetBackup policy name → CRM account, via the naming standard (pure, no DB).

Derived from ``backup-musteri-isim.xlsx`` (sheet AD-KARŞILIĞI: 172 customers,
233 policy tokens) and validated against 1,294 distinct live policy names:

    <first4(word1)>[-<first4(word2)>]-<workload>-<env>-<type>

Turkish-folded, lowercase. This module reproduces 116 of the sheet's 233 tokens
(50%) exactly via the standard. The second segment is often NOT the second name
word — it is a business-unit or system code the customer chose (e.g. anku-bw,
anku-mii for Ankutsan). No rule derives those from account names. guess_policy_owner()
falls back from the two-segment token to the single-segment one when needed;
the single-segment token (first4 of word1) is what generalizes to live policies.

Against 2,687 CRM accounts and 1,294 live policies:
  - unique owner (1 candidate):  759 (59%)
  - ambiguous (2+ candidates):   360 (28%)
  - no guess (token not in index): 175 (14%)

When ambiguous, guess_policy_owner() returns *every* candidate and refuses to
choose. Picking one when there are several binds backup capacity to the wrong
customer, reaching billing and capacity reports; the ambiguity is surfaced instead.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable, Mapping

from shared.customer.unmapped_classifier import norm

# Legal-form and generic words that are not part of the trading name and never
# contribute a policy token. Folded (norm()) before comparison.
_NAME_STOPWORDS: frozenset[str] = frozenset({
    "anonim", "sirketi", "sirket", "limited", "sti",
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
    """Every policy prefix this account plausibly owns under the standard.

    Known limitations (non-derivable cases):
    - "hd holding" -> "hd-hold": head is 2 chars, below the 3-char minimum,
      so no two-segment token is emitted.
    - "Kuçükoğlu Holding" -> "kucu-oglu": the second segment splits the FIRST
      word, not the second word.
    """
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
