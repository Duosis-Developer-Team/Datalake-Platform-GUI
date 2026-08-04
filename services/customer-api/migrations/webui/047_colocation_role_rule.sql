-- Colocation sellable rack-role rules (global -- one row per Loki rack role).
--
-- Which rack roles count as sellable colocation inventory used to be the
-- module constant NON_SELLABLE_ROLE_IDS in shared/colocation/allocation.py,
-- i.e. a deploy-time decision. Operators now own it from Administration ->
-- Integrations -> NetBox / Loki -> Colocation Configuration.
--
-- The seed below is TODAY'S SHIPPED BEHAVIOUR (commit 7cd4c9e2), so applying
-- this migration moves no number: DC13 reads 272 sellable free U before and
-- after. ON CONFLICT DO NOTHING keeps a re-run from overwriting an operator's
-- edit.
--
-- Global on purpose: no dc column. See
-- docs/superpowers/specs/2026-08-04-colocation-rack-role-config-design.md §3.

CREATE TABLE IF NOT EXISTS gui_colocation_role_rule (
    role_id    TEXT PRIMARY KEY,
    sellable   BOOLEAN NOT NULL,
    notes      TEXT,
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO gui_colocation_role_rule (role_id, sellable, notes, updated_by)
VALUES
    ('1', FALSE, 'NETWORK RACK - switching gear, cannot be rented out', 'migration-047'),
    ('2', TRUE,  'HOST RACK - the sellable base', 'migration-047'),
    ('3', FALSE, 'NON-STANDART RACK - allocated to a colocation customer', 'migration-047'),
    ('4', FALSE, 'CUSTOMER RACK - allocated to a colocation customer', 'migration-047')
ON CONFLICT (role_id) DO NOTHING;
