-- Reject match_method values that are meaningless for their data_source.
-- id_exact correlates by numeric tenant id: valid only for physical_device and
-- auranotify. On a name-matched source it produced a rule the SQL path dropped
-- and the in-memory classifier read as `contains`, hiding resources from both
-- the customer view and the Unmapped page at the same time.
--
-- NOT VALID: new and updated rows are checked immediately; pre-existing rows are
-- left alone so this migration cannot fail on live data. Clean the violators
-- listed by scripts/alias_match_impact_report.py, then run:
--     ALTER TABLE gui_crm_customer_source_mapping
--         VALIDATE CONSTRAINT chk_source_mapping_method_for_source;

ALTER TABLE gui_crm_customer_source_mapping
    DROP CONSTRAINT IF EXISTS chk_source_mapping_method_for_source;

ALTER TABLE gui_crm_customer_source_mapping
    ADD CONSTRAINT chk_source_mapping_method_for_source CHECK (
        CASE
            WHEN data_source IN ('physical_device', 'auranotify')
                THEN match_method = 'id_exact'
            ELSE match_method IN ('contains', 'prefix', 'suffix', 'exact')
        END
    ) NOT VALID;
