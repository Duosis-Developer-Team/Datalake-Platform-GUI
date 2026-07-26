# TASK-16 — NetBackup Müşteri Prefixleri

**Tip:** Veri / Konfigürasyon · **Efor:** S · **Öncelik:** Orta-Yüksek

## Hedef
NetBackup'ta bulunan müşterilerin **prefix bilgileri** alınarak sisteme tanımlanacak.

## Mevcut durum

Eşleştirme altyapısı hazır:
- Tablo: `gui_crm_customer_source_mapping` (bulutwebui)
- `data_source = 'backup_netbackup'` **zaten destekleniyor**
- `match_method` seçenekleri: `exact`, `prefix`, `contains`, `suffix`, `id_exact`
- Çözümleyici: `services/customer-api/app/services/customer_mapping_resolver.py`
- Seed örneğinde varsayılan `contains`:
  ```python
  {"data_source":"backup_netbackup","match_method":"contains","match_value":"Boyner","priority":20}
  ```
- API: `PUT /api/v1/crm/aliases/{crm_accountid}/source-mappings`
- UI: Settings › Integrations › CRM aliases (`src/utils/crm_source_mapping_ui.py`,
  grup: `("backup","Backup & Replication",("backup_veeam","backup_zerto","backup_netbackup"))`)

**Yani bu madde çoğunlukla kod değil, veri/konfigürasyon işi.**
Yapılacak: NetBackup istemci/politika adlarındaki prefix desenlerini çıkarıp müşterilere bağlamak.

Kaynak kolonlar (`raw_netbackup_jobs_metrics`): `workloaddisplayname` (istemci/iş yükü adı),
`policytype`, `jobtype`, `destinationmediaservername`
(`raw_netbackup_disk_pools_metrics`: `netbackup_host`, `name`, `diskvolumes_name`)

## Yapılacaklar

- [ ] **Prefix keşfi:** NetBackup'taki tüm tekil `workloaddisplayname` değerlerini çıkar,
      ayırıcıya göre (`-`, `_`, `.`) ilk parçaları frekansa göre sırala
- [ ] Her prefix için CRM hesap adlarıyla bulanık eşleştirme yap (öneri listesi üret)
      — `shared/customer/match.py` ve `unmapped_classifier.py` içindeki mevcut bulanık eşleştirmeyi kullan
- [ ] Öneri listesini **insan onayından geçir** (otomatik yazma yok — yanlış eşleşme fatura hatasıdır)
- [ ] Onaylananları `gui_crm_customer_source_mapping`'e `match_method='prefix'` ile yaz
- [ ] `contains` ile tanımlı mevcut NetBackup kurallarını gözden geçir: prefix daha güvenliyse dönüştür
- [ ] Kapsama raporu: prefix'lerle eşleşen / eşleşmeyen NetBackup istemci oranı
- [ ] Eşleşmeyenleri "Eşleşmeyen Veriler" akışına dahil et (TASK-15'in butonuyla düzeltilebilsin)

## Doğrulama SQL'leri

```sql
-- 1) NetBackup istemci adları ve ayırıcı analizi
SELECT workloaddisplayname,
       split_part(workloaddisplayname,'-',1) AS tire_prefix,
       split_part(workloaddisplayname,'_',1) AS alt_cizgi_prefix,
       split_part(workloaddisplayname,'.',1) AS nokta_prefix,
       COUNT(*) AS job
FROM   public.raw_netbackup_jobs_metrics
WHERE  starttime > now() - interval '90 days' AND workloaddisplayname IS NOT NULL
GROUP  BY 1,2,3,4 ORDER BY job DESC LIMIT 200;

-- 2) Prefix frekans dağılımı (aday liste)
SELECT lower(split_part(workloaddisplayname,'-',1)) AS prefix,
       COUNT(DISTINCT workloaddisplayname) AS istemci,
       COUNT(*) AS job,
       ROUND(SUM(kilobytestransferred)/1024.0/1024.0, 1) AS gb
FROM   public.raw_netbackup_jobs_metrics
WHERE  starttime > now() - interval '90 days'
GROUP  BY 1 HAVING COUNT(DISTINCT workloaddisplayname) >= 2
ORDER  BY istemci DESC LIMIT 100;

-- 3) CRM hesap adları (eşleştirme hedefi)
SELECT DISTINCT name FROM public.discovery_crm_accounts
WHERE name IS NOT NULL AND btrim(name) <> '' ORDER BY 1;

-- 4) Mevcut NetBackup kuralları (bulutwebui)
SELECT crm_accountid, match_method, match_value, priority, enabled, source, updated_at
FROM   gui_crm_customer_source_mapping
WHERE  data_source = 'backup_netbackup' ORDER BY match_value;

-- 5) Kapsama: kaç istemci bir kurala düşüyor (kural listesi elde olduktan sonra)
--    Python tarafında hesaplanmalı (cross-DB JOIN yok) - resolver ile.

-- 6) Politika bazlı kırılım (image vs application - ADR-0025)
SELECT policytype, COUNT(DISTINCT workloaddisplayname) AS istemci, COUNT(*) AS job
FROM   public.raw_netbackup_jobs_metrics
WHERE  starttime > now() - interval '90 days'
GROUP  BY 1 ORDER BY 2 DESC;
```

## Kabul kriterleri
- [ ] Prefix keşif raporu üretilmiş (prefix, istemci sayısı, job, GB, önerilen müşteri, güven skoru)
- [ ] Onaylı prefix'ler `gui_crm_customer_source_mapping`'e `prefix` yöntemiyle yazılmış
- [ ] Bir örnek müşteride Customer View NetBackup paneli veri gösteriyor (TASK-06 ile uçtan uca)
- [ ] Kapsama oranı ölçülmüş (öncesi/sonrası: eşleşen istemci %)
- [ ] Çakışan prefix yok (`match_value` birden fazla müşteride tanımlı değil)

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, task/query-map/06-backup-dr.md,
datalake-platform-knowledge-base/adrs/ADR-0008-crm-customer-identity-resolution.md,
services/customer-api/app/services/customer_mapping_resolver.py,
shared/customer/{match.py,unmapped_classifier.py}, src/utils/crm_source_mapping_ui.py

Görev: NetBackup müşteri prefix'lerini keşfet ve sisteme tanımla.

1. scripts/discover_netbackup_prefixes.py yaz:
   - raw_netbackup_jobs_metrics.workloaddisplayname üzerinden -, _, . ayırıcılarıyla prefix çıkar
   - Her prefix için: tekil istemci sayısı, job sayısı, transfer GB
   - discovery_crm_accounts.name ile bulanık eşleştirme (shared/customer/match.py'deki mevcut mantığı
     yeniden kullan, yeni bir eşleştirme algoritması icat etme) -> önerilen müşteri + güven skoru
   - Çıktı: task/GUI/reports/netbackup-prefix-onerileri.md (markdown tablo) + CSV
2. OTOMATİK YAZMA YAPMA. Rapor insan onayına gidecek.
3. Onaylı listeyi uygulayan ayrı bir script yaz (scripts/apply_netbackup_prefixes.py):
   - CSV okur, PUT /api/v1/crm/aliases/{accountid}/source-mappings ile
     data_source='backup_netbackup', match_method='prefix' kuralı ekler
   - --dry-run varsayılan olsun; --apply ile yazsın
   - Çakışma (aynı match_value başka müşteride) varsa yazmayı reddetsin
4. Uygulama sonrası kapsama raporu: eşleşen/eşleşmeyen istemci oranı, öncesi/sonrası.

Kısıt: Yanlış eşleşme fatura hatasıdır - güven skoru düşük önerileri "manuel inceleme" olarak işaretle.
```

## İlgili
- TASK-06 (Customer View NetBackup eksikliği) — bu maddenin doğrudan çözümü
- TASK-15 (alias butonu) — kalan eşleşmeyenleri operasyon ekibi tek tek düzeltir
