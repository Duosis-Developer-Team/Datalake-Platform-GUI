"""Synchronous psycopg2 connection pool for the admin API."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2.extras import RealDictCursor

from app import config

logger = logging.getLogger(__name__)

_pool: pg_pool.ThreadedConnectionPool | None = None


def init_pool() -> None:
    global _pool
    if _pool is None:
        _pool = pg_pool.ThreadedConnectionPool(
            1,
            20,
            host=config.AUTH_DB_HOST,
            port=config.AUTH_DB_PORT,
            dbname=config.AUTH_DB_NAME,
            user=config.AUTH_DB_USER,
            password=config.AUTH_DB_PASS,
        )
        logger.info(
            "Admin API DB pool created host=%s port=%s db=%s",
            config.AUTH_DB_HOST,
            config.AUTH_DB_PORT,
            config.AUTH_DB_NAME,
        )


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


def get_pool() -> pg_pool.ThreadedConnectionPool:
    if _pool is None:
        init_pool()
    return _pool  # type: ignore[return-value]


@contextmanager
def connection() -> Iterator[Any]:
    p = get_pool()
    conn = p.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        p.putconn(conn)


def fetch_all(sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
    with connection() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute(sql, params or ())
            return [dict(r) for r in cur.fetchall()]
        finally:
            cur.close()


def fetch_one(sql: str, params: tuple | None = None) -> dict[str, Any] | None:
    with connection() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute(sql, params or ())
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            cur.close()


def execute(sql: str, params: tuple | None = None) -> int:
    with connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute(sql, params or ())
            return cur.rowcount
        finally:
            cur.close()
