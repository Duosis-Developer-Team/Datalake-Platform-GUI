# TASK-B4 — Nutanix Backup'ın CRM ile Eşleştirilmesi

**Tip:** Hesaplama / Feature · **Efor:** M · **Öncelik:** Orta-Yüksek

## Hedef
Nutanix (Hyperconverged) yedeklerinin CRM hizmet kalemleriyle eşleştirilmesi.

## CRM kalemleri

| SKU | Ürün | Birim | Registry |
|---|---|---|---|
| `000BLT-45` | Hyperconverged İmaj Yedekleme Hizmeti | GB | ✅ `family: backup_nutanix` |
| `000BLT-221` | Remote Backup Hizmeti (Nutanix) | GB | ❌ yok |

Panel eşlemesi (`shared/sellable/panel_mapping.py`) **zaten var**:
```python
backup_image_hyperconverged   ("Hyperconverged" + "İmaj Yedekleme")
backup_remote_nutanix         ("Remote Backup" + "Nutanix")
```

> **Açık soru A-03:** İkisi ayrı ayrı mı hesaplanacak? "İmaj Yedekleme" lokal snapshot,
> "Remote Backup" uzak siteye replikasyon gibi duruyor — ama teyit gerekiyor.

## Altyapı tarafı

| Kaynak | Tablo | Not |
|---|---|---|
| Snapshot programı | `nutanix_snapshot_schedule`, `nutanix_snapshot_schedule_metrics` | registry `infra_tables` |
| Yardımcılar | `shared/nutanix/snapshot_helpers.py` | **saf fonksiyon, DB'siz, test edilebilir** |
| Sorgular | `services/datacenter-api/app/db/queries/nutanix_snapshot.py` | `SNAPSHOTS_BY_IPS_LATEST`, `SNAPSHOTS_BY_CUSTOMER_LATEST` |
| Endpoint'ler | `/datacenters/{dc}/backup/nutanix`, `/backup/nutanix/table`, `/backup/nutanix/missing`, `/backup/nutanix/refresh`, `/customers/{c}/backup/nutanix` | ✅ hazır |

`snapshot_helpers.py` neler yapıyor:
- `parse_customer(protection_domain_name, vm_names)` — ilk `-` öncesi token = müşteri
  (jenerik programlar `1Days_10RP`, `2Hours-360RP` elenir)
- `parse_retention(schedule_local_max_snapshots, protection_domain_name)` — `1Day_7RP` → 7
- **`vm_names` kolonu VAR** ← Veeam/Zerto'da olmayan avantaj (bkz. TASK-B3 blokajı)

## Registry'deki formül ve şüphem

```yaml
"000BLT-45":
  matching_rule: Nutanix Backup imaj policy x gün x total hyperconverged disk
```

Bu formül **"satılan GB"yi türetiyor**, gerçek snapshot tüketimini değil. İkisi çok farklı olabilir:
- Formül: `retention (RP) × korunan disk` → teorik üst sınır
- Gerçek: snapshot'ların fiili disk tüketimi (delta bazlı, çok daha küçük)

**Bu doğrulanmalı** — TASK-B1'deki pre/post dedup sorusunun Nutanix karşılığı.

## Yapılacaklar

- [ ] **Formül doğrulaması:** `retention × disk` hesabı ile gerçek snapshot tüketimini karşılaştır;
      CRM satılan GB hangisine yakın?
- [ ] `000BLT-221` (Remote Backup) registry'ye ekle
- [ ] A-03 kararı: iki SKU ayrı panel mi, tek panel mi
- [ ] `gui_panel_definition` kayıtları: `backup_image_hyperconverged`, `backup_remote_nutanix`
- [ ] **DC compute endpoint'i** (TASK-B2 ile aynı desen):
      `GET /datacenters/{dc}/compute/backup-nutanix` → `stor_cap`, `stor_provisioned_gb`
- [ ] `_FAMILY_COMPUTE_ENDPOINT`'e `"backup_nutanix": "backup-nutanix"` ekle
- [ ] **`vm_names` avantajını kullan:** korunan VM listesi mevcut → müşteri eşleşmesi
      `parse_customer` yerine/yanında `gui_crm_customer_source_mapping` `virtualization`
      kurallarıyla da yapılabilir (daha tutarlı olur)
- [ ] "Missing entities" (müşterisi çözülemeyen protection domain) raporunu
      TASK-15'in alias düzeltme akışına bağla
- [ ] DC View Backup sekmesinde Nutanix satılabilir alan kartı

## Doğrulama SQL'leri

```sql
-- 1) Snapshot programları ve retention dağılımı
SELECT protection_domain_name, schedule_local_max_snapshots, vm_names,
       collection_time
FROM   public.nutanix_snapshot_schedule_metrics
WHERE  collection_time > now() - interval '2 days'
ORDER  BY protection_domain_name LIMIT 100;
-- ⇒ önce information_schema ile kolon adlarını doğrula

-- 2) Müşterisi çözülemeyen protection domain'ler ("Missing Entities")
SELECT protection_domain_name, COUNT(*) 
FROM   public.nutanix_snapshot_schedule_metrics
WHERE  collection_time > now() - interval '2 days'
  AND  protection_domain_name !~ '-'          -- '-' yoksa müşteri parse edilemiyor
GROUP  BY 1 ORDER BY 2 DESC;

-- 3) Korunan HC disk toplamı (formülün "total hyperconverged disk" bileşeni)
SELECT COUNT(DISTINCT vm_name) AS vm,
       ROUND(SUM(disk_capacity)/1024.0^4, 2) AS disk_tib_ham
FROM   public.nutanix_vm_metrics
WHERE  collection_time > now() - interval '1 day'
  AND  LEFT(vm_name,1) <> '_' AND vm_name !~* 'silinecek';
-- ⚠️ RF2: fiziksel tüketim için /2 (query-map/02-nutanix.md) — tam bir kez uygula

-- 4) CRM'de satılan Nutanix backup GB
SELECT p.productnumber, p.name, d.uomid_name,
       SUM(d.quantity) AS satilan_gb, SUM(d.extendedamount) AS tl,
       COUNT(DISTINCT so.customerid) AS musteri
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
JOIN   discovery_crm_products    p  ON p.productid     = d.productid
WHERE  so.statecode = 0 AND p.productnumber IN ('000BLT-45','000BLT-221')
GROUP  BY 1,2,3;

-- 5) Formül vs gerçek: retention x disk hesabı
--    (Python tarafında snapshot_helpers.parse_retention ile — SQL'de regex tekrarlamayın)
```

```bash
curl -s "http://10.134.52.250:8000/api/v1/datacenters/DC13/backup/nutanix" | python3 -m json.tool | head -40
curl -s "http://10.134.52.250:8000/api/v1/datacenters/DC13/backup/nutanix/missing" | python3 -m json.tool | head -30
```

## Kabul kriterleri
- [ ] `retention × disk` formülü ile gerçek tüketim karşılaştırılmış, CRM'e hangisinin yakın olduğu gösterilmiş
- [ ] `000BLT-221` registry + panel tanımında
- [ ] DC View'da Nutanix backup satılabilir alan kartı görünüyor
- [ ] RF2 bölmesi tam bir kez uygulanmış
- [ ] "Missing entities" listesi üretiliyor ve alias akışına bağlı
- [ ] `vm_names` üzerinden müşteri eşleşmesi `virtualization` kurallarıyla tutarlı

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, task/GUI/KARARLAR.md,
task/GUI/TASK-B2-netbackup-dcview-sellable.md (aynı desen),
task/query-map/{02-nutanix.md,06-backup-dr.md},
shared/nutanix/snapshot_helpers.py, shared/sellable/panel_mapping.py,
shared/matching/product_matching_registry.yaml,
services/datacenter-api/app/db/queries/nutanix_snapshot.py,
services/customer-api/app/services/sellable_service.py (_FAMILY_COMPUTE_ENDPOINT)

Görev: Nutanix backup'ı CRM ile eşleştir ve DC View'da satılabilir alan olarak göster.

ADIM 1 - FORMÜL DOĞRULAMASI (kod yazmadan):
  Registry "Nutanix Backup imaj policy x gün x total hyperconverged disk" diyor.
  Bu teorik hesabı gerçek snapshot tüketimiyle karşılaştır. CRM satılan GB (000BLT-45)
  hangisine yakın? TASK-B1'in Nutanix karşılığı - önce bunu raporla.

ADIM 2:
  000BLT-221 (Remote Backup Nutanix) registry'ye ekle.
  A-03 kararına göre 000BLT-45 ile ayrı mı tek mi panel - karar verilmemişse AYRI panel varsay
  ve bunu kodda yorumla belirt.

ADIM 3:
  GET /api/v1/datacenters/{dc}/compute/backup-nutanix ekle - TASK-B2'deki
  /compute/backup-netbackup ile AYNI cevap sözleşmesi (stor_cap, stor_provisioned_gb, stor_pct).
  sellable_service.py _FAMILY_COMPUTE_ENDPOINT'e "backup_nutanix": "backup-nutanix" ekle.

ADIM 4:
  Müşteri eşleşmesinde snapshot_helpers.parse_customer YANINDA vm_names üzerinden
  gui_crm_customer_source_mapping virtualization kurallarını da uygula ve iki sonucu karşılaştır.
  Uyuşmazlıkları "Missing Entities" raporuna ekle.

ADIM 5:
  dc_view.py Backup sekmesine Nutanix sellable kartı. Veri yoksa render etme.

Kısıt:
- Nutanix storage RF2 bölmesi TAM BİR KEZ (query-map/02-nutanix.md). İki kez uygulanırsa
  değerler yarıya iner - regresyon testi yaz.
- snapshot_helpers.py saf fonksiyon kalsın, DB erişimi ekleme.
- tests/: formül hesabı, RF2 tek-kez kuralı, müşteri eşleşme karşılaştırması.
```
