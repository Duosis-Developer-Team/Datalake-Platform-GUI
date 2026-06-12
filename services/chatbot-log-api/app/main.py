"""chatbot-log-api FastAPI entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, logs
from app.services import mongo_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await mongo_store.close_client()


app = FastAPI(
    title="Bulutistan Chatbot Log API",
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

app.include_router(health.router, tags=["health"])
app.include_router(logs.router, prefix="/api/v1/logs", tags=["logs"])
