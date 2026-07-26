# TASK-B1 — NetBackup Faturalama Tabanı: Pre-dedup mu Post-dedup mu?

**Tip:** Analiz (kod yok) · **Efor:** S · **Öncelik:** ÇOK YÜKSEK (B2/B4'ü blokluyor)
**Karar:** [K-01](KARARLAR.md#k-01--netbackup-faturalama-tabanı-önce-mutabakat)

## Neden kritik
Pre-dedup ile post-dedup arasında **3–10× fark** olabilir. Yanlış taban seçilirse tüm NetBackup
faturalandırması ve satılabilir alan hesabı yanlış çıkar.

| Taban | Anlamı | Nereden |
|---|---|---|
| **Pre-dedup** | Müşterinin yedeklediği ham veri | `SUM(kilobytestransferred)` |
| **Post-dedup** | Bizim gerçekten harcadığımız disk | `SUM(kilobytestransferred / NULLIF(dedupratio,0))` |

Customer View ikisini de hesaplıyor (`netbackup_pre_dedup_gib`, `netbackup_post_dedup_gib`
— `src/pages/customer_view.py` ~1046, ~2757), ama **hangisinin fatura tabanı olduğu yazılı değil**.

İlgili CRM kalemleri:

| SKU | Ürün | Birim |
|---|---|---|
| `000BLT-203` | Klasik Mimari İmaj Yedekleme (Veritas Netbackup) | GB |
| `000BLT-142` | Uygulama Yedekleme Hizmeti (Veritas NetBackup) | GB |

Panel eşlemesi zaten var: `shared/sellable/panel_mapping.py` → `backup_netbackup_storage`
(kural: isimde "Veritas" veya "NetBackup").
Politika kırılımı: `shared/backup/policy_panel_mapping.yaml` — `VMWARE` → image, diğerleri → application.

## Yöntem: üç yönlü mutabakat

```
(A) CRM satılan GB     ← discovery_crm_salesorderdetails (000BLT-203 + 000BLT-142)
(B) Pre-dedup GB       ← raw_netbackup_jobs_metrics.kilobytestransferred
(C) Post-dedup GB      ← (B) / dedupratio
(D) Fiziksel disk GB   ← raw_netbackup_disk_pools_metrics.usedcapacitybytes
```

**Beklenti:** `(C) ≈ (D)` olmalı (post-dedup = gerçek disk tüketimi). Değilse hesap yanlıştır.
Sonra `(A)`'nın `(B)`'ye mi `(C)`'ye mi yakın olduğuna bakılır → **taban budur**.

## Doğrulama SQL'leri

```sql
-- (A) CRM'de satılan NetBackup GB — toplam ve müşteri kırılımı
SELECT p.productnumber, p.name, d.uomid_name,
       SUM(d.quantity)        AS satilan_gb,
       SUM(d.extendedamount)  AS toplam_tl,
       COUNT(DISTINCT so.customerid) AS musteri,
       ROUND(SUM(d.extendedamount)/NULLIF(SUM(d.quantity),0), 4) AS tl_per_gb
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
JOIN   discovery_crm_products    p  ON p.productid     = d.productid
WHERE  so.statecode = 0
  AND  p.productnumber IN ('000BLT-203','000BLT-142')
GROUP  BY 1,2,3 ORDER BY 1;

-- (B) + (C) Pre / post dedup — son 30 gün, politika kategorisi kırılımlı
SELECT CASE WHEN upper(COALESCE(policytype,'')) = 'VMWARE' THEN 'image' ELSE 'application' END AS kategori,
       COUNT(*)                                                        AS job,
       ROUND(SUM(kilobytestransferred)/1024.0/1024.0, 1)               AS pre_dedup_gb,
       ROUND(SUM(kilobytestransferred / NULLIF(dedupratio,0))/1024.0/1024.0, 1) AS post_dedup_gb,
       ROUND(AVG(NULLIF(dedupratio,0))::numeric, 2)                    AS ort_dedup_orani
FROM   public.raw_netbackup_jobs_metrics
WHERE  starttime > now() - interval '30 days'
  AND  jobtype = 'BACKUP'
GROUP  BY 1;

-- (D) Fiziksel disk tüketimi — latest snapshot per volume
WITH latest AS (
  SELECT DISTINCT ON (netbackup_host, name, diskvolumes_name)
         netbackup_host, name, diskvolumes_name,
         usablesizebytes, usedcapacitybytes, availablespacebytes
  FROM   public.raw_netbackup_disk_pools_metrics
  ORDER  BY netbackup_host, name, diskvolumes_name, collection_timestamp DESC
)
SELECT ROUND(SUM(usablesizebytes)  /1024.0^3, 1) AS toplam_gb,
       ROUND(SUM(usedcapacitybytes)/1024.0^3, 1) AS kullanilan_gb,
       ROUND(SUM(availablespacebytes)/1024.0^3, 1) AS bos_gb,
       COUNT(*) AS volume
FROM   latest;
-- ⇒ kullanilan_gb ile (C) post_dedup_gb karşılaştırılır

-- (E) Müşteri bazlı karşılaştırma (en açıklayıcı olan)
SELECT workloaddisplayname,
       ROUND(SUM(kilobytestransferred)/1024.0/1024.0, 1)               AS pre_gb,
       ROUND(SUM(kilobytestransferred / NULLIF(dedupratio,0))/1024.0/1024.0, 1) AS post_gb,
       COUNT(*) AS job, MAX(starttime) AS son_job
FROM   public.raw_netbackup_jobs_metrics
WHERE  starttime > now() - interval '30 days' AND jobtype = 'BACKUP'
GROUP  BY 1 ORDER BY pre_gb DESC LIMIT 50;
-- ⇒ TASK-16 prefix eşleşmesi geldikten sonra bu müşteriye bağlanıp (A) ile satır satır karşılaştırılır

-- (F) Dedup oranı sağlıklı mı (0 veya NULL varsa hesap patlar)
SELECT COUNT(*) FILTER (WHERE dedupratio IS NULL) AS null_dedup,
       COUNT(*) FILTER (WHERE dedupratio = 0)     AS sifir_dedup,
       MIN(dedupratio), MAX(dedupratio), AVG(dedupratio)
FROM   public.raw_netbackup_jobs_metrics
WHERE  starttime > now() - interval '30 days' AND jobtype = 'BACKUP';
```

## Çıktı
`task/GUI/reports/netbackup-fatura-tabani-mutabakat.md`:
- (A)–(F) tablolarının sonuçları
- `(C) ≈ (D)` doğrulaması geçti mi
- **Öneri:** taban pre-dedup mi post-dedup mi, gerekçesiyle
- Müşteri bazlı en büyük 10 sapma

## Kabul kriterleri
- [ ] Beş sorgunun çıktısı raporda
- [ ] Post-dedup hesabı ile fiziksel disk tüketimi arasındaki fark ölçülmüş ve açıklanmış
- [ ] CRM satılan GB'nin hangi tabana yakın olduğu sayıyla gösterilmiş
- [ ] `dedupratio` veri kalitesi (NULL/0 oranı) raporlanmış
- [ ] Karar paydaşa sunulmuş ve KARARLAR.md K-01 güncellenmiş

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, task/GUI/KARARLAR.md,
task/query-map/06-backup-dr.md, shared/backup/policy_classification.py,
shared/backup/policy_panel_mapping.yaml, src/pages/customer_view.py (netbackup_pre/post_dedup_gib)

Görev: NetBackup faturalama tabanının pre-dedup mu post-dedup mu olduğunu MUTABAKATLA tespit et.
KOD DEĞİŞİKLİĞİ YAPMA — sadece analiz raporu.

scripts/reconcile_netbackup_billing_basis.py:
1. TASK-B1'deki (A)-(F) sorgularını çalıştır.
2. Kritik doğrulama: post-dedup hesabı ile raw_netbackup_disk_pools_metrics'teki gerçek
   kullanılan disk yakın mı? Değilse hesabın kendisi hatalıdır - bunu önce raporla.
3. CRM satılan GB'yi (A) her iki tabanla karşılaştır, yüzde farkı ver.
4. dedupratio veri kalitesini kontrol et (NULL/0 satırlar hesabı bozar).
5. policytype kırılımını image/application olarak ayır (policy_panel_mapping.yaml kullan,
   kendi listeni yazma).

Çıktı: task/GUI/reports/netbackup-fatura-tabani-mutabakat.md
Rapor sonunda net bir öneri ve gerekçe olsun. Emin değilsen "belirsiz" de, uydurma.
```
