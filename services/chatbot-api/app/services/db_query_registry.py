"""Allowlisted read-only DB query templates (CTO pack 05).

These are the ONLY SQL statements the chatbot may ever run against the DB, and
only when ``CHATBOT_DB_ENABLED=true``. The examples below are illustrative and
disabled by default. Before enabling a template, a developer must verify it
against the real schema and confirm it touches no sensitive columns
(``assert_read_only`` enforces the latter at execution time).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.services.db_readonly import ReadOnlyViolation, assert_read_only, get_db


@dataclass
class DBQuery:
    key: str
    description: str
    sql: str
    params: tuple[str, ...] = ()
    enabled: bool = False  # opt-in per template after schema verification


# NOTE: example templates — kept disabled until verified against live schema.
DB_QUERIES: dict[str, DBQuery] = {
    "db_list_recent_collection_times": DBQuery(
        key="db_list_recent_collection_times",
        description="Latest collection time per source table.",
        sql=(
            "SELECT source_name, max(collectiontime) AS latest_collectiontime "
            "FROM data_collection_health "
            "GROUP BY source_name "
            "ORDER BY latest_collectiontime DESC "
            "LIMIT %(limit)s"
        ),
        params=("limit",),
        enabled=False,
    ),
    "db_find_customer_alias": DBQuery(
        key="db_find_customer_alias",
        description="Find CRM/customer aliases by name.",
        sql=(
            "SELECT crm_accountid, crm_name, webui_customer_name "
            "FROM crm_customer_aliases "
            "WHERE crm_name ILIKE %(q)s OR webui_customer_name ILIKE %(q)s "
            "LIMIT 20"
        ),
        params=("q",),
        enabled=False,
    ),
}

# Validate templates at import time so a malformed template fails fast in CI
# rather than at request time.
for _q in DB_QUERIES.values():
    assert_read_only(_q.sql)


def list_enabled_keys() -> list[str]:
    return [k for k, q in DB_QUERIES.items() if q.enabled]


def run_query(key: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Run an allowlisted, enabled template. Raises ``ReadOnlyViolation`` otherwise."""
    q = DB_QUERIES.get(key)
    if q is None:
        raise ReadOnlyViolation(f"unknown query key: {key}")
    if not q.enabled:
        raise ReadOnlyViolation(f"query '{key}' is not enabled")
    bound = {p: (params or {}).get(p) for p in q.params}
    return get_db().run_template(q.sql, bound)
