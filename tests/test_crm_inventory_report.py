"""Tests for CRM inventory report component."""
from __future__ import annotations

from src.components.crm_inventory_report import (
    INVENTORY_REPORT_SCHEMA_VERSION,
    _header_money_badges,
    build_report_body,
    build_report_table,
    columns_for_family,
    filter_by_search,
    filter_service_rows,
    prepare_service_row,
)


def _sample_row(**kwargs):
    base = {
        "panel_key": "virt_classic_cpu",
        "service_label": "Klasik Mimari — CPU",
        "family_label": "Klasik Mimari",
        "family": "virt_classic",
        "display_unit": "vCPU",
        "total": 100.0,
        "crm_sold_qty": 30.0,
        "crm_sold_tl": 45000.0,
        "used_qty": 40.0,
        "used_tl": 60000.0,
        "free_qty": 60.0,
        "sellable_qty": 20.0,
        "potential_tl": 30000.0,
        "sellable_profile": "dual_track",
        "sellable_alloc_qty": 18.0,
        "sellable_max_qty": 22.0,
        "potential_tl_alloc": 27000.0,
        "potential_tl_max": 33000.0,
        "status": "over",
        "has_infra_source": True,
        "infra_binding": "bound",
    }
    base.update(kwargs)
    return base


def test_columns_for_family_profiles():
    # Every profile carries Unsold + trailing "Birim Fiyat"; dual_track also
    # carries Sellable Alloc/Max/Ort.
    assert len(columns_for_family("standard")) == 8
    assert len(columns_for_family("dual_track")) == 10
    assert len(columns_for_family("allocation_only")) == 8
    assert len(columns_for_family("virt_km", hide_used=True)) == 7
    assert "unsold_fmt" in [c["id"] for c in columns_for_family("standard")]
    assert "unsold_fmt" in [c["id"] for c in columns_for_family("dual_track")]


def test_dual_track_has_sellable_average_column():
    cols = columns_for_family("dual_track")
    ids = [c["id"] for c in cols]
    assert ids.index("sellable_avg_fmt") == ids.index("sellable_max_fmt") + 1
    assert "sellable_avg_fmt" not in [c["id"] for c in columns_for_family("allocation_only")]


def test_prepare_service_row_sellable_average_uses_real_avg_field():
    """Sellable (Ort.) comes from the avg-utilization track, NOT from the mean
    of alloc and max. Average utilization is below peak utilization, so the avg
    track must yield MORE sellable capacity than the max track -- the defect
    Can reported was avg reading lower than max."""
    row = prepare_service_row(_sample_row(
        inventory_hide_used=True,
        sellable_avg_qty=30.0,
        potential_tl_avg=45000.0,
    ))
    assert "30 vCPU" in row["sellable_avg_fmt"]
    assert "45,000 TL" in row["sellable_avg_fmt"]
    # The old placeholder would have produced the mean of 18 and 22.
    assert "20 vCPU" not in row["sellable_avg_fmt"]


def test_sellable_average_absent_renders_em_dash():
    """No avg data must render as em-dash, never 0 and never a mean."""
    row = prepare_service_row(_sample_row(inventory_hide_used=True))
    assert row["sellable_avg_fmt"].startswith("—")


def test_zero_sellable_hint_maps_reason():
    """Power-HANA-style 0 sellable must be explained (RAM/ratio full), not look like a bug."""
    row = prepare_service_row(_sample_row(
        family="virt_power_hana",
        sellable_profile="allocation_only",
        sellable_alloc_qty=0.0,
        sellable_max_qty=None,
        sellable_constraint_reason="ratio_bound",
        inventory_hide_used=True,
    ))
    assert "Satılabilir 0" in row["service_label"]
    assert "oran" in row["service_label"].lower()


def test_zero_sellable_hint_generic_without_reason():
    row = prepare_service_row(_sample_row(
        family="virt_power_hana",
        sellable_profile="allocation_only",
        sellable_alloc_qty=0.0,
        sellable_max_qty=None,
        inventory_hide_used=True,
    ))
    assert "Satılabilir 0" in row["service_label"]


def test_no_zero_sellable_hint_when_positive():
    row = prepare_service_row(_sample_row(inventory_hide_used=True))  # alloc 18 > 0
    assert "Satılabilir 0" not in row["service_label"]


def test_prepare_service_row_sellable_average_dash_for_non_dual():
    row = prepare_service_row(_sample_row(
        family="virt_power",
        sellable_profile="allocation_only",
        sellable_max_qty=None,
        potential_tl_max=None,
        inventory_hide_used=True,
    ))
    assert row["sellable_avg_fmt"] == "—\n—"


def test_prepare_service_row_formats_qty_tl_blocks():
    row = prepare_service_row(_sample_row(inventory_hide_used=True))
    assert row["service_label"] == "Klasik Mimari — CPU"
    assert "60 vCPU" in row["free_fmt"]
    assert "45,000 TL" in row["crm_sold_fmt"]
    assert row["used_fmt"] == "—\n—"
    assert "18 vCPU" in row["sellable_alloc_fmt"]
    assert "22 vCPU" in row["sellable_max_fmt"]


def test_prepare_service_row_marks_suspect_data_quality():
    row = prepare_service_row(_sample_row(data_quality="suspect"))
    assert row["service_label"].startswith("⚠")
    assert row["data_quality"] == "suspect"


def test_prepare_service_row_standard_free_and_unsold_columns():
    row = prepare_service_row(_sample_row(
        sellable_profile="standard",
        sellable_alloc_qty=None,
        sellable_max_qty=None,
        free_qty=60.0,
        free_tl=90000.0,
        unsold_qty=70.0,
        unsold_tl=105000.0,
        unit_price_tl=1500.0,
    ))
    assert "60 vCPU" in row["free_fmt"]
    assert "90,000 TL" in row["free_fmt"]
    assert "70 vCPU" in row["unsold_fmt"]
    assert row["sellable_alloc_fmt"] == "—\n—"


def test_prepare_service_row_s3_physical_free_not_sellable():
    row = prepare_service_row(_sample_row(
        panel_key="storage_s3_istanbul",
        family="storage_s3",
        display_unit="TB",
        sellable_profile="standard",
        total=2000.0,
        used_qty=800.0,
        free_qty=1200.0,
        free_tl=914400.0,  # stale — overridden by catalog
        unit_price_tl=778.63,
        unit_price_unit="TB",
        has_price=True,
        sellable_qty=385.0,
        potential_tl=38500.0,
        inventory_free_mode="physical",
    ))
    # Catalog 778.63 TL/TB × 1,200 TB free
    assert "1,200 TB" in row["free_fmt"]
    assert f"{1200.0 * 778.63:,.0f} TL" in row["free_fmt"]
    assert "385 TB" not in row["free_fmt"]
    assert row["unit_price_fmt"] == "778.63 TL/TB"


def test_prepare_service_row_netbackup_used_qty_tl_only():
    row = prepare_service_row(_sample_row(
        panel_key="backup_netbackup_storage",
        family="backup_netbackup",
        display_unit="TB",
        sellable_profile="standard",
        crm_sold_qty=58.0,
        crm_sold_tl=23246.0,
        total=44069.0,
        used_qty=411.0,
        used_tl=94530.0,
        pool_used_qty=411.0,
        pre_dedup_qty=411.0,
        post_dedup_qty=5.0,
        post_dedup_tl=1150.0,
        dedup_savings_qty=406.0,
        dedup_savings_pct=98.8,
        dedup_factor=81.8,
        dedup_margin_tl=93380.0,
        free_qty=42115.0,
        free_tl=58961.0,
        unsold_qty=44011.0,
        unit_price_tl=1.43,
        unit_price_unit="GB",
        has_price=True,
        inventory_free_mode="physical",
        used_compare_note="Pool used: 411.0 TB · jobs PostDedup: 5.0 TB",
    ))
    assert "58 TB" in row["crm_sold_fmt"]
    assert "23,246 TL" in row["crm_sold_fmt"]
    assert row["total_fmt"] == "44,069 TB"
    assert "Pool used" not in row["total_fmt"]
    assert "411 TB" in row["used_fmt"]
    assert "Pool used" in row["used_fmt"]
    assert row["pre_dedup_fmt"] == "411 TB\n94,530 TL"
    assert "5" in row["post_dedup_fmt"] and "1,150 TL" in row["post_dedup_fmt"]
    assert "98.8%" in row["dedup_savings_fmt"]
    assert "93,380 TL" in row["dedup_savings_fmt"]
    assert "42,115 TB" in row["free_fmt"]
    assert "44,011 TB" in row["unsold_fmt"]
    # Free valued at catalog 1.43 TL/GB (qty TB → GB × price)
    expected_free_tl = f"{42115.0 * 1024.0 * 1.43:,.0f} TL"
    assert expected_free_tl in row["free_fmt"]
    assert "58,961 TL" not in row["free_fmt"]
    assert row["unit_price_fmt"] == "1.43 TL/GB"
    assert "58 TB" not in row["total_fmt"]


def test_columns_for_family_netbackup_includes_used():
    cols = columns_for_family("backup_netbackup")
    col_ids = [c["id"] for c in cols]
    assert col_ids == [
        "service_label",
        "display_unit",
        "crm_sold_fmt",
        "total_fmt",
        "used_fmt",
        "pre_dedup_fmt",
        "post_dedup_fmt",
        "dedup_savings_fmt",
        "free_fmt",
        "unsold_fmt",
        "unit_price_fmt",
    ]


def test_build_report_table_no_fixed_columns():
    row = _sample_row(
        panel_key="backup_netbackup_storage",
        family="backup_netbackup",
        display_unit="TB",
        sellable_profile="standard",
    )
    table = build_report_table(
        [row],
        table_id=f"test-nb-{INVENTORY_REPORT_SCHEMA_VERSION}",
        family="backup_netbackup",
    )
    assert getattr(table, "fixed_columns", None) is None
    assert table.style_table["tableLayout"] == "fixed"
    assert table.style_table["width"] == "100%"


def _header_align_for_column(table, column_id: str) -> str | None:
    for rule in table.style_header_conditional or []:
        if rule.get("if", {}).get("column_id") == column_id:
            return rule.get("textAlign")
    return None


def test_report_table_numeric_header_alignment():
    table = build_report_table(
        [_sample_row()],
        table_id="test-align-report",
        sellable_profile="standard",
    )
    for col_id in ("crm_sold_fmt", "total_fmt", "used_fmt", "free_fmt"):
        assert _header_align_for_column(table, col_id) == "right"


def test_unmapped_table_numeric_alignment():
    from src.components.crm_inventory_report import build_unmapped_table

    table = build_unmapped_table(
        [{"product_name": "X", "resource_unit": "TB", "entitled_qty": 10, "entitled_amount_tl": 5000}],
        table_id="test-unmapped-align",
    )
    assert _header_align_for_column(table, "entitled_qty") == "right"
    assert _header_align_for_column(table, "entitled_amount_tl") == "right"
    data_rules = {
        r.get("if", {}).get("column_id"): r.get("textAlign")
        for r in (table.style_data_conditional or [])
        if r.get("if", {}).get("column_id") in ("entitled_qty", "entitled_amount_tl")
    }
    assert data_rules.get("entitled_qty") == "right"
    assert data_rules.get("entitled_amount_tl") == "right"


def test_filter_by_search_matches_family():
    rows = [
        _sample_row(),
        _sample_row(panel_key="x", service_label="Veeam Backup", family_label="Veeam"),
    ]
    out = filter_by_search(rows, "veeam")
    assert len(out) == 1
    assert out[0]["panel_key"] == "x"


def test_build_report_body_flat_view():
    payload = {
        "families": [],
        "crm_only_panels": [],
        "unmapped_products": [],
        "panels": [_sample_row()],
        "summary": {"note": ""},
    }
    body = build_report_body(payload, filter_mode="all", view_mode="flat")
    assert len(body) >= 1


def test_filter_service_rows_issues():
    rows = [_sample_row(), _sample_row(panel_key="x", status="ok", infra_binding="crm_only", has_infra_source=False)]
    out = filter_service_rows(rows, "issues")
    assert len(out) == 1
    assert out[0]["status"] == "over"


def test_build_report_body_family_sections():
    payload = {
        "families": [{
            "family": "virt_classic",
            "family_label": "Klasik Mimari",
            "label": "Klasik Mimari",
            "has_infra": True,
            "panels": [_sample_row()],
        }],
        "crm_only_panels": [],
        "unmapped_products": [],
        "panels": [_sample_row()],
    }
    body = build_report_body(payload, filter_mode="all")
    assert len(body) >= 1


def test_prepare_service_row_crm_sub_line_km():
    row = prepare_service_row(_sample_row(
        crm_sold_qty=440.0,
        crm_sold_qty_general=440.0,
        crm_sold_qty_km=12.0,
        crm_sold_tl=660000.0,
        inventory_hide_used=True,
    ))
    assert "440 vCPU" in row["crm_sold_fmt"]
    assert "(KM: 12 vCPU)" in row["crm_sold_fmt"]
    assert "660,000 TL" in row["crm_sold_fmt"]


def test_prepare_service_row_crm_sub_line_hana():
    row = prepare_service_row(_sample_row(
        family="virt_power",
        display_unit="Core",
        crm_sold_qty=80.0,
        crm_sold_qty_general=50.0,
        crm_sold_qty_hana=30.0,
        crm_sold_tl=120000.0,
        sellable_profile="allocation_only",
        inventory_hide_used=True,
    ))
    assert "(HANA: 30 Core)" in row["crm_sold_fmt"]


def test_prepare_service_row_ignores_zero_km_sub_bucket():
    row = prepare_service_row(_sample_row(
        crm_sold_qty=58.0,
        crm_sold_qty_km=0.0,
        crm_sold_tl=23246.0,
        sellable_profile="standard",
        display_unit="TB",
        used_qty=5.0,
        free_qty=44000.0,
        sellable_qty=44000.0,
    ))
    assert "(KM:" not in row["crm_sold_fmt"]
    assert "58 TB" in row["crm_sold_fmt"]
    assert "23,246 TL" in row["crm_sold_fmt"]


def test_columns_for_family_includes_power_hana_virt():
    cols = columns_for_family("virt_power_hana", hide_used=True)
    col_ids = [c["id"] for c in cols]
    assert "used_fmt" not in col_ids
    assert "free_fmt" in col_ids


def test_flat_view_keeps_sellable_columns_with_netbackup_row():
    """Flat/list view must not drop Sellable columns just because a NetBackup row
    is present in the mixed table (regression: netbackup row forced whole table to
    the standard profile, hiding Sellable Alloc/Max util)."""
    virt_row = _sample_row()
    netbackup_row = _sample_row(
        panel_key="backup_netbackup_storage",
        family="backup_netbackup",
        family_label="NetBackup",
        display_unit="TB",
        sellable_profile="standard",
        inventory_free_mode="physical",
    )
    table = build_report_table(
        [virt_row, netbackup_row],
        table_id="test-flat-with-nb",
        include_family=True,
        sellable_profile="dual_track",
    )
    col_ids = [c["id"] for c in table.columns]
    assert "sellable_alloc_fmt" in col_ids
    assert "sellable_max_fmt" in col_ids


def test_prepare_service_row_virt_free_shows_tl():
    """Free capacity on virt families should carry a TL value (free_qty * unit price)."""
    row = prepare_service_row(_sample_row(
        inventory_hide_used=True,
        free_qty=60.0,
        unit_price_tl=1500.0,
    ))
    assert "60 vCPU" in row["free_fmt"]
    assert "90,000 TL" in row["free_fmt"]


def test_prepare_service_row_virt_free_tl_missing_without_price():
    """No unit price -> Free TL stays em-dash (no fabricated value)."""
    row = prepare_service_row(_sample_row(inventory_hide_used=True, free_qty=60.0))
    assert "60 vCPU" in row["free_fmt"]
    assert row["free_fmt"].endswith("—")


def test_unit_price_column_present_and_formatted():
    cols = columns_for_family("dual_track")
    assert cols[-1]["id"] == "unit_price_fmt"
    assert cols[-1]["name"] == "Birim Fiyat"
    row = prepare_service_row(_sample_row(
        unit_price_tl=99.0, display_unit="vCPU", inventory_hide_used=True,
    ))
    assert row["unit_price_fmt"] == "99 TL/vCPU"


def test_unit_price_small_value_keeps_precision():
    """Per-TB / per-GB catalog prices must not round to zero."""
    row = prepare_service_row(_sample_row(
        panel_key="backup_netbackup_storage",
        family="backup_netbackup",
        display_unit="TB",
        sellable_profile="standard",
        unit_price_tl=1.42,
        unit_price_unit="GB",
        has_price=True,
        inventory_free_mode="physical",
    ))
    assert row["unit_price_fmt"] == "1.42 TL/GB"


def test_physical_free_valued_at_catalog_price():
    """NetBackup Free / Birim Fiyat use catalog unit price in service UOM (GB).

    Display qty stays TB; TL = TB×1024 × TL/GB. CRM-sold implied is not used.
    """
    row = prepare_service_row(_sample_row(
        panel_key="backup_netbackup_storage",
        family="backup_netbackup",
        display_unit="TB",
        sellable_profile="standard",
        crm_sold_qty=79.0,
        crm_sold_tl=38210.0,
        free_qty=238.0,
        free_tl=338.0,            # stale mis-scaled value — must be overridden
        unit_price_tl=1.43,       # catalog TL/GB
        unit_price_unit="GB",
        has_price=True,
        inventory_free_mode="physical",
    ))
    expected_free_tl = f"{238.0 * 1024.0 * 1.43:,.0f} TL"
    assert expected_free_tl in row["free_fmt"]
    assert "338 TL" not in row["free_fmt"]
    assert row["unit_price_fmt"] == "1.43 TL/GB"


def test_unit_price_missing_shows_dash():
    row = prepare_service_row(_sample_row(sellable_profile="standard", inventory_hide_used=True))
    assert row["unit_price_fmt"] == "—"


def test_header_money_badges_crm_sold_and_sellable_interval():
    badges = _header_money_badges(
        [
            _sample_row(
                potential_tl_alloc=27000.0,
                potential_tl_max=33000.0,
                potential_tl_avg=45000.0,
            ),
            _sample_row(
                panel_key="virt_classic_ram",
                crm_sold_tl=5000.0,
                potential_tl_alloc=3000.0,
                potential_tl_max=4000.0,
                potential_tl_avg=5000.0,
            ),
        ],
        profile="dual_track",
    )
    labels = [getattr(b, "children", None) or str(b) for b in badges]
    joined = " ".join(str(x) for x in labels)
    assert "CRM Sold" in joined
    assert "Sellable" in joined
    assert "Sellable Alloc" not in joined
    assert "Sellable Max" not in joined
    assert "Sellable Ort." not in joined
    # Σmin = 27000+3000=30000; Σmax = 45000+5000=50000
    assert "30,000 TL" in joined
    assert "50,000 TL" in joined


def test_header_money_badges_hides_zero_sellable_tracks():
    badges = _header_money_badges(
        [_sample_row(potential_tl_alloc=0.0, potential_tl_max=None, potential_tl_avg=None,
                     sellable_alloc_qty=0.0, sellable_max_qty=None, sellable_avg_qty=None)],
        profile="dual_track",
    )
    labels = " ".join(str(getattr(b, "children", None) or b) for b in badges)
    assert "CRM Sold" in labels
    assert "Sellable Alloc" not in labels
    assert "Sellable Max" not in labels
    # Zero-only tracks → no Sellable interval chip
    assert labels.count("Sellable") == 0 or "Sellable 0" not in labels

def test_prepare_service_row_netbackup_total_is_capacity_only():
    """NetBackup Total is pool usable qty only; Transfer holds PreDedup."""
    row = prepare_service_row(_sample_row(
        panel_key="backup_netbackup_storage",
        family="backup_netbackup",
        display_unit="TB",
        sellable_profile="standard",
        total=1544.0,
        pre_dedup_qty=5024.0,
        used_tl=1000.0,
        dedup_factor=3.2,
        dedup_savings_pct=69.3,
        free_qty=238.0,
        free_tl=338.0,
        inventory_free_mode="physical",
    ))
    assert row["total_fmt"] == "1,544 TB"
    assert "5,024 TB" in row["pre_dedup_fmt"]
    assert "3.2" not in row["total_fmt"]


def test_prepare_service_row_no_dedup_note_when_absent():
    """Rows without pre-dedup metrics keep a clean single-line Total."""
    row = prepare_service_row(_sample_row(
        panel_key="storage_s3_istanbul",
        family="storage_s3",
        display_unit="TB",
        sellable_profile="standard",
        total=2000.0,
        inventory_free_mode="physical",
    ))
    assert row["total_fmt"] == "2,000 TB"
