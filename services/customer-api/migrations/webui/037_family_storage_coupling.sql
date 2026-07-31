-- 037_family_storage_coupling.sql
-- Per-virtualisation-environment compute <-> storage coupling rule.
--
-- The sellable pipeline has to answer one question per environment: when a
-- family runs out of CPU/RAM, is its free disk still sellable?
--
--   merged   -> no. Storage joins the compute min() and is capped by the
--               compute bottleneck (hyperconverged semantics: the disk lives
--               in the same nodes, so with no node left the disk is dead weight).
--   separate -> yes. Storage is sized from its own pool and is never capped by
--               CPU/RAM (classic VMware + external SAN, IBM Power semantics).
--   auto     -> keep the built-in behaviour: per-host `host_storage_in_triple`
--               for host-based families, family ratio + storage cap otherwise.
--
-- Every family is seeded as 'auto' on purpose: this migration must be a no-op
-- for the numbers. Operators move an environment out of 'auto' from
-- Administration -> Platform -> Compute / Storage.

BEGIN;

CREATE TABLE IF NOT EXISTS gui_family_storage_coupling (
    family      TEXT        NOT NULL,
    dc_code     TEXT        NOT NULL DEFAULT '*',
    mode        TEXT        NOT NULL DEFAULT 'auto'
                            CHECK (mode IN ('auto', 'merged', 'separate')),
    notes       TEXT        NOT NULL DEFAULT '',
    updated_by  TEXT        NOT NULL DEFAULT 'seed',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (family, dc_code)
);

COMMENT ON TABLE gui_family_storage_coupling IS
    'Compute/storage coupling per family and DC. dc_code=''*'' is the default row.';

INSERT INTO gui_family_storage_coupling (family, dc_code, mode, notes, updated_by)
VALUES
    ('virt_hyperconverged', '*', 'auto', 'Nutanix — cluster storage pool; built-in rule keeps storage out of the per-host min().', 'seed'),
    ('virt_classic',        '*', 'auto', 'VMware — external datastores; built-in rule uses the shared IBM storage range.',          'seed'),
    ('virt_km',             '*', 'auto', 'KM clusters — shared LUN.',                                                              'seed'),
    ('virt_power',          '*', 'auto', 'IBM Power — storage range shared with KM datastores.',                                    'seed'),
    ('virt_intel_hana',     '*', 'auto', 'SAP Intel HANA — runs on the shared Nutanix/KM cluster.',                                 'seed'),
    ('virt_power_hana',     '*', 'auto', 'SAP Power HANA — shares IBM Power infrastructure with virt_power.',                       'seed')
ON CONFLICT (family, dc_code) DO NOTHING;

COMMIT;
