from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.api_auth import verify_api_user
from app.services.customer_service import CustomerService
from app.routers import customers
from app.core.redis_client import init_redis_pool, close_redis_pool, redis_is_healthy

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    svc = CustomerService()
    app.state.db = svc
    init_redis_pool()
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
def ready():
    return {"status": "ready"}
