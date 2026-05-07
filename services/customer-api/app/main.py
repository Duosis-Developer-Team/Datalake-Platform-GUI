from __future__ import annotations
# ruff: noqa: E402

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from psycopg2 import Error as Psycopg2Error
from starlette.responses import JSONResponse

from app.telemetry import instrument_fastapi_app, setup_sdk

setup_sdk()

from app.config import settings
from app.core.api_auth import verify_api_user
from app.services.customer_service import CustomerService
from app.services.itsm_service import ITSMService
from app.services.sales_service import SalesService
from app.services.scheduler_service import start_scheduler
from app.services.webui_db import WebuiPool
from app.routers import admin_cache, customers, itsm, sales
from app.core.redis_client import init_redis_pool, close_redis_pool, redis_is_healthy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


_WEBUI_REQUIRED = _env_bool("WEBUI_DB_REQUIRED", settings.webui_db_required)


@asynccontextmanager
async def lifespan(app: FastAPI):
    svc = CustomerService()
    webui = WebuiPool()
    app.state.db = svc
    app.state.webui = webui
    app.state.sales = SalesService(
        get_connection=svc._get_connection,
        run_row=svc._run_row,
        run_rows=svc._run_rows,
        get_customer_assets=lambda name: svc.get_customer_resources(name, None),
        webui=webui,
    )
    app.state.itsm = ITSMService(
        get_connection=svc._get_connection,
        run_row=svc._run_row,
        run_rows=svc._run_rows,
    )
    init_redis_pool()

    # CRM/sellable computation moved to dedicated crm-engine container.
    scheduler = start_scheduler(svc)
    app.state.scheduler = scheduler
    yield
    if getattr(app.state, "scheduler", None) and app.state.scheduler.running:
        app.state.scheduler.shutdown(wait=False)
    close_redis_pool()
    if svc._pool:
        svc._pool.closeall()
    webui.close()


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
    sales.router,
    prefix="/api/v1",
    tags=["crm-sales"],
    dependencies=[Depends(verify_api_user)],
)

app.include_router(
    itsm.router,
    prefix="/api/v1",
    tags=["itsm"],
    dependencies=[Depends(verify_api_user)],
)
app.include_router(
    admin_cache.router,
    prefix="/api/v1",
    tags=["admin"],
    dependencies=[Depends(verify_api_user)],
)


@app.get("/health", response_model=dict)
def health():
    svc: CustomerService = app.state.db
    webui: WebuiPool = app.state.webui
    return {
        "status": "ok",
        "db_pool": "ok" if svc._pool else "unavailable",
        "webui_pool": "ok" if webui.is_available else "unavailable",
        "redis": "ok" if redis_is_healthy() else "unavailable",
    }


@app.get("/ready")
def ready(response: Response):
    svc: CustomerService = app.state.db
    webui: WebuiPool = app.state.webui
    db_ok = svc._pool is not None
    webui_ok = webui.is_available
    redis_ok = redis_is_healthy()
    webui_gate_ok = webui_ok if _WEBUI_REQUIRED else True
    if not db_ok or not redis_ok or not webui_gate_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "db_pool": "ok" if db_ok else "unavailable",
            "webui_pool": "ok" if webui_ok else "unavailable",
            "webui_required": _WEBUI_REQUIRED,
            "redis": "ok" if redis_ok else "unavailable",
        }
    return {"status": "ready", "webui_required": _WEBUI_REQUIRED}


@app.exception_handler(Psycopg2Error)
async def _postgres_error_handler(request: Request, exc: Psycopg2Error):
    """Surface PostgreSQL errors in JSON instead of an opaque 500.

    Typical operator-facing causes:
    - Missing relation: WebUI volume/schema predates migrations 005+ (sellable tables).
    - permission denied for role: GRANT INSERT/UPDATE on gui_* tables.
    """
    logger.exception("PostgreSQL error %s %s", request.method, request.url.path)
    detail = str(exc).strip()
    low = detail.lower()
    hint = ""
    if "does not exist" in low and "relation" in low:
        hint = (
            " WebUI schema may be missing sellable tables — apply SQL files under "
            "services/customer-api/migrations/webui/ (start with 005_panel_sellable_schema.sql) "
            "to the WEBUI database, or recreate the webui-db volume on fresh installs."
        )
    elif "permission denied" in low or "insufficient_privilege" in low:
        hint = " Grant INSERT/UPDATE/USAGE on gui_* objects to WEBUI_DB_USER."
    elif "there is no unique or exclusion constraint matching the on conflict specification" in low:
        hint = (
            " gui_panel_resource_ratio / gui_unit_conversion must have PRIMARY KEY "
            "(family, dc_code) and (from_unit, to_unit). Re-run 005_panel_sellable_schema.sql."
        )
    return JSONResponse(status_code=500, content={"detail": detail + hint})


instrument_fastapi_app(app)
