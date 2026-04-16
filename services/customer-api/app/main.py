from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.core.api_auth import verify_api_user
from app.services.customer_service import CustomerService
from app.routers import customers
from app.core.redis_client import init_redis_pool, close_redis_pool, redis_is_healthy
from app.utils.time_range import cache_time_ranges

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_DEFAULT_WARMED_CUSTOMERS = ("Boyner",)


def _warmed_customers() -> tuple[str, ...]:
    raw = (os.getenv("WARMED_CUSTOMERS") or "").strip()
    if not raw:
        return _DEFAULT_WARMED_CUSTOMERS
    names = tuple(n.strip() for n in raw.split(",") if n.strip())
    return names or _DEFAULT_WARMED_CUSTOMERS


def _warm_customer_caches(svc: CustomerService) -> None:
    customers = _warmed_customers()
    for tr in cache_time_ranges():
        for customer_name in customers:
            try:
                svc.get_customer_resources(customer_name, tr)
            except Exception as exc:
                logger.warning(
                    "Startup warm-up failed for customer=%s preset=%s: %s",
                    customer_name,
                    tr.get("preset", ""),
                    exc,
                )


@asynccontextmanager
async def lifespan(app: FastAPI):
    svc = CustomerService()
    app.state.db = svc
    init_redis_pool()
    threading.Thread(target=_warm_customer_caches, args=(svc,), daemon=True).start()
    yield
    close_redis_pool()
    if svc._pool:
        svc._pool.closeall()


app = FastAPI(
    title="Bulutistan Customer API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    customers.router,
    prefix="/api/v1",
    tags=["customers"],
    dependencies=[Depends(verify_api_user)],
)


@app.get("/health", response_model=dict)
def health():
    svc: CustomerService = app.state.db
    return {
        "status": "ok",
        "db_pool": "ok" if svc._pool else "unavailable",
        "redis": "ok" if redis_is_healthy() else "unavailable",
    }


@app.get("/ready")
def ready(response: Response):
    svc: CustomerService = app.state.db
    db_ok = svc._pool is not None
    redis_ok = redis_is_healthy()
    if not db_ok or not redis_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "db_pool": "ok" if db_ok else "unavailable",
            "redis": "ok" if redis_ok else "unavailable",
        }
    return {"status": "ready"}
