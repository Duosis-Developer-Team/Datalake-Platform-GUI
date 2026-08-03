"""True SWR behaviour for CRM inventory overview in api_client."""
from __future__ import annotations

import time
from unittest.mock import patch

from src.services import api_client as api
from src.services import cache_service


def _inventory_payload(panel_count: int = 2) -> dict:
    return {
        "dc_code": "*",
        "summary": {"panel_count": panel_count},
        "panels": [{"panel_key": "virt_classic_cpu"}],
        "families": [],
    }


def _set_with_age(key: str, value: dict, age_seconds: float) -> None:
    cache_service.set(key, value)
    cache_service.set(api._fetched_ts_key(key), time.time() - age_seconds)


def test_inventory_fresh_entry_served_without_refetch(monkeypatch):
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    key = "api:crm_inventory_overview:*"
    _set_with_age(key, _inventory_payload(1), age_seconds=10)
    calls: list[int] = []

    out = api._api_cache_get_inventory_overview(
        key,
        lambda: calls.append(1) or _inventory_payload(99),
    )

    assert out["summary"]["panel_count"] == 1
    assert calls == []


def test_inventory_stale_entry_served_and_background_refresh_scheduled(monkeypatch):
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    key = "api:crm_inventory_overview:*"
    _set_with_age(key, _inventory_payload(1), age_seconds=400)
    calls: list[int] = []

    with patch.object(api, "_schedule_inventory_swr_refresh") as schedule:
        out = api._api_cache_get_inventory_overview(
            key,
            lambda: calls.append(1) or _inventory_payload(99),
        )

    assert out["summary"]["panel_count"] == 1
    assert calls == []
    assert out.get("stale") is True
    assert out.get("cache_status") == "stale"
    schedule.assert_called_once()


def test_inventory_miss_blocks_on_fetch(monkeypatch):
    cache_service.clear()
    key = "api:crm_inventory_overview:*"
    calls: list[int] = []

    out = api._api_cache_get_inventory_overview(
        key,
        lambda: calls.append(1) or _inventory_payload(5),
    )

    assert out["summary"]["panel_count"] == 5
    assert calls == [1]
    assert cache_service.get(key) is not None


def test_inventory_read_timeout_defaults_to_eight():
    assert api._INVENTORY_READ_TIMEOUT == 8.0
    assert api._INVENTORY_WARM_READ_TIMEOUT == 300.0


def test_get_crm_inventory_overview_uses_warm_timeout_when_force_recompute(monkeypatch):
    captured: dict = {}
    real_client = api.httpx.Client

    def _fake_client(**kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return real_client(**kwargs)

    monkeypatch.setattr(api.httpx, "Client", _fake_client)
    monkeypatch.setattr(api, "_get_json", lambda client, path: _inventory_payload(3))

    out = api.get_crm_inventory_overview("*", force_recompute=True)

    assert out["summary"]["panel_count"] == 3
    assert captured["timeout"] == api._INVENTORY_WARM_TIMEOUT
