"""Per-DC licensed-OS breakdown, split by virtualization architecture.

DC View needs the split (a DC owner sells capacity per architecture); Customer
View does not. The split rule is the one the platform already bills on:
`cluster ILIKE '%KM%'` is Classic, everything else Hyperconverged. Power is a
separate source entirely (ibm_lpar_general.lpar_details_ostype).

Live shape 2026-07-27, per DC and architecture, VMware side:
    DC13-Nutanix-vDC  hyperconv  5,214 VMs  2,412 Windows  160 RHEL   52 SUSE
    DC13-KM-vDC       classic    1,652 VMs    860 Windows  136 RHEL   44 SUSE
    DC11-Nutanix-nvDC hyperconv  1,450 VMs    891 Windows   20 RHEL   45 SUSE
Power, all DCs: 300 LPARs report "Linux - SUSE", 21 Linux, 20 Unknown, 14 AIX.
"""
from __future__ import annotations

import re

from app.db.queries import licensed_os as loq


def _count_placeholders(sql: str) -> int:
    return len(re.findall(r"(?<!%)%s", sql))


def test_dc_vm_os_query_is_scoped_by_datacenter_and_time():
    sql = loq.VM_OS_BY_DC
    assert "public.vm_metrics" in sql
    assert "datacenter ILIKE %s" in sql
    assert _count_placeholders(sql) == 4   # netbox dc pattern + dc pattern + start + end


def test_dc_vm_os_query_returns_the_cluster_so_the_arch_split_can_be_applied():
    sql = loq.VM_OS_BY_DC
    assert "cluster" in sql
    assert "guest_os" in sql


def test_dc_queries_expose_power_state_for_the_running_only_view():
    assert "status_value" in loq.VM_OS_BY_DC
    assert "lpar_details_state" in loq.POWER_OS_BY_DC


def test_dc_vm_os_query_dedupes_to_one_row_per_vm():
    """vm_metrics writes every 15 minutes; without DISTINCT ON a 7-day window
    counts the same guest hundreds of times."""
    assert "DISTINCT ON (vmname)" in loq.VM_OS_BY_DC


def test_dc_vm_os_query_excludes_deleted_machines():
    # Leading underscore marks a deleted/archived VM across the platform.
    assert "LEFT(vmname, 1) <> '_'" in loq.VM_OS_BY_DC


def test_power_os_query_reads_the_hmc_ostype():
    sql = loq.POWER_OS_BY_DC
    assert "ibm_lpar_general" in sql
    assert "lpar_details_ostype" in sql
    assert "lpar_details_servername LIKE %s" in sql
    assert _count_placeholders(sql) == 3


def test_power_os_query_counts_each_lpar_once():
    assert "DISTINCT ON (lparname)" in loq.POWER_OS_BY_DC


def test_ahv_blind_spot_query_counts_vms_without_any_os_signal():
    """Pure-Nutanix VMs have no guest OS anywhere. The DC card must state how many
    guests it cannot classify rather than fold them into 'unknown' silently."""
    sql = loq.AHV_VM_COUNT_BY_DC
    assert "discovery_netbox_virtualization_vm" in sql
    assert "AHV" in sql
    assert _count_placeholders(sql) == 1


def test_dc_scoped_netbox_queries_key_on_cluster_name_not_site_name():
    """NetBox site_name is city-level (ISTANBUL / ANKARA / IZMIR): scoping a
    DC-code pattern against it returns nothing. Verified live 2026-07-27 —
    site_name ILIKE '%DC13%' resolves 0 tenants, cluster_name resolves 577."""
    for sql in (loq.AHV_VM_COUNT_BY_DC, loq.DC_TENANT_VM_COUNTS):
        assert "cluster_name ILIKE %s" in sql
        assert "site_name" not in sql


def test_tenant_footprint_queries_pair_up_for_share_calculation():
    assert _count_placeholders(loq.DC_TENANT_VM_COUNTS) == 1   # this DC
    assert _count_placeholders(loq.TENANT_VM_COUNTS_ALL) == 0  # everywhere
    for sql in (loq.DC_TENANT_VM_COUNTS, loq.TENANT_VM_COUNTS_ALL):
        assert "custom_fields_musteri" in sql
        assert "GROUP BY tenant" in sql
        # Deduped before counting: the raw table holds ~2 records per VM, which
        # would inflate every tenant's footprint.
        assert "DISTINCT ON" in sql


def test_tenant_counts_dedupe_identically_so_a_dc_share_cannot_exceed_one():
    """Both queries must reduce the SAME per-VM (tenant, cluster) assignment.

    When the DC-scoped query deduped inside the filtered set and the global one
    across everything, a VM with disagreeing duplicate NetBox records landed under
    different tenants in each — live on 2026-07-27 one tenant showed 350 VMs in
    DC13 against 342 platform-wide, i.e. a footprint share above 100%.
    """
    dc_sql, all_sql = loq.DC_TENANT_VM_COUNTS, loq.TENANT_VM_COUNTS_ALL
    # Same dedup CTE, verbatim, in both.
    cte = dc_sql.split("SELECT tenant, COUNT(*)")[0]
    assert cte == all_sql.split("SELECT tenant, COUNT(*)")[0]
    # The DC filter is applied AFTER the dedup, not inside it.
    assert "cluster_name ILIKE %s" not in cte
    assert "cluster_name ILIKE %s" in dc_sql
    # Deterministic tie-break, so repeated runs pick the same record.
    assert "id" in cte


def test_tenant_queries_exclude_system_vms():
    for sql in (loq.DC_TENANT_VM_COUNTS, loq.TENANT_VM_COUNTS_ALL, loq.AHV_VM_COUNT_BY_DC):
        assert "NOT LIKE 'vcls" in sql


def test_no_stray_percent_signs():
    for sql in (
        loq.VM_OS_BY_DC,
        loq.POWER_OS_BY_DC,
        loq.AHV_VM_COUNT_BY_DC,
        loq.DC_TENANT_VM_COUNTS,
        loq.TENANT_VM_COUNTS_ALL,
    ):
        assert re.search(r"(?<!%)%(?!s)", sql.replace("%%", "")) is None
