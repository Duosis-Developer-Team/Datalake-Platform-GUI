-- 035: Remap legacy Veeam/Zerto replication CRM products to classic/HC page_keys.
-- Prefer product display names from gui_crm_price_override when present
-- (mirrors shared/sellable/panel_mapping.py). Also pin known catalog SKUs from
-- TASK-B3 when productid is already on the legacy page_key (name join may miss).
-- Legacy combined panels stay registered but inventory_visible=false.
-- Operator overrides (gui_crm_service_mapping_override) are untouched.

BEGIN;

-- ---------- Name-based remap (when price_override.product_name is populated) ----------

-- Veeam Replication — Klasik Mimari
UPDATE gui_crm_service_mapping_seed s
SET    page_key = 'backup_veeam_replication_classic_cpu'
FROM   gui_crm_price_override p
WHERE  s.productid = p.productid
  AND  p.product_name ILIKE '%Klasik Mimari%'
  AND  p.product_name ILIKE '%Veeam Replication%'
  AND  p.product_name ILIKE '%vCpu%'
  AND  s.page_key = 'backup_veeam_replication_cpu';

UPDATE gui_crm_service_mapping_seed s
SET    page_key = 'backup_veeam_replication_classic_ram'
FROM   gui_crm_price_override p
WHERE  s.productid = p.productid
  AND  p.product_name ILIKE '%Klasik Mimari%'
  AND  p.product_name ILIKE '%Veeam Replication%'
  AND  p.product_name ILIKE '%RAM%'
  AND  s.page_key = 'backup_veeam_replication_ram';

UPDATE gui_crm_service_mapping_seed s
SET    page_key = 'backup_veeam_replication_classic_storage'
FROM   gui_crm_price_override p
WHERE  s.productid = p.productid
  AND  p.product_name ILIKE '%Klasik Mimari%'
  AND  p.product_name ILIKE '%Veeam Replication%'
  AND  p.product_name ILIKE '%Disk%'
  AND  s.page_key = 'backup_veeam_replication_storage';

-- Veeam Replication — Hyperconverged Mimari
UPDATE gui_crm_service_mapping_seed s
SET    page_key = 'backup_veeam_replication_hyperconverged_cpu'
FROM   gui_crm_price_override p
WHERE  s.productid = p.productid
  AND  p.product_name ILIKE '%Hyperconverged%'
  AND  p.product_name ILIKE '%Veeam Replication%'
  AND  p.product_name ILIKE '%vCpu%'
  AND  s.page_key = 'backup_veeam_replication_cpu';

UPDATE gui_crm_service_mapping_seed s
SET    page_key = 'backup_veeam_replication_hyperconverged_ram'
FROM   gui_crm_price_override p
WHERE  s.productid = p.productid
  AND  p.product_name ILIKE '%Hyperconverged%'
  AND  p.product_name ILIKE '%Veeam Replication%'
  AND  p.product_name ILIKE '%RAM%'
  AND  s.page_key = 'backup_veeam_replication_ram';

UPDATE gui_crm_service_mapping_seed s
SET    page_key = 'backup_veeam_replication_hyperconverged_storage'
FROM   gui_crm_price_override p
WHERE  s.productid = p.productid
  AND  p.product_name ILIKE '%Hyperconverged%'
  AND  p.product_name ILIKE '%Veeam Replication%'
  AND  p.product_name ILIKE '%Disk%'
  AND  s.page_key = 'backup_veeam_replication_storage';

-- Zerto Replication — Klasik Mimari
UPDATE gui_crm_service_mapping_seed s
SET    page_key = 'backup_zerto_replication_classic_cpu'
FROM   gui_crm_price_override p
WHERE  s.productid = p.productid
  AND  p.product_name ILIKE '%Klasik Mimari%'
  AND  p.product_name ILIKE '%Zerto Replication%'
  AND  p.product_name ILIKE '%vCpu%'
  AND  s.page_key = 'backup_zerto_replication_cpu';

UPDATE gui_crm_service_mapping_seed s
SET    page_key = 'backup_zerto_replication_classic_ram'
FROM   gui_crm_price_override p
WHERE  s.productid = p.productid
  AND  p.product_name ILIKE '%Klasik Mimari%'
  AND  p.product_name ILIKE '%Zerto Replication%'
  AND  p.product_name ILIKE '%RAM%'
  AND  s.page_key = 'backup_zerto_replication_ram';

UPDATE gui_crm_service_mapping_seed s
SET    page_key = 'backup_zerto_replication_classic_storage'
FROM   gui_crm_price_override p
WHERE  s.productid = p.productid
  AND  p.product_name ILIKE '%Klasik Mimari%'
  AND  p.product_name ILIKE '%Zerto Replication%'
  AND  p.product_name ILIKE '%Disk%'
  AND  s.page_key = 'backup_zerto_replication_storage';

-- Zerto Replication — Hyperconverged Mimari
UPDATE gui_crm_service_mapping_seed s
SET    page_key = 'backup_zerto_replication_hyperconverged_cpu'
FROM   gui_crm_price_override p
WHERE  s.productid = p.productid
  AND  p.product_name ILIKE '%Hyperconverged%'
  AND  p.product_name ILIKE '%Zerto Replication%'
  AND  p.product_name ILIKE '%vCpu%'
  AND  s.page_key = 'backup_zerto_replication_cpu';

UPDATE gui_crm_service_mapping_seed s
SET    page_key = 'backup_zerto_replication_hyperconverged_ram'
FROM   gui_crm_price_override p
WHERE  s.productid = p.productid
  AND  p.product_name ILIKE '%Hyperconverged%'
  AND  p.product_name ILIKE '%Zerto Replication%'
  AND  p.product_name ILIKE '%RAM%'
  AND  s.page_key = 'backup_zerto_replication_ram';

UPDATE gui_crm_service_mapping_seed s
SET    page_key = 'backup_zerto_replication_hyperconverged_storage'
FROM   gui_crm_price_override p
WHERE  s.productid = p.productid
  AND  p.product_name ILIKE '%Hyperconverged%'
  AND  p.product_name ILIKE '%Zerto Replication%'
  AND  p.product_name ILIKE '%Disk%'
  AND  s.page_key = 'backup_zerto_replication_storage';

-- Runtime classify() already maps Klasik/HC display names → classic/hc page_keys
-- (shared/sellable/panel_mapping.py). Seed remap above is for CRM Inventory joins.

-- Legacy combined panels: keep registry, hide from inventory (034 classic/HC visible).
UPDATE gui_panel_definition
SET    inventory_visible = FALSE,
       notes             = COALESCE(
           NULLIF(notes, ''),
           'Legacy combined replication panel — superseded by classic/HC split'
       ),
       updated_by        = 'seed',
       updated_at        = NOW()
WHERE  panel_key IN (
    'backup_veeam_replication_cpu',
    'backup_veeam_replication_ram',
    'backup_veeam_replication_storage',
    'backup_zerto_replication_cpu',
    'backup_zerto_replication_ram',
    'backup_zerto_replication_storage'
);

COMMIT;
