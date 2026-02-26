"""
main.py — Query-Service entry point

FastAPI uygulaması:
  - httpx.AsyncClient'ı lifespan context manager ile yönetir (startup / shutdown).
  - redis.asyncio client'ı lifespan context manager ile yönetir (startup / shutdown).
  - DB-Service ile haberleşme altyapısını kurar.
  - Tüm routerları register eder.

Mimari notu:
  - asyncpg.Pool (db-service) → httpx.AsyncClient (query-service)
  - Aynı DI pattern: client ve redis, app.state üzerinde yaşar; dependency ile sunulur.
"""

import asyncio
import os
from contextlib import asynccontextmanager, suppress

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI

from shared.utils.logger import setup_logger
from shared.utils.trusted_network import TrustedNetworkMiddleware
from src.tasks.sampler import run_sampler

from src.routers.data import overview_router, router as data_router
from src.routers.health import router as health_router

# ── Logging ──────────────────────────────────────────────────────────────────
# Servis root logger — tüm src.* alt logger'ları formatı hiyerarşi üzerinden
# miras alır; modüllerdeki getLogger(__name__) satırlarına dokunulmaz.

logger = setup_logger("query-service")


# ── Lifespan: httpx.AsyncClient + redis.asyncio ───────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Uygulama başlangıcında httpx.AsyncClient ve Redis client oluşturur,
    kapanışta güvenli şekilde kapatır.

    DB-Service veya Redis erişilemez olsa bile servis ayağa kalkar;
    /health çalışır, veri endpoint'leri 503 ile yanıt verir.
    """
    db_service_url = os.getenv("DB_SERVICE_URL", "http://db-service:8001")
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    internal_key = os.getenv("INTERNAL_API_KEY", "")
    # db-service soğuk başlangıçta 74s alabilir; 90s timeout güvenli eşik.
    timeout = httpx.Timeout(90.0, connect=10.0)

    # ── httpx client ──────────────────────────────────────────────────────────
    client = httpx.AsyncClient(
        base_url=db_service_url,
        headers={"X-Internal-Key": internal_key},
        timeout=timeout,
    )

    try:
        # Bağlantıyı doğrula: db-service /health endpoint'ine ping at.
        resp = await client.get("/health")
        if resp.status_code == 200:
            logger.info(
                "httpx client ready — db-service reachable at %s", db_service_url
            )
        else:
            logger.warning(
                "db-service /health returned %s — proceeding anyway", resp.status_code
            )
    except httpx.RequestError as exc:
        logger.error(
            "Cannot reach db-service at startup (%s): %s — proceeding anyway",
            db_service_url, exc,
        )

    # ── Redis client ──────────────────────────────────────────────────────────
    redis_client = aioredis.from_url(
        redis_url, encoding="utf-8", decode_responses=True
    )

    try:
        await redis_client.ping()
        logger.info("Redis client ready — connected at %s", redis_url)
    except Exception as exc:
        logger.warning(
            "Cannot reach Redis at startup (%s): %s — proceeding anyway",
            redis_url, exc,
        )

    app.state.db_client = client
    app.state.redis = redis_client

    # ── Arka plan örnekleyici görevi ──────────────────────────────────────────
    sampler_task = asyncio.create_task(run_sampler(app))
    logger.info("Sampler task created.")

    yield  # ← Uygulama buradan çalışır

    # ── Shutdown: sampler'ı temizce durdur ───────────────────────────────────
    sampler_task.cancel()
    with suppress(asyncio.CancelledError):
        await sampler_task
    logger.info("Sampler task stopped.")

    await client.aclose()
    logger.info("httpx client closed.")

    await redis_client.aclose()
    logger.info("Redis client closed.")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Datalake Query-Service",
    description="Business Logic & Caching Layer — httpx + Redis + FastAPI",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(TrustedNetworkMiddleware)

app.include_router(health_router)
app.include_router(data_router)
app.include_router(overview_router)
