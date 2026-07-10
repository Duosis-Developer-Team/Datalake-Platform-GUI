"""Phase 2: a customer whose interactive /resources comes back empty (cold miss /
backend timed out) triggers an on-demand background warm, so the next visit hits
the cache. Populated resources must NOT trigger a warm.
"""
import contextlib
from unittest.mock import patch

from src.pages import customer_view as cv
from tests.test_customer_view_tab_sections import _patch_all_getters, _tr


def _patch_extra_getters(stack):
    """Getters _customer_content calls that _patch_all_getters doesn't cover — patch
    them so the test stays hermetic (no real network) and fast."""
    for name, value in [
        ("get_customer_itsm_extremes", {}),
        ("get_customer_itsm_tickets", []),
        ("get_physical_inventory_customer", []),
        ("get_customer_resource_compliance", {}),
        ("get_customer_nutanix_snapshots", {}),
    ]:
        stack.enter_context(patch.object(cv.api, name, return_value=value))


def test_customer_content_triggers_warm_on_empty_resources():
    with contextlib.ExitStack() as s:
        _patch_all_getters(s)
        _patch_extra_getters(s)
        s.enter_context(patch.object(cv.api, "get_customer_resources",
                                     return_value={"totals": {}, "assets": {}}))
        with patch("src.services.app_background_warm.trigger_customer_view_warm") as m_warm:
            cv._customer_content("Acme", _tr())
    m_warm.assert_called_once()
    assert m_warm.call_args.args[0] == "Acme"


def test_customer_content_no_warm_when_resources_populated():
    with contextlib.ExitStack() as s:
        _patch_all_getters(s)
        _patch_extra_getters(s)  # default _RESOURCES has a non-empty totals dict
        with patch("src.services.app_background_warm.trigger_customer_view_warm") as m_warm:
            cv._customer_content("Acme", _tr())
    m_warm.assert_not_called()
