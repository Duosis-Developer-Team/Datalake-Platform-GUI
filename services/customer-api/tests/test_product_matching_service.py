"""Tests for product matching registry + ProductMatchingService."""
from __future__ import annotations

from shared.matching import clear_registry_cache, load_product_matching_registry
from shared.matching.loader import VALID_STATUSES


def test_registry_loads_capacity_and_documented_skus():
    clear_registry_cache()
    reg = load_product_matching_registry()
    assert "000BLT-46" in reg
    assert reg["000BLT-46"]["match_status"] == "capacity"
    assert reg["000BLT-46"]["panel_key"] == "virt_hyperconverged_cpu"
    assert "000BLT-123" in reg
    assert reg["000BLT-123"]["match_status"] == "documented"
    assert "000BLT-144" in reg
    assert reg["000BLT-144"]["match_status"] == "sold_noted_customer_phase"
    for entry in reg.values():
        assert entry["match_status"] in VALID_STATUSES


def test_product_matching_service_merges_sold_and_panels():
    from app.services.product_matching_service import ProductMatchingService

    class _FakeDb:
        _pool = object()

        def _run_query(self, _sql, _params=None):
            return [
                {
                    "productnumber": "000BLT-46",
                    "product_name": "Hyperconverged Mimari Intel CPU",
                    "resource_unit": "vCPU",
                    "sold_qty": 100.0,
                    "sold_amount_tl": 150000.0,
                },
                {
                    "productnumber": "00999-ORPHAN",
                    "product_name": "Unknown Sold SKU",
                    "resource_unit": "Adet",
                    "sold_qty": 5.0,
                    "sold_amount_tl": 50.0,
                },
            ]

    svc = ProductMatchingService(customer_svc=_FakeDb(), inventory_svc=None)
    payload = svc.compute_product_matching(
        panel_by_key={
            "virt_hyperconverged_cpu": {
                "panel_key": "virt_hyperconverged_cpu",
                "total": 200.0,
                "used_qty": 80.0,
                "free_qty": 120.0,
                "status": "ok",
                "display_unit": "vCPU",
            }
        }
    )
    by_pn = {p["productnumber"]: p for p in payload["products"]}
    hc = by_pn["000BLT-46"]
    assert hc["crm_sold_qty"] == 100.0
    assert hc["infra_total"] == 200.0
    assert hc["match_status"] == "capacity"
    orphan = by_pn["00999-ORPHAN"]
    assert orphan["match_status"] == "documented"
    assert "not yet in matching registry" in orphan["notes"]
    assert payload["summary"]["with_sold_count"] >= 2
