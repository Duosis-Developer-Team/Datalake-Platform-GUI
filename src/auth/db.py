"""Auth database connection pool and low-level helpers."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2.extras import RealDictCursor

from src.auth import config

logger = logging.getLogger(__name__)

_pool: pg_pool.ThreadedConnectionPool | None = None


def get_pool() -> pg_pool.ThreadedConnectionPool:
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
            "Auth DB pool created host=%s port=%s db=%s",
            config.AUTH_DB_HOST,
            config.AUTH_DB_PORT,
            config.AUTH_DB_NAME,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


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


@contextmanager
def cursor(dict_rows: bool = True) -> Iterator[Any]:
    with connection() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor if dict_rows else None)
        try:
            yield cur
        finally:
            cur.close()


def fetch_one(sql: str, params: tuple | None = None) -> dict[str, Any] | None:
    with cursor() as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
        return dict(row) if row else None


def fetch_all(sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
    with cursor() as cur:
        cur.execute(sql, params or ())
        return [dict(r) for r in cur.fetchall()]


def execute(sql: str, params: tuple | None = None) -> int:
    with cursor() as cur:
        cur.execute(sql, params or ())
        return cur.rowcount
