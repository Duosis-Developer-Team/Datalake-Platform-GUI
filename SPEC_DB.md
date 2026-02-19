SPEC_DB.md - Master Database Integration Specification
1. Executive Summary
This document serves as the SINGLE SOURCE OF TRUTH for integrating the live PostgreSQL database into the Duosis Dashboard.
Objective: Replace MockService with a robust DatabaseService.
Strict Rule: No hallucinations. No guessing. Use the exact SQL snippets and logic defined below.

2. Infrastructure Scope
2.1 Target Data Centers
The system must support the following 9 Data Center Codes dynamically. The logic must allow iterating over these codes or accepting them as parameters.

AZ11 (Azerbaycan)

DC11 (Istanbul)

DC12

DC13 (Istanbul)

DC14

DC15

DC16

DC17

ICT11 (Almanya)

2.2 Database Configuration
Library: psycopg2 (Ensure it is in requirements.txt).

Credentials: Do not hardcode. Load from os.getenv or a config.py file.

DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS.

3. The DatabaseService Architecture
Create a class src/services/db_service.py.
Frontend pages (home.py, datacenters.py, dc_view.py) MUST NOT contain SQL. They only call methods from this service.

3.1 Helper Methods
_get_connection(): Manages connecting to PostgreSQL.

_execute_query_single(sql, params): Returns a single row (tuple) or None. Handles errors gracefully (returns None on error).

_execute_query_value(sql, params): Returns the first column of the first row (e.g., a count), or 0 if empty.

4. RAW SQL Repository (Do Not Modify Math)
These queries are extracted from Grafana. Use them EXACTLY as shown.
Critical: Replace the hardcoded string 'AZ11' with %s for Python parameter injection.

A. NUTANIX Queries (Source: nutanix_cluster_metrics)
Used for: Intel Tab, Global Sums.

1. Host Count:

SQL
SELECT num_nodes 
FROM public.nutanix_cluster_metrics 
WHERE cluster_name LIKE %s 
ORDER BY collection_time DESC LIMIT 1
2. Memory (Total/Used) - TB:

SQL
SELECT 
  total_memory_capacity, 
  ((memory_usage_avg / 1000 ) * total_memory_capacity) / 1000 
FROM nutanix_cluster_metrics 
WHERE cluster_name LIKE %s 
ORDER BY collection_time DESC LIMIT 1
3. Storage (Total/Used) - TB:

SQL
SELECT 
  storage_capacity / 2, 
  storage_usage / 2 
FROM nutanix_cluster_metrics 
WHERE cluster_name LIKE %s 
ORDER BY collection_time DESC LIMIT 1
4. CPU (Total/Used) - GHz:

SQL
SELECT 
  total_cpu_capacity, 
  (cpu_usage_avg * total_cpu_capacity) / 1000000 
FROM nutanix_cluster_metrics 
WHERE cluster_name LIKE %s 
ORDER BY collection_time DESC LIMIT 1
B. VMWARE Queries (Source: datacenter_metrics)
Used for: Intel Tab, Global Sums.

1. Host & Cluster Count:

SQL
SELECT total_cluster_count, total_host_count, total_vm_count 
FROM public.datacenter_metrics 
WHERE datacenter ILIKE %s 
ORDER BY timestamp DESC LIMIT 1
2. Memory (Total/Used) - Convert Bytes to GB/TB:

SQL
SELECT 
  total_memory_capacity_gb * 1024*1024*1024, 
  total_memory_used_gb * 1024*1024*1024 
FROM datacenter_metrics 
WHERE datacenter ILIKE %s 
ORDER BY timestamp DESC LIMIT 1
3. Storage (Total/Used) - Bytes:

SQL
SELECT 
  total_storage_capacity_gb*(1024*1024), 
  total_used_storage_gb*(1024*1024) 
FROM datacenter_metrics 
WHERE datacenter ILIKE %s 
ORDER BY timestamp DESC LIMIT 1
4. CPU (Total/Used) - Hz:

SQL
SELECT 
  total_cpu_ghz_capacity * 1000000000, 
  total_cpu_ghz_used * 1000000000 
FROM datacenter_metrics 
WHERE datacenter ILIKE %s 
ORDER BY timestamp DESC LIMIT 1
C. IBM POWER (HMC) Queries (Source: ibm_server_general)
Used for: Power Tab, Global Sums.

1. Host Count:

SQL
SELECT COUNT(DISTINCT server_details_servername) 
FROM public.ibm_server_general 
WHERE server_details_servername LIKE %s
Note: Since we lack CPU/RAM/VM Count queries for IBM, return 0 for those metrics to avoid errors.

D. ENERGY Queries (Source: Multiple)
Used for: Header Cards.

1. Racks Total Energy (Complex Regex):

SQL
SELECT SUM(
    CASE 
        WHEN kabin_enerji ~ '^[0-9]+(\.[0-9]+)?$' THEN kabin_enerji::float * 1000 
        ELSE regexp_replace(regexp_replace(kabin_enerji, '.', '.'), '[^0-9.]', '', 'g')::float * 1000 
    END
) 
FROM loki_racks 
WHERE location_name = %s 
  AND id IN (SELECT DISTINCT id FROM loki_racks)
2. IBM Energy:

SQL
SELECT sum(power_watts) FROM ibm_server_power_sum WHERE server_name ILIKE %s
3. vCenter Energy:

SQL
WITH latest_per_host AS (
  SELECT DISTINCT ON (vm.vmhost) vm.power_usage
  FROM public.vmhost_metrics vm 
  WHERE vmhost ILIKE %s 
  ORDER BY vm.vmhost, vm."timestamp" DESC
)
SELECT SUM(power_usage) FROM latest_per_host
5. Aggregation Logic (The "Brain")
This section defines how DatabaseService methods should process the raw SQL results.

5.1 Method: get_dc_details(dc_code)
Goal: Provide full data for the DC View Page (dc_view.py).
Inputs: dc_code (e.g., 'AZ11').
Process:

Format Query Parameter: Prepare string like f"%{dc_code}%".

Run Queries: Execute ALL queries in Section 4 for this DC.

Handle None: value = query_result if query_result else 0.

Calculate Aggregates & Normalize Units (CRITICAL STEP):

1.  **Memory Normalization (Target: GB):**
    * `Nutanix_Mem_GB` = Nutanix_Mem_Raw * 1024 (Since Raw is TB)
    * `VMware_Mem_GB` = VMware_Mem_Raw / (1024*1024*1024) (Since Raw is Bytes)
    * `Total_Intel_Ram_Cap` = Nutanix_Mem_GB + VMware_Mem_GB

2.  **Storage Normalization (Target: TB):**
    * `Nutanix_Storage_TB` = Nutanix_Storage_Raw (Already TB)
    * `VMware_Storage_TB` = VMware_Storage_Raw / (1024*1024) (VMware query is GB*1MB = KB. Convert KB to TB: / 1024 / 1024 / 1024)
    * `Total_Intel_Storage_Cap` = Nutanix_Storage_TB + VMware_Storage_TB

3.  **CPU Normalization (Target: GHz):**
    * `Nutanix_CPU_GHz` = Nutanix_CPU_Raw (Already GHz)
    * `VMware_CPU_GHz` = VMware_CPU_Raw / 1000000000 (Since Raw is Hz)
    * `Total_Intel_CPU_Cap` = Nutanix_CPU_GHz + VMware_CPU_GHz

4.  **Final Assignments:**
    * `Intel_Hosts` = Nutanix_Host + VMware_Host
    * `Intel_VMs` = VMware_VMs (Nutanix query missing)
    * `Power_Hosts` = IBM_Host_Count

Python
{
    "meta": {"name": dc_code, "location": "Unknown"}, # Map AZ11->Azerbaycan manually if needed
    "intel": {
        "hosts": ..., "vms": ...,
        "cpu_cap": ..., "cpu_used": ...,
        "ram_cap": ..., "ram_used": ...,
        "storage_cap": ..., "storage_used": ...
    },
    "power": {
        "hosts": ..., "vms": 0, "cpu": 0, "ram": 0 # Defaulting to 0 for missing IBM metrics
    },
    "energy": {
        "total_kw": (Racks + IBM + vCenter) / 1000 # Convert W to kW if needed
    }
}
5.2 Method: get_all_datacenters_summary()
Goal: Provide list data for Data Centers Page (datacenters.py).
Process:

Define DC List: ['AZ11', 'DC11', ..., 'ICT11'].

Loop through each dc in list.

Call get_dc_details(dc).

Extract Summary Metrics:

Total Hosts = Intel Hosts + Power Hosts.

Total VMs = Intel VMs + Power VMs.

Total Clusters = Nutanix Clusters (if avail) + VMware Clusters.

Return: List of Dictionaries.

5.3 Method: get_global_overview()
Goal: Provide totals for Home Dashboard (home.py).
Process:

Call get_all_datacenters_summary().

Sum up all results:

Global_Hosts = Sum of all DCs.

Global_VMs = Sum of all DCs.

Global_Power = Sum of all DCs energy.

Return: A single dictionary with global totals.

6. Implementation Checklist & Safety
Null Safety: The code MUST handle None returns from SQL.

Bad: total = nutanix_val + vmware_val (Crashes if one is None)

Good: total = (nutanix_val or 0) + (vmware_val or 0)

Unit Consistency:

Frontend expects readable units (TB, GB).

Backend should return consistent raw numbers (Bytes) or standardized (GB), consistent across all providers. Recommendation: Return Bytes/Hz from Service, format in Frontend.

DC Iteration: Ensure the loop covers all 9 Data Centers defined in Section 2.1.