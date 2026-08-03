-- 045: Unbind OS management services from licensed-OS infra telemetry.
-- Inventory Overview must show only Windows / RHEL / SUSE *licence* SKUs under
-- the OS Lisans group (ADR-0034). Management services (mgmt_os_*) remain CRM
-- products but are CRM-only on this screen — they are not licences.
-- Nulling source_table + total_column makes SellableService.has_infra False
-- (same pattern as 038_disable_zerto_site_metrics_infra.sql).

UPDATE gui_panel_infra_source
SET source_table = NULL,
    total_column = NULL,
    total_unit = NULL,
    allocated_table = NULL,
    allocated_column = NULL,
    allocated_unit = NULL,
    filter_clause = NULL,
    notes = COALESCE(notes, '') || CASE
        WHEN COALESCE(notes, '') = '' THEN
            'disabled: mgmt OS is CRM-only on inventory (045 / ADR-0034)'
        WHEN notes LIKE '%mgmt OS is CRM-only%' THEN ''
        ELSE '; disabled: mgmt OS is CRM-only on inventory (045 / ADR-0034)'
    END
WHERE panel_key IN (
    'mgmt_os_windows',
    'mgmt_os_linux',
    'mgmt_os_sap',
    'mgmt_os_unix'
)
AND (
    LOWER(COALESCE(source_table, '')) = '__licensed_os_detection__'
    OR (source_table IS NOT NULL AND total_column IS NOT NULL)
);
