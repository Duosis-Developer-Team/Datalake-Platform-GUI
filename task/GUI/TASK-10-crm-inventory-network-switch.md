# TASK-10 — CRM Inventory: Network ve Switch Eklemeleri

**Tip:** Feature · **Efor:** M · **Öncelik:** Orta-Yüksek

## Hedef
CRM inventory'e network tarafı entegre edilecek; özellikle **switch donanımları** envantere dahil edilecek.

## Mevcut durum — kritik tespit

`shared/matching/product_matching_registry.yaml` **222 CRM ürününden yalnızca 36'sını** kapsıyor.
Network ailesinde durum:

| SKU | Ürün | Birim | Registry | infra_tables |
|---|---|---|---|---|
| `000BLT-67` | Data Switch Port ve SFP Hizmeti | Adet | ✅ var (`documented`) | `discovery_netbox_inventory_device` |
| `000BLT-20` | Cross Connection Port Hizmeti | Adet | ✅ var (`documented`) | — (boş) |
| `000BLT-91` | Public IPv4 Blok /29 | Adet | ✅ var (`documented`) | — (IPAM tablosu yok) |
| `000BLT-68` | **Management Switch Port Hizmeti** | Adet | ❌ **YOK** | — |
| `000BLT-208` | Veri Merkezi Erişim ve L3 DDoS | Mbit | ❌ **YOK** (registry'de), ama billing kodunda var | — |

`000BLT-208` ilginç: `services/datacenter-api/app/db/queries/crm_network_pricing.py` içinde
`NETWORK_DC_ACCESS_PRODUCT_ID = "e2f585bb-c2e0-f011-8406-6045bd9c244d"` olarak **hard-code** edilmiş
(bu GUID = `000BLT-208`). Registry'ye taşınmalı, GUID kodda kalmamalı.

## Altyapı tarafında switch verisi nerede

| Kaynak | Tablo | Kullanım |
|---|---|---|
| **NetBox (Loki)** | `discovery_netbox_inventory_device` | Fiziksel cihaz envanteri: `name`, `device_type_model`, `site_name`, `location_name`, `tenant_name`, `status_value`, rol |
| **Zabbix** | `raw_zabbix_network_device_health_metrics` | Cihaz sağlığı, `loki_id` → NetBox `id` eşlemesi |
| **Zabbix interface** | `raw_zabbix_network_interface_*` | Port bazlı trafik, 95p |
| Sorgular | `services/datacenter-api/app/db/queries/zabbix_network.py` | `NETWORK_DEVICES_FOR_DC_LATEST`, port-summary, 95p, interface-table |
| Rol bazlı UI | `src/pages/dc_view.py` — `NETWORK_TOP_SCOPES = ["overview","switch","router_uplink","firewall","load_balancer"]` | Switch rolü zaten ayrı scope |

⚠️ `loki_id` varchar, NetBox `id` int8 → join öncesi `numeric_loki_id_predicate()` ile filtreleyin
(Zabbix'te `VFW_2289` gibi alias'lar var).

## Yapılacaklar

- [ ] `000BLT-68` ve `000BLT-208`'i registry'ye ekle; `000BLT-67`/`000BLT-20`'yi `capacity`'ye taşımayı değerlendir
- [ ] `crm_network_pricing.py`'deki hard-code GUID'i registry/DB lookup'a çevir
- [ ] **Switch port envanteri sorgusu yaz:** NetBox'ta switch rolündeki cihazların port sayısı;
      Zabbix interface tablosundan kullanılan/boş port ayrımı
- [ ] Yeni panel_key'ler: `network_switch_port`, `network_mgmt_switch_port`, `network_cross_connect`
      (`gui_crm_service_pages` + `gui_panel_definition`)
- [ ] Inventory ekranında yeni **"Network"** ailesi accordion grubu
      (`crm_inventory_report.py` içindeki aile listelerine ekle)
- [ ] Birim: "Adet" (port sayısı) — `gui_unit_conversion` gerekmiyor ama `display_unit` doğru set edilmeli
- [ ] Fiyat: `gui_crm_price_override` yoksa CRM ima edilen fiyat (`extendedamount/quantity`)
- [ ] **Cache etkisi:** yeni satırlar inventory yükünü artırır → **TASK-01 bitmeden bunu prod'a almayın**

## Doğrulama SQL'leri

```sql
-- 1) NetBox'ta switch cihazları ve DC dağılımı
SELECT d.site_name, d.location_name, d.device_type_model, COUNT(*) AS cihaz
FROM   public.discovery_netbox_inventory_device d
WHERE  d.status_value = 'active'
  AND  (d.name ILIKE '%sw%' OR d.device_type_model ILIKE '%switch%' OR d.device_type_model ILIKE '%nexus%'
        OR d.device_type_model ILIKE '%catalyst%' OR d.device_type_model ILIKE '%arista%')
GROUP  BY 1,2,3 ORDER BY 4 DESC;

-- 2) Cihaz rolü kolonu var mı (rol bazlı filtre için)
SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema='public' AND table_name='discovery_netbox_inventory_device'
ORDER BY ordinal_position;

-- 3) Zabbix interface tarafında port sayısı (DC bazlı)
SELECT COUNT(DISTINCT loki_id) AS cihaz, COUNT(*) AS interface_satir,
       MAX(collection_timestamp) AS son_veri
FROM   public.raw_zabbix_network_interface_metrics_v
WHERE  collection_timestamp > now() - interval '1 day'
  AND  loki_id ~ '^[0-9]+$';

-- 4) CRM'de satılan switch port miktarı
SELECT p.productnumber, p.name, d.uomid_name,
       SUM(d.quantity) AS satilan_adet, SUM(d.extendedamount) AS tl,
       ROUND(SUM(d.extendedamount)/NULLIF(SUM(d.quantity),0),2) AS ima_edilen_birim_fiyat
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid=d.salesorderid
JOIN   discovery_crm_products p ON p.productid=d.productid
WHERE  so.statecode=0 AND p.productnumber IN ('000BLT-67','000BLT-68','000BLT-20','000BLT-91','000BLT-208')
GROUP  BY 1,2,3 ORDER BY 1;

-- 5) Müşteri bazlı switch (tenant) — customer view'a bağlamak için
SELECT tenant_name, COUNT(*) AS cihaz
FROM   public.discovery_netbox_inventory_device
WHERE  status_value='active' AND tenant_name IS NOT NULL
GROUP  BY 1 ORDER BY 2 DESC LIMIT 30;
```

## Kabul kriterleri
- [ ] `000BLT-67/68/20/91/208` registry'de tanımlı, hard-code GUID kalmadı
- [ ] Inventory ekranında "Network" ailesi görünüyor: CRM Sold vs altyapı port sayısı
- [ ] Switch port sayısı NetBox/Zabbix SQL'i ile ±%1 uyumlu
- [ ] Yeni satırlarla birlikte inventory-overview p95 hâlâ < 800 ms (sıcak cache)
- [ ] Eşleşmeyen network SKU'ları "unmapped" bandında doğru raporlanıyor

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, task/query-map/{08-zabbix-monitoring.md,09-discovery-inventory.md},
datalake-platform-knowledge-base/wiki/CRM-Inventory-Infra-Matching.md,
shared/matching/product_matching_registry.yaml,
services/datacenter-api/app/db/queries/{zabbix_network.py,crm_network_pricing.py},
services/customer-api/app/services/inventory_overview_service.py, src/components/crm_inventory_report.py

Görev: CRM Inventory'ye network / switch ailesini ekle.

1. Keşif: NetBox discovery_netbox_inventory_device şemasını information_schema ile dök.
   Switch cihazlarını hangi kolonla güvenilir şekilde ayırabileceğimizi belirle
   (device_role varsa onu kullan, yoksa device_type_model deseni). Bulgunu raporla.
2. registry'ye ekle: 000BLT-68 (Management Switch Port), 000BLT-208 (DC Erişim/L3 DDoS).
   000BLT-67 ve 000BLT-20 için capacity'ye taşınabilirlik değerlendir.
   crm_network_pricing.py'deki hard-code NETWORK_DC_ACCESS_PRODUCT_ID'yi registry lookup'a çevir.
3. Yeni panel_key'ler: network_switch_port, network_mgmt_switch_port, network_cross_connect.
   gui_crm_service_pages + gui_panel_definition seed'i ve idempotent migration.
4. Altyapı sorgusu: DC bazlı switch cihaz ve port sayısı (NetBox + Zabbix interface).
   loki_id join'inde numeric_loki_id_predicate() kullan.
5. inventory_overview_service.py'de yeni "network" ailesini üret; crm_inventory_report.py'de
   accordion grubu ve kolon setini ekle (birim: Adet, Used = kullanılan port).
6. Performans: yeni satırların inventory-overview süresine etkisini önce/sonra ölç ve raporla.
7. tests/: switch sayımı ve panel üretimi için unit test.

Kısıt: TASK-01 (cache) tamamlanmadan prod'a alınmayacak - bunu commit mesajında belirt.
```
