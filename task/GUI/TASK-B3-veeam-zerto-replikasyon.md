# TASK-B3 — Veeam / Zerto Replikasyonunun CRM ile Eşleştirilmesi

**Tip:** Hesaplama / Feature · **Efor:** L · **Öncelik:** YÜKSEK
**Karar:** [K-02](KARARLAR.md#k-02--veeamzerto-replikasyon-hi̇bri̇t-yöntem) — hibrit yöntem
**Durum (2026-07-31):** `feature/backup-ia-veeam-split` — Backup IA Image|Application|Veeam|Zerto; Veeam session_type YAML; HC Nutanix ∩ vendor; virt sold exclusion + Customer Role badge; CRM classic/HC remap (035); Zerto DS + site context. Altra CRM SKU + license feed + Mapping Save hâlâ açık.

---

## 1. Veeam ile Zerto arasındaki fark (referans)

|  | **Veeam** | **Zerto** |
|---|---|---|
| Ne yapar | **Hem yedekleme hem replikasyon** | **Sadece replikasyon / DR** |
| Teknoloji | Snapshot bazlı, periyodik (job schedule) | Journal bazlı, **sürekli (CDP)** — sıfıra yakın RPO |
| Birim | Job / Session / Repository | **VPG** (Virtual Protection Group) |
| Hedefte ne durur | Backup → repository'de dosya<br>Replica → **çalışmaya hazır VM** | **Çalışmaya hazır VM + journal** |
| Ayırt edici kolon | **`type`** = `VSphereReplica` \| `Backup` \| … | yok — hepsi replikasyon |
| VM sayısı | `objects_count` | **`vmscount`** |

> **Tek cümle:** Veeam'de replikasyon mu yedekleme mi olduğunu `raw_veeam_jobs_states.type`
> söyler; Zerto'da böyle bir soru yoktur — VPG demek replikasyon demektir.

### Datalake tabloları ve kolonları (doğrulandı)

```sql
-- raw_veeam_jobs_states (VEEAM_UNIQUE_JOBS_LATEST)
collection_time, id, name, type, status, last_result, last_run,
objects_count, session_id, workload, source_ip
--                                    ^^^^^^^^^  ← IP eşleşmesi için değerli (TASK-M1)

-- raw_zerto_vpg_metrics (ZERTO_UNIQUE_VPGS_LATEST)
collection_timestamp, id, name, status, vmscount, source_site, target_site,
provisioned_storage_mb, used_storage_mb, zerto_host

-- Diğer: raw_veeam_sessions, raw_veeam_repositories_states,
--        raw_zerto_site_metrics, raw_zerto_license_metrics
```

### CRM tarafı — ne satıyoruz

**Veeam** (hem backup hem replikasyon SKU'su var):

| SKU | Ürün | Birim |
|---|---|---|
| 000BLT-150 | Klasik Mimari Veeam Replication **vCpu** | vCPU |
| 000BLT-149 | Klasik Mimari Veeam Replication **RAM** | GB |
| 000BLT-146 / 182 | Klasik Mimari Veeam Replication **Disk** (NVMe / SSD) | GB |
| 000BLT-163 | Hyperconverged Veeam Replication vCpu | vCPU |
| 000BLT-162 | Hyperconverged Veeam Replication RAM | GB |
| 000BLT-160 / 161 | Hyperconverged Veeam Replication Disk (SSD / SSD Hybrid) | GB |
| 000BLT-144 / 145 | Veeam Cloud Connect **Backup** Lisansı | per VM |
| 000BLT-147 / 148 | Veeam Cloud Connect **Replication** Lisansı | per VM |
| 000BLT-71 | Offsite Backup Disk Alanı (Veeam) | GB |
| 000BLT-151 | Veeam Replikasyon Yönetim Hizmeti | Adet |

**Zerto** (yalnızca replikasyon):

| SKU | Ürün | Birim |
|---|---|---|
| 000BLT-174 | Klasik Mimari Zerto Replication **vCpu** | vCPU |
| 000BLT-175 | Klasik Mimari Zerto Replication **RAM** | GB |
| 000BLT-176 / 181 | Klasik Mimari Zerto Replication **Disk** (NVMe / SSD) | GB |
| 000BLT-170 | Hyperconverged Zerto Replication vCpu | vCPU |
| 000BLT-171 | Hyperconverged Zerto Replication RAM | GB |
| 000BLT-172 / 173 | Hyperconverged Zerto Replication Disk | GB |
| 000BLT-169 | Zerto Enterprise Cloud Edition License | Adet |
| 000BLT-167 | Zerto Replikasyon Yönetim Hizmeti | Adet |

**Ürün adları hesabı tarif ediyor:** birim vCPU / RAM GB / Disk GB — **depolama değil, replika
VM'in tükettiği kaynak**. Mantığı doğru: DR sitesinde o VM için gerçekten CPU/RAM/disk ayrılıyor.

Panel eşlemesi **zaten var** (`shared/sellable/panel_mapping.py`):
```python
backup_veeam_replication_cpu / _ram / _storage    ("Veeam Replication" + vCpu|RAM|Disk)
backup_zerto_replication_cpu / _ram / _storage    ("Zerto Replication" + vCpu|RAM|Disk)
backup_veeam_image                                 ("Veeam Cloud Connect Backup")
license_veeam / license_zerto / mgmt_replication_*
```

---

## 2. Blokaj: VM adı kırılımı toplanmıyor

> `raw_zerto_vpg_metrics` → `vmscount` **var**, VM adı listesi **yok**
> `raw_veeam_jobs_states` → `objects_count` **var**, VM adı listesi **yok**

Yani "bu replika VM Zerto'ya mı Veeam'e mi ait" sorusu **veriden doğrudan cevaplanamıyor**.
(Karşılaştırma: Nutanix snapshot tarafında `vm_names` toplanıyor — `shared/nutanix/snapshot_helpers.py`.)

**Karar (K-02):** Hibrit yöntemle ilerlenir; collector genişletmesi backlog'a alınır.

---

## 3. Hibrit yöntem — 4 adım

### Adım 1 · Replika VM havuzunu çıkar (isim deseni)

Desenler ve canlı sayılar (KB, 2026-07-16 · NetBox `discovery_netbox_virtualization_vm`):

| Desen | VM |
|---|---:|
| suffix `_DR` | 2.440 |
| embedded `-dr-` / `_dr_` | 696 |
| suffix `_replica` | 360 |
| suffix `_DRC` | 219 |
| contains `replica` / `replika` | 25 |
| **toplam** | **~3.740** |
| (ayrıca `silinecek` → hariç) | 2.953 |

> **Zorunlu:** NetBox'ta `lower(name)` bazında 19.479 duplike satır var.
> Her join öncesi `DISTINCT ON (lower(name))` uygulanmalı.

### Adım 2 · Vendor atamasını mutabakatla yap

```
Zerto replika VM sayısı ≈ SUM(raw_zerto_vpg_metrics.vmscount)          [latest per VPG]
Veeam replika VM sayısı ≈ SUM(raw_veeam_jobs_states.objects_count)     [type='VSphereReplica']
                                                                        [latest per job]
Toplam ≈ Adım 1'deki isim havuzu
```
Fark = **kaçak veya çift sayım** → ayrı rapor. Sessizce yutulmayacak.

Ek sinyal: `zerto_host` / `source_site` / `target_site` DC bilgisi taşıyor; Veeam'de `source_ip`
üzerinden DC çözülebiliyor. DC kırılımında vendor ataması bu sayede daha güvenilir.

### Adım 3 · Müşteri kırılımı

Mevcut `gui_crm_customer_source_mapping` `virtualization` kuralları **zaten çalışıyor** —
`_DR` son eki müşteri prefix'ini bozmuyor (`boyner-app-01_DR` hâlâ `boyner` prefix'i taşır).
Ek kural gerekmiyor; TASK-15'in butonu kalan boşlukları kapatır.

### Adım 4 · Kaynak toplamı

Replika VM'lerin `vm_metrics` (Klasik) / `nutanix_vm_metrics` (HC) satırlarından:
CPU (`number_of_cpus` / `cpu_count`), RAM, Disk.
Mimari ayrımı: `cluster ILIKE '%KM%'` → Klasik, aksi → Hyperconverged
(CRM SKU'ları da Klasik/Hyperconverged olarak ayrılmış — birebir örtüşüyor).

---

## 4. ⚠️ Beş uyarı (hesap yapmadan önce oku)

1. **Çift faturalama riski — en kritik.** Bir `_DR` VM hem `virt_classic_cpu` hem
   `backup_zerto_replication_cpu` olarak sayılırsa müşteri **iki kez** ödüyor.
   Registry `000BLT-47/53/51` için `family: backup_replication` diyor ve KB
   *"Classify via global VM name patterns **before** virt billable"* notunu koymuş.
   **Bunun gerçekten uygulandığı doğrulanmalı** (aşağıda SQL var).

2. **Zerto `provisioned_storage_mb` ≠ VM disk toplamı.** Zerto provisioned = hedef disk **+ journal**.
   Journal tipik olarak %7–20 ek yer kaplar. → **Açık soru A-01.**

3. **Nutanix RF2.** `nutanix_vm_metrics` ham disk kapasitesi replikasyon faktörü nedeniyle
   fiziksel tüketimin ~2 katı. `task/query-map/02-nutanix.md` "storage /2" diyor —
   replikasyon hesabında bu bölme **iki kez uygulanmamalı**.

4. **`silinecek` VM'ler.** Adında `silinecek` geçen 2.953 VM tüm billable toplamlardan
   **önce** çıkarılmalı, ayrı iç rapora gitmeli.

5. **Veeam replica vs Veeam backup karışması.** `type='VSphereReplica'` filtresi konmazsa
   backup job'ları replikasyon sayılır. `backup_veeam_image` (000BLT-144/145, Cloud Connect Backup)
   ayrı bir paneldir, replikasyonla toplanmamalı.

---

## 5. Doğrulama SQL'leri

```sql
-- 1) Replika VM havuzu — VMware (dedup edilmiş NetBox ile)
WITH nb AS (
  SELECT DISTINCT ON (lower(name)) name
  FROM   public.discovery_netbox_virtualization_vm
  WHERE  name IS NOT NULL
  ORDER  BY lower(name)
)
SELECT CASE
         WHEN name ~* 'silinecek'                THEN 'silinecek'
         WHEN name ~* '_DRC$'                    THEN 'suffix_DRC'
         WHEN name ~* '_DR$'                     THEN 'suffix_DR'
         WHEN name ~* '_replica$|_replika$'      THEN 'suffix_replica'
         WHEN name ~* '[-_]dr[-_]'               THEN 'embedded_dr'
         WHEN name ~* 'replica|replika'          THEN 'contains_replica'
         ELSE 'billable'
       END AS bucket,
       COUNT(*) AS vm
FROM   nb GROUP BY 1 ORDER BY 2 DESC;

-- 2) Zerto: VPG'ler ve korunan VM sayısı (latest per VPG)
WITH latest AS (
  SELECT DISTINCT ON (id) id, name, status, vmscount, source_site, target_site,
         provisioned_storage_mb, used_storage_mb, zerto_host, collection_timestamp
  FROM   public.raw_zerto_vpg_metrics
  WHERE  collection_timestamp > now() - interval '7 days'
  ORDER  BY id, collection_timestamp DESC
)
SELECT COUNT(*) AS vpg, SUM(vmscount) AS zerto_korunan_vm,
       ROUND(SUM(provisioned_storage_mb)/1024.0, 1) AS provisioned_gb,
       ROUND(SUM(used_storage_mb)/1024.0, 1)        AS used_gb,
       MAX(collection_timestamp) AS son_veri
FROM   latest;

-- 3) Veeam: replikasyon job'ları (type filtresi ŞART)
WITH latest AS (
  SELECT DISTINCT ON (id) id, name, type, status, last_result, objects_count,
         workload, source_ip, collection_time
  FROM   public.raw_veeam_jobs_states
  WHERE  collection_time > now() - interval '7 days'
  ORDER  BY id, collection_time DESC
)
SELECT type, COUNT(*) AS job, SUM(objects_count) AS nesne
FROM   latest GROUP BY 1 ORDER BY 2 DESC;
-- ⇒ type='VSphereReplica' satırı = Veeam replika VM sayısı

-- 4) MUTABAKAT: isim havuzu vs vendor sayaçları
--    (1)'deki DR bucket toplamı  ≈  (2) zerto_korunan_vm + (3) VSphereReplica nesne
--    Fark raporlanacak.

-- 5) ÇİFT FATURALAMA KONTROLÜ — en kritik sorgu
--    Bir _DR VM hem virt hem replikasyon toplamında mı?
SELECT COUNT(DISTINCT vmname) AS dr_vm_metrikte_var,
       SUM(number_of_cpus)    AS dr_vcpu,
       ROUND(SUM(total_memory_capacity_gb)::numeric, 1) AS dr_ram_gb,
       ROUND(SUM(provisioned_space_gb)::numeric/1024, 2) AS dr_disk_tb
FROM   public.vm_metrics
WHERE  "timestamp" > now() - interval '1 day'
  AND  LEFT(vmname,1) <> '_'
  AND  vmname !~* 'silinecek'
  AND  (vmname ~* '_DR$|_DRC$|_replica$|_replika$|[-_]dr[-_]|replica|replika');
-- ⇒ Bu sayılar virt_classic sellable toplamının İÇİNDE mi? İçindeyse çift sayım var.

-- 6) CRM tarafı: replikasyon SKU'ları ne kadar satılmış
SELECT p.productnumber, p.name, d.uomid_name,
       SUM(d.quantity) AS miktar, SUM(d.extendedamount) AS tl,
       COUNT(DISTINCT so.customerid) AS musteri
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
JOIN   discovery_crm_products    p  ON p.productid     = d.productid
WHERE  so.statecode = 0
  AND  (p.name ILIKE '%Veeam Replication%' OR p.name ILIKE '%Zerto Replication%')
GROUP  BY 1,2,3 ORDER BY 1;
-- ⇒ (5)'teki altyapı toplamı ile karşılaştır: satılan ≈ kullanılan mı?

-- 7) Nutanix HC tarafı için aynı havuz
SELECT COUNT(DISTINCT vm_name) AS dr_vm,
       SUM(cpu_count) AS vcpu,
       ROUND(SUM(memory_capacity)/1024.0^3, 1) AS ram_gb,
       ROUND(SUM(disk_capacity)/1024.0^4, 2)   AS disk_tib_ham
FROM   public.nutanix_vm_metrics
WHERE  collection_time > now() - interval '1 day'
  AND  LEFT(vm_name,1) <> '_' AND vm_name !~* 'silinecek'
  AND  (vm_name ~* '_DR$|_DRC$|_replica$|_replika$|[-_]dr[-_]|replica|replika');
-- ⚠️ disk_tib_ham RF2 içerir — /2 kuralını tam BİR kez uygula
```

## Kabul kriterleri
- [ ] Replika VM havuzu dedup edilmiş NetBox üzerinden çıkarılmış, `silinecek` hariç
- [ ] Vendor mutabakatı yapılmış; isim havuzu ile vendor sayaçları arasındaki fark **raporlanmış**
- [ ] **Çift faturalama kontrolü yapılmış**: replika VM'ler billable virt toplamında değil
- [ ] Klasik / Hyperconverged ayrımı CRM SKU'larıyla örtüşüyor
- [ ] Nutanix RF2 bölmesi tam bir kez uygulanmış
- [ ] `type='VSphereReplica'` filtresi uygulanmış; Veeam backup job'ları karışmıyor
- [ ] CRM satılan vs altyapı kullanılan karşılaştırma tablosu üretilmiş
- [ ] Inventory'de Veeam/Zerto replikasyon aileleri CPU/RAM/Disk satırlarıyla görünüyor

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, task/GUI/KARARLAR.md (K-02),
task/query-map/{01-vmware.md,02-nutanix.md,06-backup-dr.md},
<repo-kök>/datalake-platform-knowledge-base/wiki/CRM-Inventory-Infra-Matching.md,
<repo-kök>/datalake-platform-knowledge-base/adrs/ADR-0025-policy-based-backup-replication-ui.md,
shared/sellable/panel_mapping.py, shared/matching/product_matching_registry.yaml,
services/datacenter-api/app/db/queries/backup.py, shared/backup/unique_jobs.py,
services/customer-api/app/services/inventory_overview_service.py

Görev: Veeam ve Zerto replikasyonunu CRM ile eşleştir (HİBRİT yöntem - K-02).

ADIM 1 - TEŞHİS (kod yazmadan, rapor üret):
  TASK-B3'teki 7 SQL'i çalıştır. Özellikle (5) çift faturalama kontrolünü öne çıkar:
  replika VM'ler bugün virt_classic / virt_hyperconverged sellable toplamının içinde mi?
  Bu sorunun cevabı EVET ise, diğer her şeyden önce onu düzelt.

ADIM 2 - REPLİKA HAVUZU:
  shared/ altında saf bir modül yaz (örn. shared/backup/replica_classifier.py):
  - is_replica(name) -> bool  (desenler: _DR$, _DRC$, _replica$, _replika$, [-_]dr[-_], replica|replika)
  - is_deleted(name) -> bool  ('silinecek', leading '_')
  Desenleri KODA GÖMME - config/replica_patterns.yaml'dan oku (ileride Settings UI ile düzenlenebilir).
  DB'siz, unit test edilebilir olsun.

ADIM 3 - VENDOR MUTABAKATI:
  Zerto: SUM(vmscount) latest-per-VPG.  Veeam: SUM(objects_count) WHERE type='VSphereReplica',
  latest-per-job. İsim havuzu ile karşılaştır, farkı reconciliation_gap olarak raporla.
  DC kırılımında zerto_host/source_site ve veeam source_ip kullan.

ADIM 4 - KAYNAK TOPLAMI VE PANELLER:
  Replika VM'lerin vm_metrics / nutanix_vm_metrics kaynaklarını topla.
  Klasik (cluster ILIKE '%KM%') / Hyperconverged ayrımı yap.
  Nutanix storage'da RF2 bölmesini TAM BİR KEZ uygula (query-map/02-nutanix.md).
  panel_mapping.py'de zaten tanımlı panel_key'leri kullan:
  backup_veeam_replication_cpu/_ram/_storage, backup_zerto_replication_cpu/_ram/_storage.
  Yeni panel_key icat etme.

ADIM 5 - ÇİFT SAYIM ENGELİ:
  Replika VM'ler billable virt toplamından DÜŞÜLMELİ. Bunu tek bir yerde, sınıflandırma
  aşamasında yap (KB: "classify before virt billable"). Her tüketicide ayrı filtre yazma.

Kısıt:
- NetBox join'lerinde DISTINCT ON (lower(name)) zorunlu (19.479 duplike ad var).
- Zerto provisioned_storage_mb journal içeriyor olabilir (açık soru A-01) - kullanmadan önce
  bunu koda yorum olarak yaz ve karar bekle; şimdilik VM disk toplamını kullan.
- tests/: replica_classifier için desen testleri, mutabakat hesabı, RF2 tek-kez kuralı.
```

## Backlog (K-02 gereği)
**Collector genişletmesi:** Zerto VPG `protectedVms` ve Veeam job objects listesinin datalake'e
çekilmesi (`project-zabake` collector + NiFi deploy). Geldiğinde Adım 3'teki mutabakat yerine
kesin vendor ataması yapılır. Tahmini 1–2 hafta.
