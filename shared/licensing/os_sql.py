"""Guest-OS detection SQL, shared by datacenter-api and customer-api.

One copy on purpose: DC View, Customer View and CRM Inventory Overview all report
licensed-guest counts, and three near-identical queries drifting apart would show
three different numbers for the same estate.

Scoping notes:
  * vm_metrics is the source for VMware-visible guests — it is the only table with
    both the DC (`datacenter`) and the cluster the Classic/Hyperconverged split
    bills on (`cluster ILIKE '%KM%'`), and its guest_os column is always written.
  * ibm_lpar_general.lpar_details_ostype is Power's only guest-OS signal.
  * Pure-Nutanix (AHV) guests have no guest OS in any source; they are counted, not
    classified. See AHV_VM_COUNT_BY_DC in the datacenter-api query module.

Every query takes an ILIKE pattern so callers can pass '%DC13%' for one DC or '%'
for the whole platform.
"""
from __future__ import annotations

# Params: (dc_wildcard, start_ts, end_ts)
# DISTINCT ON because vm_metrics writes every 15 minutes — without it a 7-day
# window counts the same guest hundreds of times.
VM_OS_BY_DC = """
SELECT DISTINCT ON (vmname)
    cluster,
    vmname,
    guest_os
FROM public.vm_metrics
WHERE datacenter ILIKE %s
  AND LEFT(vmname, 1) <> '_'
  AND "timestamp" BETWEEN %s AND %s
ORDER BY vmname, "timestamp" DESC
"""

# Params: (dc_wildcard, start_ts, end_ts)
# Values seen live: 'Linux - SUSE' (300 LPARs), 'Linux', 'AIX', 'AIX/Linux',
# 'Unknown'. Server names carry the DC, LPAR names do not.
POWER_OS_BY_DC = """
SELECT DISTINCT ON (lparname)
    lparname,
    lpar_details_ostype
FROM public.ibm_lpar_general
WHERE lpar_details_servername LIKE %s
  AND LEFT(lparname, 1) <> '_'
  AND time BETWEEN %s AND %s
ORDER BY lparname, time DESC
"""

# Params: (cluster_wildcard,)
#
# Widest guest source, for platform-level reporting (CRM Inventory Overview).
# vm_metrics only sees what vCenter manages — 8,911 guests — while NetBox knows
# 20,158 including Nutanix-only ones. Measured 2026-07-27 the difference is stark:
# Windows reads 4,956 through vm_metrics and 8,057 through NetBox. Anything
# claiming to be a platform total has to use the wider set.
#
# Scoped on cluster_name rather than site_name so the same query can answer for
# one DC (site_name is city-level: ISTANBUL / ANKARA / IZMIR). Pass '%' for all.
VM_OS_NETBOX_BY_CLUSTER = """
SELECT guest_os FROM (
    SELECT DISTINCT ON (
        COALESCE(NULLIF(btrim(custom_fields_config_instance_uuid), ''),
                 lower(name) || '|' || coalesce(cluster_name, ''))
    )
        custom_fields_guest_os AS guest_os
    FROM public.discovery_netbox_virtualization_vm
    WHERE COALESCE(cluster_name, '') ILIKE %s
      AND lower(name) NOT LIKE 'vcls%%'
    ORDER BY
        COALESCE(NULLIF(btrim(custom_fields_config_instance_uuid), ''),
                 lower(name) || '|' || coalesce(cluster_name, '')),
        (btrim(COALESCE(custom_fields_guest_os, '')) <> '') DESC
) d
"""
