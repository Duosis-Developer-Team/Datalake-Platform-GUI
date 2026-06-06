#!/usr/bin/env python3
"""Tests for CRM source mapping UI helpers."""
from __future__ import annotations

from src.utils.crm_source_mapping_ui import collect_mappings_for_account, mappings_for_column


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
