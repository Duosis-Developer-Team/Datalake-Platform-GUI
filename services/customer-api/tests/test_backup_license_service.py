"""Unit tests for backup license compliance wiring helpers."""
from __future__ import annotations

from app.services.backup_license_service import (
    BACKUP_LICENSE_PRODUCTNUMBERS,
    attach_license_compliance_to_bundle,
    build_backup_license_compliance,
    sold_qty_by_sku_from_rows,
    usage_signals_from_backup,
)
from app.services.sales_service import SalesService


def test_backup_license_productnumbers_cover_skus():
    assert "000BLT-144" in BACKUP_LICENSE_PRODUCTNUMBERS
    assert "000BLT-145" in BACKUP_LICENSE_PRODUCTNUMBERS
    assert "000BLT-147" in BACKUP_LICENSE_PRODUCTNUMBERS
    assert "000BLT-148" in BACKUP_LICENSE_PRODUCTNUMBERS
    assert "000BLT-169" in BACKUP_LICENSE_PRODUCTNUMBERS


def test_usage_signals_from_backup_totals():
    usage = usage_signals_from_backup(
        {"veeam_defined_sessions": 12, "zerto_protected_vms": 4},
        {},
    )
    assert usage["veeam_backup"] == 12.0
    assert usage["veeam_replication"] == 12.0
    assert usage["zerto"] == 4.0


def test_usage_signals_zerto_falls_back_to_vpgs():
    usage = usage_signals_from_backup(
        {},
        {"zerto": {"protected_total_vms": 0, "vpgs": [{"id": 1}, {"id": 2}]}},
    )
    assert usage["zerto"] == 2.0


def test_sold_qty_by_sku_from_rows_sums():
    sold = sold_qty_by_sku_from_rows(
        [
            {"productnumber": "000BLT-144", "sold_qty": 2},
            {"product_number": "000BLT-145", "quantity": 3},
            {"productnumber": "000BLT-144", "sold_qty": 1},
        ]
    )
    assert sold["000BLT-144"] == 3.0
    assert sold["000BLT-145"] == 3.0


def test_build_backup_license_compliance_unsold_usage():
    rows = build_backup_license_compliance(
        backup_totals={"veeam_defined_sessions": 5, "zerto_protected_vms": 0},
        sold_by_sku={},
    )
    by_cat = {r["category"]: r for r in rows}
    assert by_cat["veeam_backup"]["status"] == "unsold_usage"
    assert by_cat["veeam_replication"]["status"] == "unsold_usage"
    assert by_cat["zerto"]["status"] == "no_usage"


def test_build_backup_license_compliance_ok_with_sold_rows():
    rows = build_backup_license_compliance(
        backup_totals={"veeam_defined_sessions": 2, "zerto_protected_vms": 3},
        sold_rows=[
            {"productnumber": "000BLT-144", "sold_qty": 1},
            {"productnumber": "000BLT-145", "sold_qty": 1},
            {"productnumber": "000BLT-169", "sold_qty": 5},
        ],
    )
    by_cat = {r["category"]: r for r in rows}
    assert by_cat["veeam_backup"]["status"] == "ok"
    assert by_cat["veeam_backup"]["sold_qty"] == 2.0
    assert by_cat["zerto"]["status"] == "ok"
    assert by_cat["veeam_replication"]["status"] == "unsold_usage"


def test_attach_license_compliance_to_bundle():
    bundle = {"totals": {"backup": {}}, "assets": {"backup": {"veeam": {}}}}
    attach_license_compliance_to_bundle(
        bundle,
        [{"category": "zerto", "status": "ok"}],
    )
    assert bundle["assets"]["backup"]["license_compliance"][0]["status"] == "ok"


def test_sales_service_get_backup_license_compliance_wires_sold_query():
    captured: list[tuple] = []

    def _run_query(sql, params):
        captured.append((sql, params))
        return [{"productnumber": "000BLT-169", "sold_qty": 2}]

    svc = SalesService(
        get_connection=None,
        run_row=None,
        run_rows=None,
        get_customer_assets=None,
        webui=None,
    )
    svc._run_query = _run_query  # type: ignore[method-assign]
    svc._resolve_account_ids = lambda _name: ["acct-1"]  # type: ignore[method-assign]

    rows = svc.get_backup_license_compliance(
        "Acme",
        backup_totals={"veeam_defined_sessions": 0, "zerto_protected_vms": 4},
        backup_assets={},
    )
    assert captured
    assert "productnumber" in captured[0][0].lower() or "PRODUCTNUMBER" in captured[0][0]
    by_cat = {r["category"]: r for r in rows}
    assert by_cat["zerto"]["status"] == "ok"
    assert by_cat["zerto"]["sold_qty"] == 2.0
