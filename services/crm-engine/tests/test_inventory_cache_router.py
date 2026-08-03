"""HTTP contract tests for inventory overview cache headers and PM embed skip."""
from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import inventory as inventory_router


def _payload(*, cache_status: str = "hit", stale: bool = False, with_pm: bool = False) -> dict:
    body = {
        "dc_code": "*",
        "summary": {"panel_count": 1},
        "panels": [{"panel_key": "virt_classic_cpu"}],
        "cache_status": cache_status,
        "stale": stale,
    }
    if with_pm:
        body["product_matching"] = {"products": [{"productid": "p1"}], "summary": {}}
    return body


def _make_client(
    *,
    payload: dict | None = None,
    matching: MagicMock | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(inventory_router.router, prefix="/api/v1")

    inventory = MagicMock()
    inventory.is_available.return_value = True
    inventory.compute_inventory_overview.return_value = payload or _payload()
    inventory.write_inventory_cache = MagicMock()

    app.state.inventory = inventory
    app.state.product_matching = matching
    return TestClient(app)


def test_inventory_overview_x_cache_hit():
    client = _make_client(payload=_payload(cache_status="hit"))
    response = client.get("/api/v1/crm/inventory-overview?dc_code=*")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "hit"


def test_inventory_overview_x_cache_stale():
    client = _make_client(payload=_payload(cache_status="stale", stale=True))
    response = client.get("/api/v1/crm/inventory-overview?dc_code=*")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "stale"


def test_inventory_overview_x_cache_miss():
    client = _make_client(payload=_payload(cache_status="miss"))
    response = client.get("/api/v1/crm/inventory-overview?dc_code=*")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "miss"


def test_inventory_overview_skips_product_matching_when_already_embedded():
    matching = MagicMock()
    matching.is_available.return_value = True
    matching.compute_product_matching = MagicMock(
        return_value={"products": [{"productid": "new"}], "summary": {}},
    )
    client = _make_client(payload=_payload(with_pm=True), matching=matching)

    response = client.get("/api/v1/crm/inventory-overview?dc_code=*")

    assert response.status_code == 200
    matching.compute_product_matching.assert_not_called()
    assert response.json()["product_matching"]["products"][0]["productid"] == "p1"


def test_inventory_overview_embeds_product_matching_on_cache_miss():
    matching = MagicMock()
    matching.is_available.return_value = True
    matching.compute_product_matching.return_value = {
        "products": [{"productid": "fresh"}],
        "summary": {},
    }
    client = _make_client(payload=_payload(cache_status="miss"), matching=matching)

    response = client.get("/api/v1/crm/inventory-overview?dc_code=*")

    assert response.status_code == 200
    matching.compute_product_matching.assert_called_once()
    assert response.json()["product_matching"]["products"][0]["productid"] == "fresh"
    client.app.state.inventory.write_inventory_cache.assert_called_once()
