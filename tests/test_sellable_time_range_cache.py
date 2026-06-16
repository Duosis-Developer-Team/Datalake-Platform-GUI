"""Sellable cache keys include GUI time-range for Virt alignment."""
from unittest.mock import patch

from src.services import api_client as api
from src.services import cache_service


def test_sellable_by_panel_cache_key_includes_time_range():
    cache_service.clear()
    calls = []

    def fake_get_json(client, path, params=None):
        calls.append(path)
        return []

    with patch.object(api, "_get_json", side_effect=fake_get_json):
        tr = {"preset": "30d", "start": "2026-05-01", "end": "2026-06-01"}
        api.get_sellable_by_panel("DC13", "virt_classic", None, tr=tr)
        api.get_sellable_by_panel("DC13", "virt_classic", None, tr={"preset": "7d"})

    assert len(calls) == 2


def test_virt_sellable_panels_reuses_by_panel_cache():
    cache_service.clear()
    calls = {"n": 0}

    def fake_get_json(client, path, params=None):
        calls["n"] += 1
        return []

    with patch.object(api, "_get_json", side_effect=fake_get_json):
        api.get_virt_sellable_panels("DC13", None, None, tr={"preset": "7d"})

    assert calls["n"] == 4
