"""Tests for the canonical column spine (TASK-99 ADR-001)."""
from __future__ import annotations

from src.components.crm_inventory_report import (
    _GROUP_BLOCKS,
    _SPINE,
    _SPINE_OVERRIDES,
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
        "sellable_profile": "standard",
        "status": "over",
        "has_infra_source": True,
        "infra_binding": "bound",
    }
    base.update(kwargs)
    return base


def test_spine_and_group_block_ids_all_have_producers():  # TEST-U-004
    """Every id referenced by _SPINE / _SPINE_OVERRIDES / _GROUP_BLOCKS must be a
    key prepare_service_row() actually returns — else the column renders blank
    with no producer, exactly BUG-001 (delta_fmt was declared but never
    produced)."""
    row = prepare_service_row(_sample_row())
    produced_keys = set(row.keys())

    ids = {col["id"] for col in _SPINE}
    for overrides in _SPINE_OVERRIDES.values():
        ids.update(col["id"] for col in overrides.values())
    for block in _GROUP_BLOCKS.values():
        ids.update(col["id"] for col in block)

    missing = ids - produced_keys
    assert not missing, f"columns with no producer in prepare_service_row: {missing}"
