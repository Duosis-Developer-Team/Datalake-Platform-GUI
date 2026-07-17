from unittest.mock import MagicMock

from app.services.customer_mapping_resolver import DATA_SOURCES, UI_COLUMN_SOURCES
from app.services.sales_service import SalesService


def test_auranotify_is_a_known_data_source():
    # The UI has shipped an AuraNotify section that posts this value.
    assert "auranotify" in DATA_SOURCES


def test_auranotify_maps_to_a_ui_column():
    assert UI_COLUMN_SOURCES["auranotify"] == ("auranotify",)


def test_saving_an_auranotify_mapping_does_not_raise():
    svc = SalesService.__new__(SalesService)
    svc._webui = MagicMock()
    svc._invalidate_mapping_caches = MagicMock(return_value=None)
    svc.list_source_mappings_for_account = lambda account_id: []

    # Before this task this raised ValueError -> unhandled -> HTTP 500.
    out = svc.save_source_mappings(
        "acct-1",
        crm_account_name="Acme",
        mappings=[
            {"data_source": "auranotify", "match_method": "id_exact", "match_value": "42"}
        ],
    )

    assert out["cache_warning"] is None
    svc._webui.execute_all.assert_called_once()
