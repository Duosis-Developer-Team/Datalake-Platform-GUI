# TASK-18 — Colocation Hizmeti Hesaplama Altyapısı

**Tip:** Feature · **Efor:** M · **Öncelik:** Orta

## Hedef
Colocation hizmeti için hizmet kalemi ↔ altyapı verisi hesaplama altyapısının hazırlanması.

## İyi haber: altyapı zaten büyük ölçüde hazır

| Bileşen | Yer |
|---|---|
| Ortak modüller | `shared/colocation/matching.py`, `shared/colocation/occupancy.py` |
| Servis | `services/customer-api/app/services/colocation_matching_service.py` |
| Endpoint | `GET /api/v1/crm/colocation/{dc_code}` (customer-api `routers/colocation.py`) |
| DC endpoint'leri | `/datacenters/{dc}/racks`, `/racks/{rack}/devices`, `/racks/occupancy` |
| UI | DC View › Colocation sekmesi, `floor_map.py` (colocation summary strip), Internal Resources tablosu |
| Yetki | `sec:dc_view:colocation` |
| Kaynak tablolar | `discovery_loki_racks` (`site_name`, `u_height`), `discovery_netbox_inventory_device` (tenant, location) |
| Son işler | `ded60355 feat(colocation): Internal Resources table`, `95bba70b used_u_breakdown (External/Internal/Untagged)`, `7e015d98 exact per-customer U + de-dup` |

**Eksik olan: CRM ürün bağlantısı.** Colocation SKU'ları registry'de **yok**:

| SKU | Ürün | Birim | Registry |
|---|---|---|---|
| `000BLT-155` | Veri Merkezi Barındırma Hizmeti (Standart Kabinet) | Adet | ❌ |
| `000BLT-154` | Veri Merkezi Barındırma Hizmeti (Standart Dışı Kabinet) | Adet | ❌ |
| `000BLT-156` | Veri Merkezi Barındırma Hizmeti (U) | **U** | ❌ |
| `000BLT-157` | Veri Merkezi Enerji Birim Bedeli | **kW** | ❌ |

`000BLT-156` özellikle değerli: birimi **U** ve altyapı tarafında `used_u_breakdown` zaten hesaplanıyor
⇒ doğrudan `capacity` eşleşmesi kurulabilir.

## Yapılacaklar

- [ ] Dört SKU'yu registry'ye ekle:
  ```yaml
  "000BLT-156":
    name: Veri Merkezi Barındırma Hizmeti (U)
    usage_source: Loki - Racks
    matching_rule: Müşteri başına kullanılan U (NetBox tenant x rack occupancy)
    match_status: capacity
    panel_key: colocation_used_u
    family: colocation
    infra_tables: [discovery_loki_racks, discovery_netbox_inventory_device]
  "000BLT-155": # Standart Kabinet - Adet
    match_status: capacity
    panel_key: colocation_rack_standard
    family: colocation
  "000BLT-154": # Standart Dışı Kabinet - Adet
    panel_key: colocation_rack_nonstandard
    family: colocation
  "000BLT-157": # Enerji kW
    match_status: capacity
    panel_key: colocation_energy_kw
    family: colocation
    infra_tables: [vmhost_metrics]   # veya enerji kaynağı - task/query-map/07-energy.md
  ```
- [ ] `gui_crm_service_pages` kayıtları (`resource_unit`: U / Adet / kW)
- [ ] Seed SQL yeniden üret + idempotent migration
- [ ] `colocation_matching_service.py`'yi inventory pipeline'ına bağla:
      Sold (CRM U/kabinet) vs Used (gerçek U) vs Free
- [ ] Inventory ekranında "Colocation" ailesi
- [ ] Enerji için `task/query-map/07-energy.md`'deki kW kaynağını kullan
      (`STATIC_TOTAL_ENERGY_KW` geçici çözümüne dikkat — gerçek kaynağa bağlayın)
- [ ] Customer View'da colocation kartı (müşteri kendi kabinetini görsün — **TASK-13 ile uyumlu**:
      kendi U'sunu görür, komşusunun cihazlarını görmez)

## Doğrulama SQL'leri

```sql
-- 1) Rack kapasitesi (Loki)
SELECT site_name, COUNT(*) AS rack, SUM(u_height) AS toplam_u
FROM   public.discovery_loki_racks GROUP BY 1 ORDER BY 3 DESC;

-- 2) Müşteri (tenant) başına kullanılan U — de-dup dikkat
SELECT d.tenant_name, d.site_name, COUNT(*) AS cihaz
FROM   public.discovery_netbox_inventory_device d
WHERE  d.status_value='active' AND d.tenant_name IS NOT NULL
GROUP  BY 1,2 ORDER BY 3 DESC LIMIT 40;
-- NOT: gerçek U hesabı shared/colocation/occupancy.py'de; rack unit pozisyon kolonlarını
--      information_schema ile doğrulayın (position/u_height/device_type_u_height).

-- 3) CRM'de satılan colocation
SELECT p.productnumber, p.name, d.uomid_name,
       SUM(d.quantity) AS miktar, SUM(d.extendedamount) AS tl,
       COUNT(DISTINCT so.customerid) AS musteri
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid=d.salesorderid
JOIN   discovery_crm_products p ON p.productid=d.productid
WHERE  so.statecode=0 AND p.productnumber IN ('000BLT-154','000BLT-155','000BLT-156','000BLT-157')
GROUP  BY 1,2,3 ORDER BY 1;

-- 4) NetBox rack pozisyon kolonları var mı (U hesabının ön koşulu)
SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema='public' AND table_name='discovery_netbox_inventory_device'
  AND (column_name ILIKE '%rack%' OR column_name ILIKE '%position%' OR column_name ILIKE '%u_height%');
```

```bash
curl -s "http://10.134.52.250:8001/api/v1/crm/colocation/DC13" | python3 -m json.tool | head -50
curl -s "http://10.134.52.250:8000/api/v1/datacenters/DC13/racks/occupancy" | python3 -m json.tool | head -40
```

## Kabul kriterleri
- [ ] 4 SKU registry + `gui_crm_service_pages`'te tanımlı, migration uygulanmış
- [ ] Inventory'de "Colocation" ailesi: CRM Sold (U/Adet/kW) vs Used vs Free
- [ ] Used U değeri `/racks/occupancy` ve `crm/colocation/{dc}` çıktılarıyla tutarlı
- [ ] Duplike rack satırı yok (`7e015d98` de-dup düzeltmesi korunuyor)
- [ ] Customer View'da müşteri kendi colocation kullanımını görüyor, başkasınınkini görmüyor

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, task/query-map/{07-energy.md,09-discovery-inventory.md},
shared/colocation/{matching.py,occupancy.py},
services/customer-api/app/services/colocation_matching_service.py,
services/customer-api/app/routers/colocation.py,
shared/matching/product_matching_registry.yaml, config/crm_service_mapping.yaml

Görev: Colocation hizmet kalemlerini CRM inventory hesabına bağla.

1. Keşif: /api/v1/crm/colocation/{dc} ve /datacenters/{dc}/racks/occupancy cevaplarını dök.
   used_u_breakdown (External/Internal/Untagged) alanlarının şeklini yaz.
2. registry'ye ekle: 000BLT-156 (U, capacity, panel colocation_used_u),
   000BLT-155/154 (Adet, kabinet sayısı), 000BLT-157 (kW, enerji).
   Enerji için task/query-map/07-energy.md'deki gerçek kaynağı kullan;
   STATIC_TOTAL_ENERGY_KW geçici değerine BAĞLANMA.
3. gui_crm_service_pages kayıtları + config/crm_service_mapping.yaml + generate_seed_sql.py
   + idempotent migration.
4. inventory_overview_service.py: colocation ailesini üret.
   Sold = CRM miktarı, Used = colocation_matching_service'ten gerçek U/kabinet, Free = fark.
   Mevcut de-dup mantığını (commit 7e015d98) yeniden kullan, kendi sayımını yazma.
5. crm_inventory_report.py: "Colocation" accordion grubu ve U/Adet/kW birimleri.
6. tests/: U toplamının occupancy endpoint'iyle tutarlılığı, duplike rack olmadığı.

Kısıt: Colocation U hesabı zaten shared/colocation/occupancy.py'de - paralel bir hesap yazma,
mevcut modülü kullan.
```
