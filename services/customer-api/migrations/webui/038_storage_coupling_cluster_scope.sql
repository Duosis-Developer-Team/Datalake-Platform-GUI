-- 038_storage_coupling_cluster_scope.sql
-- Widen the compute/storage coupling rule from family-only to (family, cluster).
--
-- Why: the built-in 'auto' rule is finer than a family. `host_storage_in_triple`
-- decides per HOST — a pooled Nutanix node and a KM host with a shared LUN can
-- sit in the same family and disagree. A family-level override flattens that.
-- Measured 2026-08-02 across 36 clusters / 235 hosts: every family is currently
-- uniform (classic 100% local, hyperconverged 100% pooled), so this migration is
-- a no-op today. It exists so the finer rule has somewhere to live the day a
-- cluster stops agreeing with its family.
--
-- Scope resolution (most specific wins), implemented in SellableService:
--     (family, dc_code, 'cluster', <cluster name>)   -- narrowest
--     (family, dc_code, 'family',  '')
--     (family, '*',     'family',  '')               -- widest
--     no row                                         -- 'auto' = built-in rule
--
-- Cluster scope only means something for families whose sellable is computed
-- host-by-host (_HOST_BASED_FAMILIES: virt_classic, virt_hyperconverged). The
-- board keeps the switch disabled for the rest.

BEGIN;

ALTER TABLE gui_family_storage_coupling
    ADD COLUMN IF NOT EXISTS scope_kind TEXT NOT NULL DEFAULT 'family',
    ADD COLUMN IF NOT EXISTS scope_key  TEXT NOT NULL DEFAULT '';

-- Existing rows are family-scoped by construction; the defaults above already
-- backfilled them. Constrain only after the backfill so the ALTER cannot fail.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'gui_family_storage_coupling_scope_kind_check'
    ) THEN
        ALTER TABLE gui_family_storage_coupling
            ADD CONSTRAINT gui_family_storage_coupling_scope_kind_check
            CHECK (scope_kind IN ('family', 'cluster'));
    END IF;
END $$;

-- A family row must carry an empty key and a cluster row must carry a real one,
-- otherwise two spellings of "the family default" could both exist and the
-- resolver would pick between them arbitrarily.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'gui_family_storage_coupling_scope_key_check'
    ) THEN
        ALTER TABLE gui_family_storage_coupling
            ADD CONSTRAINT gui_family_storage_coupling_scope_key_check
            CHECK (
                (scope_kind = 'family'  AND scope_key = '')
                OR (scope_kind = 'cluster' AND scope_key <> '')
            );
    END IF;
END $$;

-- Widen the primary key. The old PK (family, dc_code) would reject a second row
-- for the same family in the same DC, which is exactly what a cluster rule is.
ALTER TABLE gui_family_storage_coupling
    DROP CONSTRAINT IF EXISTS gui_family_storage_coupling_pkey;

ALTER TABLE gui_family_storage_coupling
    ADD CONSTRAINT gui_family_storage_coupling_pkey
    PRIMARY KEY (family, dc_code, scope_kind, scope_key);

COMMENT ON COLUMN gui_family_storage_coupling.scope_kind IS
    '''family'' = whole environment; ''cluster'' = one cluster inside it.';
COMMENT ON COLUMN gui_family_storage_coupling.scope_key IS
    'Cluster name for scope_kind=''cluster''; empty string for ''family''.';

-- Explain the two family cards that overlap on purpose, so the next reader does
-- not "fix" one of them by deleting it.
UPDATE gui_family_storage_coupling
SET    notes = 'KM clusters — shared LUN. Subset of virt_classic: the panel reads '
               'cluster_metrics filtered to KM cluster names while virt_classic reads '
               'the whole DC. Both cards are live; keep their modes consistent.'
WHERE  family = 'virt_km'
  AND  scope_kind = 'family'
  AND  updated_by = 'seed';

UPDATE gui_family_storage_coupling
SET    notes = 'IBM Power — compute is per-frame (ibm_server_general). A frame-to-array '
               'link does exist (ibm_lpar_general.lparname -> '
               'raw_ibm_storage_mdiskgrp_host_mapping.host_name, which is the LPAR name '
               'plus a -NNNNNNNN suffix); it covers 34/36 frames and no frame spans two '
               'arrays. What is not attributable is array FREE space: the same pools also '
               'serve the KM/classic ESXi hosts, which is why virt_power carries a '
               '[min, max] storage range. Power is separate from compute in practice.'
WHERE  family = 'virt_power'
  AND  scope_kind = 'family'
  AND  updated_by = 'seed';

UPDATE gui_family_storage_coupling
SET    notes = 'SAP Power HANA — shares IBM Power infrastructure with virt_power. Its '
               'panels carry no infra source by default (CRM-only); binding them to the '
               'IBM tables would count the same frames twice.'
WHERE  family = 'virt_power_hana'
  AND  scope_kind = 'family'
  AND  updated_by = 'seed';

COMMIT;
