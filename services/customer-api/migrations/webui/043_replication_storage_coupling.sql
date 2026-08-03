-- 043_replication_storage_coupling.sql
-- Add Veeam/Zerto Classic/HC replication families to Compute / Storage coupling.
--
-- Default mode is 'separate': replication storage is a dedicated pool and must
-- not be capped by CPU/RAM (ADR-0032). Operators may move cards to merged/auto
-- from Administration -> Platform -> Compute / Storage.
--
-- Ratios stay independent per family (gui_panel_resource_ratio); this migration
-- only seeds coupling rows.

BEGIN;

INSERT INTO gui_family_storage_coupling (
    family, dc_code, scope_kind, scope_key, mode, notes, updated_by
) VALUES
    (
        'backup_veeam_replication_classic', '*', 'family', '', 'separate',
        'Veeam Replication Classic — compute host SoT from virt_classic; '
        'own resource ratios; storage dedicated (separate by default).',
        'seed'
    ),
    (
        'backup_zerto_replication_classic', '*', 'family', '', 'separate',
        'Zerto Replication Classic — compute host SoT from virt_classic; '
        'own resource ratios; storage dedicated (separate by default).',
        'seed'
    ),
    (
        'backup_veeam_replication_hyperconverged', '*', 'family', '', 'separate',
        'Veeam Replication HC — compute host SoT from virt_hyperconverged; '
        'own resource ratios; storage dedicated (separate by default).',
        'seed'
    ),
    (
        'backup_zerto_replication_hyperconverged', '*', 'family', '', 'separate',
        'Zerto Replication HC — compute host SoT from virt_hyperconverged; '
        'own resource ratios; storage dedicated (separate by default).',
        'seed'
    )
ON CONFLICT (family, dc_code, scope_kind, scope_key) DO NOTHING;

COMMIT;
