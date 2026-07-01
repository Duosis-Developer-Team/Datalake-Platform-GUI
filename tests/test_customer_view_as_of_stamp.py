"""Data-freshness "as-of" stamp: the customer view shows when its data was last
fetched (the no-stale UX promise — cache == DB, and here's the timestamp).
"""
from unittest.mock import patch

from src.pages import customer_view as cv
from src.services import api_client as api
from src.services import cache_service


def test_get_customer_resources_as_of_after_fetch():
    cache_service.clear()
    # Non-empty payload so it is actually persisted (and thus stamped).
    payload = {"totals": {"vms_total": 1}, "assets": {"classic": {"vm_count": 1}}}
    with patch.object(api, "_get_json", return_value=payload):
        api.get_customer_resources("Acme", {"preset": "7d"})
    ts = api.get_customer_resources_as_of("Acme", {"preset": "7d"})
    assert ts is not None


def test_get_customer_resources_as_of_none_when_never_fetched():
    cache_service.clear()
    assert api.get_customer_resources_as_of("NeverSeen", {"preset": "7d"}) is None


def test_as_of_stamp_text_formats_hh_mm(monkeypatch):
    monkeypatch.setattr(cv.api, "get_customer_resources_as_of", lambda n, tr: 1_700_000_000.0)
    txt = cv._as_of_stamp_text({"customer": "Acme", "tr": {}})
    assert "as-of" in txt.lower() or "veri" in txt.lower()
    assert ":" in txt  # HH:MM


def test_as_of_stamp_text_empty_when_no_data(monkeypatch):
    monkeypatch.setattr(cv.api, "get_customer_resources_as_of", lambda n, tr: None)
    assert cv._as_of_stamp_text({"customer": "Acme"}) == ""
    assert cv._as_of_stamp_text({}) == ""
