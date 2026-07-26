# TASK-02 — Endpoint Kontrolü ve Veri Doğruluğu (Loki Baseline)

**Tip:** Veri doğrulama · **Efor:** L · **Öncelik:** Yüksek (diğer maddelerin önkoşulu)
**Paydaş:** Can (süreç bilgisi), Murat Bey (Loki'nin baseline alınması yönlendirmesi)

## Hedef
Dashboard'da **Power** ve **NetBackup Storage** değerleri yanlış geliyor. Loki (NetBox) baseline
alınarak endpoint bazında kapsam/kaynak doğrulaması yapılacak; sapmanın nerede oluştuğu tespit edilip düzeltilecek.

## "Loki baseline" ne demek
Loki = NetBox envanteri; platformda **DC listesi ve lokasyon hiyerarşisinin tek doğruluk kaynağı** (ADR-0006).
Bir ekranda DC bazlı bir sayı gösteriliyorsa kapsamı `loki_locations`'tan gelen DC listesiyle birebir olmalı.

```sql
-- Baseline DC listesi
SELECT DISTINCT CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name
FROM public.loki_locations WHERE status_value='active' ORDER BY 1;
```

Ham tablolarda DC kolonu yoksa DC serbest metinden regex ile çıkarılıyor —
`services/datacenter-api/app/services/dc_service.py :: _extract_dc_from_text`,
`r'(DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+)'`. **Sapmaların ana kaynağı burası.**

## Kapsam: iki hedef metrik

### A) Power (IBM Power / LPAR)
| Katman | Yer |
|---|---|
| Sorgu | `src/queries/ibm.py`, `services/datacenter-api/app/db/queries/ibm.py` |
| Tablolar | `ibm_lpar_general`, `ibm_vios_general`, `ibm_server_general` |
| DC çıkarımı | `lpar_details_servername` üzerinden regex (bkz. `task/query-map/03-ibm-power.md`) |
| UI | `src/pages/dc_view.py` (Power sekmesi), `src/pages/customer_view.py` (`_tab` ~1611 "Power Mimari") |

> Not: TASK-03 Power sekmesini kaldırıyor. **Yine de** Power verisi Inventory/Sellable tarafında
> kullanılıyor (`virt_power`, `virt_power_hana` aileleri) — bu maddedeki doğrulama sekme kaldırılsa da geçerli.

### B) NetBackup Storage
| Katman | Yer |
|---|---|
| Sorgu | `services/datacenter-api/app/db/queries/backup.py` |
| Tablolar | `raw_netbackup_disk_pools_metrics`, `raw_netbackup_jobs_metrics` |
| DC çıkarımı | `netbackup_host` / `destinationmediaservername` metninden regex |
| UI | `src/components/backup_panel.py`, `dc_view.py` Backup sekmesi, `crm_inventory_report.py` (`backup_netbackup` ailesi) |

## Yöntem — endpoint bazlı 4 adımlı kontrol

Her endpoint için:
1. **Kapsam:** endpoint'in döndüğü DC seti = Loki DC seti mi? (eksik/fazla DC var mı)
2. **Tazelik:** kaynak tablonun son `collection_timestamp`'i kaç saat önce?
3. **Toplam:** endpoint'in döndüğü toplam = ham SQL toplamı mı? (birim dönüşümü dahil: bytes↔GiB↔TB)
4. **Tekilleştirme:** "latest snapshot per entity" uygulanmış mı, çift sayım var mı?

### Kontrol edilecek endpoint listesi
```
GET /api/v1/datacenters/{dc}/backup/netbackup
GET /api/v1/datacenters/{dc}/backup/netbackup/jobs
GET /api/v1/datacenters/{dc}/backup/{vendor}/unique-jobs
GET /api/v1/datacenters/{dc}                       (Power blokları)
GET /api/v1/datacenters/summary
GET /api/v1/crm/inventory-overview                 (virt_power*, backup_netbackup satırları)
GET /api/v1/crm/sellable-potential/by-family
```

## Doğrulama SQL'leri

```sql
-- 1) Loki DC seti
SELECT DISTINCT CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc
FROM public.loki_locations WHERE status_value='active' ORDER BY 1;

-- 2) NetBackup'ın "gördüğü" DC seti (regex ile)
SELECT DISTINCT substring(netbackup_host from '(DC[0-9]+|AZ[0-9]+|ICT[0-9]+|UZ[0-9]+|DH[0-9]+)') AS dc,
       COUNT(*) AS satir, MAX(collection_timestamp) AS son_veri
FROM public.raw_netbackup_disk_pools_metrics
GROUP BY 1 ORDER BY 1;
-- ⇒ (1) ile (2) farkı = kapsam sapması. NULL dc = regex tutmayan host adları (incelenmeli).

-- 3) NetBackup storage toplamı — latest snapshot per disk volume
WITH latest AS (
  SELECT DISTINCT ON (netbackup_host, name, diskvolumes_name)
         netbackup_host, name, diskvolumes_name,
         usablesizebytes, usedcapacitybytes, availablespacebytes, collection_timestamp
  FROM public.raw_netbackup_disk_pools_metrics
  ORDER BY netbackup_host, name, diskvolumes_name, collection_timestamp DESC
)
SELECT substring(netbackup_host from '(DC[0-9]+|AZ[0-9]+|ICT[0-9]+|UZ[0-9]+|DH[0-9]+)') AS dc,
       ROUND(SUM(usablesizebytes)   / 1024^4, 2) AS usable_tib,
       ROUND(SUM(usedcapacitybytes) / 1024^4, 2) AS used_tib,
       COUNT(*) AS volume_sayisi
FROM latest GROUP BY 1 ORDER BY 1;

-- 4) Power / LPAR — DC dağılımı ve tazelik
SELECT substring(lpar_details_servername from '(DC[0-9]+|AZ[0-9]+|ICT[0-9]+|UZ[0-9]+|DH[0-9]+)') AS dc,
       COUNT(DISTINCT lparname) AS lpar_sayisi,
       ROUND(SUM(lpar_processor_currentvirtualprocessors)::numeric, 2) AS vcpu,
       ROUND(SUM(lpar_memory_logicalmem)::numeric/1024, 2)            AS ram_gb,
       MAX("time") AS son_veri
FROM public.ibm_lpar_general
WHERE "time" > now() - interval '2 days'
GROUP BY 1 ORDER BY 1;

-- 5) Çift sayım kontrolü: aynı LPAR birden çok satırda mı?
SELECT lparname, COUNT(*) AS satir, COUNT(DISTINCT lpar_details_servername) AS server_sayisi
FROM public.ibm_lpar_general
WHERE "time" > now() - interval '1 day'
GROUP BY 1 HAVING COUNT(*) > 1 ORDER BY 2 DESC LIMIT 20;

-- 6) Kaynak erişilebilirliği (HMDL) — akış duruyor mu?
SELECT dc_name, collector_type, target_name, last_check_status, last_check_time
FROM hmdl.collector_target
WHERE collector_type IN ('IBM-HMC','VmWare','Nutanix')
ORDER BY dc_name, collector_type;
```

## Yapılacaklar

- [ ] Yukarıdaki SQL'lerin çıktısını `task/GUI/reports/2026-07-xx-baseline.md`'ye kaydet (öncesi durumu)
- [ ] Her endpoint için API cevabı ile SQL toplamını yan yana koyan karşılaştırma tablosu üret
- [ ] Sapma tipini sınıflandır: (a) kapsam/DC eşleme, (b) tekilleştirme, (c) birim dönüşümü, (d) akış durmuş
- [ ] `_extract_dc_from_text` regex'ini tutmayan host adları için eşleme tablosu / özel kural ekle
      (`zabbix_network.py`'daki `DH3 → DC13` deseninin aynısı; tek yerde toplayın)
- [ ] Düzeltmeleri uygula, cache temizle, aynı karşılaştırmayı tekrarla
- [ ] Sonucu `docs/` altında kalıcı bir "veri doğruluğu" notuna bağla

## Kabul kriterleri
- [ ] Her endpoint için "API değeri = SQL değeri (±%1)" tablosu üretilmiş
- [ ] Loki DC listesi ile endpoint kapsamı arasındaki fark **0** (ya da bilinçli/dokümante istisna)
- [ ] Regex ile DC çıkarılamayan satır sayısı 0 veya raporlanmış
- [ ] Power ve NetBackup Storage değerleri Murat Bey'in beklediği baseline ile uyumlu (onay alınmış)

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, task/query-map/03-ibm-power.md,
task/query-map/06-backup-dr.md, task/query-map/09-discovery-inventory.md,
services/datacenter-api/app/services/dc_service.py (_extract_dc_from_text),
services/datacenter-api/app/db/queries/{backup.py,ibm.py,loki.py}

Görev: Power ve NetBackup Storage değerlerinin doğruluğunu Loki (loki_locations) baseline'ına göre denetle.

1. Bir doğrulama scripti yaz (scripts/verify_loki_baseline.py):
   - loki_locations'tan aktif DC listesini çeker
   - raw_netbackup_disk_pools_metrics ve ibm_lpar_general için regex DC dağılımını çıkarır
   - datacenter-api endpoint'lerini çağırıp API değeri ile SQL değerini yan yana yazar
   - Çıktı: markdown tablo (dc, kaynak, sql_deger, api_deger, fark_pct, son_veri_yasi)
2. Sapmaları sınıflandır: kapsam / tekilleştirme / birim / akış durmuş.
3. Kapsam sapması varsa: DC çıkarım regex'ini tek bir yardımcı modülde topla ve host-adı istisnalarını
   config'e taşı (kod içine gömme). zabbix_network.py'deki DH3->DC13 istisnasını da oraya taşı.
4. Tekilleştirme sapması varsa DISTINCT ON (latest snapshot per entity) uygula.
5. Değişiklik yapmadan önce ölçümü, yaptıktan sonra tekrar ölçümü raporla.

Kısıt: Ham veriye yazma yok. Sadece okuma + GUI/servis katmanı düzeltmesi.
Şema adlarını information_schema ile doğrula, varsayma.
```

## Bağımlılık
TASK-05 (DC11 backup), TASK-06 (Customer View eksikleri) ve TASK-16 (NetBackup prefix) bu maddenin
yöntemini ve çıktısını kullanır. **Önce bu bitmeli.**
