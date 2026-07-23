# Licensed-OS detection SQL (TASK-81). VMware phase.
# Reads the latest raw_vmware_vm_config row per VM, LEFT JOINs the Tools-reported
# runtime OS as a truth-correction, excludes templates. Classification of the
# returned strings happens in Python (shared.licensing.os_classifier).
#
# Verification (TASK-81 Task 2): raw_vmware_vm_runtime carries vm_moid,
# vcenter_uuid, guest_guest_full_name, and collection_timestamp (confirmed via
# datalake/SQL/All Tables/raw_vmware_vm_runtime.sql), so the runtime LEFT JOIN
# below is used as-is.

# Params: (start_ts, end_ts, start_ts, end_ts)
VM_OS_CONFIG_LATEST = """
WITH cfg AS (
    SELECT DISTINCT ON (vm_moid, vcenter_uuid)
        vm_moid, vcenter_uuid, name, guest_id, guest_full_name, template
    FROM public.raw_vmware_vm_config
    WHERE collection_timestamp BETWEEN %s AND %s
    ORDER BY vm_moid, vcenter_uuid, collection_timestamp DESC
),
rt AS (
    SELECT DISTINCT ON (vm_moid, vcenter_uuid)
        vm_moid, vcenter_uuid, guest_guest_full_name
    FROM public.raw_vmware_vm_runtime
    WHERE collection_timestamp BETWEEN %s AND %s
    ORDER BY vm_moid, vcenter_uuid, collection_timestamp DESC
)
SELECT
    cfg.name,
    cfg.guest_id,
    COALESCE(NULLIF(rt.guest_guest_full_name, ''), cfg.guest_full_name) AS guest_full_name
FROM cfg
LEFT JOIN rt USING (vm_moid, vcenter_uuid)
WHERE COALESCE(template, false) = false
"""

# Params: (start_ts, end_ts, start_ts, end_ts, pattern)
VM_OS_CONFIG_LATEST_FOR_CUSTOMER = """
WITH cfg AS (
    SELECT DISTINCT ON (vm_moid, vcenter_uuid)
        vm_moid, vcenter_uuid, name, guest_id, guest_full_name, template
    FROM public.raw_vmware_vm_config
    WHERE collection_timestamp BETWEEN %s AND %s
    ORDER BY vm_moid, vcenter_uuid, collection_timestamp DESC
),
rt AS (
    SELECT DISTINCT ON (vm_moid, vcenter_uuid)
        vm_moid, vcenter_uuid, guest_guest_full_name
    FROM public.raw_vmware_vm_runtime
    WHERE collection_timestamp BETWEEN %s AND %s
    ORDER BY vm_moid, vcenter_uuid, collection_timestamp DESC
)
SELECT
    cfg.name,
    cfg.guest_id,
    COALESCE(NULLIF(rt.guest_guest_full_name, ''), cfg.guest_full_name) AS guest_full_name
FROM cfg
LEFT JOIN rt USING (vm_moid, vcenter_uuid)
WHERE COALESCE(template, false) = false
  AND cfg.name ILIKE %s
"""
