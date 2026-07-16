"""SQL for the deleted-VM registry (item 2).

Two DBs:
  * datalake (bulutlake): the all-time scan over metric tables — SLOW (~84s full
    seq-scan on the leading-'_' predicate), run only by the scheduler with an
    elevated statement_timeout.
  * webui-db: the small registry table read/written on the request path.
"""

# --- datalake: all-time deleted VMs with first/last metric date (scheduler only) ---

DELETED_VMWARE_ALLTIME = """
SELECT vmname AS name,
       MIN("timestamp")::date AS first_seen,
       MAX("timestamp")::date AS last_seen
FROM public.vm_metrics
WHERE LEFT(vmname, 1) = '_'
GROUP BY vmname
"""

DELETED_NUTANIX_ALLTIME = """
SELECT vm_name AS name,
       MIN(collection_time)::date AS first_seen,
       MAX(collection_time)::date AS last_seen
FROM public.nutanix_vm_metrics
WHERE LEFT(vm_name, 1) = '_'
GROUP BY vm_name
"""

# --- webui-db: upsert one registry row (first_seen retention-protected) ---

UPSERT_DELETED_VM = """
INSERT INTO gui_deleted_vm_registry
    (platform, vm_name, customer, request_date, planned_date,
     first_seen, last_seen, actual_delete_date, updated_at)
VALUES
    (%(platform)s, %(vm_name)s, %(customer)s, %(request_date)s, %(planned_date)s,
     %(first_seen)s, %(last_seen)s, %(actual_delete_date)s, NOW())
ON CONFLICT (platform, vm_name) DO UPDATE SET
    customer           = EXCLUDED.customer,
    request_date       = EXCLUDED.request_date,
    planned_date       = EXCLUDED.planned_date,
    first_seen         = LEAST(gui_deleted_vm_registry.first_seen, EXCLUDED.first_seen),
    last_seen          = GREATEST(gui_deleted_vm_registry.last_seen, EXCLUDED.last_seen),
    actual_delete_date = EXCLUDED.actual_delete_date,
    updated_at         = NOW()
"""

# --- webui-db: per-customer read for the panel (tiny table, ILIKE is instant) ---
# Matches the customer's resolved virtualization patterns (same set the resources
# path uses), so the panel shows the same VMs it always did — now all-time + dated.

LIST_DELETED_VMS_BY_PATTERNS = """
SELECT platform, vm_name, customer, request_date, planned_date,
       first_seen, last_seen, actual_delete_date
FROM gui_deleted_vm_registry
WHERE vm_name ILIKE ANY(%s)
ORDER BY (actual_delete_date IS NULL) DESC,   -- still-running (overdue) first
         planned_date DESC NULLS LAST,
         vm_name
"""

REGISTRY_COUNT = "SELECT COUNT(*) AS n FROM gui_deleted_vm_registry"
