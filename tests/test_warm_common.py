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


def test_warm_common_warms_unmapped_resources(monkeypatch):
    # The unmapped (Eşleşmeyen Veriler) page has no other warm timer, and its
    # backend key is day-stable — it rolls at UTC midnight. Without this, the
    # first visitor after the roll pays the full orphan scan interactively.
    monkeypatch.setattr(warm, "_warm_home_bundle", lambda tr: None)
    monkeypatch.setattr(warm, "_warm_dc_and_availability_sla", lambda rows, tr: 0)
    monkeypatch.setattr(warm, "_warm_customer_view", lambda *a, **k: 0)
    tr = {"preset": "7d", "start": "2026-07-10", "end": "2026-07-16"}
    with patch("src.services.api_client.get_all_datacenters_summary", return_value=[]), \
         patch("src.services.api_client.get_unmapped_resources", return_value={"rows": []}) as m_unmapped:
        stats = warm.warm_common(tr)
    m_unmapped.assert_called_once_with(tr)
    assert stats.get("unmapped") is True


def test_warm_common_survives_unmapped_failure(monkeypatch):
    # An orphan report is the lowest-priority warm and runs last. Its failure must
    # stay contained: warm_common still returns, and the steps that already ran keep
    # their stats rather than being lost to a raise.
    monkeypatch.setattr(warm, "_warm_dc_and_availability_sla", lambda rows, tr: 0)
    monkeypatch.setattr(warm, "_warm_customer_view", lambda *a, **k: 0)
    home = {"n": 0}
    monkeypatch.setattr(warm, "_warm_home_bundle", lambda tr: home.__setitem__("n", home["n"] + 1))
    with patch("src.services.api_client.get_all_datacenters_summary", return_value=[]), \
         patch("src.services.api_client.get_unmapped_resources", side_effect=RuntimeError("backend down")):
        stats = warm.warm_common({"preset": "7d"})
    assert home["n"] == 1
    assert stats.get("unmapped") is False
    assert stats["home"] is True


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
