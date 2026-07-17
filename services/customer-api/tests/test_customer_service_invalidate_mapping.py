from unittest.mock import MagicMock, patch

import pytest

from app.services.customer_service import CustomerService
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
        "app.services.customer_service.invalidate_for_accounts"
    ) as inv, patch.object(CustomerService, "_schedule_mapping_warm"):
        inv.return_value = MagicMock(deleted_count=2, matched_names=("Boyner",), scanned_count=9)
        warning = svc.invalidate_mapping_caches({"acct-1"})

    assert warning is None
    cache.delete_prefix.assert_any_call("unmapped_resources:")


def test_invalidate_returns_warning_when_cache_fails():
    svc = _svc()
    with patch("app.services.customer_service.cache"), patch(
        "app.services.customer_service.invalidate_for_accounts",
        side_effect=ResolutionError("webui down"),
    ), patch.object(CustomerService, "_schedule_mapping_warm"):
        warning = svc.invalidate_mapping_caches({"acct-1"})

    # A warning string, not an exception: the DB write already committed.
    assert warning is not None
    assert "cache" in warning.lower()


def test_invalidate_warms_the_matched_names():
    svc = _svc()
    with patch("app.services.customer_service.cache"), patch(
        "app.services.customer_service.invalidate_for_accounts"
    ) as inv, patch.object(CustomerService, "_schedule_mapping_warm") as warm:
        inv.return_value = MagicMock(
            deleted_count=2, matched_names=("Boyner", "BOYNER A.Ş."), scanned_count=9
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
        "app.services.customer_service.invalidate_for_accounts"
    ) as inv, patch.object(
        CustomerService, "_schedule_mapping_warm", side_effect=RuntimeError("scheduler down")
    ):
        inv.return_value = MagicMock(deleted_count=2, matched_names=("Boyner",), scanned_count=9)
        warning = svc.invalidate_mapping_caches({"acct-1"})

    assert warning is None


def test_invalidate_with_no_accounts_is_a_noop():
    svc = _svc()
    with patch("app.services.customer_service.cache"), patch(
        "app.services.customer_service.invalidate_for_accounts"
    ) as inv:
        assert svc.invalidate_mapping_caches(set()) is None
        inv.assert_not_called()
