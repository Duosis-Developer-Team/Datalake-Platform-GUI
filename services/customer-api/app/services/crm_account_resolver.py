"""Shared CRM accountid resolution for sales and infra customer lookups."""
from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional

from app.db.queries import customer as cq
from app.db.queries import service_mapping as smq

logger = logging.getLogger(__name__)


def resolve_crm_account_ids(
    display_name: str,
    *,
    webui: Optional[Any],
    datalake_account_lookup: Optional[Callable[[str], Optional[str]]] = None,
) -> List[str]:
    """
    Resolve a GUI customer display name to one or more CRM account GUIDs.

    Resolution chain (ADR-0008):
      1. gui_crm_customer_alias (canonical key or ILIKE account name)
      2. gui_crm_customer_alias display-name fallback
      3. discovery_crm_accounts display-name fallback (datalake)
    """
    name = (display_name or "").strip()
    if not name:
        return []

    ids: list[str] = []

    if webui is not None and getattr(webui, "is_available", False):
        try:
            rows = webui.run_rows(
                smq.RESOLVE_ALIAS_BY_NAME,
                (name, f"%{name}%"),
            )
            ids = [str(r["crm_accountid"]) for r in rows if r.get("crm_accountid")]
            if ids:
                return _dedupe(ids)

            resolved = webui.run_one(
                smq.RESOLVE_ACCOUNTID_BY_DISPLAY_NAME,
                (name, name, name),
            )
            if resolved and resolved.get("crm_accountid"):
                return [str(resolved["crm_accountid"])]
        except Exception as exc:
            logger.warning("WebUI CRM account resolution failed for %s: %s", name, exc)

    if datalake_account_lookup is not None:
        try:
            account_id = datalake_account_lookup(name)
            if account_id:
                return [str(account_id)]
        except Exception as exc:
            logger.warning("Datalake CRM account resolution failed for %s: %s", name, exc)

    return []


def make_datalake_account_lookup(get_connection, run_row) -> Callable[[str], Optional[str]]:
    """Build a datalake fallback using CRM_ACCOUNT_BY_DISPLAY_NAME."""

    def _lookup(display_name: str) -> Optional[str]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                row = run_row(cur, cq.CRM_ACCOUNT_BY_DISPLAY_NAME, (display_name, display_name))
        if not row:
            return None
        if isinstance(row, dict):
            return row.get("crm_accountid")
        return row[0] if row else None

    return _lookup


def _dedupe(ids: List[str]) -> List[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in ids:
        key = str(raw).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out
