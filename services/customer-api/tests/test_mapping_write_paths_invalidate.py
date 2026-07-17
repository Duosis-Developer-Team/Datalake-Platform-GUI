"""Every mapping write path must invalidate — and the alias writers must
resolve *before* they write.

The subtle half is the ordering. upsert_alias and delete_alias mutate
gui_crm_customer_alias, the very table the resolver reads, so a plan built
after their write can answer "this name belongs to nobody" for a name that,
moments earlier, belonged to the account being changed. That None is
indistinguishable from a legitimate "not ours", the key gets skipped as
already-correct, and the stale primary plus its zombie :last_good shadow
survive the full TTL — the exact bug this branch exists to kill.

The ordering tests below therefore drive the *real* planner over a fake alias
table that the fake webui mutates, exactly as the live DB would. Resolve-then-
write passes; write-then-resolve deletes nothing and fails.
"""
from unittest.mock import MagicMock

from app.db.queries import service_mapping as smq
from app.services.mapping_cache_invalidator import plan_invalidation_for_accounts
from app.services.sales_service import SalesService

# Live shape: one account cached under two display names, primary + shadow.
BOYNER_KEY = "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16"
BOYNER_SHADOW = BOYNER_KEY + ":last_good"
CACHED_KEYS = [BOYNER_KEY, BOYNER_SHADOW, "some_other_namespace:junk"]


def _service():
    invalidate = MagicMock(return_value=None)
    svc = SalesService.__new__(SalesService)
    svc._webui = MagicMock()
    svc._invalidate_mapping_caches = invalidate
    svc._plan_mapping_invalidation = None
    svc._apply_mapping_invalidation = None
    svc._invalidate_all_mapping_caches = None
    svc.list_source_mappings_for_account = lambda account_id: []
    return svc, invalidate


# ---------------------------------------------------------------------------
# Fakes that reproduce the resolver's dependency on gui_crm_customer_alias
# ---------------------------------------------------------------------------


class _FakeAliasWebui:
    """A webui whose alias writes actually mutate the rows the resolver reads."""

    def __init__(self, alias_rows):
        self.is_available = True
        self.alias_rows = alias_rows
        self.executed: list[str] = []

    def execute(self, sql, params):
        self.executed.append(sql)
        if sql == smq.DELETE_ALIAS:
            self.alias_rows.pop(params[0], None)
            return 1
        if sql == smq.UPSERT_ALIAS:
            account_id, crm_account_name, canonical_key, _netbox, _notes = params
            # Mirrors the real statement: canonical_customer_key is assigned
            # EXCLUDED outright, with no COALESCE to preserve the old value.
            self.alias_rows[account_id] = {
                "crm_account_name": crm_account_name,
                "canonical_customer_key": canonical_key,
            }
            return 1
        return 1


def _alias_resolver(alias_rows):
    """Mirrors RESOLVE_ALIAS_BY_NAME: canonical_customer_key = %s OR
    crm_account_name ILIKE '%%name%%'. Both read gui_crm_customer_alias, so a
    name resolves only while its row is there and still matches."""

    def resolve(display_name):
        for account_id, row in alias_rows.items():
            if row["canonical_customer_key"] == display_name:
                return account_id
            if display_name.casefold() in (row["crm_account_name"] or "").casefold():
                return account_id
        # No alias row matched. The real path then tries
        # CRM_ACCOUNT_BY_DISPLAY_NAME, which is an exact `TRIM(a.name) ILIKE %s`
        # with no wildcards, so it cannot stand in for the substring match above.
        return None

    return resolve


def _service_with_real_planner(alias_rows):
    """SalesService wired to the real planner over the fake alias table."""
    webui = _FakeAliasWebui(alias_rows)
    deleted: list[str] = []
    svc = SalesService.__new__(SalesService)
    svc._webui = webui
    svc._invalidate_mapping_caches = None
    svc._invalidate_all_mapping_caches = None
    svc._plan_mapping_invalidation = lambda account_ids: plan_invalidation_for_accounts(
        account_ids,
        resolve_account_id=_alias_resolver(alias_rows),
        scan_keys=lambda prefix: [k for k in CACHED_KEYS if k.startswith(prefix)],
    )
    svc._apply_mapping_invalidation = lambda plan: deleted.extend(plan.doomed_keys)
    return svc, webui, deleted


# ---------------------------------------------------------------------------
# Ordering: resolve before the write
# ---------------------------------------------------------------------------


def test_delete_alias_resolves_before_the_row_is_gone():
    """The finding's case, with the live data that produced it: "Boyner" is
    cached for the account whose CRM legal name is BOYNER BÜYÜK MAĞAZACILIK
    A.Ş., and resolves *only* through that row's ILIKE '%Boyner%' — its
    canonical_customer_key is null, so there is no other route. Once the row is
    deleted the name resolves to nothing, so a plan built after the write skips
    both keys and leaves them stale."""
    alias_rows = {
        "acct-1": {
            "crm_account_name": "BOYNER BÜYÜK MAĞAZACILIK A.Ş.",
            "canonical_customer_key": None,
        }
    }
    svc, webui, deleted = _service_with_real_planner(alias_rows)

    svc.delete_alias("acct-1")

    # Primary and zombie shadow both go. Resolve-after-write deletes neither.
    assert set(deleted) == {BOYNER_KEY, BOYNER_SHADOW}
    assert webui.executed == [smq.DELETE_ALIAS]
    assert alias_rows == {}  # the write really did happen


def test_upsert_alias_resolves_before_the_canonical_key_is_overwritten():
    """The narrower variant: UPSERT_ALIAS assigns canonical_customer_key =
    EXCLUDED with no COALESCE, so a name that resolved only via the old
    canonical key stops resolving the moment the statement lands."""
    alias_rows = {
        "acct-1": {
            # Does not contain "Boyner", so the ILIKE route cannot rescue this.
            "crm_account_name": "Acme Holding A.Ş.",
            "canonical_customer_key": "Boyner",
        }
    }
    svc, webui, deleted = _service_with_real_planner(alias_rows)

    svc.upsert_alias("acct-1", "Acme Holding A.Ş.", "acme-canonical", "acme-netbox", None)

    assert set(deleted) == {BOYNER_KEY, BOYNER_SHADOW}
    # The overwrite really happened: "Boyner" is now unresolvable.
    assert _alias_resolver(alias_rows)("Boyner") is None


def test_delete_alias_ordering_is_plan_write_apply():
    """Belt-and-braces on the sequence itself: the deletion must stay *after*
    the commit (clearing earlier would let a concurrent reader refill the cache
    from pre-write rows), while only the resolution moves ahead of it."""
    recorder = MagicMock()
    svc = SalesService.__new__(SalesService)
    svc._webui = MagicMock()
    svc._webui.execute = recorder.write
    svc._invalidate_mapping_caches = None
    svc._invalidate_all_mapping_caches = None
    svc._plan_mapping_invalidation = recorder.plan
    svc._apply_mapping_invalidation = recorder.apply

    svc.delete_alias("acct-1")

    assert [c[0] for c in recorder.mock_calls] == ["plan", "write", "apply"]


def test_upsert_alias_ordering_is_plan_write_apply():
    recorder = MagicMock()
    svc = SalesService.__new__(SalesService)
    svc._webui = MagicMock()
    svc._webui.execute = recorder.write
    svc._invalidate_mapping_caches = None
    svc._invalidate_all_mapping_caches = None
    svc._plan_mapping_invalidation = recorder.plan
    svc._apply_mapping_invalidation = recorder.apply

    svc.upsert_alias("acct-1", "Acme", None, "acme-netbox", None)

    assert [c[0] for c in recorder.mock_calls] == ["plan", "write", "apply"]


def test_alias_writers_plan_for_their_own_account():
    recorder = MagicMock()
    svc = SalesService.__new__(SalesService)
    svc._webui = MagicMock()
    svc._invalidate_mapping_caches = None
    svc._invalidate_all_mapping_caches = None
    svc._plan_mapping_invalidation = recorder
    svc._apply_mapping_invalidation = MagicMock()

    svc.delete_alias("acct-1")

    recorder.assert_called_once_with({"acct-1"})


def test_delete_alias_returns_the_rowcount_it_captured():
    """The rowcount is read from the DELETE, not from the invalidation that
    follows it — the router reports 404 off this value."""
    svc, _invalidate = _service()
    svc._plan_mapping_invalidation = MagicMock(return_value=object())
    svc._apply_mapping_invalidation = MagicMock(return_value=None)
    svc._webui.execute.return_value = 3

    assert svc.delete_alias("acct-1") == 3


def test_delete_alias_returns_zero_when_no_row_matched():
    svc, _invalidate = _service()
    svc._plan_mapping_invalidation = MagicMock(return_value=object())
    svc._apply_mapping_invalidation = MagicMock(return_value=None)
    svc._webui.execute.return_value = 0

    assert svc.delete_alias("missing") == 0


# ---------------------------------------------------------------------------
# Paths whose resolution is stable across the write
# ---------------------------------------------------------------------------


def test_save_source_mappings_invalidates_its_account():
    """save_source_mappings writes gui_crm_customer_source_mapping only, which
    the resolver never reads, so resolve-then-delete in one call is correct."""
    svc, invalidate = _service()

    svc.save_source_mappings("acct-1", crm_account_name="Acme", mappings=[])

    invalidate.assert_called_once_with({"acct-1"})


def test_invalidation_is_optional_when_not_injected():
    svc, _ = _service()
    svc._invalidate_mapping_caches = None

    # Must not blow up when the callable was never wired (e.g. unit tests).
    assert svc._invalidate_for({"acct-1"}) is None


def test_alias_invalidation_is_optional_when_not_injected():
    svc, _ = _service()

    # Same for the split halves: unwired means no-op, never AttributeError.
    assert svc._plan_invalidation_for({"acct-1"}) is None
    assert svc._apply_invalidation(None) is None
    assert svc._invalidate_all() is None


def test_invalidation_warning_is_returned_not_raised():
    svc, invalidate = _service()
    invalidate.return_value = "Mapping kaydedildi, ancak cache temizlenemedi."

    warning = svc._invalidate_for({"acct-1"})

    assert warning == "Mapping kaydedildi, ancak cache temizlenemedi."
