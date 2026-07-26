# TASK-04 — Hyperconverged Mantık Hatasının Düzeltilmesi (unit / unit price)

**Tip:** Hesaplama · **Efor:** M · **Öncelik:** Yüksek

## Hedef
Hyperconverged altındaki ürünlerde **unit** (birim) ve **unit price** (birim fiyat) kolonlarında mantık
hatası var. Tüm kalemler yeniden düzenlenecek.

## Mevcut durum — birim/fiyat mantığı nerede

### Birim (unit) çözümlemesi
Üç ayrı kaynak var, önceliği karıştırmak kolay (`docs/CRM_SERVICE_MAPPING.md`):

| Kaynak | Anlamı |
|---|---|
| `gui_crm_service_pages.resource_unit` | `page_key` için **varsayılan** etiket (örn. `virt_classic` → vCPU) |
| `v_gui_crm_product_mapping.resource_unit` | Bilinçli olarak **NULL** — join'lerin `salesorderdetails.uomid_name`'i tercih etmesi için |
| `discovery_crm_salesorderdetails.uomid_name` | **Satır bazlı gerçek birim** (vCPU / GB / TB / Adet …) |

### Fiyat (unit price) çözümlemesi
`src/components/crm_inventory_report.py`:
```python
_crm_sold_unit_price(row)     # ~204: crm_sold_tl / crm_sold_qty  (satıştan ima edilen fiyat)
_effective_unit_price(row, is_physical)  # ~220: physical ailelerde ima edilen fiyat,
                                         #       aksi halde row["unit_price_tl"] (katalog)
_fmt_unit_price(value, unit)  # ~235: "N TL/{unit}"
```
Backend'de: `gui_crm_price_override` (operatör) → `discovery_crm_productpricelevels` (katalog) sırası
(bkz. `services/datacenter-api/app/db/queries/crm_network_pricing.py` aynı deseni kullanıyor).

### Hyperconverged'e özel davranış
```python
# inventory_overview_service.py
_HOST_DUAL_FAMILIES  = {"virt_classic", "virt_hyperconverged"}   # dual-track sellable
_PHYSICAL_FREE_FAMILIES = {"storage_s3", "backup_netbackup"}     # HC bunda YOK
# crm_inventory_report.py
_INVENTORY_VIRT_FAMILIES = {"virt_classic","virt_hyperconverged","virt_power","virt_power_hana"}
```

HC ürünleri (`shared/matching/product_matching_registry.yaml`):

| SKU | Ürün | panel_key | infra tabloları |
|---|---|---|---|
| 000BLT-46 | Hyperconverged Mimari Intel CPU | `virt_hyperconverged_cpu` | `nutanix_vm_metrics`, `cluster_metrics` |
| 000BLT-52 | Hyperconverged Mimari Intel RAM | `virt_hyperconverged_ram` | `nutanix_vm_metrics`, `cluster_metrics` |
| 000BLT-48 | HC Intel Disk - SSD | `virt_hyperconverged_storage` | `nutanix_vm_metrics` |
| 000BLT-50 | HC Intel Disk - SSD Hybrid | `virt_hyperconverged_storage` | `nutanix_vm_metrics` |
| 000BLT-47/53/51 | DR varyantları | — | `family: backup_replication` (billable virt DEĞİL) |
| 000BLT-45 | HC İmaj Yedekleme | — | `family: backup_nutanix` |

## Şüpheli hata kaynakları (öncelik sırasıyla)

1. **İki disk SKU'su tek panel'e düşüyor** (`000BLT-48` + `000BLT-50` → `virt_hyperconverged_storage`).
   Farklı birim fiyatlı iki ürünün miktarı toplanıp tek "birim fiyat" gösteriliyorsa fiyat **anlamsız** olur
   (ağırlıklı ortalama gerekir).
2. **Birim karışımı:** CPU satırı vCPU, RAM/Disk satırı GB/TB. `uomid_name` GB iken panel varsayılanı TB ise
   1024× sapma oluşur → `gui_unit_conversion` (`GET/PUT /api/v1/crm/unit-conversions`) kontrol edilmeli.
3. **Nutanix storage /2 kuralı:** `task/query-map/02-nutanix.md`'de belirtilen replikasyon bölmesi
   HC toplamına uygulanmış mı? Uygulanmadıysa/iki kez uygulandıysa Free ve birim fiyat kayar.
4. **DR satırlarının sızması:** `000BLT-47/53/51` `backup_replication` ailesinde olmalı; HC billable'a
   karışıyorsa satılan miktar şişer, ima edilen birim fiyat düşer.
5. **`_effective_unit_price` yanlış dal:** HC `_PHYSICAL_FREE_FAMILIES`'te olmadığı için her zaman
   katalog `unit_price_tl` kullanıyor; ancak katalogda TL fiyatı boşsa (prod'da price-level'lar genelde boş)
   satır 0 TL veya boş görünür.

## Yapılacaklar

- [ ] HC ailesinin **tam kalem dökümünü** çıkar: SKU, `uomid_name`, satılan miktar, satılan TL, ima edilen fiyat,
      katalog fiyatı, override fiyatı → tek tablo
- [ ] Aynı panel'e düşen çok-SKU'lu satırlar için **miktar-ağırlıklı ortalama birim fiyat** uygula;
      UI'da tooltip ile "N ürünün ağırlıklı ortalaması" göster
- [ ] Birim dönüşüm zincirini tek yerde topla: satır birimi (`uomid_name`) → panel görüntü birimi
      (`display_unit`) dönüşümü eksikse satırı **"Unit conversion missing"** olarak işaretle
      (bu etiket kodda zaten var: `crm_inventory_report.py` ~284)
- [ ] DR SKU'larının HC billable'a karışmadığını doğrula
- [ ] Nutanix storage bölme kuralının tam olarak bir kez uygulandığını doğrula
- [ ] Katalog fiyatı boş olan HC SKU'ları için `gui_crm_price_override` girilmesi gerektiğini
      Settings ekranında uyarı olarak göster
- [ ] `shared/sellable/verify_units.py` içindeki birim doğrulamasını HC kalemleri için genişlet + unit test

## Doğrulama SQL'leri

```sql
-- 1) HC ürünlerinin gerçek satış birimleri ve ima edilen birim fiyatı
SELECT p.productnumber, p.name, d.uomid_name,
       SUM(d.quantity)                                   AS miktar,
       SUM(d.extendedamount)                             AS toplam_tl,
       ROUND(SUM(d.extendedamount)/NULLIF(SUM(d.quantity),0), 2) AS ima_edilen_birim_fiyat,
       MIN(d.priceperunit) AS min_satir_fiyat, MAX(d.priceperunit) AS max_satir_fiyat
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
JOIN   discovery_crm_products    p  ON p.productid     = d.productid
WHERE  so.statecode = 0
  AND  p.productnumber IN ('000BLT-46','000BLT-52','000BLT-48','000BLT-50','000BLT-47','000BLT-53','000BLT-51','000BLT-45')
GROUP BY 1,2,3 ORDER BY 1;
-- ⇒ min/max satır fiyatı çok farklıysa tek "birim fiyat" göstermek yanlıştır.

-- 2) Katalog fiyatı var mı (prod'da price-level genelde boş)
SELECT p.productnumber, p.name, ppl.amount, pl.transactioncurrency_text
FROM   discovery_crm_products p
LEFT JOIN discovery_crm_productpricelevels ppl ON ppl.productid = p.productid
LEFT JOIN discovery_crm_pricelevels        pl  ON pl.pricelevelid = ppl.pricelevelid
WHERE  p.productnumber IN ('000BLT-46','000BLT-52','000BLT-48','000BLT-50');

-- 3) Operatör override var mı (bulutwebui)
SELECT productid, product_name, unit_price_tl, resource_unit, currency, updated_at
FROM   gui_crm_price_override ORDER BY updated_at DESC;

-- 4) Birim dönüşüm tablosu (bulutwebui)
SELECT * FROM gui_unit_conversion ORDER BY 1,2;

-- 5) Altyapı tarafı: HC gerçek kapasite (Nutanix)
SELECT COUNT(DISTINCT vm_name) AS vm,
       SUM(cpu_count)          AS vcpu,
       ROUND(SUM(memory_capacity)/1024^3, 2) AS ram_gb,
       ROUND(SUM(disk_capacity) /1024^4, 2)  AS disk_tib
FROM   public.nutanix_vm_metrics
WHERE  collection_time > now() - interval '1 day'
  AND  vm_name NOT ILIKE '%silinecek%'
  AND  LEFT(vm_name,1) <> '_';
```

```bash
curl -s "http://10.134.52.250:8070/api/v1/crm/inventory-overview?dc_code=*" \
 | python3 -c "
import json,sys
d=json.load(sys.stdin)
for r in d.get('rows',[]):
    if 'hyperconv' in str(r.get('family_label','')+r.get('panel_key','')).lower():
        print(r.get('service_label'), '|', r.get('display_unit'), '|', r.get('crm_sold_fmt'), '|', r.get('unit_price_fmt'))
"
curl -s http://10.134.52.250:8070/api/v1/crm/unit-conversions | python3 -m json.tool
```

## Kabul kriterleri
- [ ] Her HC satırında `display_unit`, satılan miktarın gerçek `uomid_name`'i ile tutarlı
- [ ] Birim fiyat = miktar-ağırlıklı ortalama; tek SKU'lu satırlarda o SKU'nun fiyatına eşit
- [ ] Dönüşümü tanımsız satırlar "Unit conversion missing" olarak işaretli, sessizce 0 göstermiyor
- [ ] DR (`000BLT-47/53/51`) kalemleri HC billable toplamında **yok**
- [ ] Nutanix storage bölme kuralı tam olarak bir kez uygulanmış (SQL toplamı = UI toplamı)

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, docs/CRM_SERVICE_MAPPING.md,
task/query-map/02-nutanix.md, task/query-map/05-sellable-potential.md,
shared/matching/product_matching_registry.yaml, shared/sellable/verify_units.py,
src/components/crm_inventory_report.py, services/customer-api/app/services/inventory_overview_service.py

Görev: Hyperconverged ailesindeki unit ve unit price mantık hatasını düzelt.

1. Önce teşhis: TASK-04 dosyasındaki 5 doğrulama SQL'ini çalıştır ve sonucu raporla.
   Özellikle 000BLT-48 ve 000BLT-50'nin aynı panel_key'e (virt_hyperconverged_storage) düştüğünü
   ve satır fiyatlarının farklı olup olmadığını doğrula.
2. Birim fiyat hesabını düzelt: bir panel satırı birden fazla SKU'dan besleniyorsa
   miktar-ağırlıklı ortalama birim fiyat hesapla (SUM(extendedamount)/SUM(quantity) mantığı,
   ama panel display_unit'ine dönüştürülmüş miktarla). Tek SKU'da davranış değişmesin.
3. Birim dönüşümünü netleştir: satır birimi (uomid_name) -> panel display_unit dönüşümü
   gui_unit_conversion'ta tanımlı değilse satırı "Unit conversion missing" olarak işaretle,
   0 veya boş gösterme.
4. DR SKU'larının (000BLT-47/53/51) HC billable toplamına karışmadığını doğrula; karışıyorsa
   registry family'sine göre filtrele.
5. Nutanix storage replikasyon bölmesinin tam olarak bir kez uygulandığını doğrula.
6. shared/sellable/verify_units.py'yi HC kalemleri için genişlet; tests/ altında
   ağırlıklı ortalama ve eksik dönüşüm senaryoları için unit test yaz (TDD, önce test).

Kısıt: Klasik (virt_classic) ailesinin davranışı değişmemeli - regression testi ekle.
```
