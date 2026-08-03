-- 044_replication_coupling_default_merged.sql
-- Flip Classic/HC replication Compute/Storage default from separate → merged.
-- Only touches seed rows so operator overrides are preserved.

BEGIN;

UPDATE gui_family_storage_coupling
SET    mode = 'merged',
       notes = CASE family
           WHEN 'backup_veeam_replication_classic' THEN
               'Veeam Replication Classic — compute host SoT from virt_classic; '
               'own resource ratios; storage merged with compute by default.'
           WHEN 'backup_zerto_replication_classic' THEN
               'Zerto Replication Classic — compute host SoT from virt_classic; '
               'own resource ratios; storage merged with compute by default.'
           WHEN 'backup_veeam_replication_hyperconverged' THEN
               'Veeam Replication HC — compute host SoT from virt_hyperconverged; '
               'own resource ratios; storage merged with compute by default.'
           WHEN 'backup_zerto_replication_hyperconverged' THEN
               'Zerto Replication HC — compute host SoT from virt_hyperconverged; '
               'own resource ratios; storage merged with compute by default.'
           ELSE notes
       END,
       updated_at = NOW()
WHERE  family IN (
           'backup_veeam_replication_classic',
           'backup_zerto_replication_classic',
           'backup_veeam_replication_hyperconverged',
           'backup_zerto_replication_hyperconverged'
       )
  AND  dc_code = '*'
  AND  scope_kind = 'family'
  AND  scope_key = ''
  AND  updated_by = 'seed';

COMMIT;
