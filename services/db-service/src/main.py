"""
main.py — DB-Service entry point

FastAPI uygulaması:
  - asyncpg pool'u lifespan context manager ile yönetir (startup / shutdown).
  - Tüm routerları register eder.
  - Logging yapılandırması burada başlar.
"""

import logging
import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from src.routers.data import overview_router, router as data_router
from src.routers.health import router as health_router

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan: asyncpg pool ────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Uygulama başlangıcında asyncpg connection pool oluşturur,
    kapanışta güvenli şekilde kapatır.
    DB erişilemez olsa bile servis ayağa kalkar; /health çalışır,
    /db-status ve veri endpoint'leri 503 ile yanıt verir.
    """
    pool: asyncpg.Pool | None = None
    try:
        pool = await asyncpg.create_pool(
            host=os.getenv("DB_HOST", "10.134.16.6"),
            port=int(os.getenv("DB_PORT", "5000")),
            database=os.getenv("DB_NAME", "bulutlake"),
            user=os.getenv("DB_USER", "datalakeui"),
            password=os.getenv("DB_PASS"),
            min_size=2,
            max_size=8,
            command_timeout=60,     # Uzun sorgu bloklarını önler
        )
        logger.info(
            "asyncpg pool created — host=%s port=%s db=%s",
            os.getenv("DB_HOST"), os.getenv("DB_PORT"), os.getenv("DB_NAME"),
        )
    except Exception as exc:
        logger.error("Failed to create asyncpg pool at startup: %s", exc)
        logger.warning("Service will start without DB connectivity. /health still works.")

    app.state.pool = pool
    yield  # ← Uygulama buradan çalışır

    if pool:
        await pool.close()
        logger.info("asyncpg pool closed.")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Datalake DB-Service",
    description="Data Access Layer (DAL) — asyncpg + FastAPI",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(data_router)
app.include_router(overview_router)
