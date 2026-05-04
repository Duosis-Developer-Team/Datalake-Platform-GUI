"""crm-engine entrypoint.

Hosts CRM/sellable computation endpoints decoupled from customer-api so that
heavy WebUI-config + datalake aggregation traffic does not contend with the
real-time customer/asset/sales/itsm dashboards.

Routes mounted under /api/v1:
  - /crm/sellable-potential/*    (sellable router)
  - /crm/panels, /crm/resource-ratios, /crm/unit-conversions   (sellable router)
  - /crm/metric-tags*            (sellable router)
  - /crm/config/*                (crm_config router)
  - /crm/service-mapping*        (service_mapping router)

Background scheduler runs SellableService.snapshot_all every
REFRESH_INTERVAL_MINUTES; customer cache warm-up stays in customer-api.
"""
from __future__ import annotations

import atexit
import logging
import os
from contextlib import asynccontextmanager

import redis as _redis
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from psycopg2 import Error as Psycopg2Error
from starlette.responses import JSONResponse

from app.telemetry import instrument_fastapi_app, setup_sdk

setup_sdk()

from app.config import settings
from app.core.api_auth import verify_api_user
from app.core.redis_client import close_redis_pool, init_redis_pool, redis_is_healthy
from app.routers import crm_config, sellable, service_mapping
from app.services.crm_config_service import CrmConfigService
from app.services.currency_service import CurrencyService
from app.services.customer_service import CustomerService
from app.services.sales_service import SalesService
from app.services.sellable_service import SellableService
from app.services.tagging_service import TaggingService
from app.services.webui_db import WebuiPool

# Redis DB used by datacenter-api (default 0); crm-engine reads dc_details keys from it.
_DATACENTER_REDIS_DB = int(os.getenv("DATACENTER_REDIS_DB", "0"))
_DATACENTER_API_URL = os.getenv("DATACENTER_API_URL", "http://datacenter-api:8000")

_dc_redis_client: _redis.Redis | None = None


def _init_datacenter_redis() -> _redis.Redis | None:
    global _dc_redis_client
    try:
        client = _redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=_DATACENTER_REDIS_DB,
            password=settings.redis_password or None,
            socket_timeout=settings.redis_socket_timeout,
            decode_responses=True,
        )
        client.ping()
        _dc_redis_client = client
        logger.info(
            "Datacenter Redis connected: %s:%s db=%d",
            settings.redis_host, settings.redis_port, _DATACENTER_REDIS_DB,
        )
        return client
    except Exception as exc:
        logger.warning("Datacenter Redis unavailable (dc_details fallback via HTTP): %s", exc)
        _dc_redis_client = None
        return None


def _close_datacenter_redis() -> None:
    global _dc_redis_client
    if _dc_redis_client:
        try:
            _dc_redis_client.close()
        except Exception:
            pass
        _dc_redis_client = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REFRESH_INTERVAL_MINUTES = 15


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


_WEBUI_REQUIRED = _env_bool("WEBUI_DB_REQUIRED", settings.webui_db_required)


def _start_scheduler(sellable_svc: SellableService) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func=sellable_svc.snapshot_all,
        trigger=IntervalTrigger(minutes=REFRESH_INTERVAL_MINUTES),
        id="sellable_snapshot",
        name="Sellable Potential snapshot",
        replace_existing=True,
        misfire_grace_time=60,
    )
    try:
        sellable_svc.snapshot_all()
    except Exception:  # noqa: BLE001 - never abort startup
        logger.exception("Initial sellable snapshot failed")
    scheduler.start()
    logger.info(
        "crm-engine scheduler started (sellable snapshot every %d minutes).",
        REFRESH_INTERVAL_MINUTES,
    )
    atexit.register(lambda: _stop(scheduler))
    return scheduler


def _stop(scheduler: BackgroundScheduler) -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("crm-engine scheduler stopped.")


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
    init_redis_pool()
    dc_redis = _init_datacenter_redis()

    config_svc = CrmConfigService(webui)
    currency_svc = CurrencyService(svc)
    tagging_svc = TaggingService(webui)
    sellable_svc = SellableService(
        customer_service=svc,
        webui=webui,
        config_service=config_svc,
        currency_service=currency_svc,
        tagging_service=tagging_svc,
        datacenter_redis=dc_redis,
        datacenter_api_url=_DATACENTER_API_URL,
    )
    app.state.crm_config = config_svc
    app.state.currency = currency_svc
    app.state.tagging = tagging_svc
    app.state.sellable = sellable_svc

    app.state.scheduler = _start_scheduler(sellable_svc)
    yield
    if getattr(app.state, "scheduler", None) and app.state.scheduler.running:
        app.state.scheduler.shutdown(wait=False)
    close_redis_pool()
    _close_datacenter_redis()
    if svc._pool:
        svc._pool.closeall()
    webui.close()


app = FastAPI(
    title="Bulutistan CRM Engine",
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
    crm_config.router,
    prefix="/api/v1",
    tags=["crm-config"],
    dependencies=[Depends(verify_api_user)],
)

app.include_router(
    sellable.router,
    prefix="/api/v1",
    tags=["crm-sellable"],
    dependencies=[Depends(verify_api_user)],
)

app.include_router(
    service_mapping.router,
    prefix="/api/v1",
    tags=["crm-service-mapping"],
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
