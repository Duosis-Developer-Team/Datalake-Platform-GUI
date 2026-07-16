-- 027_deleted_vm_registry.sql
-- All-time registry of deletion-marked VMs (name starts with '_').
--
-- Why a table (not a live query): "all time" means dropping the time-window
-- filter, and the source scan over vm_metrics / nutanix_vm_metrics with a
-- leading-'_' predicate is a full seq-scan (~84s measured), which exceeds the
-- request-path statement_timeout (60s). The customer-api scheduler fills this
-- table offline (elevated timeout); the deleted-VMs panel reads it per-customer
-- instantly. first_seen is persisted so request/first dates survive retention
-- pruning of old metric rows.
BEGIN;

CREATE TABLE IF NOT EXISTS gui_deleted_vm_registry (
    platform            TEXT NOT NULL,          -- 'vmware' | 'nutanix'
    vm_name             TEXT NOT NULL,
    customer            TEXT,                    -- parsed prefix (before first '-')
    request_date        DATE,                    -- planned_date - 14 days
    planned_date        DATE,                    -- date encoded in the VM name
    first_seen          DATE,                    -- earliest metric for this '_' name
    last_seen           DATE,                    -- latest metric
    actual_delete_date  DATE,                    -- last_seen once metrics stop; NULL while emitting
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (platform, vm_name)
);

CREATE INDEX IF NOT EXISTS idx_deleted_vm_registry_customer
    ON gui_deleted_vm_registry (lower(customer));

COMMIT;
