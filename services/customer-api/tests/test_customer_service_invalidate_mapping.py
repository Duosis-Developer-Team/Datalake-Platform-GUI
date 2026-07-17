from unittest.mock import MagicMock, patch

import pytest

from app.services.customer_service import CustomerService
from app.services.mapping_cache_invalidator import ResolutionError


def _svc():
    svc = CustomerService.__new__(CustomerService)
    svc._webui = MagicMock()
    return svc


def test_strict_resolver_raises_instead_of_swallowing():
    svc = _svc()
    with patch.object(
        CustomerService, "_lookup_alias_for_display_name", side_effect=RuntimeError("db down")
    ):
        with pytest.raises(ResolutionError):
            svc.resolve_account_id_strict("Boyner")


def test_strict_resolver_returns_none_for_unknown_name():
    svc = _svc()
    with patch.object(
        CustomerService, "_lookup_alias_for_display_name", return_value=(None, None, None)
    ):
        assert svc.resolve_account_id_strict("Ghost Corp") is None


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


def test_invalidate_with_no_accounts_is_a_noop():
    svc = _svc()
    with patch("app.services.customer_service.cache"), patch(
        "app.services.customer_service.invalidate_for_accounts"
    ) as inv:
        assert svc.invalidate_mapping_caches(set()) is None
        inv.assert_not_called()
