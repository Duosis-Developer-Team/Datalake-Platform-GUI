"""HTTP contract tests for app.routers.sellable — no real DB.

We mount the router on a tiny FastAPI app with mocked ``app.state``
services so we validate URL shapes + JSON field names without needing
Dockerised Postgres.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import sellable as sellable_router


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(sellable_router.router, prefix="/api/v1")

    sellable = MagicMock()
    sellable.is_available = True
    sellable.compute_summary.return_value.to_dict.return_value = {
        "dc_code": "*",
        "total_potential_tl": 100.0,
        "constrained_loss_tl": 5.0,
        "ytd_sales_tl": 50.0,
        "unmapped_product_count": 2,
        "families": [],
    }
    sellable.compute_all_panels.return_value = [
        MagicMock(
            to_dict=lambda: {
                "panel_key": "virt_hyperconverged_cpu",
                "family": "virt_hyperconverged",
                "resource_kind": "cpu",
                "sellable_constrained": 3.0,
            }
        )
    ]
    sellable.get_metric_dict.return_value = {
        "a.b.c": MagicMock(metric_key="a.b.c", value=1.0, unit="TL", scope_type="global", scope_id="*"),
    }
    sellable.list_metric_snapshots.return_value = [
        {"metric_key": "a.b.c", "scope_type": "global", "scope_id": "*", "value": 1.0, "unit": "TL", "captured_at": None},
    ]

    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.side_effect = [
        [{"panel_key": "p1", "label": "L", "family": "f", "resource_kind": "cpu", "display_unit": "vCPU", "sort_order": 1, "enabled": True, "notes": None, "updated_by": "x", "updated_at": None}],
        [{"family": "f", "dc_code": "*", "cpu_per_unit": 1.0, "ram_gb_per_unit": 8.0, "storage_gb_per_unit": 100.0, "notes": None, "updated_by": "x", "updated_at": None}],
        [{"from_unit": "GHz", "to_unit": "vCPU", "factor": 8.0, "operation": "divide", "ceil_result": True, "notes": None, "updated_by": "x", "updated_at": None}],
    ]
    webui.run_one.return_value = {"panel_key": "p1", "dc_code": "*"}
    webui.execute.return_value = 1

    app.state.sellable = sellable
    app.state.webui = webui

    return TestClient(app)


def test_summary_endpoint():
    c = _make_client()
    r = c.get("/api/v1/crm/sellable-potential/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["total_potential_tl"] == 100.0
    assert body["unmapped_product_count"] == 2


def test_by_panel_family_filter():
    c = _make_client()
    r = c.get("/api/v1/crm/sellable-potential/by-panel?family=virt_hyperconverged")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    sellable = c.app.state.sellable
    sellable.compute_all_panels.assert_called()


def test_by_family_endpoint():
    c = _make_client()
    r = c.get("/api/v1/crm/sellable-potential/by-family")
    assert r.status_code == 200
    assert r.json() == []


def test_metric_tags_returns_list_of_rows():
    c = _make_client()
    r = c.get("/api/v1/crm/metric-tags")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["metric_key"] == "a.b.c"


def test_metric_snapshots_endpoint():
    c = _make_client()
    r = c.get("/api/v1/crm/metric-tags/snapshots?metric_key=a.b.c&hours=24")
    assert r.status_code == 200
    assert r.json()[0]["value"] == 1.0


def test_list_panels_reads_webui():
    c = _make_client()
    r = c.get("/api/v1/crm/panels")
    assert r.status_code == 200
    assert r.json()[0]["panel_key"] == "p1"


def test_upsert_panel_validates_resource_kind():
    c = _make_client()
    r = c.put(
        "/api/v1/crm/panels/bad",
        json={
            "label": "x",
            "family": "f",
            "resource_kind": "invalid",
            "display_unit": "GB",
            "sort_order": 1,
            "enabled": True,
        },
    )
    assert r.status_code == 400


def test_upsert_ratio_rejects_non_positive():
    c = _make_client()
    r = c.put(
        "/api/v1/crm/resource-ratios/f",
        json={"dc_code": "*", "cpu_per_unit": 0.0, "ram_gb_per_unit": 8.0, "storage_gb_per_unit": 100.0},
    )
    assert r.status_code == 400


def test_upsert_unit_conversion_rejects_bad_operation():
    c = _make_client()
    r = c.put(
        "/api/v1/crm/unit-conversions/A/B",
        json={"factor": 1.0, "operation": "xor", "ceil_result": False},
    )
    assert r.status_code == 400


def test_sellable_unavailable_returns_503():
    app = FastAPI()
    app.include_router(sellable_router.router, prefix="/api/v1")
    bad = MagicMock()
    bad.is_available = False
    app.state.sellable = bad
    app.state.webui = MagicMock(is_available=True)

    c = TestClient(app)
    r = c.get("/api/v1/crm/sellable-potential/summary")
    assert r.status_code == 503
