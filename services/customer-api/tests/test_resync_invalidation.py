"""Coverage for the cache-invalidation call site inside resync_aliases_from_datalake.

resync drops the whole customer_assets namespace rather than a targeted account
set. Two independent reasons, both load-bearing:

1. It *cannot* target correctly. Both of its loops write gui_crm_customer_alias,
   which the resolver reads, so a targeted plan would have to resolve before the
   first write. But half the account set (the remap ends) comes from
   LIST_ORPHAN_SOURCE_MAPPINGS, which finds mappings whose account has no alias
   row — a question that only answers correctly *after* the alias upserts have
   run. The set is unknowable at the only moment resolution is still valid.
2. Targeting would buy nothing. The accounts reconciled from the project rows
   are every project customer, i.e. every customer that can hold a cached view.
   A targeted plan deletes the same keys minus the ones whose name stopped
   resolving across the very renames resync performs — precisely the stale ones.

So the tests below assert the namespace-wide drop and, critically, that it runs
*after* the writes. The old per-account expectations (both ends of a remap must
be invalidated) are now satisfied by construction: everything is invalidated.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.services.sales_service import SalesService


class _FakeWebui:
    """Mirrors the mocking pattern from test_sales_service_resync_aliases.py."""

    def __init__(self, orphans):
        self.is_available = True
        self.executed: list[tuple] = []
        self._orphans = orphans

    def execute(self, sql, params):
        self.executed.append((sql, params))
        return 1

    def run_rows(self, sql, params=()):
        # resync_aliases_from_datalake only calls webui.run_rows once, for
        # LIST_ORPHAN_SOURCE_MAPPINGS.
        return list(self._orphans)


def _make_service(*, project_rows, orphans, run_one, invalidate_all_mapping_caches):
    webui = _FakeWebui(orphans)
    svc = SalesService(
        get_connection=lambda: None,
        run_row=lambda cur, sql, params: None,
        run_rows=lambda *a, **kw: [],
        webui=webui,
        invalidate_all_mapping_caches=invalidate_all_mapping_caches,
    )
    svc._load_crm_project_customer_rows = lambda: project_rows
    svc._run_one = run_one
    svc.seed_boyner_source_mappings = lambda: {"status": "ok", "rows_upserted": 0}
    return svc, webui


def _fallback_run_one(sql, params):
    """Fakes the CRM_ACCOUNT_BY_DISPLAY_NAME fallback lookup.

    - "Fallback Account" resolves to a *different* account (a genuine remap
      whose target was never in the project rows).
    - "Stable Account" resolves back to its own current account id (a no-op
      remap that must be skipped).
    - Anything else is unresolved.
    """
    name = (params[0] if params else "") or ""
    key = name.casefold()
    if key == "fallback account":
        return {"crm_accountid": "new-fallback-id"}
    if key == "stable account":
        return {"crm_accountid": "acct-no-remap"}
    return None


_PROJECT_ROWS = [{"crm_accountid": "reconciled-1", "crm_account_name": "Reconciled Co"}]
_ORPHANS = [
    {"id": 1, "crm_accountid": "old-fallback", "crm_account_name": "Fallback Account"}
]


def test_resync_drops_every_cached_view():
    """Covers what the old per-account assertions covered — the remap target
    resolved only via CRM_ACCOUNT_BY_DISPLAY_NAME, the remap *source* that lost
    a mapping, and every reconciled project account — by covering everything."""
    invalidate_all = MagicMock(return_value=None)

    svc, _webui = _make_service(
        project_rows=_PROJECT_ROWS,
        orphans=_ORPHANS,
        run_one=_fallback_run_one,
        invalidate_all_mapping_caches=invalidate_all,
    )

    result = svc.resync_aliases_from_datalake()

    assert result["mappings_remapped"] == 1
    invalidate_all.assert_called_once_with()


def test_resync_invalidates_after_its_writes():
    """Only resolution may move ahead of a write; the deletion must not. If the
    cache were cleared before the alias upserts committed, a concurrent reader
    would refill it straight from the pre-write rows."""
    calls: list[str] = []

    class _RecordingWebui(_FakeWebui):
        def execute(self, sql, params):
            calls.append("write")
            return super().execute(sql, params)

    webui = _RecordingWebui(_ORPHANS)
    svc = SalesService(
        get_connection=lambda: None,
        run_row=lambda cur, sql, params: None,
        run_rows=lambda *a, **kw: [],
        webui=webui,
        invalidate_all_mapping_caches=lambda: calls.append("invalidate"),
    )
    svc._load_crm_project_customer_rows = lambda: _PROJECT_ROWS
    svc._run_one = _fallback_run_one
    svc.seed_boyner_source_mappings = lambda: {"status": "ok", "rows_upserted": 0}

    svc.resync_aliases_from_datalake()

    assert "write" in calls
    assert calls[-1] == "invalidate"
    assert calls.index("invalidate") > max(
        i for i, c in enumerate(calls) if c == "write"
    )


def test_resync_invalidation_is_optional_when_not_injected():
    svc, _webui = _make_service(
        project_rows=_PROJECT_ROWS,
        orphans=_ORPHANS,
        run_one=_fallback_run_one,
        invalidate_all_mapping_caches=None,
    )

    # Must not blow up when the callable was never wired.
    result = svc.resync_aliases_from_datalake()

    assert result["status"] == "ok"


def test_skipped_orphans_still_do_not_get_remapped():
    """Not an invalidation assertion any more, but the remap-skipping logic it
    used to ride on still matters: an ambiguous/collision name and a no-op remap
    (new_account_id == old_account_id) must not touch the DB."""
    project_rows = [
        {"crm_accountid": "reconciled-1", "crm_account_name": "Reconciled Co"},
        {"crm_accountid": "amb-1", "crm_account_name": "Ambiguous Co"},
        {"crm_accountid": "amb-2", "crm_account_name": "Ambiguous Co"},
    ]
    orphans = [
        # Ambiguous display name -> skipped before any resolution attempt.
        {"id": 1, "crm_accountid": "old-ambiguous", "crm_account_name": "Ambiguous Co"},
        # Resolves back to itself -> no-op remap, skipped.
        {"id": 2, "crm_accountid": "acct-no-remap", "crm_account_name": "Stable Account"},
    ]

    svc, _webui = _make_service(
        project_rows=project_rows,
        orphans=orphans,
        run_one=_fallback_run_one,
        invalidate_all_mapping_caches=MagicMock(return_value=None),
    )

    result = svc.resync_aliases_from_datalake()

    assert result["mappings_remapped"] == 0
    assert result["name_collisions"] == ["ambiguous co"]
