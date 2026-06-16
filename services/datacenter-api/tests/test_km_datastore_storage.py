"""Classic KM storage aligns with KM datastore sum."""
from __future__ import annotations

from app.services.dc_service import DatabaseService


def test_patch_classic_row_storage_replaces_gb_values():
    row = (5, 10, 100.0, 50.0, 200.0, 100.0, 999.0, 500.0)
    patched = DatabaseService._patch_classic_row_storage(row, cap_gb=514560.0, used_gb=410240.0)
    assert patched[6] == 514560.0
    assert patched[7] == 410240.0


def test_patch_classic_row_storage_skips_when_zero():
    row = (5, 10, 100.0, 50.0, 200.0, 100.0, 999.0, 500.0)
    patched = DatabaseService._patch_classic_row_storage(row, cap_gb=0.0, used_gb=0.0)
    assert patched[6] == 999.0
    assert patched[7] == 500.0


def test_apply_classic_datastore_storage_section_tb_units():
    classic = {"stor_cap": 0.0, "stor_used": 0.0, "hosts": 5}
    out = DatabaseService._apply_classic_datastore_storage_section(classic, 2048.0, 1024.0)
    assert out["stor_cap"] == 2.0
    assert out["stor_used"] == 1.0
    assert out["hosts"] == 5


def test_apply_classic_datastore_storage_section_skips_zero_cap():
    classic = {"stor_cap": 9.0, "stor_used": 1.0}
    out = DatabaseService._apply_classic_datastore_storage_section(classic, 0.0, 0.0)
    assert out["stor_cap"] == 9.0
