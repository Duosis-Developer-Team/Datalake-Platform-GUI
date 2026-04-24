from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.telemetry import instrument_fastapi_app, setup_sdk

setup_sdk()

from app.core.api_auth import verify_api_user
from app.services.customer_service import CustomerService
from app.services.itsm_service import ITSMService
from app.services.scheduler_service import start_scheduler
from app.routers import customers, itsm
from app.core.redis_client import init_redis_pool, close_redis_pool, redis_is_healthy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    svc = CustomerService()
    app.state.db = svc
    app.state.itsm = ITSMService(
        get_connection=svc._get_connection,
        run_row=svc._run_row,
        run_rows=svc._run_rows,
    )
    init_redis_pool()
    scheduler = start_scheduler(svc)
    app.state.scheduler = scheduler
    yield
    if getattr(app.state, "scheduler", None) and app.state.scheduler.running:
        app.state.scheduler.shutdown(wait=False)
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

app.include_router(
    itsm.router,
    prefix="/api/v1",
    tags=["itsm"],
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


instrument_fastapi_app(app)
