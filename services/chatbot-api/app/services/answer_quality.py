"""Detect table-only or narrative-incomplete LLM answers."""

from __future__ import annotations

import re

_ANALIZ_RE = re.compile(r"\*\*Analiz:?\*\*", re.IGNORECASE)
_SONUC_RE = re.compile(r"\*\*Sonuç:?\*\*", re.IGNORECASE)
_TABLE_ROW_RE = re.compile(r"^\|.*\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|\s*$")
_WORD_RE = re.compile(r"\w+", re.UNICODE)

NARRATIVE_RETRY_PROMPT = (
    "Önceki cevabın yalnızca tablo içeriyordu veya **Analiz** / **Sonuç** bölümleri eksikti. "
    "Türkçe, insani bir yönetici özeti yaz: önce **Analiz** (en az 2 cümle), sonra **Sonuç** "
    "(1-3 cümle). Kritik sayıları cümle içinde ver. Markdown tablo KULLANMA."
)

NARRATIVE_RETRY_STRICT_PROMPT = (
    "Hâlâ tablo veya çok kısa cevap verdin. Yalnızca paragraf halinde Türkçe yaz. "
    "Mutlaka **Analiz:** (en az 3 cümle) ve **Sonuç:** (en az 2 cümle) olsun. "
    "Pipe karakteri (|) ve markdown tablo satırı kullanma. Sayıları cümle içinde ver."
)


def _prose_word_count(text: str) -> int:
    """Count words outside markdown table rows."""
    words = 0
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s or _TABLE_ROW_RE.match(s) or _TABLE_SEP_RE.match(s):
            continue
        words += len(_WORD_RE.findall(s))
    return words


def is_table_heavy(answer: str) -> bool:
    """True when markdown tables dominate and prose is too thin."""
    text = (answer or "").strip()
    if not text:
        return False
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    table_lines = sum(
        1 for ln in lines if _TABLE_ROW_RE.match(ln) or _TABLE_SEP_RE.match(ln)
    )
    if table_lines <= 2:
        return False
    prose_words = _prose_word_count(text)
    data_rows = max(0, table_lines - 2)
    if data_rows >= 4 and prose_words < 80:
        return True
    return prose_words < 50 and table_lines / len(lines) > 0.35


def is_narrative_incomplete(answer: str) -> bool:
    """True when the answer lacks required prose sections or is table-dominated."""
    text = (answer or "").strip()
    if not text:
        return True
    if text.lstrip().startswith("|"):
        return True
    if is_table_heavy(text):
        return True
    has_analiz = bool(_ANALIZ_RE.search(text))
    has_sonuc = bool(_SONUC_RE.search(text))
    if has_analiz and has_sonuc and not is_table_heavy(text):
        if _prose_word_count(text) >= 12:
            return False
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return True
    table_lines = sum(1 for ln in lines if _TABLE_ROW_RE.match(ln))
    if table_lines and table_lines / len(lines) > 0.5:
        return True
    return True
