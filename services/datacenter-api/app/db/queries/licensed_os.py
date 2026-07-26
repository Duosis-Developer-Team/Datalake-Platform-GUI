# Licensed-OS detection SQL (TASK-81).
#
# Source: the LIVE NetBox VM snapshot (discovery_netbox_virtualization_vm), whose
# custom_fields_guest_os carries the guest OS display string (~92% populated,
# refreshed daily). The original VMware source (raw_vmware_vm_config /
# raw_vmware_vm_runtime) stopped collecting 2026-03-12 (~136 days stale), so the
# 7-day window returned 0 rows and nothing could be classified. NetBox is the
# inventory-of-record (Loki) and is current, so we read guest OS from it.
#
# One row per VM (discovery_netbox_virtualization_vm.id is unique — a snapshot,
# not a timeseries), so no time window or DISTINCT ON is needed. guest_id is a
# vSphere-only enum absent from NetBox → NULL; the classifier works on the
# display string alone. Classification happens in Python
# (shared.licensing.os_classifier).

# Params: none
VM_OS_NETBOX = """
SELECT
    name,
    NULL::text AS guest_id,
    custom_fields_guest_os AS guest_full_name
FROM public.discovery_netbox_virtualization_vm
"""

# Params: (pattern,)  — VM name ILIKE, same customer heuristic as before.
VM_OS_NETBOX_FOR_CUSTOMER = """
SELECT
    name,
    NULL::text AS guest_id,
    custom_fields_guest_os AS guest_full_name
FROM public.discovery_netbox_virtualization_vm
WHERE name ILIKE %s
"""
