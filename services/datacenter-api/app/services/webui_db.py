"""WebUI App DB pool for the datacenter-api.

Read-only path: this service consults the GUI configuration tables for resource
thresholds and calculation variables that drive the sales-potential calculation.
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
    """Lightweight pool to the WebUI App DB. Read-only by convention."""

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
                maxconn=2,
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
                "datacenter-api WebUI DB pool ready (host=%s, db=%s).",
                self._host,
                self._name,
            )
        except OperationalError as exc:
            logger.warning("Failed to initialise WebUI DB pool (will fallback to defaults): %s", exc)
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
                logger.exception("WebUI putconn failed")

    def run_rows(self, sql: str, params: Iterable[Any] | None = None) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                if cur.description is None:
                    return []
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]

    def close(self) -> None:
        if self._pool is not None:
            try:
                self._pool.closeall()
            except Exception:
                logger.exception("WebUI closeall failed")
            self._pool = None
