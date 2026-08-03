"""Release note üretiminin saf çekirdeği.

Bu modüldeki fonksiyonlar DB'ye ve ağa dokunmaz; hepsi aynı girdiye aynı çıktıyı verir.
Modelden gelen her şey `validate_note`'tan geçmeden hiçbir yere yazılmaz.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

BUCKETS: tuple[str, str, str] = ("added", "fixed", "improved")
MAX_TEXT = 200
_TRT = ZoneInfo("Europe/Istanbul")

# Conventional commit başlığı: tip, (scope), !, açıklama
_PREFIX_RE = re.compile(
    r"^(feat|fix|perf|chore|docs|refactor|test|style|build|ci)(\(([^)]+)\))?!?:\s*(.*)$",
    re.IGNORECASE,
)
# 7-40 karakterlik hex bloğu = sha benzeri jeton
_SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b", re.IGNORECASE)

# Okura gösterilen üç kova. Listede olmayan tip nota hiç girmez.
_TYPE_BUCKET = {"feat": "added", "fix": "fixed", "perf": "improved", "refactor": "improved"}


def parse_commit_subject(subject: str) -> tuple[str, str, str | None]:
    """('feat', 'temiz özet', 'scope'). Prefix yoksa ('other', subject, None)."""
    text = (subject or "").strip()
    m = _PREFIX_RE.match(text)
    if not m:
        return "other", text, None
    return m.group(1).lower(), m.group(4).strip(), (m.group(3) or None)


def trt_date(dt: datetime | None = None) -> date:
    """Verilen anın Europe/Istanbul takvim günü."""
    if dt is None:
        return datetime.now(_TRT).date()
    return dt.astimezone(_TRT).date()


def calver(d: date, seq: int) -> str:
    return f"{d.year}.{d.month:02d}.{seq}"


def fingerprint(changes: list[dict]) -> str:
    """Aynı commit kümesi = aynı parmak izi. Sıra fark etmez."""
    shas = sorted({str(c.get("commit_sha") or "")[:12] for c in changes or [] if c.get("commit_sha")})
    return hashlib.sha256("|".join(shas).encode("utf-8")).hexdigest()


def _empty_note() -> dict:
    return {b: [] for b in BUCKETS}


def deterministic_note(changes: list[dict]) -> dict:
    """Commit'lerden kodla yazılmış not. Asla hata vermez, asla boş sha üretmez."""
    note = _empty_note()
    for c in changes or []:
        bucket = _TYPE_BUCKET.get(str(c.get("change_type") or "").lower())
        if not bucket:
            continue
        sha = str(c.get("commit_sha") or "")[:12]
        text = str(c.get("summary") or "").strip()
        if not sha or not text:
            continue
        text = text[0].upper() + text[1:]
        note[bucket].append({"text": text[:MAX_TEXT], "shas": [sha]})
    return note


def _clean_text(text: str) -> str:
    text = _PREFIX_RE.sub(r"\4", text)
    text = _SHA_RE.sub("", text)
    text = re.sub(r"\(\s*\)|\[\s*\]", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" -–—:,;()")


def validate_note(raw, allowed_shas: set[str]) -> dict:
    """Modelin çıktısını kurallara indirger. Kurallar sırayla uygulanır.

    1. Bilinmeyen kova atılır.
    2. `allowed_shas` dışındaki sha atılır.
    3. Bir sha'yı yalnızca ilk bullet kullanabilir.
    4. 200 karakteri aşan metin düzeltilmez, atılır.
    5. Metindeki sha benzeri jetonlar ve conventional prefix temizlenir.
    6. Sha'sı kalmayan veya metni boşalan bullet atılır.
    7. Hiçbir bullet ayakta kalmadıysa boş not döner (çağıran merdivende ilerler).
    """
    clean = _empty_note()
    if not isinstance(raw, dict):
        return clean
    used: set[str] = set()
    for bucket in BUCKETS:
        items = raw.get(bucket)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_shas = item.get("shas")
            if not isinstance(raw_shas, list):
                continue
            shas = [str(s)[:12] for s in raw_shas if isinstance(s, str)]
            shas = [s for s in shas if s in allowed_shas and s not in used]
            text = str(item.get("text") or "").strip()
            if len(text) > MAX_TEXT:
                continue
            text = _clean_text(text)
            if not shas or not text:
                continue
            used.update(shas)
            clean[bucket].append({"text": text, "shas": shas})
    if not any(clean[b] for b in BUCKETS):
        return _empty_note()
    return clean


def build_payload(release: dict, changes: list[dict]) -> dict:
    """Modele gidecek gövde. Sadece bu alanlar gider; DB satırı olduğu gibi gönderilmez."""
    return {
        "version": str(release.get("version") or ""),
        "released_at": str(release.get("released_at") or "")[:10],
        "changes": [
            {
                "change_type": str(c.get("change_type") or "other"),
                "summary": str(c.get("summary") or ""),
                "sha": str(c.get("commit_sha") or "")[:12],
                "scope": c.get("scope"),
            }
            for c in changes or []
            if c.get("commit_sha")
        ],
    }
