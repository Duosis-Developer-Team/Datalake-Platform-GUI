"""Item 3.1/3.2: per-tab render functions that fetch only their own data and
render, so each tab can load independently (item 3.3/3.4). Here we cover the
independent tabs (availability, physical inventory, ITSM, S3): each calls just
its own api getter(s) and returns a component.
"""
from unittest.mock import patch

from src.pages import customer_view as cv


def _tr():
    return {"start": "2024-06-01", "end": "2024-06-07", "preset": "7d"}


def test_render_availability_tab_fetches_only_availability():
    bundle = {"service_downtimes": [], "vm_downtimes": [], "vm_outage_counts": {}}
    with patch.object(cv.api, "get_customer_availability_bundle", return_value=bundle) as m:
        out = cv.render_availability_tab("Acme", _tr())
    m.assert_called_once_with("Acme", _tr())
    assert out is not None


def test_render_physical_inventory_tab_fetches_only_phys():
    with patch.object(cv.api, "get_physical_inventory_customer", return_value=[]) as m:
        out = cv.render_physical_inventory_tab("Acme")
    m.assert_called_once_with("Acme")
    assert out is not None


def test_render_itsm_tab_fetches_only_itsm_calls():
    with patch.object(cv.api, "get_customer_itsm_summary", return_value={}) as m1, \
         patch.object(cv.api, "get_customer_itsm_extremes", return_value={}) as m2, \
         patch.object(cv.api, "get_customer_itsm_tickets", return_value=[]) as m3:
        out = cv.render_itsm_tab("Acme", _tr())
    m1.assert_called_once()
    m2.assert_called_once()
    m3.assert_called_once()
    assert out is not None


def test_render_s3_tab_fetches_only_s3():
    with patch.object(cv.api, "get_customer_s3_vaults", return_value={"vaults": []}) as m:
        out = cv.render_s3_tab("Acme", _tr())
    m.assert_called_once_with("Acme", _tr())
    assert out is not None
