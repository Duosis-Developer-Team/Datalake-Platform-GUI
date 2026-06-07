"""Unit tests for customer catalog helpers."""
from __future__ import annotations

from app.services import customer_catalog as cc


def _boyner_row(*, is_vip: bool = False, mapped: bool = True) -> dict:
    mappings = (
        [{"data_source": "virtualization", "match_value": "Boyner", "enabled": True, "source": "seed"}]
        if mapped
        else []
    )
    return cc.build_catalog_row(
        crm_accountid="acc-boyner",
        crm_account_name="Boyner Holding",
        source_mappings=mappings,
        is_vip=is_vip,
        cache_pinned=is_vip,
        ytd_revenue=125000.0,
        currency="TL",
    )


def test_build_catalog_row_marks_boyner_seed_as_mapped(monkeypatch):
    monkeypatch.setattr(cc, "_real_data_cached", lambda _name: False)
    row = _boyner_row()
    assert row["mapped"] is True
    assert row["mapping_status"] == "seed"
    assert row["list_group"] == "mapped"


def test_group_catalog_rows_excludes_vip_from_mapped_and_unmapped():
    rows = [
        _boyner_row(),
        cc.build_catalog_row(
            crm_accountid="acc-a",
            crm_account_name="Alpha Corp",
            source_mappings=[],
            is_vip=False,
            cache_pinned=False,
        ),
        cc.build_catalog_row(
            crm_accountid="acc-v",
            crm_account_name="VIP Corp",
            source_mappings=[],
            is_vip=True,
            cache_pinned=True,
        ),
    ]
    groups = cc.group_catalog_rows(rows)
    assert len(groups["vip"]) == 1
    assert groups["vip"][0]["crm_account_name"] == "VIP Corp"
    assert len(groups["mapped"]) == 1
    assert groups["mapped"][0]["crm_account_name"] == "Boyner Holding"
    assert len(groups["unmapped"]) == 1
    assert groups["unmapped"][0]["crm_account_name"] == "Alpha Corp"


def test_vip_unmapped_customer_still_reports_mapped_false(monkeypatch):
    monkeypatch.setattr(cc, "_real_data_cached", lambda _name: False)
    row = _boyner_row(is_vip=True, mapped=False)
    assert row["is_vip"] is True
    assert row["mapped"] is False
    assert row["list_group"] == "vip"


def test_build_overview_payload_counts_groups_and_pending_overuse():
    rows = [
        _boyner_row(),
        cc.build_catalog_row(
            crm_accountid="acc-a",
            crm_account_name="Alpha Corp",
            source_mappings=[],
            is_vip=False,
            cache_pinned=False,
        ),
    ]
    overview = cc.build_overview_payload(
        catalog_rows=rows,
        sales_total={"total_revenue": 500000.0, "currency": "TL", "order_count": 12},
        service_sales=[{"service_code": "virt", "service_label": "Virtualization", "amount_tl": 100.0}],
    )
    assert overview["total_customers"] == 2
    assert overview["mapped_count"] == 1
    assert overview["unmapped_count"] == 1
    assert overview["vip_count"] == 0
    assert overview["total_revenue"] == 500000.0
    assert overview["overuse_status"] == "pending"
    assert overview["overuse_customer_count"] == 1


def test_map_service_sales_lines_aggregates_by_category():
    product_mapping = {
        "p1": {"category_code": "virt", "category_label": "Virtualization"},
        "p2": {"category_code": "virt", "category_label": "Virtualization"},
        "p3": {"category_code": "backup", "category_label": "Backup"},
    }
    lines = [
        {"productid": "p1", "amount_tl": 100.0},
        {"productid": "p2", "amount_tl": 50.0},
        {"productid": "p3", "amount_tl": 25.0},
    ]
    out = cc.map_service_sales_lines(lines, product_mapping)
    assert out[0]["service_code"] == "virt"
    assert out[0]["amount_tl"] == 150.0
