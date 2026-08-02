"""CRM Inventory Replication column semantics."""
from __future__ import annotations

from src.components.crm_inventory_report import columns_for_family, prepare_service_row


def test_replication_columns_use_allocated_and_sellable_triad():
    cols = columns_for_family("backup_veeam_replication_classic")
    ids = [c["id"] for c in cols]
    names = {c["id"]: c["name"] for c in cols}
    assert names["used_fmt"] == "Allocated"
    assert "sellable_alloc_fmt" in ids
    assert "sellable_max_fmt" in ids
    assert "sellable_avg_fmt" in ids
    assert "sellable_range_fmt" in ids


def test_replication_free_uses_capacity_not_sellable_min():
    row = prepare_service_row(
        {
            "service_label": "Veeam Replication Classic — CPU",
            "family": "backup_veeam_replication_classic",
            "display_unit": "vCPU",
            "total": 100.0,
            "used_qty": 60.0,
            "free_qty": 40.0,
            "free_tl": 400.0,
            "sellable_qty": 0.0,
            "sellable_alloc_qty": 30.0,
            "sellable_max_qty": 25.0,
            "sellable_avg_qty": 20.0,
            "sellable_min_qty": 0.0,
            "sellable_max_qty_range": 30.0,
            "potential_tl_alloc": 300.0,
            "potential_tl_max": 250.0,
            "potential_tl_avg": 200.0,
            "unit_price_tl": 10.0,
            "has_infra_source": True,
            "has_price": True,
            "sellable_profile": "dual_track",
            "inventory_free_mode": "capacity",
            "used_is_allocation": True,
            "status": "ok",
        }
    )
    assert "40" in row["free_fmt"]
    assert "0 vCPU" not in row["free_fmt"].split("\n")[0] or "40" in row["free_fmt"]
    assert "30" in row["sellable_alloc_fmt"]
    assert row["used_is_allocation"] is True


def test_allocation_exceeds_hint():
    row = prepare_service_row(
        {
            "service_label": "Zerto Classic CPU",
            "family": "backup_zerto_replication_classic",
            "display_unit": "vCPU",
            "total": 10.0,
            "used_qty": 20.0,
            "free_qty": 0.0,
            "has_infra_source": True,
            "has_price": False,
            "sellable_profile": "dual_track",
            "inventory_free_mode": "capacity",
            "data_quality": "suspect",
            "suspect_reason": "allocation_exceeds_total",
            "status": "ok",
        }
    )
    assert "Allocation exceeds capacity" in row["service_label"]
