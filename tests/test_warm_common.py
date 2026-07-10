"""GAP4.1: user-independent warm. warm() was only triggered by a logged-in
user's interval, so with no active session the common pages stayed cold.
warm_common() warms the shared aggregate data (overview/datacenters + SLA)
without a user, and re-reads default_time_range each call (also covering the
daily 7d-window rollover, GAP5).
"""
from unittest.mock import patch

from src.services import app_background_warm as warm


def test_warm_common_warms_home_and_sla_without_user(monkeypatch):
    called = {"home": 0, "sla": 0}
    monkeypatch.setattr(warm, "_warm_home_bundle", lambda tr: called.__setitem__("home", called["home"] + 1))
    monkeypatch.setattr(warm, "_warm_dc_and_availability_sla", lambda rows, tr: called.__setitem__("sla", called["sla"] + 1) or 1)
    monkeypatch.setattr(warm, "_warm_customer_view", lambda *a, **k: 0)
    with patch("src.services.api_client.get_all_datacenters_summary", return_value=[{"id": "DC1"}]):
        stats = warm.warm_common({"preset": "7d", "start": "a", "end": "b"})
    assert called["home"] == 1
    assert called["sla"] == 1
    assert stats["home"] is True


def test_warm_common_uses_default_time_range_when_none(monkeypatch):
    seen = {}
    monkeypatch.setattr(warm, "_warm_home_bundle", lambda tr: seen.__setitem__("tr", tr))
    monkeypatch.setattr(warm, "_warm_dc_and_availability_sla", lambda rows, tr: 0)
    monkeypatch.setattr(warm, "_warm_customer_view", lambda *a, **k: 0)
    with patch("src.services.api_client.get_all_datacenters_summary", return_value=[]):
        warm.warm_common(None)
    assert seen.get("tr") and "preset" in seen["tr"]  # default_time_range resolved


def test_warm_common_warms_customer_view_for_warmed_customers(monkeypatch):
    # customer-view had NO server-side timer (only browser events); warm_common runs
    # on the 240s server timer, so it must also seed the warmed customers' cache.
    monkeypatch.setattr(warm, "_warm_home_bundle", lambda tr: None)
    monkeypatch.setattr(warm, "_warm_dc_and_availability_sla", lambda rows, tr: 0)
    with patch("src.services.api_client.get_all_datacenters_summary", return_value=[]), \
         patch("src.services.db_service.WARMED_CUSTOMERS", ("Acme", "Globex")), \
         patch("src.services.app_background_warm._warm_customer_view", return_value=2) as m_cv:
        stats = warm.warm_common({"preset": "7d"})
    m_cv.assert_called_once()
    assert stats.get("customer_view") == 2
