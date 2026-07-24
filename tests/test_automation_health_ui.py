"""Unit tests for HMDL automation-health UI helpers."""

from src.utils.hmdl_sync_ui import (
    automation_status_badge,
    relative_age,
    staleness_alert_banner,
)


def test_relative_age_none():
    assert relative_age(None) == "—"


def test_relative_age_recent():
    assert relative_age(0.1) == "az önce"


def test_relative_age_hours():
    assert relative_age(5) == "5 sa önce"
    assert relative_age(47) == "47 sa önce"


def test_relative_age_days_turkish_comma():
    # 58.7h / 24 = 2.446 -> 2.4 gün, Türkçe ondalık virgülü
    assert relative_age(58.7) == "2,4 gün önce"


def test_automation_status_badge_colors():
    assert automation_status_badge("fresh").color == "green"
    assert automation_status_badge("stale").color == "orange"
    assert automation_status_badge("dead").color == "red"
    assert automation_status_badge("unknown").color == "gray"


def test_staleness_banner_none_when_no_alert():
    assert staleness_alert_banner({"alert": 0, "stale": 0, "dead": 0}, "/x") is None


def test_staleness_banner_when_alert():
    b = staleness_alert_banner({"alert": 3, "stale": 1, "dead": 2}, "/x")
    assert b is not None
    assert b.color == "red"
