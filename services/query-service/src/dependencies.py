"""
dependencies.py — Query-Service Dependency Injection

Üç bağımlılık:
  - verify_internal_key : GUI → query-service isteklerini X-Internal-Key ile korur.
  - get_db_client       : app.state.db_client'tan httpx.AsyncClient döndürür.
  - get_redis           : app.state.redis'ten redis.asyncio.Redis döndürür.
"""

import os

import httpx
import redis.asyncio as aioredis
from fastapi import Header, HTTPException, Request, status


async def verify_internal_key(
    x_internal_key: str = Header(..., description="Servisler arası API anahtarı"),
) -> None:
    """
    Gelen istekteki X-Internal-Key header'ını doğrular.
    Güvenlik zinciri: GUI-Service → (bu kontrol) → Query-Service → DB-Service
    """
    expected = os.getenv("INTERNAL_API_KEY", "")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_API_KEY is not configured on the server.",
        )
    if x_internal_key != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-Internal-Key header.",
        )


async def get_db_client(request: Request) -> httpx.AsyncClient:
    """
    FastAPI dependency: app.state.db_client'tan httpx.AsyncClient döndürür.
    Client lifespan context manager'da oluşturulur ve kapatılır.
    """
    client: httpx.AsyncClient | None = getattr(request.app.state, "db_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DB service client is not available.",
        )
    return client


async def get_redis(request: Request) -> aioredis.Redis:
    """
    FastAPI dependency: app.state.redis'ten Redis client döndürür.
    Client lifespan context manager'da oluşturulur ve kapatılır.
    """
    redis: aioredis.Redis | None = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis client is not available.",
        )
    return redis
