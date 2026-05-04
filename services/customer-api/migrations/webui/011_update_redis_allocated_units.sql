-- 011_update_redis_allocated_units.sql
-- Updates allocated_unit for panels whose allocated data now comes from the
-- datacenter-api Redis cache (dc_details.classic / dc_details.hyperconv)
-- instead of being queried directly from datalake VM-level tables.
--
-- SellableService reads the following Redis fields:
--   classic.cpu_used  (GHz)  classic.mem_used (GB)  classic.stor_used (TB)
--   hyperconv.cpu_used (GHz) hyperconv.mem_used (GB) hyperconv.stor_used (TB)
--
-- allocated_unit must match what Redis actually returns so that the
-- gui_unit_conversion chain produces correct display values.
-- Example: GHz → vCPU (divide by 8), TB → GB (multiply by 1024).

BEGIN;

-- vm_metrics panels (classic KM VMware → Redis classic.*)
UPDATE gui_panel_infra_source
SET allocated_unit = 'GHz', notes = COALESCE(NULLIF(notes,''), '') || ' [allocated_unit updated to GHz for Redis path]'
WHERE allocated_table = 'vm_metrics'
  AND allocated_column = 'number_of_cpus'
  AND updated_by = 'seed';

UPDATE gui_panel_infra_source
SET allocated_unit = 'TB', notes = COALESCE(NULLIF(notes,''), '') || ' [allocated_unit updated to TB for Redis path]'
WHERE allocated_table = 'vm_metrics'
  AND allocated_column = 'provisioned_space_gb'
  AND updated_by = 'seed';

-- nutanix_vm_metrics panels (hyperconverged → Redis hyperconv.*)
UPDATE gui_panel_infra_source
SET allocated_unit = 'GHz', notes = COALESCE(NULLIF(notes,''), '') || ' [allocated_unit updated to GHz for Redis path]'
WHERE allocated_table = 'nutanix_vm_metrics'
  AND allocated_column = 'cpu_count'
  AND updated_by = 'seed';

UPDATE gui_panel_infra_source
SET allocated_unit = 'GB', notes = COALESCE(NULLIF(notes,''), '') || ' [allocated_unit updated to GB for Redis path]'
WHERE allocated_table = 'nutanix_vm_metrics'
  AND allocated_column = 'memory_capacity'
  AND updated_by = 'seed';

UPDATE gui_panel_infra_source
SET allocated_unit = 'TB', notes = COALESCE(NULLIF(notes,''), '') || ' [allocated_unit updated to TB for Redis path]'
WHERE allocated_table = 'nutanix_vm_metrics'
  AND allocated_column = 'disk_capacity'
  AND updated_by = 'seed';

COMMIT;
