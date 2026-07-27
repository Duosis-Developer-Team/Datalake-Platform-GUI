-- services/customer-api/migrations/webui/031_licensed_os_infra_sources.sql
-- CRM Inventory Overview: bind the licence / OS-management panels to guest-OS
-- telemetry so their rows stop rendering as
-- "(CRM entitled — infra telemetry pending)" with dashes in Total/Used.
--
-- The counts are computed in code (SellableService._query_licensed_os_totals ->
-- app/utils/licensed_os_inventory.py), keyed on panel_key. source_table is a
-- documented sentinel and is never executed as SQL for these panels — the same
-- arrangement 029 uses for dc_hosting_u.
--
-- total == allocated for every one of these: a Windows licence can only be sold
-- to a Windows guest, so there is no headroom to report. The point of the row is
-- the CRM-sold column sitting next to a real Used figure.
BEGIN;

INSERT INTO gui_panel_infra_source
    (panel_key, dc_code, source_table, total_column, total_unit,
     allocated_table, allocated_column, allocated_unit, filter_clause, notes, updated_by)
SELECT
    p.panel_key, '*',
    '__licensed_os_detection__', 'detected_guests', p.unit,
    '__licensed_os_detection__', 'detected_guests', p.unit,
    NULL,
    p.note,
    'seed'
FROM (VALUES
    ('license_windows_os', 'per VM',
     'Detected Windows guests (vm_metrics.guest_os).'),
    ('license_redhat', 'Adet',
     'Detected RHEL guests (vm_metrics.guest_os).'),
    ('license_suse', 'Adet',
     'Detected SUSE guests (vm_metrics.guest_os).'),
    ('mgmt_os_windows', 'per VM',
     'Detected Windows guests — same estate as the OS licence, billed as a service.'),
    ('mgmt_os_linux', 'per VM',
     'Every detected Linux guest (RHEL + SUSE + free distributions).'),
    ('mgmt_os_sap', 'per VM',
     'SUSE LPARs on Power (ibm_lpar_general.lpar_details_ostype = Linux - SUSE).'),
    ('mgmt_os_unix', 'per VM',
     'AIX LPARs (ibm_lpar_general.lpar_details_ostype).')
) AS p(panel_key, unit, note)
WHERE EXISTS (SELECT 1 FROM gui_panel_definition d WHERE d.panel_key = p.panel_key)
ON CONFLICT (panel_key, dc_code) DO UPDATE SET
    source_table     = EXCLUDED.source_table,
    total_column     = EXCLUDED.total_column,
    total_unit       = EXCLUDED.total_unit,
    allocated_table  = EXCLUDED.allocated_table,
    allocated_column = EXCLUDED.allocated_column,
    allocated_unit   = EXCLUDED.allocated_unit,
    filter_clause    = EXCLUDED.filter_clause,
    notes            = COALESCE(NULLIF(EXCLUDED.notes, ''), gui_panel_infra_source.notes),
    updated_by       = 'seed',
    updated_at       = NOW();

COMMIT;
