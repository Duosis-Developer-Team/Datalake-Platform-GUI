"""
services/query_service.py — Query-Service iş mantığı katmanı

Task 2.1: db-service'e saf proxy — httpx.AsyncClient üzerinden veri çeker
          ve shared.schemas Pydantic modelleri ile valide ederek döndürür.

Task 2.2: Provider adapter pipeline — db-service yanıtlarını zenginleştirir:
  - VMwareProvider  : cpu/ram sanity check, birim bilgisi
  - NutanixProvider : storage /2 dedup validasyonu
  - IBMProvider     : enerji caveat loglama
  - Dinamik status  : "Healthy" / "Degraded" (kullanım eşiklerine göre)

Task 2.3: Redis cache-aside — 15 dakika (900s) TTL ile önbellekleme:
  - Cache HIT  → Redis'ten oku, Pydantic modeline çevir, döndür (<1s)
  - Cache MISS → db-service'ten çek, enrich et, Redis'e yaz, döndür
  - Redis hatası → sessiz geçiş (warn log) + db-service'e düşme
"""

import json
import logging

import httpx
import redis.asyncio as aioredis
from fastapi import HTTPException, status

from shared.schemas.responses import DCDetail, DCSummary, GlobalOverview, OverviewTrends, TrendSeries
from src.providers.base import BaseProvider
from src.providers.ibm import IBMProvider
from src.providers.nutanix import NutanixProvider
from src.providers.vmware import VMwareProvider

logger = logging.getLogger(__name__)

CACHE_TTL: int = 900  # 15 dakika


class QueryService:
    """
    db-service ile iletişim, enrichment ve cache katmanı.

    Constructor:
        client: Lifespan'da oluşturulan httpx.AsyncClient (base_url ve
                X-Internal-Key header'ı önceden ayarlanmış).
        redis:  Lifespan'da oluşturulan redis.asyncio.Redis client.
    """

    def __init__(self, client: httpx.AsyncClient, redis: aioredis.Redis) -> None:
        self._client = client
        self._redis = redis
        self._providers: list[BaseProvider] = [
            VMwareProvider(),
            NutanixProvider(),
            IBMProvider(),
        ]

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_summary(self) -> list[DCSummary]:
        """
        Tüm datacenters için özet metrik listesi.
        db-service: GET /datacenters/summary → list[DCSummary]

        Task 2.2: Her DC'nin status alanı kullanım eşiklerine göre dinamik hesaplanır.
        Task 2.3: Redis cache-aside (cache key: "dc_summary_all", TTL: 900s)
        """
        key = "dc_summary_all"

        # 1. Cache hit
        try:
            cached = await self._redis.get(key)
            if cached:
                logger.debug("Cache HIT: %s", key)
                return [DCSummary.model_validate(item) for item in json.loads(cached)]
        except Exception as exc:
            logger.warning("Redis GET error on %s: %s — falling through to db-service", key, exc)

        # 2. Cache miss — db-service'ten çek + enrich
        summaries = await self._proxy_list(
            path="/datacenters/summary",
            model=DCSummary,
            label="datacenters/summary",
        )
        enriched = [
            summary.model_copy(
                update={"status": BaseProvider.calculate_status_from_stats(summary.stats)}
            )
            for summary in summaries
        ]

        # 3. Redis'e yaz
        try:
            payload = json.dumps([s.model_dump(mode="json") for s in enriched])
            await self._redis.set(key, payload, ex=CACHE_TTL)
            logger.debug("Cache MISS — stored: %s (TTL=%ds)", key, CACHE_TTL)
        except Exception as exc:
            logger.warning("Redis SET error on %s: %s — data returned but not cached", key, exc)

        return enriched

    async def get_dc_detail(self, dc_code: str) -> DCDetail:
        """
        Tek bir datacenter'ın tam metrik profili.
        db-service: GET /datacenters/{dc_code} → DCDetail

        Task 2.2: Provider pipeline uygulanır (validasyon + loglama).
        Task 2.3: Redis cache-aside (cache key: f"dc_detail:{dc_code}", TTL: 900s)
        """
        key = f"dc_detail:{dc_code}"

        # 1. Cache hit
        try:
            cached = await self._redis.get(key)
            if cached:
                logger.debug("Cache HIT: %s", key)
                return DCDetail.model_validate_json(cached)
        except Exception as exc:
            logger.warning("Redis GET error on %s: %s — falling through to db-service", key, exc)

        # 2. Cache miss — db-service + provider pipeline
        detail = await self._proxy_single(
            path=f"/datacenters/{dc_code}",
            model=DCDetail,
            label=f"datacenters/{dc_code}",
        )
        for provider in self._providers:
            detail = provider.enrich_detail(detail)

        # 3. Redis'e yaz
        try:
            await self._redis.set(key, detail.model_dump_json(), ex=CACHE_TTL)
            logger.debug("Cache MISS — stored: %s (TTL=%ds)", key, CACHE_TTL)
        except Exception as exc:
            logger.warning("Redis SET error on %s: %s — data returned but not cached", key, exc)

        return detail

    async def get_overview(self) -> GlobalOverview:
        """
        Platform geneli KPI özeti.
        db-service: GET /overview → GlobalOverview

        Task 2.3: Redis cache-aside (cache key: "global_overview", TTL: 900s)
        """
        key = "global_overview"

        # 1. Cache hit
        try:
            cached = await self._redis.get(key)
            if cached:
                logger.debug("Cache HIT: %s", key)
                return GlobalOverview.model_validate_json(cached)
        except Exception as exc:
            logger.warning("Redis GET error on %s: %s — falling through to db-service", key, exc)

        # 2. Cache miss — db-service'ten çek
        overview = await self._proxy_single(
            path="/overview",
            model=GlobalOverview,
            label="overview",
        )

        # 3. Redis'e yaz
        try:
            await self._redis.set(key, overview.model_dump_json(), ex=CACHE_TTL)
            logger.debug("Cache MISS — stored: %s (TTL=%ds)", key, CACHE_TTL)
        except Exception as exc:
            logger.warning("Redis SET error on %s: %s — data returned but not cached", key, exc)

        return overview

    async def get_overview_trends(self) -> OverviewTrends:
        """
        Redis sliding window listelerinden trend verilerini okur.

        Her liste: [en yeni, ..., en eski]  (LPUSH ile solön ekleniyor)
        LRANGE 0 -1 → reversed() ile kronolojik sıraya çevrilir.

        Redis yoksa veya listeler boşsa → boş TrendSeries dönülür (graceful).
        """
        _KEY_MAP = {
            "cpu_pct":   "trend:cpu_pct",
            "ram_pct":   "trend:ram_pct",
            "energy_kw": "trend:energy_kw",
        }

        results: dict[str, TrendSeries] = {}

        for field, redis_key in _KEY_MAP.items():
            try:
                raw_items = await self._redis.lrange(redis_key, 0, -1)  # [yeni...eski]
                # Kronolojik sıra (eski → yeni)
                items = list(reversed(raw_items))
                labels: list[str]   = []
                values: list[float] = []
                for item in items:
                    parsed = json.loads(item)
                    labels.append(parsed["ts"])
                    values.append(float(parsed["v"]))
                results[field] = TrendSeries(labels=labels, values=values)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Trends: Redis okuma hatası (%s): %s — boş seri döndürülüyor",
                    redis_key, exc,
                )
                results[field] = TrendSeries(labels=[], values=[])

        return OverviewTrends(
            cpu_pct=results["cpu_pct"],
            ram_pct=results["ram_pct"],
            energy_kw=results["energy_kw"],
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _proxy_list(self, path: str, model: type, label: str) -> list:
        """Tek roundtrip — list endpoint proxy."""
        try:
            resp = await self._client.get(path)
            resp.raise_for_status()
            return [model.model_validate(item) for item in resp.json()]
        except httpx.TimeoutException:
            logger.error("Timeout while fetching %s from db-service", label)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=f"db-service timed out while fetching {label}.",
            )
        except httpx.HTTPStatusError as exc:
            logger.error("db-service %s returned %s", label, exc.response.status_code)
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"db-service error on {label}: {exc.response.text}",
            )
        except httpx.RequestError as exc:
            logger.error("Cannot reach db-service for %s: %s", label, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="db-service is unreachable.",
            )

    async def _proxy_single(self, path: str, model: type, label: str):
        """Tek roundtrip — single object endpoint proxy."""
        try:
            resp = await self._client.get(path)
            resp.raise_for_status()
            return model.model_validate(resp.json())
        except httpx.TimeoutException:
            logger.error("Timeout while fetching %s from db-service", label)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=f"db-service timed out while fetching {label}.",
            )
        except httpx.HTTPStatusError as exc:
            logger.error("db-service %s returned %s", label, exc.response.status_code)
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"db-service error on {label}: {exc.response.text}",
            )
        except httpx.RequestError as exc:
            logger.error("Cannot reach db-service for %s: %s", label, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="db-service is unreachable.",
            )
