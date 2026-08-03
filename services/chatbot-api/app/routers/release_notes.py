"""Release note üretimi. Stateless: DB'ye dokunmaz, durum tutmaz.

Operasyonel hatalarda HTTP 500 değil, 200 + status="failed" döner; çağıran taraf
kendi merdiveninde bir basamak ilerlesin diye.
"""

from __future__ import annotations

import json
import logging
import os
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.api_auth import verify_api_user
from app.services.llm_client import LLMError, get_llm_client

logger = logging.getLogger(__name__)
router = APIRouter()

_BUCKETS = ("added", "fixed", "improved")
_FENCE_RE = re.compile(r"```(?:json)?", re.IGNORECASE)

# Çıktı kesilirse JSON yarım kalır ve `_parse_json` None döner — yani `max_tokens`
# darsa hata "unparsable" diye görünür, "truncated" diye değil. 192 commit'lik bir
# sürümde 1200 token yetmiyordu. Kova başına 8 maddelik tavanla birlikte bu sınır
# artık gerçek bir tavan değil, yalnızca kaçak çıktıya karşı emniyet kemeri.
_MAX_TOKENS = int(os.getenv("RELEASE_NOTE_MAX_TOKENS", "4000"))

_SYSTEM = """Sen bir release note yazarısın. Okuyucun paneli kullanan bir müşteri:
kodu görmedi, commit'leri okumadı, ekibin iç kelimelerini bilmiyor.

Sana geliştiricilerin commit listesi verilir. İşin bu listeyi ÇEVİRMEK değil,
kullanıcı için ne değiştiğini ANLATMAK. Her madde şu sorunun cevabı olmalı:
"Bu değişiklikten sonra kullanıcı ne yapabiliyor ya da neyi artık yaşamıyor?"
Commit başlığını yeniden yazmak bu sorunun cevabı değildir.

Örnekler — solda kabul edilmeyen, sağda beklenen:
- "Sellable çip başlıkları ve Free/Unsold sütunları eklendi"
  -> "Kapasite tablosunda satılabilir ve boşta kalan miktarlar artık ayrı sütunlarda görünüyor."
- "Veeam sekmesinde tanımsız _kpi_strip sorunu çözüldü"
  -> "Veeam sekmesi açılırken sayfanın boş kalmasına yol açan hata giderildi."
- "Phase A/B kapsama akışı ve probe sağlık durumu eklendi"
  -> "Yedekleme kapsamı ekranında hangi sistemlerin izlendiği ve izlemenin çalışıp
     çalışmadığı görülebiliyor."
- "Replication triad için maksimum kullanım TL = max_qty x fiyat kuralı düzeltildi"
  -> "Replication hizmetinin aylık tutarı artık en yüksek kullanım üzerinden doğru hesaplanıyor."

Kurallar:
- Yalnızca JSON döndür. Açıklama, markdown, kod bloğu yok.
- Şema: {"headline": "...", "added": [...], "fixed": [...], "improved": [...]}
- Her madde şu biçimde: {"text": "...", "shas": ["<sha>"]}
- `shas` içindeki her değer, sana verilen commit listesindeki `sha` alanlarından biri OLMAK ZORUNDA.
- Bir sha'yı yalnızca tek bir maddede kullan.
- İÇ TERİM KULLANMA. Kod/dosya/tablo/sütun adı (`_kpi_strip`), fonksiyon adı, kart
  numarası (TASK-64) ve ekip içi kelimeler ("çip", "coupling", "SoT", "IA", "probe",
  "Phase A/B", "triad") yasak. Bunlar müşteriye hiçbir şey anlatmaz. Anlamını
  müşterinin ekranda gördüğü isimlerle yaz.
- Anlamı koruyarak yeniden yazabilir, birden çok commit'i tek cümlede birleştirebilirsin.
  Ama YENİ BİLGİ EKLEYEMEZSİN: sayı, yüzde, tarih, kişi adı, performans iddiası
  ("2 kat hızlandı") uydurma.
- Bir commit'in kullanıcıya ne kazandırdığını çıkaramıyorsan onu hiç yazma.
  Eksik not, yanlış nottan iyidir.
- Cümle Türkçe olsun; müşterinin üründe zaten gördüğü terimleri (panel, backup,
  snapshot, restore point, cluster) İngilizce bırak.
- Her madde en fazla 200 karakter, tek cümle; "feat:" gibi prefix içermesin.
- headline: sürümü tek cümlede özetleyen Türkçe başlık, en fazla 80 karakter.
  Kova adlarını sıralama ("yenilikler ve düzeltmeler" gibi) — sürümün asıl
  getirdiği şeyi söyle.
- Her kova en fazla 8 madde. Commit sayısı bundan fazlaysa hepsini yazma:
  kullanıcının ekranda göreceği değişiklikleri seç, birbirine yakın commit'leri
  tek maddede birleştir (birleştirdiklerinin sha'larını aynı maddede topla).
  Bu not bir changelog değil, kullanıcıya "ne değişti" diye anlatılan kısa bir özet."""

_STRICT_SUFFIX = """

KATI MOD: Kullanıcıya ne kazandırdığından emin olmadığın her maddeyi at. Kalanları
yine müşterinin diliyle yaz — kesinlik, commit başlığını kopyalamak demek değil.
Hiçbir madde güvenli değilse boş listeler döndür."""


class ReleaseChangeIn(BaseModel):
    change_type: str = "other"
    summary: str = ""
    sha: str = ""
    scope: str | None = None


class ReleaseNoteRequest(BaseModel):
    version: str
    released_at: str = ""
    changes: list[ReleaseChangeIn] = Field(default_factory=list)
    strict: bool = False
    complaint: str | None = None
    model: str | None = None


class ReleaseNoteResponse(BaseModel):
    status: str
    headline: str | None = None
    body: dict = Field(default_factory=dict)
    model: str | None = None
    detail: str | None = None


def _parse_json(answer: str) -> dict | None:
    """Model çıktısından JSON nesnesini çıkarır. Çıkaramazsa None."""
    text = _FENCE_RE.sub("", answer or "").replace("```", "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


@router.post("/generate", response_model=ReleaseNoteResponse)
async def generate(
    req: ReleaseNoteRequest, _user=Depends(verify_api_user)
) -> ReleaseNoteResponse:
    system = _SYSTEM + (_STRICT_SUFFIX if req.strict else "")
    user = json.dumps(
        {
            "version": req.version,
            "released_at": req.released_at,
            "changes": [c.model_dump() for c in req.changes],
        },
        ensure_ascii=False,
    )
    if req.complaint:
        user += (
            "\n\nÖnceki denemen şu sebeple reddedildi: "
            + req.complaint
            + "\nBu sefer aynı hatayı yapma."
        )

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        result = get_llm_client().complete(messages, model=req.model, max_tokens=_MAX_TOKENS)
    except LLMError as exc:
        logger.warning("release note generation failed (%s): %s", exc.error_type, exc.detail)
        return ReleaseNoteResponse(status="failed", detail=exc.error_type)

    parsed = _parse_json(result.answer)
    if parsed is None:
        # Cevabın uzunluğunu ve sonunu logla: `unparsable`'ın en sık sebebi çıktının
        # `max_tokens`'ta kesilmesi ve JSON'un yarım kalması. Kuyruk kapanış ayracıyla
        # bitmiyorsa sebep budur; bu bilgi olmadan hata teşhis edilemiyordu.
        answer = result.answer or ""
        logger.warning(
            "release note answer was not JSON (model=%s, chars=%s, tail=%r)",
            result.model,
            len(answer),
            answer[-120:],
        )
        return ReleaseNoteResponse(status="failed", detail="unparsable")

    headline = parsed.get("headline")
    return ReleaseNoteResponse(
        status="ok",
        headline=str(headline) if headline else None,
        body={b: (parsed.get(b) if isinstance(parsed.get(b), list) else []) for b in _BUCKETS},
        model=result.model,
    )
