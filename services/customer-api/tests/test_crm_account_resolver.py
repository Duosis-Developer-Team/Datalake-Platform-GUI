"""Tests for shared CRM accountid resolution."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.services.crm_account_resolver import resolve_crm_account_ids


class _WebuiAliasOnly:
    is_available = True

    def run_rows(self, sql: str, params=None):
        if "gui_crm_customer_alias" in sql:
            return [{"crm_accountid": "alias-id-1"}]
        return []

    def run_one(self, sql: str, params=None):
        return None


class _WebuiEmpty:
    is_available = True

    def run_rows(self, sql: str, params=None):
        return []

    def run_one(self, sql: str, params=None):
        return None


def test_resolve_crm_account_ids_from_alias_table():
    ids = resolve_crm_account_ids("Acme Corp", webui=_WebuiAliasOnly())
    assert ids == ["alias-id-1"]


def test_resolve_crm_account_ids_datalake_fallback():
    lookup = MagicMock(return_value="datalake-guid")
    ids = resolve_crm_account_ids(
        "4A KOZMETIK",
        webui=_WebuiEmpty(),
        datalake_account_lookup=lookup,
    )
    assert ids == ["datalake-guid"]
    lookup.assert_called_once_with("4A KOZMETIK")
