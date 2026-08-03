"""CRM Inventory Replication column semantics."""
from __future__ import annotations

from src.components.crm_inventory_report import (
    _fmt_sellable_tl_interval,
    _header_money_badges,
    _row_sellable_tl_bounds,
    columns_for_family,
    prepare_service_row,
)


def test_replication_columns_keep_triad_drop_minmax():
    cols = columns_for_family("backup_veeam_replication_classic")
    ids = [c["id"] for c in cols]
    names = {c["id"]: c["name"] for c in cols}
    assert names["used_fmt"] == "Allocated"
    assert "unsold_fmt" in ids
    assert "sellable_alloc_fmt" in ids
    assert "sellable_max_fmt" in ids
    assert "sellable_avg_fmt" in ids
    assert "sellable_range_fmt" not in ids


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
            "unsold_qty": 70.0,
            "unsold_tl": 700.0,
            "crm_sold_qty": 30.0,
            "sellable_qty": 0.0,
            "sellable_alloc_qty": 30.0,
            "sellable_max_qty": 25.0,
            "sellable_avg_qty": 20.0,
            "potential_tl_alloc": 300.0,
            "potential_tl_max": 250.0,
            "potential_tl_avg": 200.0,
            "unit_price_tl": 10.0,
            "has_infra_source": True,
            "has_price": True,
            "sellable_profile": "dual_track",
            "inventory_free_mode": "infra",
            "used_is_allocation": True,
            "status": "ok",
        }
    )
    assert "40" in row["free_fmt"]
    assert "70" in row["unsold_fmt"]
    assert "0 vCPU" not in row["free_fmt"].split("\n")[0] or "40" in row["free_fmt"]
    assert "30" in row["sellable_alloc_fmt"]
    assert row["used_is_allocation"] is True


def test_unsold_fallback_when_api_omits_unsold_qty():
    row = prepare_service_row(
        {
            "service_label": "Veeam Replication Classic — CPU",
            "family": "backup_veeam_replication_classic",
            "display_unit": "vCPU",
            "total": 8512.0,
            "crm_sold_qty": 0.0,
            "used_qty": 19047.0,
            "free_qty": 0.0,
            "unit_price_tl": 37.47,
            "has_infra_source": True,
            "has_price": True,
            "sellable_profile": "dual_track",
            "inventory_free_mode": "infra",
            "status": "ok",
        }
    )
    assert "8,512" in row["unsold_fmt"]
    assert "—" not in row["unsold_fmt"].split("\n")[0]


def test_replication_storage_triad_formats_from_constrained_fields():
    row = prepare_service_row(
        {
            "service_label": "Veeam Replication Classic — Storage",
            "family": "backup_veeam_replication_classic",
            "display_unit": "GB",
            "resource_kind": "storage",
            "total": 10000.0,
            "used_qty": 4000.0,
            "free_qty": 6000.0,
            "unsold_qty": 9000.0,
            "sellable_alloc_qty": 2500.0,
            "sellable_max_qty": 2500.0,
            "sellable_avg_qty": 2500.0,
            "potential_tl_alloc": 25000.0,
            "potential_tl_max": 25000.0,
            "potential_tl_avg": 25000.0,
            "unit_price_tl": 10.0,
            "has_infra_source": True,
            "has_price": True,
            "sellable_profile": "dual_track",
            "inventory_free_mode": "infra",
            "used_is_allocation": True,
            "status": "ok",
        }
    )
    assert "2,500 GB" in row["sellable_alloc_fmt"]
    assert "2,500 GB" in row["sellable_max_fmt"]
    assert "2,500 GB" in row["sellable_avg_fmt"]
    assert "—" not in row["sellable_alloc_fmt"].split("\n")[0]


def test_replication_storage_fills_triad_from_sellable_qty_when_tracks_missing():
    row = prepare_service_row(
        {
            "service_label": "Veeam Replication HC — Storage",
            "family": "backup_veeam_replication_hyperconverged",
            "panel_key": "backup_veeam_replication_hyperconverged_storage",
            "display_unit": "GB",
            "resource_kind": "storage",
            "total": 10000.0,
            "crm_sold_qty": 0.0,
            "used_qty": 1000.0,
            "free_qty": 9000.0,
            "sellable_qty": 18563.2,
            "unit_price_tl": 0.5,
            "has_infra_source": True,
            "has_price": True,
            "sellable_profile": "dual_track",
            "inventory_free_mode": "infra",
            "status": "ok",
        }
    )
    assert "18,563" in row["sellable_alloc_fmt"] or "18,563.2" in row["sellable_alloc_fmt"]
    assert "—" not in row["sellable_alloc_fmt"].split("\n")[0]
    # Unsold fallback = Total − CRM Sold (10,000 − 0)
    assert "10,000" in row["unsold_fmt"]


def test_row_sellable_tl_bounds_and_header_interval():
    lo, hi = _row_sellable_tl_bounds(
        {
            "potential_tl_alloc": 364622.0,
            "potential_tl_max": 500000.0,
            "potential_tl_avg": 938087.0,
        }
    )
    assert lo == 364622.0
    assert hi == 938087.0
    assert _fmt_sellable_tl_interval(lo, hi) == "364,622 TL – 938,087 TL"

    badges = _header_money_badges(
        [
            {
                "family": "backup_veeam_replication_classic",
                "potential_tl_alloc": 100.0,
                "potential_tl_max": 200.0,
                "potential_tl_avg": 300.0,
                "crm_sold_tl": 0.0,
            },
            {
                "family": "backup_zerto_replication_classic",
                "potential_tl_alloc": 50.0,
                "potential_tl_max": 40.0,
                "potential_tl_avg": 60.0,
                "crm_sold_tl": 0.0,
            },
        ],
        profile="replication",
    )
    labels = " ".join(str(getattr(b, "children", None) or b) for b in badges)
    assert "CRM Sold" in labels
    assert "Sellable" in labels
    assert "Sellable Alloc" not in labels
    # Row mins 100+40=140; row maxes 300+60=360
    assert "140 TL" in labels
    assert "360 TL" in labels

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
            "inventory_free_mode": "infra",
            "data_quality": "suspect",
            "suspect_reason": "allocation_exceeds_total",
            "status": "ok",
        }
    )
    assert "Allocation exceeds capacity" in row["service_label"]
