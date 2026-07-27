"""SQL for the Unmapped (Eşleşmeyen Veriler) pseudo-account — Phase 1: VMs.

Pulls the distinct set of *live* VM names per platform, window-bounded and
already stripped of deleted VMs (leading '_'). Ownership classification happens
in Python (see shared.customer.unmapped_classifier) — no leading-wildcard scan.
"""

# Distinct VMware VM names in the window, excluding deleted ('_' prefix).
UNMAPPED_VMWARE_NAMES = """
SELECT DISTINCT vmname AS name
FROM public.vm_metrics
WHERE "timestamp" BETWEEN %s AND %s
  AND vmname IS NOT NULL
  AND LEFT(vmname, 1) <> '_'
"""

# Distinct Nutanix VM names in the window, excluding deleted ('_' prefix).
UNMAPPED_NUTANIX_NAMES = """
SELECT DISTINCT vm_name AS name
FROM public.nutanix_vm_metrics
WHERE collection_time BETWEEN %s AND %s
  AND vm_name IS NOT NULL
  AND LEFT(vm_name, 1) <> '_'
"""

# All CRM accounts (for fuzzy alias-gap owner guessing + the one-click alias
# action, which needs the accountid to address the save endpoint).
CRM_ACCOUNT_NAMES = """
SELECT DISTINCT name, accountid
FROM public.discovery_crm_accounts
WHERE name IS NOT NULL AND btrim(name) <> ''
"""

# Distinct NetBackup policy names in the window. starttime is the job's own
# clock (this table has no collection_time), so the window bounds it directly.
UNMAPPED_NETBACKUP_POLICIES = """
SELECT DISTINCT policyname AS name
FROM public.raw_netbackup_jobs_metrics
WHERE starttime BETWEEN %s AND %s
  AND policyname IS NOT NULL
  AND btrim(policyname) <> ''
"""
