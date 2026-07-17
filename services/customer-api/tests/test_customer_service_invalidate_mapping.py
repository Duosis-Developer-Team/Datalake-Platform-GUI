from unittest.mock import MagicMock, patch

import pytest

from app.services.customer_service import CustomerService, MappingInvalidationPlan
from app.services.mapping_cache_invalidator import ResolutionError


def _svc():
    svc = CustomerService.__new__(CustomerService)
    svc._webui = MagicMock()
    return svc


def test_strict_resolver_raises_when_webui_lookup_fails():
    """A real DB failure inside the lookup must surface as ResolutionError, not
    as a clean None. Only the webui mock's own method is patched — the
    resolver's real code path (_lookup_alias_for_display_name_raising) runs
    for real, so this proves the exception actually propagates through it."""
    svc = _svc()
    svc._webui.is_available = True
    svc._webui.run_rows.side_effect = RuntimeError("db down")
    with pytest.raises(ResolutionError):
        svc.resolve_account_id_strict("Boyner")


def test_strict_resolver_raises_when_webui_unavailable():
    """If webui is down we cannot tell who owns the name — that is "cannot
    tell", not "belongs to nobody", so it must raise rather than return None."""
    svc = _svc()
    svc._webui.is_available = False
    with pytest.raises(ResolutionError):
        svc.resolve_account_id_strict("Boyner")


def test_strict_resolver_returns_none_when_genuinely_not_found():
    """A lookup that genuinely finds nothing (no alias row, no accountid row,
    no datalake match) is a clean "belongs to nobody" and must return None,
    not raise."""
    svc = _svc()
    svc._webui.is_available = True
    svc._webui.run_rows.return_value = []
    svc._webui.run_one.return_value = None
    svc._pool = None  # no datalake fallback available; resolve_crm_account_ids
    # degrades to [] without touching the DB when both webui and the datalake
    # lookup are unavailable.

    assert svc.resolve_account_id_strict("Ghost Corp") is None


def test_lookup_alias_for_display_name_still_swallows_exceptions():
    """Regression guard: the non-strict wrapper used by every other caller
    (resolve_source_patterns, resolve_infra_search_name, ...) must keep
    swallowing failures and returning (None, None, None) — only the strict
    resolver is allowed to raise."""
    svc = _svc()
    svc._webui.is_available = True
    svc._webui.run_rows.side_effect = RuntimeError("db down")
    assert svc._lookup_alias_for_display_name("Boyner") == (None, None, None)


def test_invalidate_drops_unmapped_resources_too():
    svc = _svc()
    with patch("app.services.customer_service.cache") as cache, patch(
        "app.services.customer_service.plan_invalidation_for_accounts"
    ) as inv, patch.object(CustomerService, "_schedule_mapping_warm"):
        inv.return_value = MagicMock(
            doomed_keys=("k1", "k2"), matched_names=("Boyner",), scanned_count=9
        )
        warning = svc.invalidate_mapping_caches({"acct-1"})

    assert warning is None
    cache.delete_prefix.assert_any_call("unmapped_resources:")


def test_invalidate_returns_warning_when_cache_fails():
    svc = _svc()
    with patch("app.services.customer_service.cache"), patch(
        "app.services.customer_service.plan_invalidation_for_accounts",
        side_effect=ResolutionError("webui down"),
    ), patch.object(CustomerService, "_schedule_mapping_warm"):
        warning = svc.invalidate_mapping_caches({"acct-1"})

    # A warning string, not an exception: the DB write already committed.
    assert warning is not None
    assert "cache" in warning.lower()


def test_invalidate_warms_the_matched_names():
    svc = _svc()
    with patch("app.services.customer_service.cache"), patch(
        "app.services.customer_service.plan_invalidation_for_accounts"
    ) as inv, patch.object(CustomerService, "_schedule_mapping_warm") as warm:
        inv.return_value = MagicMock(
            doomed_keys=("k1", "k2"), matched_names=("Boyner", "BOYNER A.Ş."), scanned_count=9
        )
        svc.invalidate_mapping_caches({"acct-1"})

    warm.assert_called_once_with(("Boyner", "BOYNER A.Ş."))


def test_invalidate_does_not_raise_when_warm_scheduling_fails():
    """Task 6 replaces the _schedule_mapping_warm no-op stub with a real
    debounced scheduler that can fail. invalidate_mapping_caches's "never
    raises" invariant holds only if the DB write already committed makes it
    a lie to report failure — a warm failure must not become an exception
    that escapes this method, nor should it be reported as a cache-clear
    failure, since the actual invalidation (the deletes) already succeeded."""
    svc = _svc()
    with patch("app.services.customer_service.cache"), patch(
        "app.services.customer_service.plan_invalidation_for_accounts"
    ) as inv, patch.object(
        CustomerService, "_schedule_mapping_warm", side_effect=RuntimeError("scheduler down")
    ):
        inv.return_value = MagicMock(
            doomed_keys=("k1", "k2"), matched_names=("Boyner",), scanned_count=9
        )
        warning = svc.invalidate_mapping_caches({"acct-1"})

    assert warning is None


def test_invalidate_with_no_accounts_is_a_noop():
    svc = _svc()
    with patch("app.services.customer_service.cache"), patch(
        "app.services.customer_service.plan_invalidation_for_accounts"
    ) as inv:
        assert svc.invalidate_mapping_caches(set()) is None
        inv.assert_not_called()


# ---------------------------------------------------------------------------
# The plan/apply split
# ---------------------------------------------------------------------------


def test_plan_deletes_nothing_yet():
    """The whole point of planning separately: it resolves, but the cache must
    still be intact afterwards — deletion waits for the DB write to commit."""
    svc = _svc()
    with patch("app.services.customer_service.cache") as cache, patch(
        "app.services.customer_service.plan_invalidation_for_accounts"
    ) as inv:
        inv.return_value = MagicMock(
            doomed_keys=("k1",), matched_names=("Boyner",), scanned_count=9
        )
        plan = svc.plan_mapping_invalidation({"acct-1"})

    assert plan.doomed_keys == ("k1",)
    cache.delete.assert_not_called()
    cache.delete_prefix.assert_not_called()


def test_plan_carries_the_warning_instead_of_raising():
    """Planning runs on a request that is about to commit, so a resolution
    failure must travel as a warning, never as an exception."""
    svc = _svc()
    with patch("app.services.customer_service.cache"), patch(
        "app.services.customer_service.plan_invalidation_for_accounts",
        side_effect=ResolutionError("webui down"),
    ):
        plan = svc.plan_mapping_invalidation({"acct-1"})

    assert plan.warning is not None
    assert plan.doomed_keys == ()


def test_apply_returns_the_plans_warning_and_deletes_nothing():
    svc = _svc()
    plan = MappingInvalidationPlan(account_ids=("acct-1",), warning="cache temizlenemedi")
    with patch("app.services.customer_service.cache") as cache:
        warning = svc.apply_mapping_invalidation(plan)

    assert warning == "cache temizlenemedi"
    cache.delete_prefix.assert_not_called()


def test_apply_deletes_exactly_the_planned_keys():
    svc = _svc()
    plan = MappingInvalidationPlan(
        account_ids=("acct-1",),
        doomed_keys=("customer_assets:v:Boyner:a:b", "customer_assets:v:Boyner:a:b:last_good"),
        matched_names=("Boyner",),
        scanned_count=4,
    )
    with patch("app.services.customer_service.cache") as cache, patch.object(
        CustomerService, "_schedule_mapping_warm"
    ) as warm:
        warning = svc.apply_mapping_invalidation(plan)

    assert warning is None
    cache.delete.assert_any_call("customer_assets:v:Boyner:a:b")
    cache.delete.assert_any_call("customer_assets:v:Boyner:a:b:last_good")
    cache.delete_prefix.assert_any_call("unmapped_resources:")
    warm.assert_called_once_with(("Boyner",))


def test_apply_of_a_noop_plan_touches_nothing():
    """An empty account set means nothing changed, so unmapped_resources: must
    not be dropped either — distinct from a real plan that matched zero keys."""
    svc = _svc()
    with patch("app.services.customer_service.cache") as cache:
        assert svc.apply_mapping_invalidation(svc.plan_mapping_invalidation(set())) is None

    cache.delete_prefix.assert_not_called()


# ---------------------------------------------------------------------------
# The resolver-free bulk path (resync)
# ---------------------------------------------------------------------------


def test_invalidate_all_drops_every_key_without_resolving():
    svc = _svc()
    keys = [
        "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16",
        "customer_assets:cpu-usage-v3:Ghost Corp:2026-07-09:2026-07-16",
    ]
    with patch("app.services.customer_service.cache") as cache, patch.object(
        CustomerService, "_scan_cache_keys", return_value=keys
    ), patch.object(CustomerService, "_schedule_mapping_warm") as warm, patch.object(
        CustomerService, "resolve_account_id_strict"
    ) as resolver:
        warning = svc.invalidate_all_mapping_caches()

    assert warning is None
    # "Ghost Corp" resolves to nobody; the targeted path would skip it and leave
    # it stale. Here it goes, and no resolver was consulted at all.
    for key in keys:
        cache.delete.assert_any_call(key)
    resolver.assert_not_called()
    cache.delete_prefix.assert_any_call("unmapped_resources:")
    warm.assert_called_once_with(("Boyner", "Ghost Corp"))


def test_invalidate_all_returns_warning_when_the_scan_fails():
    svc = _svc()
    with patch("app.services.customer_service.cache"), patch.object(
        CustomerService, "_scan_cache_keys", side_effect=RuntimeError("redis down")
    ):
        warning = svc.invalidate_all_mapping_caches()

    assert warning is not None
    assert "cache" in warning.lower()
