"""Unit tests for shared Veeam / Zerto license compliance helpers."""
from __future__ import annotations

from shared.backup.license_compliance import (
    LICENSE_SKUS,
    evaluate_backup_licenses,
    evaluate_license,
)


def test_license_skus_cover_veeam_and_zerto():
    assert LICENSE_SKUS["veeam_backup"] == ("000BLT-144", "000BLT-145")
    assert LICENSE_SKUS["veeam_replication"] == ("000BLT-147", "000BLT-148")
    assert LICENSE_SKUS["zerto"] == ("000BLT-169",)


def test_evaluate_license_status_matrix():
    assert evaluate_license(5, 3) == "ok"
    assert evaluate_license(5, 0) == "unsold_usage"
    assert evaluate_license(0, 2) == "crm_only"
    assert evaluate_license(0, 0) == "no_usage"
    assert evaluate_license(None, None) == "no_usage"


def test_evaluate_backup_licenses_by_category():
    rows = evaluate_backup_licenses(
        usage={"veeam_backup": 10, "veeam_replication": 0, "zerto": 4},
        sold={"veeam_backup": 8, "veeam_replication": 2, "zerto": 0},
    )
    by_cat = {r["category"]: r for r in rows}
    assert by_cat["veeam_backup"]["status"] == "ok"
    assert by_cat["veeam_replication"]["status"] == "crm_only"
    assert by_cat["zerto"]["status"] == "unsold_usage"
    assert by_cat["veeam_backup"]["skus"] == ["000BLT-144", "000BLT-145"]


def test_evaluate_backup_licenses_sums_sku_keys():
    rows = evaluate_backup_licenses(
        usage={"000BLT-144": 1, "000BLT-145": 2},
        sold={"000BLT-144": 0, "000BLT-145": 0},
    )
    veeam = next(r for r in rows if r["category"] == "veeam_backup")
    assert veeam["usage_qty"] == 3.0
    assert veeam["sold_qty"] == 0.0
    assert veeam["status"] == "unsold_usage"


def test_evaluate_backup_licenses_empty_inputs():
    rows = evaluate_backup_licenses({}, {})
    assert len(rows) == 3
    assert all(r["status"] == "no_usage" for r in rows)
