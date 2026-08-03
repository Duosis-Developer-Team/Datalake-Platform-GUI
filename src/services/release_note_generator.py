"""Release note üretim merdiveni.

Basamaklar:
  1. Birincil model.
  2. Somut şikayetle onarım turu (modele tam olarak neyi yanlış yaptığı söylenir).
  3. Katı mod. chatbot-api'nin LLMClient'ı upstream hatasında zaten fallback modele düşer.
  4. Merdivenin altı: kodla yazılmış not. Bu not zaten `body`'de durduğu için ek iş gerekmez.

`body` hiçbir yolda boş kalmaz; ham commit subject'i de gövdeye hiç girmez, çünkü
deterministik not conventional prefix'i ayıklanmış özeti kullanır.
"""

from __future__ import annotations

import logging

from src.auth import versions_crud
from src.services import chatbot_client
from src.services import release_notes as rn

logger = logging.getLogger(__name__)

# (strict, şikayet üretilsin mi)
_ATTEMPTS = ((False, False), (False, True), (True, False))


def _allowed_shas(changes: list[dict]) -> set[str]:
    return {str(c.get("commit_sha") or "")[:12] for c in changes if c.get("commit_sha")}


def _complaint(raw_body, allowed: set[str]) -> str:
    """Reddedilen çıktı için modele verilecek somut gerekçe."""
    reasons: list[str] = []
    if not isinstance(raw_body, dict):
        raw_body = {}
    for bucket in rn.BUCKETS:
        items = raw_body.get(bucket)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                reasons.append("Maddeler nesne olmalı.")
                continue
            shas = [s for s in (item.get("shas") or []) if isinstance(s, str)]
            unknown = [s for s in shas if str(s)[:12] not in allowed]
            if unknown:
                reasons.append(f"Listede olmayan sha kullandın: {', '.join(unknown[:3])}.")
            if not shas:
                reasons.append("Bir maddeyi hiçbir commit'e bağlamadın.")
            if len(str(item.get("text") or "")) > rn.MAX_TEXT:
                reasons.append(f"Bir madde {rn.MAX_TEXT} karakteri aştı.")
    if not reasons:
        reasons.append("Çıktın doğrulamadan geçmedi; yalnızca sana verilen commit'leri kullan.")
    return " ".join(dict.fromkeys(reasons))[:500]


def generate_for_release(release_id: int) -> dict:
    """Notu üretir, taslağı yazar. Döner: {"status": "draft"|"auto", "headline", "body"}."""
    rel = versions_crud.get_release(release_id)
    if not rel:
        raise ValueError(f"release not found: {release_id}")

    changes = rel.get("changes") or []
    allowed = _allowed_shas(changes)
    auto_body = rn.deterministic_note(changes)

    # İnsan onaylı notu ezmeden, yayındaki gövdeyi her zaman dolu tut.
    existing = versions_crud.get_release_note(release_id)
    if existing is None or str(existing.get("source") or "auto") == "auto":
        versions_crud.upsert_note(
            release_id,
            body=auto_body,
            source="auto",
            input_fingerprint=rn.fingerprint(changes),
        )

    payload = rn.build_payload(rel, changes)
    last_raw: dict = {}
    for i, (strict, with_complaint) in enumerate(_ATTEMPTS, start=1):
        resp = chatbot_client.generate_release_note(
            payload,
            strict=strict,
            complaint=_complaint(last_raw, allowed) if with_complaint else None,
        )
        if resp.get("status") != "ok":
            logger.info("release note attempt %s failed: %s", i, resp.get("detail"))
            continue
        last_raw = resp.get("body") or {}
        clean = rn.validate_note(last_raw, allowed)
        if any(clean[b] for b in rn.BUCKETS):
            headline = resp.get("headline") or None
            versions_crud.set_draft_note(
                release_id,
                draft_headline=(str(headline)[:120] if headline else None),
                draft_body=clean,
                model=str(resp.get("model") or ""),
            )
            return {"status": "draft", "headline": headline, "body": clean}
        logger.info("release note attempt %s rejected by validator", i)

    logger.info("release %s falls back to the deterministic note", release_id)
    return {"status": "auto", "headline": None, "body": auto_body}
