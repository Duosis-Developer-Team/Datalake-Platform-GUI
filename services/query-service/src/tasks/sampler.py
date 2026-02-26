"""
tasks/sampler.py — Redis Sliding Window Zaman Serisi Örnekleyici

Her SAMPLE_INTERVAL_SEC saniyede bir platform geneli CPU%, RAM% ve
toplam enerji (kW) değerlerini alır ve Redis listelerine yazar.

Redis veri yapısı:
  - LPUSH trend:<key>  <json>   → en yeni eleman en sola eklenir
  - LTRIM trend:<key>  0  MAX-1 → kaydırmalı pencere (max 30 nokta = 2.5 saat)
  - LRANGE trend:<key> 0  -1   → [en yeni, ..., en eski] sırasında okunur
                                   (neden GET /overview/trends'de tersine çevrilir)

Her liste elemanı JSON string: {"ts": "<ISO-8601>", "v": <float>}

Hata toleransı:
  - db-service cevap vermezse → warn log, sessiz geçiş, döngü devam eder.
  - Redis yazma hatası       → warn log, sessiz geçiş, döngü devam eder.
  - Sonsuz döngü iptal edilirse asyncio.CancelledError yakalanır, temiz çıkış.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI

logger = logging.getLogger(__name__)

SAMPLE_INTERVAL_SEC: int = 300   # 5 dakika
MAX_POINTS:          int = 30    # LTRIM penceresi (30 × 5dk = 2.5 saat)

# Redis key sabitleri
_KEY_CPU    = "trend:cpu_pct"
_KEY_RAM    = "trend:ram_pct"
_KEY_ENERGY = "trend:energy_kw"


async def _take_sample(
    client: httpx.AsyncClient,
    redis:  aioredis.Redis,
) -> None:
    """
    db-service'ten platform geneli CPU%, RAM% ve enerji verisini çeker,
    Redis sliding window listelerine yazar.

    cpu_pct  / ram_pct : /datacenters/summary listesindeki tüm DC'lerin
                         basit (ağırlıksız) ortalaması.
    energy_kw          : /overview  total_energy_kw alanı.

    Herhangi bir hata oluşursa sessiz geçilir (warn log); döngü durdurmaz.
    """
    ts = datetime.now(timezone.utc).isoformat()

    # ── 1. db-service'ten veri çek ────────────────────────────────────────────
    try:
        summary_resp  = await client.get("/datacenters/summary")
        overview_resp = await client.get("/overview")
        summary_resp.raise_for_status()
        overview_resp.raise_for_status()
    except httpx.RequestError as exc:
        logger.warning("Sampler: db-service erişim hatası — %s", exc)
        return
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Sampler: db-service HTTP %s — %s",
            exc.response.status_code, exc.response.text,
        )
        return

    # ── 2. Değerleri hesapla ──────────────────────────────────────────────────
    try:
        summaries = summary_resp.json()   # list[dict]
        overview  = overview_resp.json()  # dict

        if not summaries:
            logger.warning("Sampler: /datacenters/summary boş liste döndü, örnek atlandı.")
            return

        cpu_vals = [s["stats"]["used_cpu_pct"] for s in summaries if s.get("stats")]
        ram_vals = [s["stats"]["used_ram_pct"] for s in summaries if s.get("stats")]

        if not cpu_vals or not ram_vals:
            logger.warning("Sampler: stats alanı eksik, örnek atlandı.")
            return

        cpu_avg    = round(sum(cpu_vals) / len(cpu_vals), 2)
        ram_avg    = round(sum(ram_vals) / len(ram_vals), 2)
        energy_kw  = round(float(overview.get("total_energy_kw", 0.0)), 2)

    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Sampler: veri parse hatası — %s", exc)
        return

    # ── 3. Redis'e yaz (LPUSH + LTRIM) ────────────────────────────────────────
    try:
        pipe = redis.pipeline()
        for key, value in (
            (_KEY_CPU,    cpu_avg),
            (_KEY_RAM,    ram_avg),
            (_KEY_ENERGY, energy_kw),
        ):
            entry = json.dumps({"ts": ts, "v": value})
            pipe.lpush(key, entry)
            pipe.ltrim(key, 0, MAX_POINTS - 1)

        await pipe.execute()
        logger.info(
            "Sampler: örnek yazıldı — cpu=%.1f%% ram=%.1f%% energy=%.1fkW @ %s",
            cpu_avg, ram_avg, energy_kw, ts,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sampler: Redis yazma hatası — %s", exc)


async def run_sampler(app: FastAPI) -> None:
    """
    FastAPI lifespan'dan asyncio.create_task ile çağrılan sonsuz döngü.

    app.state üzerindeki mevcut httpx.AsyncClient ve aioredis.Redis
    client'larını kullanır — yeni bağlantı açmaz.

    Servis ilk ayağa kalktığında döngü başlamadan önce anında bir örnek alır;
    böylece GUI'nin 5 dakika beklemesine gerek kalmaz.
    """
    client: httpx.AsyncClient = app.state.db_client
    redis:  aioredis.Redis    = app.state.redis

    logger.info(
        "Sampler başladı — her %ds'de bir örnek alınacak (max %d nokta).",
        SAMPLE_INTERVAL_SEC, MAX_POINTS,
    )

    # ── İlk anlık örnek (döngüden önce) ──────────────────────────────────────
    await _take_sample(client, redis)

    # ── Sonsuz döngü ─────────────────────────────────────────────────────────
    try:
        while True:
            await asyncio.sleep(SAMPLE_INTERVAL_SEC)
            await _take_sample(client, redis)
    except asyncio.CancelledError:
        logger.info("Sampler durduruldu (CancelledError).")
