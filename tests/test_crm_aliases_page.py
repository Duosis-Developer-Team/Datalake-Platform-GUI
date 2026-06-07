#!/usr/bin/env python3
"""Tests for CRM source mapping UI helpers and page data flow."""
from __future__ import annotations

from src.utils.crm_source_mapping_ui import (
    DEFAULT_ALIAS_TABLE_PAGE_SIZE,
    add_mapping_row,
    alias_from_table_selection,
    alias_to_table_row,
    aliases_to_table_rows,
    build_editor_state,
    collect_mappings_for_account,
    compute_summary,
    editor_state_from_dash_states,
    editor_state_to_save_payload,
    filter_alias_table_rows,
    mappings_for_column,
    merge_alias_after_save,
    page_count_for_rows,
    paginate_alias_table_rows,
    remove_mapping_row,
    resolve_visible_row_index,
    resolve_visible_rows,
)

_TABLE_ID = "alias-customer-table"


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


def test_resolve_visible_row_index_prefers_selected_rows_over_cleared_active_cell():
    idx = resolve_visible_row_index(
        [1],
        {"row": None, "column": 0},
        trigger_id=f"{_TABLE_ID}.active_cell",
        table_id=_TABLE_ID,
    )
    assert idx == 1


def test_resolve_visible_row_index_uses_active_cell_when_no_selection():
    idx = resolve_visible_row_index(
        [],
        {"row": 3, "column": 1},
        trigger_id=f"{_TABLE_ID}.active_cell",
        table_id=_TABLE_ID,
    )
    assert idx == 3


def test_resolve_visible_rows_uses_page_offset_when_virtual_data_missing():
    table_data = [{"crm_accountid": f"acc-{i}", "crm_account_name": f"Customer {i}"} for i in range(30)]
    visible = resolve_visible_rows(None, None, table_data, page_current=1, page_size=25)
    assert len(visible) == 5
    assert visible[0]["crm_accountid"] == "acc-25"


def test_alias_from_table_selection_builds_minimal_alias_when_missing_in_page_data():
    row = {"crm_accountid": "acc-new", "crm_account_name": "New Corp"}
    alias = alias_from_table_selection(row, [])
    assert alias is not None
    assert alias["crm_accountid"] == "acc-new"
    assert alias["source_mappings"] == []
    editor = build_editor_state(alias)
    assert editor is not None
    assert editor["crm_account_name"] == "New Corp"


def test_alias_from_table_selection_uses_page_data_when_present():
    page = [{"crm_accountid": "acc-1", "crm_account_name": "Alpha", "source_mappings": [], "notes": "x"}]
    row = {"crm_accountid": "acc-1", "crm_account_name": "Alpha"}
    alias = alias_from_table_selection(row, page)
    assert alias is not None
    assert alias["notes"] == "x"


def test_filter_alias_table_rows_matches_name():
    rows = aliases_to_table_rows(
        [
            {"crm_accountid": "a", "crm_account_name": "Alpha Corp", "source_mappings": []},
            {"crm_accountid": "b", "crm_account_name": "Beta Corp", "source_mappings": []},
        ]
    )
    filtered = filter_alias_table_rows(rows, "alpha")
    assert len(filtered) == 1
    assert filtered[0]["crm_account_name"] == "Alpha Corp"


def test_paginate_alias_table_rows_and_page_count():
    rows = [{"crm_accountid": f"acc-{i}"} for i in range(30)]
    assert page_count_for_rows(len(rows), DEFAULT_ALIAS_TABLE_PAGE_SIZE) == 2
    page0 = paginate_alias_table_rows(rows, 0, DEFAULT_ALIAS_TABLE_PAGE_SIZE)
    page1 = paginate_alias_table_rows(rows, 1, DEFAULT_ALIAS_TABLE_PAGE_SIZE)
    assert len(page0) == 25
    assert len(page1) == 5
    assert page0[0]["crm_accountid"] == "acc-0"
    assert page1[0]["crm_accountid"] == "acc-25"


def test_visible_table_rows_applies_filter_and_page(monkeypatch):
    from src.pages.settings.integrations import crm_aliases as page_mod

    aliases = [
        {"crm_accountid": "a", "crm_account_name": "Alpha", "source_mappings": []},
        {"crm_accountid": "b", "crm_account_name": "Beta", "source_mappings": []},
    ]
    rows, pages = page_mod.visible_table_rows(aliases, "beta", 0)
    assert pages == 1
    assert len(rows) == 1
    assert rows[0]["crm_account_name"] == "Beta"


def test_build_layout_includes_slide_panel_and_edit_buttons(monkeypatch):
    from src.pages.settings.integrations import crm_aliases as page_mod

    monkeypatch.setattr(
        page_mod.api,
        "get_crm_aliases",
        lambda: [{"crm_accountid": "acc-1", "crm_account_name": "Alpha", "source_mappings": []}],
    )
    layout = page_mod.build_layout()
    assert layout is not None

    def _walk(obj):
        if obj is None:
            return
        if isinstance(obj, (list, tuple)):
            for item in obj:
                yield from _walk(item)
            return
        yield obj
        children = getattr(obj, "children", None)
        if children is not None:
            yield from _walk(children)

    string_ids = set()
    pattern_ids = []
    for node in _walk(layout):
        node_id = getattr(node, "id", None)
        if node_id is None:
            continue
        if isinstance(node_id, dict):
            pattern_ids.append(node_id)
        else:
            string_ids.add(node_id)

    assert "alias-slide-panel" in string_ids
    assert "alias-table-body" in string_ids
    assert "alias-panel-store" in string_ids
    assert any(item.get("type") == "alias-edit-open" for item in pattern_ids)
