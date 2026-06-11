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
