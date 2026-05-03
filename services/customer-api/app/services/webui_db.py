"""WebUI App DB connection pool.

Holds GUI configuration tables (gui_crm_*) separate from the datalake DB.
Pool is intentionally smaller than the datalake pool because reads are tiny
configuration lookups and writes are operator-driven (low traffic).
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterable, Optional

from psycopg2 import InterfaceError, OperationalError
from psycopg2 import pool as pg_pool
from psycopg2.pool import PoolError

from app.config import settings

logger = logging.getLogger(__name__)


class WebuiPool:
    """Thin wrapper around a ThreadedConnectionPool for the WebUI App DB.

    Exposes the same `_get_connection` context manager pattern used by
    `CustomerService` so SalesService and config services can mix datalake
    and webui queries with consistent error handling.
    """

    def __init__(self) -> None:
        self._host = os.getenv("WEBUI_DB_HOST") or settings.webui_db_host
        self._port = os.getenv("WEBUI_DB_PORT") or settings.webui_db_port
        self._name = os.getenv("WEBUI_DB_NAME") or settings.webui_db_name
        self._user = os.getenv("WEBUI_DB_USER") or settings.webui_db_user
        self._pass = os.getenv("WEBUI_DB_PASS") or settings.webui_db_pass
        self._pool: Optional[pg_pool.ThreadedConnectionPool] = None
        self._init_pool()

    def _init_pool(self) -> None:
        try:
            kw: dict[str, Any] = dict(
                minconn=1,
                maxconn=4,
                host=self._host,
                port=self._port,
                dbname=self._name,
                user=self._user,
                password=self._pass,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5,
            )
            timeout = settings.webui_db_statement_timeout_ms
            if timeout > 0:
                kw["options"] = f"-c statement_timeout={timeout}"
            self._pool = pg_pool.ThreadedConnectionPool(**kw)
            logger.info(
                "WebUI DB connection pool initialized (host=%s, db=%s, min=1, max=4).",
                self._host,
                self._name,
            )
        except OperationalError as exc:
            logger.error("Failed to initialize WebUI DB pool: %s", exc)
            self._pool = None

    @property
    def is_available(self) -> bool:
        return self._pool is not None

    @contextmanager
    def _get_connection(self):
        if self._pool is None:
            raise OperationalError("WebUI connection pool is not available.")
        conn = self._pool.getconn()
        discard = False
        try:
            yield conn
        except Exception as exc:
            discard = isinstance(exc, (InterfaceError, PoolError))
            raise
        finally:
            try:
                self._pool.putconn(conn, close=discard)
            except Exception:
                logger.exception("WebUI putconn failed while returning connection")

    def run_rows(self, sql: str, params: Iterable[Any] | None = None) -> list[dict[str, Any]]:
        """Execute SELECT and return list of column-name dicts."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                if cur.description is None:
                    return []
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]

    def run_one(self, sql: str, params: Iterable[Any] | None = None) -> dict[str, Any] | None:
        rows = self.run_rows(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> int:
        """Execute INSERT/UPDATE/DELETE and return rowcount."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                conn.commit()
                return int(cur.rowcount or 0)

    def close(self) -> None:
        if self._pool is not None:
            try:
                self._pool.closeall()
            except Exception:
                logger.exception("WebUI pool closeall failed")
            self._pool = None
