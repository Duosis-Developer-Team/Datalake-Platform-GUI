"""chatbot-api FastAPI entrypoint.

Mirrors the structure of the other microservices (datacenter-api): telemetry is
initialized before app creation, CORS is permissive (calls are internal), the
chat router is mounted under ``/api/v1/chatbot`` with the same ``verify_api_user``
auth scheme, and ``/health`` / ``/ready`` are unprefixed for probes.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.telemetry import instrument_fastapi_app, setup_sdk

# Telemetry must initialize before the app/instrumentation is created.
setup_sdk()

from app.core.logging import configure_logging  # noqa: E402
from app.routers import chatbot, health  # noqa: E402
from app.services.api_clients import close_all  # noqa: E402

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Close pooled httpx clients on shutdown.
    close_all()


app = FastAPI(
    title="Bulutistan Chatbot API",
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

# Health/readiness — unprefixed, no auth (used by Docker/K8s probes).
app.include_router(health.router, tags=["health"])

# Chat — mounted under /api/v1/chatbot. Auth is enforced per-endpoint via the
# verify_api_user dependency (which also yields the user id for audit).
app.include_router(chatbot.router, prefix="/api/v1/chatbot", tags=["chatbot"])

instrument_fastapi_app(app)
