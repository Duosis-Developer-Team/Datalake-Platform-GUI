"""PUT /crm/aliases/{id}/source-mappings replaces ALL mappings for an account,
so every write path must send the union of old + new. These pin that.
"""
from src.utils.crm_source_mapping_ui import merge_source_mapping

_NEW = {
    "data_source": "virtualization",
    "match_method": "prefix",
    "match_value": "Ada_Gross_Cloud",
    "enabled": True,
    "priority": 100,
}


def test_merge_appends_without_dropping_existing_mappings():
    existing = [
        {"data_source": "virtualization", "match_method": "contains", "match_value": "Ada Gross"},
        {"data_source": "backup_netbackup", "match_method": "prefix", "match_value": "ada-gros"},
    ]
    merged, changed = merge_source_mapping(existing, _NEW)

    assert changed is True
    assert len(merged) == 3
    assert existing[0] in merged and existing[1] in merged
    assert merged[-1]["match_value"] == "Ada_Gross_Cloud"


def test_merge_is_idempotent_on_an_identical_rule():
    existing = [dict(_NEW)]
    merged, changed = merge_source_mapping(existing, _NEW)

    assert changed is False
    assert merged == existing


def test_merge_compares_value_case_insensitively_like_ilike_does():
    """Match values resolve through ILIKE, so 'ADA_GROSS_CLOUD' is the same rule."""
    existing = [{**_NEW, "match_value": "ADA_GROSS_CLOUD"}]
    _, changed = merge_source_mapping(existing, _NEW)

    assert changed is False


def test_merge_treats_a_different_method_as_a_different_rule():
    existing = [{**_NEW, "match_method": "contains"}]
    merged, changed = merge_source_mapping(existing, _NEW)

    assert changed is True
    assert len(merged) == 2


def test_merge_does_not_mutate_the_caller_list():
    existing = [{"data_source": "virtualization", "match_method": "contains", "match_value": "x"}]
    merge_source_mapping(existing, _NEW)

    assert len(existing) == 1
