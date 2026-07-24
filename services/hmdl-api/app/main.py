"""HMDL API — read-only collector topology and sync health for Platform GUI."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.telemetry import instrument_fastapi_app, setup_sdk

setup_sdk()

from app.core.api_auth import verify_api_user
from app.db import pool
from app.routers import awx, collectors

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.init_pool()
    try:
        from app.deploy_register import register_this_service
        register_this_service("hmdl-api")
    except Exception:
        pass
    yield
    pool.close_pool()


app = FastAPI(
    title="Datalake Platform HMDL API",
    version="1.0.0",
    description="Read-only HMDL collector topology, Loki sync health and target inventory.",
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

_auth_dep = [Depends(verify_api_user)]
app.include_router(
    collectors.router,
    prefix="/api/v1",
    dependencies=_auth_dep,
)
app.include_router(
    awx.router,
    prefix="/api/v1",
    dependencies=_auth_dep,
)


@app.get("/health", tags=["health"])
def health():
    try:
        pool.fetch_one("SELECT 1")
        db_status = "ok"
    except Exception:
        db_status = "unavailable"
    return {"status": "ok" if db_status == "ok" else "degraded", "db": db_status}


@app.get("/ready", tags=["health"])
def ready():
    return {"status": "ready"}


instrument_fastapi_app(app)
