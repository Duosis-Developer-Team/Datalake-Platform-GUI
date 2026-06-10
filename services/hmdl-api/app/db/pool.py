"""PostgreSQL connection pool for read-only HMDL collector queries."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from app.config import settings

_logger = logging.getLogger(__name__)
_pool: ThreadedConnectionPool | None = None


def init_pool() -> None:
    global _pool
    if _pool is not None:
        return
    timeout = settings.db_statement_timeout_ms
    _pool = ThreadedConnectionPool(
        minconn=settings.db_pool_minconn,
        maxconn=settings.db_pool_maxconn,
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_pass,
        options=f"-c search_path={settings.hmdl_schema},public -c statement_timeout={timeout}",
    )
    _logger.info("HMDL DB pool initialized (schema=%s)", settings.hmdl_schema)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def connection():
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


def fetch_all(query: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            return [dict(row) for row in cur.fetchall()]


def fetch_one(query: str, params: tuple | list | None = None) -> dict[str, Any] | None:
    rows = fetch_all(query, params)
    return rows[0] if rows else None
