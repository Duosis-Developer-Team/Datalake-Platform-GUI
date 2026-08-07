"""Tests for the canonical column spine (TASK-99 ADR-001)."""
from __future__ import annotations

from src.components.crm_inventory_report import (
    _GROUP_BLOCKS,
    _SPINE,
    _SPINE_OVERRIDES,
    columns_for_family,
    prepare_service_row,
)

# One representative per effective profile from implementation-plan.md §1.2.
_NINE_PROFILES = [
    "standard",
    "dual_track",
    "allocation_only",
    "virt_classic",
    "replication",
    "backup_netbackup",
    "storage_s3",
    "comparison_only",
    "os_licence",
]


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


def _expected_spine_slot(profile: str, idx: int) -> dict[str, str]:
    override = _SPINE_OVERRIDES.get(profile, {}).get(idx)
    return dict(override) if override is not None else dict(_SPINE[idx])


def test_all_profiles_share_spine_order():  # TEST-U-001 (AC-001)
    """Every profile's first 7 columns must be the canonical spine, with only
    its own registered override applied. Compared against _SPINE itself, not
    a hand-written list — a profile that diverges here reproduces the exact
    bug TASK-99 exists to fix: the same info lands at a different column
    index depending on which group you're looking at."""
    for profile in _NINE_PROFILES:
        cols = columns_for_family(profile)
        assert len(cols) >= len(_SPINE)
        for idx in range(len(_SPINE)):
            expected = _expected_spine_slot(profile, idx)
            assert cols[idx] == expected, f"{profile} slot {idx}: {cols[idx]} != {expected}"


def test_all_profiles_end_with_unit_price():  # TEST-U-002 (AC-002)
    """Birim Fiyat must be the last column for every profile — os_licence used
    to place it second-to-last, ahead of Lisanslanmalı TL."""
    for profile in _NINE_PROFILES:
        cols = columns_for_family(profile)
        assert cols[-1]["id"] == "unit_price_fmt"


def test_group_blocks_sit_between_unsold_and_unit_price():  # TEST-U-003 (AC-003)
    """Group-specific columns must be strictly between Unsold (spine[6]) and
    Birim Fiyat — never wedged between spine slots (the NetBackup dedup triad
    used to sit between Used and Free)."""
    spine_ids = {c["id"] for c in _SPINE}
    for profile in _NINE_PROFILES:
        cols = columns_for_family(profile)
        middle = cols[len(_SPINE):-1]
        for col in middle:
            assert col["id"] not in spine_ids
