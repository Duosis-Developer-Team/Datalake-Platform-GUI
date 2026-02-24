"""
database.py — asyncpg pool accessor.

Pool yaşam döngüsü main.py lifespan'inde yönetilir.
Her endpoint, pool'u bu modüldeki `get_pool` dependency'si aracılığıyla alır.
"""

import asyncpg
from fastapi import HTTPException, Request, status


async def get_pool(request: Request) -> asyncpg.Pool:
    """FastAPI dependency: app.state.pool'dan asyncpg Pool döndürür."""
    pool: asyncpg.Pool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection pool is not available.",
        )
    return pool
