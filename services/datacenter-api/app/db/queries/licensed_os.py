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
