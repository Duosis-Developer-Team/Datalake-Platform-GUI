"""Read-only DB access guard (CTO pack 05 / 06).

Hard rules enforced here, independent of the LLM:
* Disabled by default (``CHATBOT_DB_ENABLED=false``).
* Only ``SELECT`` / ``WITH ... SELECT`` allowed.
* Forbidden keywords (INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/CREATE/COPY/
  GRANT/REVOKE/...) rejected.
* Multiple statements rejected (no semicolon-chaining).
* Statement timeout + row cap applied at execution.
* **Only developer-defined templates run** — model-generated SQL never executes.

``psycopg2`` is imported lazily so the module imports cleanly (and the SQL-guard
unit tests run) in a dev venv without the driver installed.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger("chatbot-api.db")

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|copy|grant|revoke|"
    r"merge|call|do|vacuum|analyze|reindex|comment|lock|set|reset)\b",
    re.IGNORECASE,
)
# Sensitive columns/tables we refuse to touch even via a template (defence in depth).
_SENSITIVE = re.compile(
    r"\b(password|passwd|pwd|password_hash|pass_hash|bind_password|secret|"
    r"api_key|apikey|token|salt|private_key)\b",
    re.IGNORECASE,
)


class ReadOnlyViolation(Exception):
    """Raised when a SQL string violates the read-only contract."""


def assert_read_only(sql: str) -> None:
    """Validate that ``sql`` is a single read-only SELECT. Raises on violation."""
    if not sql or not sql.strip():
        raise ReadOnlyViolation("empty sql")
    s = sql.strip()

    # Strip a single trailing semicolon, then reject any remaining one
    # (i.e. multiple statements).
    body = s[:-1] if s.endswith(";") else s
    if ";" in body:
        raise ReadOnlyViolation("multiple statements are not allowed")

    lowered = body.lstrip().lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ReadOnlyViolation("only SELECT / WITH ... SELECT is allowed")

    if _FORBIDDEN.search(body):
        raise ReadOnlyViolation("forbidden write/DDL keyword detected")

    if _SENSITIVE.search(body):
        raise ReadOnlyViolation("query references a sensitive column/table")


class ReadOnlyDB:
    """Lazy, disabled-by-default read-only Postgres accessor."""

    def __init__(self, settings_obj=settings) -> None:
        self.settings = settings_obj

    @property
    def enabled(self) -> bool:
        return bool(self.settings.chatbot_db_enabled and self.settings.db_host and self.settings.db_pass)

    def _connect(self):
        import psycopg2  # lazy import

        conn = psycopg2.connect(
            host=self.settings.db_host,
            port=self.settings.db_port,
            dbname=self.settings.db_name,
            user=self.settings.db_user,
            password=self.settings.db_pass,
            connect_timeout=5,
            options=f"-c statement_timeout={self.settings.db_statement_timeout_ms} -c default_transaction_read_only=on",
        )
        conn.set_session(readonly=True, autocommit=True)
        return conn

    def run_template(self, sql: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
        """Execute a *developer-defined* SELECT template with bound params.

        Returns at most ``db_max_rows`` rows as dicts. Raises ``ReadOnlyViolation``
        if disabled or if the SQL fails validation.
        """
        if not self.enabled:
            raise ReadOnlyViolation("db tools are disabled")
        assert_read_only(sql)

        conn = None
        try:
            conn = self._connect()
            with conn.cursor() as cur:
                cur.execute(sql, params or {})
                cols = [d[0] for d in cur.description] if cur.description else []
                rows = cur.fetchmany(self.settings.db_max_rows)
                return [dict(zip(cols, r)) for r in rows]
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # pragma: no cover - defensive
                    pass


_db_singleton: Optional[ReadOnlyDB] = None


def get_db() -> ReadOnlyDB:
    global _db_singleton
    if _db_singleton is None:
        _db_singleton = ReadOnlyDB()
    return _db_singleton
