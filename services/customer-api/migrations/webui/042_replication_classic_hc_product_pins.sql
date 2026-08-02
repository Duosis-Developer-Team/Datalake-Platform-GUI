-- 042: Pin known Veeam/Zerto replication productids to classic/HC page_keys
-- (catalog names from discovery_crm_products; 035 name-join via price_override
-- was a no-op when overrides were empty). Also hide HC Nutanix image inventory
-- row until sellable semantics are clarified.

BEGIN;

-- Veeam Classic
UPDATE gui_crm_service_mapping_seed SET page_key = 'backup_veeam_replication_classic_cpu'
WHERE productid = 'e2635018-5c6d-f011-b4cc-6045bd93381c';
UPDATE gui_crm_service_mapping_seed SET page_key = 'backup_veeam_replication_classic_ram'
WHERE productid = 'e0635018-5c6d-f011-b4cc-6045bd93381c';
UPDATE gui_crm_service_mapping_seed SET page_key = 'backup_veeam_replication_classic_storage'
WHERE productid IN (
    'da635018-5c6d-f011-b4cc-6045bd93381c',
    '69e3822e-6eaa-f011-bbd3-6045bd9a4052'
);

-- Veeam HC
UPDATE gui_crm_service_mapping_seed SET page_key = 'backup_veeam_replication_hyperconverged_cpu'
WHERE productid = 'fc635018-5c6d-f011-b4cc-6045bd93381c';
UPDATE gui_crm_service_mapping_seed SET page_key = 'backup_veeam_replication_hyperconverged_ram'
WHERE productid = 'fa635018-5c6d-f011-b4cc-6045bd93381c';
UPDATE gui_crm_service_mapping_seed SET page_key = 'backup_veeam_replication_hyperconverged_storage'
WHERE productid IN (
    'f6635018-5c6d-f011-b4cc-6045bd93381c',
    'f8635018-5c6d-f011-b4cc-6045bd93381c'
);

-- Zerto Classic
UPDATE gui_crm_service_mapping_seed SET page_key = 'backup_zerto_replication_classic_cpu'
WHERE productid = '8a5a940d-2895-f011-b41c-002248873b68';
UPDATE gui_crm_service_mapping_seed SET page_key = 'backup_zerto_replication_classic_ram'
WHERE productid = 'd02c2e5a-2895-f011-b41c-002248873b68';
UPDATE gui_crm_service_mapping_seed SET page_key = 'backup_zerto_replication_classic_storage'
WHERE productid IN (
    '9156fb9d-2895-f011-b41c-002248873b68',
    '1c48fee3-a4a9-f011-bbd3-7c1e52724e0e'
);

-- Zerto HC
UPDATE gui_crm_service_mapping_seed SET page_key = 'backup_zerto_replication_hyperconverged_cpu'
WHERE productid = 'f6d0d00f-2495-f011-b41c-002248873b68';
UPDATE gui_crm_service_mapping_seed SET page_key = 'backup_zerto_replication_hyperconverged_ram'
WHERE productid = '4979b8e9-2595-f011-b41c-002248873b68';
UPDATE gui_crm_service_mapping_seed SET page_key = 'backup_zerto_replication_hyperconverged_storage'
WHERE productid IN (
    'd5f69091-2795-f011-b41c-002248873b68',
    '2f934c48-2795-f011-b41c-002248873b68'
);

-- Ensure seed rows exist even if 010 was partial (idempotent upsert).
INSERT INTO gui_crm_service_mapping_seed (productid, page_key) VALUES
    ('e2635018-5c6d-f011-b4cc-6045bd93381c', 'backup_veeam_replication_classic_cpu'),
    ('e0635018-5c6d-f011-b4cc-6045bd93381c', 'backup_veeam_replication_classic_ram'),
    ('da635018-5c6d-f011-b4cc-6045bd93381c', 'backup_veeam_replication_classic_storage'),
    ('69e3822e-6eaa-f011-bbd3-6045bd9a4052', 'backup_veeam_replication_classic_storage'),
    ('fc635018-5c6d-f011-b4cc-6045bd93381c', 'backup_veeam_replication_hyperconverged_cpu'),
    ('fa635018-5c6d-f011-b4cc-6045bd93381c', 'backup_veeam_replication_hyperconverged_ram'),
    ('f6635018-5c6d-f011-b4cc-6045bd93381c', 'backup_veeam_replication_hyperconverged_storage'),
    ('f8635018-5c6d-f011-b4cc-6045bd93381c', 'backup_veeam_replication_hyperconverged_storage'),
    ('8a5a940d-2895-f011-b41c-002248873b68', 'backup_zerto_replication_classic_cpu'),
    ('d02c2e5a-2895-f011-b41c-002248873b68', 'backup_zerto_replication_classic_ram'),
    ('9156fb9d-2895-f011-b41c-002248873b68', 'backup_zerto_replication_classic_storage'),
    ('1c48fee3-a4a9-f011-bbd3-7c1e52724e0e', 'backup_zerto_replication_classic_storage'),
    ('f6d0d00f-2495-f011-b41c-002248873b68', 'backup_zerto_replication_hyperconverged_cpu'),
    ('4979b8e9-2595-f011-b41c-002248873b68', 'backup_zerto_replication_hyperconverged_ram'),
    ('d5f69091-2795-f011-b41c-002248873b68', 'backup_zerto_replication_hyperconverged_storage'),
    ('2f934c48-2795-f011-b41c-002248873b68', 'backup_zerto_replication_hyperconverged_storage')
ON CONFLICT (productid) DO UPDATE SET page_key = EXCLUDED.page_key;

-- Hide Hyperconverged Image Backup from CRM Inventory until later.
UPDATE gui_panel_definition
SET    inventory_visible = FALSE,
       notes = COALESCE(
           NULLIF(notes, ''),
           'Hidden from CRM Inventory — HC image sellable/match deferred'
       ),
       updated_by = 'seed',
       updated_at = NOW()
WHERE  panel_key = 'backup_image_hyperconverged';

COMMIT;
