from unittest.mock import MagicMock

from app.services.sales_service import SalesService


def _service(warning=None):
    svc = SalesService.__new__(SalesService)
    svc._webui = MagicMock()
    svc._invalidate_mapping_caches = MagicMock(return_value=warning)
    svc.list_source_mappings_for_account = lambda account_id: [{"data_source": "virtualization"}]
    return svc


def test_happy_path_has_no_warning():
    svc = _service(warning=None)

    out = svc.save_source_mappings("acct-1", crm_account_name="Acme", mappings=[])

    assert out["cache_warning"] is None
    assert out["mappings"] == [{"data_source": "virtualization"}]


def test_cache_failure_surfaces_as_a_warning_and_still_saves():
    svc = _service(warning="Mapping kaydedildi, ancak cache temizlenemedi — lütfen tekrar kaydedin.")

    out = svc.save_source_mappings("acct-1", crm_account_name="Acme", mappings=[])

    # Saved (mappings returned) AND warned — not an exception.
    assert out["mappings"] == [{"data_source": "virtualization"}]
    assert "cache" in out["cache_warning"].lower()
