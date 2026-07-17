"""Coverage for the cache-invalidation call site inside resync_aliases_from_datalake.

resync's orphan-remap loop can touch accounts that never appear in
`name_to_ids` (built solely from CRM_PROJECT_CUSTOMER_ROWS): a remap target
resolved only via the CRM_ACCOUNT_BY_DISPLAY_NAME fallback, and the remap's
*source* account (whose mapping was just moved away). Both ends must be
invalidated; skipped orphans (ambiguous name collisions, or a resolved
new_account_id equal to old_account_id) must not add anything.
"""
from __future__ import annotations

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


def _make_service(*, project_rows, orphans, run_one, invalidate_mapping_caches):
    webui = _FakeWebui(orphans)
    svc = SalesService(
        get_connection=lambda: None,
        run_row=lambda cur, sql, params: None,
        run_rows=lambda *a, **kw: [],
        webui=webui,
        invalidate_mapping_caches=invalidate_mapping_caches,
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


def test_remap_target_found_only_via_display_name_fallback_is_invalidated():
    """Finding case 1: the remap target resolved via CRM_ACCOUNT_BY_DISPLAY_NAME
    (not present in name_to_ids) must still be passed to _invalidate_for."""
    project_rows = [
        {"crm_accountid": "reconciled-1", "crm_account_name": "Reconciled Co"},
    ]
    orphans = [
        {
            "id": 1,
            "crm_accountid": "old-fallback",
            "crm_account_name": "Fallback Account",
        }
    ]
    captured: dict[str, set[str]] = {}

    def invalidate(account_ids):
        captured["ids"] = set(account_ids)
        return None

    svc, webui = _make_service(
        project_rows=project_rows,
        orphans=orphans,
        run_one=_fallback_run_one,
        invalidate_mapping_caches=invalidate,
    )

    result = svc.resync_aliases_from_datalake()

    assert result["mappings_remapped"] == 1
    assert "new-fallback-id" in captured["ids"]


def test_remap_old_account_id_is_also_invalidated():
    """Finding case 2: the remap SOURCE (old_account_id) loses a mapping and
    must be invalidated too, even though orphans are by definition not in
    name_to_ids."""
    project_rows = [
        {"crm_accountid": "reconciled-1", "crm_account_name": "Reconciled Co"},
    ]
    orphans = [
        {
            "id": 1,
            "crm_accountid": "old-fallback",
            "crm_account_name": "Fallback Account",
        }
    ]
    captured: dict[str, set[str]] = {}

    def invalidate(account_ids):
        captured["ids"] = set(account_ids)
        return None

    svc, webui = _make_service(
        project_rows=project_rows,
        orphans=orphans,
        run_one=_fallback_run_one,
        invalidate_mapping_caches=invalidate,
    )

    svc.resync_aliases_from_datalake()

    assert "old-fallback" in captured["ids"]


def test_skipped_orphans_do_not_add_ids():
    """Finding requirement: an ambiguous/collision-name orphan and a no-op
    remap (new_account_id == old_account_id) must not contribute either id."""
    project_rows = [
        {"crm_accountid": "reconciled-1", "crm_account_name": "Reconciled Co"},
        {"crm_accountid": "amb-1", "crm_account_name": "Ambiguous Co"},
        {"crm_accountid": "amb-2", "crm_account_name": "Ambiguous Co"},
    ]
    orphans = [
        # Ambiguous display name -> skipped before any resolution attempt.
        {
            "id": 1,
            "crm_accountid": "old-ambiguous",
            "crm_account_name": "Ambiguous Co",
        },
        # Resolves back to itself -> no-op remap, skipped.
        {
            "id": 2,
            "crm_accountid": "acct-no-remap",
            "crm_account_name": "Stable Account",
        },
    ]
    captured: dict[str, set[str]] = {}

    def invalidate(account_ids):
        captured["ids"] = set(account_ids)
        return None

    svc, webui = _make_service(
        project_rows=project_rows,
        orphans=orphans,
        run_one=_fallback_run_one,
        invalidate_mapping_caches=invalidate,
    )

    result = svc.resync_aliases_from_datalake()

    assert result["mappings_remapped"] == 0
    assert "old-ambiguous" not in captured["ids"]
    assert "acct-no-remap" not in captured["ids"]
    # Sanity: reconciled accounts from the project rows are still invalidated.
    assert "reconciled-1" in captured["ids"]
