#!/usr/bin/env python3
"""Tests for CRM source mapping UI helpers and page data flow."""
from __future__ import annotations

from src.utils.crm_source_mapping_ui import (
    add_mapping_row,
    alias_to_table_row,
    aliases_to_table_rows,
    build_editor_state,
    collect_mappings_for_account,
    compute_summary,
    editor_state_from_dash_states,
    editor_state_to_save_payload,
    mappings_for_column,
    merge_alias_after_save,
    remove_mapping_row,
)


def _boyner_alias() -> dict:
    mappings = [
        {"data_source": "virtualization", "match_method": "contains", "match_value": "Boyner", "enabled": True},
        {"data_source": "backup_veeam", "match_method": "prefix", "match_value": "Boyner_", "enabled": True},
        {"data_source": "physical_device", "match_method": "exact", "match_value": "Boyner", "enabled": True},
    ]
    return {
        "crm_accountid": "acc-boyner",
        "crm_account_name": "Boyner Holding",
        "source_mappings": mappings,
        "notes": "seed note",
        "source": "seed",
    }


def test_alias_to_table_row_counts_coverage_and_status():
    row = alias_to_table_row(_boyner_alias())
    assert row["crm_account_name"] == "Boyner Holding"
    assert row["mapping_count"] == 3
    assert row["coverage"] == "3/6"
    assert row["status"] == "seed"


def test_aliases_to_table_rows_sorts_by_name():
    aliases = [
        {"crm_accountid": "b", "crm_account_name": "Zeta Corp", "source_mappings": []},
        {"crm_accountid": "a", "crm_account_name": "Alpha Corp", "source_mappings": []},
    ]
    rows = aliases_to_table_rows(aliases)
    assert [r["crm_account_name"] for r in rows] == ["Alpha Corp", "Zeta Corp"]


def test_compute_summary_tracks_boyner():
    stats = compute_summary([_boyner_alias(), {"crm_accountid": "x", "crm_account_name": "Empty", "source_mappings": []}])
    assert stats["total"] == 2
    assert stats["configured"] == 1
    assert stats["empty"] == 1
    assert stats["boyner_mappings"] == 3


def test_build_editor_state_groups_by_ui_columns():
    editor = build_editor_state(_boyner_alias())
    assert editor is not None
    assert editor["crm_accountid"] == "acc-boyner"
    assert len(editor["sections"]["virtualization"]) == 1
    assert editor["sections"]["virtualization"][0]["match_value"] == "Boyner"
    assert len(editor["sections"]["s3"]) == 1
    assert editor["sections"]["s3"][0]["match_value"] == ""


def test_editor_state_from_dash_states_rebuilds_sections():
    editor = build_editor_state(_boyner_alias())
    method_states = [
        {"id": {"section": "virtualization", "index": 0}, "value": "exact"},
    ]
    value_states = [
        {"id": {"section": "virtualization", "index": 0}, "value": "Boyner Updated"},
    ]
    enabled_states = [
        {"id": {"section": "virtualization", "index": 0}, "value": True},
    ]
    source_states = [
        {"id": {"section": "virtualization", "index": 0}, "value": "virtualization"},
    ]
    synced = editor_state_from_dash_states(
        editor,
        method_states=method_states,
        value_states=value_states,
        enabled_states=enabled_states,
        source_states=source_states,
        notes="updated note",
    )
    mappings, notes = editor_state_to_save_payload(synced)
    assert notes == "updated note"
    assert any(m["match_value"] == "Boyner Updated" for m in mappings)


def test_editor_state_to_save_payload_skips_blank_values():
    editor = build_editor_state(_boyner_alias())
    mappings, notes = editor_state_to_save_payload(editor)
    assert notes == "seed note"
    assert len(mappings) == 3
    assert {m["data_source"] for m in mappings} == {"virtualization", "backup_veeam", "physical_device"}


def test_add_and_remove_mapping_row():
    editor = build_editor_state({"crm_accountid": "a", "crm_account_name": "A", "source_mappings": []})
    assert editor is not None
    updated = add_mapping_row(editor, "backup")
    assert len(updated["sections"]["backup"]) == 2
    trimmed = remove_mapping_row(updated, "backup", 1)
    assert len(trimmed["sections"]["backup"]) == 1


def test_merge_alias_after_save_updates_page_data():
    page = [{"crm_accountid": "a", "crm_account_name": "A", "source_mappings": []}]
    saved = [{"data_source": "virtualization", "match_method": "contains", "match_value": "A", "enabled": True}]
    merged = merge_alias_after_save(page, account_id="a", saved_mappings=saved, notes="ok")
    assert merged[0]["source_mappings"] == saved
    assert merged[0]["notes"] == "ok"


def test_collect_mappings_for_account_groups_by_column_index():
    method_states = [
        {"id": {"account": "acc-1", "column": "virtualization", "index": 0}, "value": "contains"},
        {"id": {"account": "acc-1", "column": "backup", "index": 0}, "value": "prefix"},
    ]
    value_states = [
        {"id": {"account": "acc-1", "column": "virtualization", "index": 0}, "value": "Boyner"},
        {"id": {"account": "acc-1", "column": "backup", "index": 0}, "value": "Boyner_Equinix"},
    ]
    enabled_states = [
        {"id": {"account": "acc-1", "column": "virtualization", "index": 0}, "value": True},
        {"id": {"account": "acc-1", "column": "backup", "index": 0}, "value": True},
    ]
    source_states = [
        {"id": {"account": "acc-1", "column": "virtualization", "index": 0}, "value": "virtualization"},
        {"id": {"account": "acc-1", "column": "backup", "index": 0}, "value": "backup_veeam"},
    ]

    mappings = collect_mappings_for_account(
        "acc-1",
        method_states,
        value_states,
        enabled_states,
        source_states,
    )
    assert len(mappings) == 2
    assert {m["data_source"] for m in mappings} == {"virtualization", "backup_veeam"}


def test_mappings_for_column_filters_sources():
    rows = [
        {"data_source": "virtualization", "match_value": "Boyner"},
        {"data_source": "backup_veeam", "match_value": "Boyner"},
        {"data_source": "s3_icos", "match_value": "Boyner"},
    ]
    virt = mappings_for_column(rows, ("virtualization", "netbox_vm_customer"))
    assert len(virt) == 1
