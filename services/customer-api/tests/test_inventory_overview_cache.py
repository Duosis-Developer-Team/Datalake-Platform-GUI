"""Redis cache behaviour for InventoryOverviewService (TTL, hit, last_good, lock)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.services import inventory_overview_service as mod
from app.services.inventory_overview_service import InventoryOverviewService


def _sample_payload() -> dict:
    return {
        "dc_code": "*",
        "summary": {"panel_count": 2, "infra_panel_count": 1},
        "panels": [{"panel_key": "virt_classic_cpu"}],
        "families": [],
        "crm_only_panels": [],
        "unmapped_products": [],
    }


@pytest.fixture
def inventory_cache_svc():
    sellable = MagicMock()
    sellable.is_available = True
    sellable.compute_all_panels.return_value = []
    sellable.recompute_family_constraints.side_effect = lambda panels, **kw: panels
    sellable._count_unmapped_products.return_value = 0
    sellable.compute_site_scoped_panels.return_value = []
    sellable.get_netbackup_inventory_metrics.return_value = {
        "total_bytes": 0.0,
        "used_pool_bytes": 0.0,
        "used_post_dedup_bytes": 0.0,
        "pre_dedup_bytes": 0.0,
        "available_bytes": 0.0,
        "dedup_savings_bytes": 0.0,
        "dedup_savings_pct": 0.0,
        "dedup_factor": 0.0,
        "by_category": {},
    }

    sales = MagicMock()
    sales._run_query.return_value = []

    webui = MagicMock()
    webui.is_available = False

    svc = InventoryOverviewService(
        sellable=sellable,
        sales=sales,
        webui=webui,
        config=MagicMock(get_calc_dict=lambda: {"efficiency.under_pct": 80.0, "efficiency.over_pct": 110.0}),
        crm_redis=MagicMock(),
    )
    svc._build_inventory_overview = MagicMock(return_value=_sample_payload())
    return svc


def test_inventory_cache_ttl_default_is_3600():
    assert mod._INVENTORY_CACHE_TTL_SEC == 3600.0


def test_compute_inventory_overview_cache_hit(inventory_cache_svc):
    redis = inventory_cache_svc._crm_redis
    cache_key = "crm:inventory_overview:*"
    redis.get.return_value = json.dumps(_sample_payload())

    payload = inventory_cache_svc.compute_inventory_overview("*")

    assert payload["cache_status"] == "hit"
    assert payload["stale"] is False
    assert payload["summary"]["panel_count"] == 2
    inventory_cache_svc._build_inventory_overview.assert_not_called()


def test_write_inventory_cache_writes_primary_and_last_good(inventory_cache_svc):
    redis = inventory_cache_svc._crm_redis
    payload = _sample_payload()

    inventory_cache_svc.write_inventory_cache("*", payload)

    assert redis.setex.call_count == 2
    primary_call = redis.setex.call_args_list[0]
    last_good_call = redis.setex.call_args_list[1]
    assert primary_call.args[0] == "crm:inventory_overview:*"
    assert last_good_call.args[0] == "crm:inventory_overview:*:last_good"
    assert primary_call.args[1] == 3600
    assert last_good_call.args[1] == 7200


def test_compute_inventory_overview_serves_last_good_when_lock_not_acquired(inventory_cache_svc):
    redis = inventory_cache_svc._crm_redis
    primary_key = "crm:inventory_overview:*"
    last_good_key = f"{primary_key}:last_good"
    stale_payload = _sample_payload()
    stale_payload["summary"]["panel_count"] = 9

    def _get_side_effect(key):
        if key == primary_key:
            return None
        if key == last_good_key:
            return json.dumps(stale_payload)
        return None

    redis.get.side_effect = _get_side_effect
    redis.set.return_value = False  # lock not acquired

    payload = inventory_cache_svc.compute_inventory_overview("*")

    assert payload["cache_status"] == "stale"
    assert payload["stale"] is True
    assert payload["summary"]["panel_count"] == 9
    inventory_cache_svc._build_inventory_overview.assert_not_called()


def test_compute_inventory_overview_miss_computes_and_writes(inventory_cache_svc):
    redis = inventory_cache_svc._crm_redis
    redis.get.return_value = None
    redis.set.return_value = True  # lock acquired

    payload = inventory_cache_svc.compute_inventory_overview("*")

    assert payload["cache_status"] == "miss"
    assert payload["stale"] is False
    inventory_cache_svc._build_inventory_overview.assert_called_once_with("*", force_recompute=False)
    assert redis.setex.call_count == 2
