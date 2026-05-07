from __future__ import annotations
# ruff: noqa: E402

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.telemetry import instrument_fastapi_app, setup_sdk

setup_sdk()

from app.core.api_auth import verify_api_user
from app.services.query_service import QueryService
from app.routers import queries

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    svc = QueryService()
    app.state.db = svc
    yield
    if svc._pool:
        svc._pool.closeall()


app = FastAPI(
    title="Bulutistan Query API",
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
    queries.router,
    prefix="/api/v1",
    tags=["queries"],
    dependencies=[Depends(verify_api_user)],
)


@app.get("/health", response_model=dict)
def health():
    svc: QueryService = app.state.db
    return {
        "status": "ok",
        "db_pool": "ok" if svc._pool else "unavailable",
    }


@app.get("/ready")
def ready():
    return {"status": "ready"}


instrument_fastapi_app(app)
