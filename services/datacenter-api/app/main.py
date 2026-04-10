from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.api_auth import verify_api_user
from app.services.dc_service import DatabaseService
from app.services.scheduler_service import start_scheduler
from app.routers import datacenters, dashboard
from app.core.redis_client import init_redis_pool, close_redis_pool, redis_is_healthy

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = DatabaseService()
    app.state.db = db
    init_redis_pool()
    scheduler = start_scheduler(db)
    app.state.scheduler = scheduler
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)
    close_redis_pool()
    if db._pool:
        db._pool.closeall()


app = FastAPI(
    title="Bulutistan Datacenter API",
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
    datacenters.router,
    prefix="/api/v1",
    tags=["datacenters"],
    dependencies=[Depends(verify_api_user)],
)
app.include_router(
    dashboard.router,
    prefix="/api/v1",
    tags=["dashboard"],
    dependencies=[Depends(verify_api_user)],
)


@app.get("/health", response_model=dict)
def health():
    db: DatabaseService = app.state.db
    return {
        "status": "ok",
        "db_pool": "ok" if db._pool else "unavailable",
        "redis": "ok" if redis_is_healthy() else "unavailable",
    }


@app.get("/ready")
def ready():
    return {"status": "ready"}
