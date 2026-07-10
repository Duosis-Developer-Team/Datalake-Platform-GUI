"""auranotify column round-trips through the generic mapping helpers."""
from __future__ import annotations

from src.utils.crm_source_mapping_ui import (
    UI_COLUMNS,
    build_editor_state,
    compute_coverage,
    editor_state_to_save_payload,
)


def _alias_with_auranotify():
    return {
        "crm_accountid": "acc-x",
        "crm_account_name": "Acme",
        "source_mappings": [
            {"data_source": "auranotify", "match_method": "id_exact", "match_value": "1498", "enabled": True},
        ],
    }


def test_auranotify_is_last_column():
    assert UI_COLUMNS[-1][0] == "auranotify"
    assert UI_COLUMNS[-1][2] == ("auranotify",)


def test_auranotify_entry_loads_into_its_section():
    state = build_editor_state(_alias_with_auranotify())
    assert state["sections"]["auranotify"][0]["match_value"] == "1498"
    assert state["sections"]["auranotify"][0]["data_source"] == "auranotify"


def test_auranotify_entry_saves_back():
    state = build_editor_state(_alias_with_auranotify())
    mappings, _ = editor_state_to_save_payload(state)
    aura = [m for m in mappings if m["data_source"] == "auranotify"]
    assert aura == [{"data_source": "auranotify", "match_method": "id_exact", "match_value": "1498", "enabled": True}]


def test_coverage_counts_auranotify():
    _covered, total = compute_coverage(_alias_with_auranotify()["source_mappings"])
    assert total == len(UI_COLUMNS) == 7
