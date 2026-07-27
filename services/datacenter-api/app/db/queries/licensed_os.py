# Licensed-OS detection SQL (TASK-81).
#
# Source: the LIVE NetBox VM snapshot (discovery_netbox_virtualization_vm), whose
# custom_fields_guest_os carries the guest OS display string (~92% populated,
# refreshed daily). The original VMware source (raw_vmware_vm_config /
# raw_vmware_vm_runtime) stopped collecting 2026-03-12 (~136 days stale), so it
# is not used.
#
# Deduped by VM identity (shared vm_topology dedup key) so each VM is classified
# once — the raw table has ~2x duplicate NetBox records per VM. status_value is
# returned so the tally can split running vs all; vCLS/system VMs are excluded in
# Python (_tally_os_rows). Classification: shared.licensing.os_classifier.

from shared.topology.vm_topology import VM_OS_DEDUP_KEY_SQL

# Params: none
VM_OS_NETBOX = f"""
SELECT DISTINCT ON ({VM_OS_DEDUP_KEY_SQL})
    name,
    NULL::text AS guest_id,
    custom_fields_guest_os AS guest_full_name,
    status_value
FROM public.discovery_netbox_virtualization_vm
ORDER BY {VM_OS_DEDUP_KEY_SQL}, (status_value = 'poweredOn') DESC
"""

# Params: (pattern,)  — VM name ILIKE, same customer heuristic as before.
#
# NOTE: the per-customer path here matches a VM *name* against the customer's CRM
# display name, which only works for the minority of VMs named after the full legal
# entity. Customer View no longer uses it — it derives the tally from the VM lists
# customer-api already resolves via the alias/source-pattern mechanism (see
# services/customer-api/app/utils/licensed_os.py). Kept for the standalone page.
VM_OS_NETBOX_FOR_CUSTOMER = f"""
SELECT DISTINCT ON ({VM_OS_DEDUP_KEY_SQL})
    name,
    NULL::text AS guest_id,
    custom_fields_guest_os AS guest_full_name,
    status_value
FROM public.discovery_netbox_virtualization_vm
WHERE name ILIKE %s
ORDER BY {VM_OS_DEDUP_KEY_SQL}, (status_value = 'poweredOn') DESC
"""

# ---------------------------------------------------------------------------
# Per-DC breakdown (DC View › Virtualization › Lisanslı OS)
# ---------------------------------------------------------------------------
#
# DC View splits by architecture; vm_metrics is the right source for that because
# it carries BOTH the DC (`datacenter`) and the cluster the billing split keys on
# (`cluster ILIKE '%KM%'`), and its guest_os column is written on every row.
# NetBox knows more VMs but its site_name is city-level (ISTANBUL/ANKARA), which
# cannot answer "how many licensed guests in DC13".

# Params: (dc_wildcard, start_ts, end_ts)
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
# Power's only guest-OS signal. Values seen live: 'Linux - SUSE' (300 LPARs),
# 'Linux', 'AIX', 'AIX/Linux', 'Unknown'.
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

# Params: (dc_wildcard,)
# Pure-Nutanix guests carry no OS in any source, so they are reported as an
# explicit "no telemetry" count instead of being folded into `unknown`.
#
# Scoped on cluster_name, NOT site_name: NetBox site_name is city-level
# (ISTANBUL / ANKARA / IZMIR), so a DC-code pattern matches nothing there.
# Cluster names carry the DC code (DC13-G1-AHV-CLS, ISTAHV-DC17-HYBRID).
AHV_VM_COUNT_BY_DC = f"""
SELECT COUNT(*) FROM (
    SELECT DISTINCT ON ({VM_OS_DEDUP_KEY_SQL}) 1 AS one
    FROM public.discovery_netbox_virtualization_vm
    WHERE cluster_name ILIKE '%%AHV%%'
      AND cluster_name ILIKE %s
      AND lower(name) NOT LIKE 'vcls%%'
    ORDER BY {VM_OS_DEDUP_KEY_SQL}
) d
"""

# ---------------------------------------------------------------------------
# Per-DC CRM attribution: which customers occupy this DC, and how much of their
# estate sits here. See shared/licensing/dc_breakdown.attribute_licences_to_dc.
# ---------------------------------------------------------------------------
#
# Both queries scope on cluster_name for the same reason as above. Tenant coverage
# measured 2026-07-27: DC13 577 tenants over 18,974 VMs, DC14 438/9,650,
# DC11 127/3,618 — good enough to attribute on. (The pre-existing
# crm_potential.DC_TENANT_VALUES uses site_name and returns zero tenants for any
# DC-code pattern.)

# Both counts MUST come from the same per-VM (tenant, cluster) assignment,
# otherwise a VM whose duplicate NetBox records disagree gets tenant A inside the
# DC-filtered dedup and tenant B in the global one — which produced a tenant whose
# DC count (350) exceeded its platform count (342) on 2026-07-27, i.e. a share
# above 100%. So dedup once, globally, with a deterministic tie-break, and filter
# by cluster afterwards. `here <= everywhere` then holds by construction.
_TENANT_DEDUPED_CTE = f"""
WITH deduped AS (
    SELECT DISTINCT ON ({VM_OS_DEDUP_KEY_SQL})
        lower(btrim(COALESCE(custom_fields_musteri, ''))) AS tenant,
        cluster_name
    FROM public.discovery_netbox_virtualization_vm
    WHERE lower(name) NOT LIKE 'vcls%%'
    ORDER BY {VM_OS_DEDUP_KEY_SQL},
             (btrim(COALESCE(custom_fields_musteri, '')) <> '') DESC,
             id
)
"""

# Params: (dc_wildcard,)
# Internal buckets (e.g. 'silinecek_makineler_*') stay in: they resolve to no CRM
# account downstream and so contribute nothing, and filtering them by name here
# would be a guess about naming conventions.
DC_TENANT_VM_COUNTS = _TENANT_DEDUPED_CTE + """
SELECT tenant, COUNT(*) AS vms
FROM   deduped
WHERE  tenant <> ''
  AND  cluster_name ILIKE %s
GROUP BY tenant
"""

# Params: none — platform-wide footprint, the denominator of each tenant's share.
TENANT_VM_COUNTS_ALL = _TENANT_DEDUPED_CTE + """
SELECT tenant, COUNT(*) AS vms
FROM   deduped
WHERE  tenant <> ''
GROUP BY tenant
"""
