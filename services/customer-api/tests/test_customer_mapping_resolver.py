#!/usr/bin/env python3
"""Unit tests for customer source mapping resolver."""
from __future__ import annotations

from app.services.customer_mapping_resolver import (
    MappingRule,
    build_resolved_patterns,
    boyner_seed_rows,
    dedupe_vm_rows,
    dedupe_zerto_vpgs,
    sql_pattern_for_match,
)


def test_sql_pattern_for_match_contains_prefix_suffix_exact():
    assert sql_pattern_for_match("contains", "Boyner") == ("ilike", "%Boyner%")
    assert sql_pattern_for_match("prefix", "Boyner") == ("ilike", "Boyner%")
    assert sql_pattern_for_match("suffix", "Boyner") == ("ilike", "%Boyner")
    assert sql_pattern_for_match("exact", "Boyner") == ("exact", "Boyner")
    assert sql_pattern_for_match("id_exact", "5") == ("id_exact", "5")


def test_build_resolved_patterns_groups_by_source():
    rules = [
        MappingRule("virtualization", "contains", "Boyner"),
        MappingRule("backup_veeam", "contains", "Boyner"),
        MappingRule("physical_device", "id_exact", "5"),
        MappingRule("itsm_servicecore", "contains", "boyner"),
    ]
    resolved = build_resolved_patterns(rules)
    assert resolved.ilike_by_source["virtualization"] == ["%Boyner%"]
    assert resolved.physical_tenant_ids == [5]
    assert resolved.itsm_needles


def test_build_resolved_patterns_uses_fallback_when_no_rules():
    resolved = build_resolved_patterns([], fallback_search_name="Acme")
    assert resolved.ilike_by_source["virtualization"] == ["%Acme%"]
    assert resolved.itsm_needles


def test_dedupe_vm_rows_by_name():
    rows = [
        {"name": "vm-a", "cpu": 1},
        {"name": "VM-A", "cpu": 2},
        {"name": "vm-b", "cpu": 3},
    ]
    out = dedupe_vm_rows(rows)
    assert len(out) == 2
    assert out[0]["name"] == "vm-a"


def test_dedupe_zerto_vpgs_by_name():
    rows = [{"name": "vpg-1"}, {"name": "VPG-1"}, {"name": "vpg-2"}]
    assert len(dedupe_zerto_vpgs(rows)) == 2


def test_boyner_seed_rows_contains_physical_and_netbox_values():
    rows = boyner_seed_rows("acc-1", "BOYNER BUYUK MAGAZACILIK A.S.")
    sources = {r["data_source"] for r in rows}
    assert "physical_device" in sources
    assert "netbox_vm_customer" in sources
    physical = [r for r in rows if r["data_source"] == "physical_device"][0]
    assert physical["match_method"] == "id_exact"
    assert physical["match_value"] == "5"
    netbox_values = {
        r["match_value"]
        for r in rows
        if r["data_source"] == "netbox_vm_customer"
    }
    assert "Boyner_Equinix" in netbox_values
