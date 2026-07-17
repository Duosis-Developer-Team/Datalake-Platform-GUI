from unittest.mock import MagicMock

from app.services.sales_service import SalesService


def _service():
    invalidate = MagicMock(return_value=None)
    svc = SalesService.__new__(SalesService)
    svc._webui = MagicMock()
    svc._invalidate_mapping_caches = invalidate
    svc.list_source_mappings_for_account = lambda account_id: []
    return svc, invalidate


def test_save_source_mappings_invalidates_its_account():
    svc, invalidate = _service()

    svc.save_source_mappings("acct-1", crm_account_name="Acme", mappings=[])

    invalidate.assert_called_once_with({"acct-1"})


def test_upsert_alias_invalidates():
    svc, invalidate = _service()

    svc.upsert_alias("acct-1", "Acme", None, "acme-netbox", None)

    invalidate.assert_called_once_with({"acct-1"})


def test_delete_alias_invalidates():
    svc, invalidate = _service()
    svc._webui.execute.return_value = 1

    svc.delete_alias("acct-1")

    invalidate.assert_called_once_with({"acct-1"})


def test_invalidation_is_optional_when_not_injected():
    svc, _ = _service()
    svc._invalidate_mapping_caches = None

    # Must not blow up when the callable was never wired (e.g. unit tests).
    assert svc._invalidate_for({"acct-1"}) is None


def test_invalidation_warning_is_returned_not_raised():
    svc, invalidate = _service()
    invalidate.return_value = "Mapping kaydedildi, ancak cache temizlenemedi."

    warning = svc._invalidate_for({"acct-1"})

    assert warning == "Mapping kaydedildi, ancak cache temizlenemedi."
