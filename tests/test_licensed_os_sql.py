"""Shared guest-OS SQL — one copy, so the three surfaces cannot report different
numbers for the same estate (DC View, Customer View, CRM Inventory Overview)."""
from __future__ import annotations

import re

from shared.licensing import os_sql


def _placeholders(sql: str) -> int:
    return len(re.findall(r"(?<!%)%s", sql))


def test_no_stray_percent_signs_anywhere():
    """A bare % in these strings is a psycopg2 format token, not a wildcard."""
    for name in ("VM_OS_BY_DC", "POWER_OS_BY_DC", "VM_OS_NETBOX_BY_CLUSTER"):
        sql = getattr(os_sql, name)
        assert re.search(r"(?<!%)%(?!s)", sql.replace("%%", "")) is None, name


def test_vm_metrics_query_is_dc_and_time_scoped():
    # dc pattern for the NetBox power-state join + dc pattern, start, end for vm_metrics
    assert _placeholders(os_sql.VM_OS_BY_DC) == 4
    assert "datacenter ILIKE %s" in os_sql.VM_OS_BY_DC


def test_vm_metrics_query_carries_power_state():
    """vm_metrics has no power column, so it is joined in from NetBox — a licence
    position reads differently for a guest that is switched off."""
    sql = os_sql.VM_OS_BY_DC
    assert "status_value" in sql
    assert "discovery_netbox_virtualization_vm" in sql


def test_power_query_carries_lpar_state():
    assert "lpar_details_state" in os_sql.POWER_OS_BY_DC


def test_power_query_is_server_and_time_scoped():
    assert _placeholders(os_sql.POWER_OS_BY_DC) == 3
    assert "lpar_details_servername LIKE %s" in os_sql.POWER_OS_BY_DC


def test_netbox_query_is_the_wide_platform_source():
    """vm_metrics only sees vCenter-managed guests (8,911); NetBox sees 20,158.
    Anything claiming to be a platform total has to use the wider set."""
    sql = os_sql.VM_OS_NETBOX_BY_CLUSTER
    assert "discovery_netbox_virtualization_vm" in sql
    assert _placeholders(sql) == 1


def test_netbox_query_scopes_on_cluster_name_so_it_can_answer_per_dc():
    # site_name is city-level (ISTANBUL / ANKARA / IZMIR) and cannot answer
    # "how many licensed guests in DC13".
    assert "cluster_name" in os_sql.VM_OS_NETBOX_BY_CLUSTER
    assert "site_name" not in os_sql.VM_OS_NETBOX_BY_CLUSTER


def test_netbox_query_dedupes_and_prefers_the_record_that_has_an_os():
    sql = os_sql.VM_OS_NETBOX_BY_CLUSTER
    assert "DISTINCT ON" in sql
    assert "custom_fields_config_instance_uuid" in sql
    assert "<> ''" in sql          # tie-break prefers a populated guest_os
    assert "NOT LIKE 'vcls" in sql  # vSphere agent VMs are not licensable guests


def test_all_queries_return_something_classifiable():
    for name in ("VM_OS_BY_DC", "VM_OS_NETBOX_BY_CLUSTER"):
        assert "guest_os" in getattr(os_sql, name)
    assert "lpar_details_ostype" in os_sql.POWER_OS_BY_DC
