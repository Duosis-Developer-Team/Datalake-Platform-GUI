"""Unit tests for catalog price × qty unit alignment."""
from __future__ import annotations

import pytest

from shared.sellable.computation import align_qty_to_price_unit, compute_catalog_tl


def test_align_tb_to_gb():
    assert align_qty_to_price_unit(1.0, "TB", "GB") == 1024.0
    assert align_qty_to_price_unit(1024.0, "GB", "TB") == 1.0


def test_compute_catalog_tl_netbackup_gb_price_tb_qty():
    # 238 TB free × 1.43 TL/GB catalog
    tl = compute_catalog_tl(238.0, 1.43, qty_unit="TB", price_unit="GB", has_price=True)
    assert tl == pytest.approx(238.0 * 1024.0 * 1.43)


def test_compute_catalog_tl_s3_same_unit():
    tl = compute_catalog_tl(8.0, 778.63, qty_unit="TB", price_unit="TB", has_price=True)
    assert tl == pytest.approx(8.0 * 778.63)
