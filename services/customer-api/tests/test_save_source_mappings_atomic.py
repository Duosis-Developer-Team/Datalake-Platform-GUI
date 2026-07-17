from unittest.mock import MagicMock

import pytest

from app.services.sales_service import SalesService


def _service(webui):
    svc = SalesService.__new__(SalesService)
    svc._webui = webui
    svc._invalidate_mapping_caches = None
    svc.list_source_mappings_for_account = lambda account_id: []
    return svc


def test_delete_and_upserts_go_through_one_transaction():
    webui = MagicMock()
    svc = _service(webui)

    svc.save_source_mappings(
        "acct-1",
        crm_account_name="Acme",
        mappings=[
            {"data_source": "virtualization", "match_method": "contains", "match_value": "acme"},
        ],
    )

    # One execute_all call carrying DELETE + UPSERT, not two separate commits.
    webui.execute_all.assert_called_once()
    statements = list(webui.execute_all.call_args[0][0])
    assert len(statements) == 2
    webui.execute.assert_not_called()


def test_bad_data_source_writes_nothing_at_all():
    webui = MagicMock()
    svc = _service(webui)

    with pytest.raises(ValueError, match="Unsupported data_source"):
        svc.save_source_mappings(
            "acct-1",
            crm_account_name="Acme",
            mappings=[{"data_source": "nope", "match_method": "contains", "match_value": "x"}],
        )

    # The DELETE must not have been committed on its own.
    webui.execute_all.assert_not_called()
    webui.execute.assert_not_called()
