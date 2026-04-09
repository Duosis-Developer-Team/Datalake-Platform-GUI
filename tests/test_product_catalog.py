"""Unit tests for product catalog parsing and AuraNotify category matching."""

from pathlib import Path

import pytest
from openpyxl import Workbook

from src.services import product_catalog as pc


@pytest.fixture
def tiny_catalog_path(tmp_path: Path) -> Path:
    p = tmp_path / "mini_catalog.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Ana Servis Kategorileri"
    ws.append(["Ana Servis Kategorisi", "Alt Kategori", "Servisler"])
    ws.append(["1. Main Category", "Sub A", "First Service"])
    ws.append([None, None, "Second Service"])
    ws.append([None, "Sub B", "Third Service"])
    wb.save(p)
    return p


def test_load_service_hierarchy_forward_fill(tiny_catalog_path: Path):
    pc.clear_service_hierarchy_cache()
    rows = pc.load_service_hierarchy(tiny_catalog_path)
    assert len(rows) == 3
    assert rows[0]["service"] == "First Service"
    assert rows[1]["sub_category"] == "Sub A"
    assert rows[2]["sub_category"] == "Sub B"


def test_nest_service_catalog_order(tiny_catalog_path: Path):
    pc.clear_service_hierarchy_cache()
    rows = pc.load_service_hierarchy(tiny_catalog_path)
    tree = pc.nest_service_catalog(rows)
    assert list(tree.keys()) == ["1. Main Category"]
    assert list(tree["1. Main Category"].keys()) == ["Sub A", "Sub B"]


def test_match_service_to_category_exact():
    cats = [
        {"category": "Hyperconverged Mimari Intel VM", "availability_pct": 99.9756},
    ]
    m = pc.match_service_to_category("Hyperconverged Mimari Intel VM", cats)
    assert m is not None
    assert m["availability_pct"] == 99.9756


def test_match_service_to_category_substring():
    cats = [
        {"category": "Backup", "availability_pct": 99.97},
    ]
    m = pc.match_service_to_category("Some long name with Backup inside", cats)
    assert m is not None


def test_service_availability_pct_no_match():
    pct, m = pc.service_availability_pct("Unknown Service XYZ", [{"category": "Other", "availability_pct": 90.0}])
    assert pct == 100.0
    assert m is None


def test_service_availability_pct_with_match():
    pct, m = pc.service_availability_pct(
        "Hyperconverged Mimari Intel VM",
        [{"category": "Hyperconverged Mimari Intel VM", "availability_pct": 99.1}],
    )
    assert pct == 99.1
    assert m is not None
