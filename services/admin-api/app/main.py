"""Admin API — user, role, LDAP, team and audit management for Datalake Platform."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.api_auth import verify_api_user
from app import database
from app.routers import audit, ldap, permissions, roles, teams, users

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_pool()
    yield
    database.close_pool()


app = FastAPI(
    title="Datalake Platform Admin API",
    version="1.0.0",
    description="Internal management API for identity, access, LDAP and audit operations.",
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

app.include_router(users.router, prefix="/api/v1", tags=["users"], dependencies=_auth_dep)
app.include_router(roles.router, prefix="/api/v1", tags=["roles"], dependencies=_auth_dep)
app.include_router(permissions.router, prefix="/api/v1", tags=["permissions"], dependencies=_auth_dep)
app.include_router(teams.router, prefix="/api/v1", tags=["teams"], dependencies=_auth_dep)
app.include_router(ldap.router, prefix="/api/v1", tags=["ldap"], dependencies=_auth_dep)
app.include_router(audit.router, prefix="/api/v1", tags=["audit"], dependencies=_auth_dep)


@app.get("/health", response_model=dict, tags=["health"])
def health():
    try:
        database.fetch_one("SELECT 1")
        db_status = "ok"
    except Exception:
        db_status = "unavailable"
    return {"status": "ok" if db_status == "ok" else "degraded", "db": db_status}


@app.get("/ready", tags=["health"])
def ready():
    return {"status": "ready"}
