"""Resolve customer names from user text using heuristics and catalog fuzzy match."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Optional

# Possessive: Boyner'in, Akbank'ın
_POSSESSIVE_RE = re.compile(
    r"\b([A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü&.\-]{1,})['’](?:in|ın|nin|nın|un|ün|nun|nün)\b"
)
# "Boyner müşterisi", "Akbank firması"
_CUSTOMER_LABEL_RE = re.compile(
    r"\b([A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü&.\-]{2,})\s+"
    r"(?:müşterisi|musterisi|firması|firmasi|şirketi|sirketi|customer)\b",
    re.IGNORECASE,
)
# Quoted names: "Boyner", 'Akbank'
_QUOTED_RE = re.compile(r"""["']([A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü&.\-\s]{2,})["']""")
# For fuzzy pass: capitalized token sequences (2+ chars)
_TOKEN_RE = re.compile(r"\b([A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü&.\-]{2,})\b")

_STOPWORDS = frozenset({
    "CRM", "DC", "CPU", "RAM", "SLA", "S3", "ITSM", "API", "GUI", "VM", "KM",
    "Datacenter", "Müşteri", "Customer", "Satış", "Sales", "Ticket", "En", "Son", "Genel",
})


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.casefold()


def extract_customer_candidates(text_raw: str, *, include_tokens: bool = True) -> list[str]:
    """Return ordered unique customer name candidates from free text."""
    text = text_raw or ""
    found: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        cleaned = (value or "").strip(" .,-")
        if len(cleaned) < 2:
            return
        key = _fold(cleaned)
        if key in seen:
            return
        seen.add(key)
        found.append(cleaned)

    for regex in (_POSSESSIVE_RE, _CUSTOMER_LABEL_RE, _QUOTED_RE):
        for match in regex.finditer(text):
            add(match.group(1))

    if include_tokens:
        for match in _TOKEN_RE.finditer(text):
            token = match.group(1)
            if token.upper() in _STOPWORDS or token in _STOPWORDS:
                continue
            if re.match(r"^(DC|AZ|ICT|UZ|DH)\d+$", token, re.IGNORECASE):
                continue
            add(token)
    return found


def _catalog_names(catalog_payload: Any) -> list[str]:
    names: list[str] = []
    if not isinstance(catalog_payload, dict):
        return names
    rows = catalog_payload.get("customers")
    if not isinstance(rows, list):
        groups = catalog_payload.get("groups")
        if isinstance(groups, dict):
            for key in ("vip", "mapped", "unmapped"):
                part = groups.get(key)
                if isinstance(part, list):
                    rows = (rows or []) + part
    if not isinstance(rows, list):
        return names
    for row in rows:
        if not isinstance(row, dict):
            continue
        for field in ("display_name", "crm_account_name"):
            val = row.get(field)
            if isinstance(val, str) and val.strip():
                names.append(val.strip())
                break
    return names


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _fold(a), _fold(b)).ratio()


def fuzzy_match_customer(
    text_raw: str,
    catalog_payload: Any,
    *,
    min_score: float = 0.72,
) -> Optional[str]:
    """Pick the best catalog customer name for text, or None."""
    catalog = _catalog_names(catalog_payload)
    if not catalog:
        return None
    candidates = extract_customer_candidates(text_raw)
    hay = _fold(text_raw)
    for name in catalog:
        folded = _fold(name)
        if folded and folded in hay:
            candidates.append(name)
    best_name: Optional[str] = None
    best_score = 0.0
    for candidate in candidates:
        for name in catalog:
            score = _similarity(candidate, name)
            if _fold(candidate) == _fold(name):
                score = 1.0
            if score > best_score:
                best_score = score
                best_name = name
    if best_name and best_score >= min_score:
        return best_name
    return None


def resolve_customer_name(
    message: str,
    *,
    selected_customer: Optional[str] = None,
    conversation_messages: Optional[list[str]] = None,
    catalog_payload: Any = None,
) -> Optional[str]:
    """Resolve customer with precedence: explicit text > context > conversation > fuzzy."""
    for candidate in extract_customer_candidates(message, include_tokens=False):
        if catalog_payload is not None:
            matched = fuzzy_match_customer(candidate, catalog_payload, min_score=0.6)
            if matched:
                return matched
        return candidate
    if selected_customer:
        return selected_customer
    for prior in reversed(conversation_messages or []):
        for candidate in extract_customer_candidates(prior, include_tokens=False):
            if catalog_payload is not None:
                matched = fuzzy_match_customer(prior, catalog_payload, min_score=0.6)
                if matched:
                    return matched
            return candidate
    if catalog_payload is not None:
        return fuzzy_match_customer(message, catalog_payload)
    return None
