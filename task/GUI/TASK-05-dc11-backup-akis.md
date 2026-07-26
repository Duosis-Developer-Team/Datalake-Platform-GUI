# TASK-05 — DC11 Backup Veri Akışı Sorunu

**Tip:** Veri akışı / tanı · **Efor:** M · **Öncelik:** Yüksek · **Paydaş:** Can

## Hedef
Şu an sadece **DC13** backup verisi geliyor; **DC11** backup'ta değer "0". Akışların durmuş olma
ihtimaline karşı Loki baz alınarak kontrol edilecek, Can ile birlikte veri akışı düzenlenecek.

## Üç olası kök neden — bu sırayla eleyin

### (1) Veri hiç toplanmıyor (NiFi/collector akışı durmuş)
`docs/erisilemeyen-sanallastirma-datasourceleri.md`'ye göre **DC11'de 6 datasource erişilemez**
(NiFi: `10.6.116.250`, `10.6.116.251`). Backup collector'ları o raporun kapsamı dışında ama aynı proxy'leri kullanıyor.

### (2) Veri var ama DC etiketlenemiyor (attribution)
Backup tablolarında DC kolonu **yok**. DC, `netbackup_host` / `destinationmediaservername` /
site adı gibi serbest metinden regex ile çıkarılıyor:
```python
# services/datacenter-api/app/services/dc_service.py
r'(DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+)'   # çıkan kod yalnızca dc_list içindeyse kabul edilir
```
DC11 media server adı bu deseni içermiyorsa veri "sahipsiz" kalır → panelde 0.
(Veeam'de bu yüzden ayrı bir `VEEAM_IP_TO_DC_SEED` IP→DC haritası var — NetBackup için benzeri gerekebilir.)

### (3) Zaman penceresi / warm-window cache
Job istatistikleri `dc_service.py` içinde **warm-window per-backup cache** kullanıyor
(`services/datacenter-api/app/utils/time_range.py`). Yanlış pencerede veri boş görünebilir.

## Tanı adımları (sırayla, her adımın çıktısını kaydedin)

```sql
-- A) Ham veri var mı? Hangi host'lar, ne zamandan beri?
SELECT netbackup_host,
       COUNT(*) AS satir,
       MIN(collection_timestamp) AS ilk,
       MAX(collection_timestamp) AS son,
       now() - MAX(collection_timestamp) AS gecikme
FROM   public.raw_netbackup_disk_pools_metrics
GROUP  BY 1 ORDER BY son DESC;

-- B) Aynısı job tablosu için
SELECT destinationmediaservername,
       COUNT(*) AS satir, MAX(starttime) AS son_job, MAX(collection_timestamp) AS son_toplama
FROM   public.raw_netbackup_jobs_metrics
GROUP  BY 1 ORDER BY son_toplama DESC;

-- C) Regex DC11'i yakalıyor mu?
SELECT netbackup_host,
       substring(netbackup_host from '(DC[0-9]+|AZ[0-9]+|ICT[0-9]+|UZ[0-9]+|DH[0-9]+)') AS cikan_dc
FROM  (SELECT DISTINCT netbackup_host FROM public.raw_netbackup_disk_pools_metrics) t
ORDER BY 1;
-- ⇒ cikan_dc NULL olan host'lar attribution kaybının kaynağıdır.

-- D) Loki'de DC11 gerçekten aktif mi (baseline)
SELECT name, parent_name, status_value, site_name, description
FROM   public.loki_locations
WHERE  name ILIKE '%DC11%' OR parent_name ILIKE '%DC11%';

-- E) DC11 NetBox cihazlarında backup rolü var mı (media server bulmanın alternatif yolu)
SELECT name, device_type_model, site_name, location_name, status_value
FROM   public.discovery_netbox_inventory_device
WHERE  (site_name ILIKE '%DC11%' OR location_name ILIKE '%DC11%')
  AND  (name ILIKE '%nbu%' OR name ILIKE '%netbackup%' OR name ILIKE '%media%' OR name ILIKE '%bck%');

-- F) Collector/akış sağlığı (HMDL)
SELECT dc_name, collector_type, target_name, target_ip, last_check_status, last_check_time
FROM   hmdl.collector_target
WHERE  dc_name ILIKE '%DC11%'
ORDER  BY collector_type, target_name;

SELECT * FROM hmdl.collector_check_log
WHERE  target_name IN (SELECT target_name FROM hmdl.collector_target WHERE dc_name ILIKE '%DC11%')
ORDER  BY checked_at DESC LIMIT 50;

-- G) Diğer vendor'lar da mı 0? (sorun NetBackup'a mı özel)
SELECT 'veeam' AS vendor, COUNT(*), MAX(collection_timestamp) FROM public.raw_veeam_sessions
UNION ALL SELECT 'zerto', COUNT(*), MAX(collection_timestamp) FROM public.raw_zerto_vpg_metrics;
```

```bash
# H) API katmanı ne diyor
for dc in DC11 DC13; do
  echo "== $dc"
  curl -s "http://10.134.52.250:8000/api/v1/datacenters/$dc/backup/netbackup" | python3 -m json.tool | head -30
  curl -s "http://10.134.52.250:8000/api/v1/datacenters/$dc/backup/netbackup/jobs?range=30d" | python3 -m json.tool | head -20
done

# I) Cache'i baypas et (warm-window şüphesi)
docker exec bulutistan-redis redis-cli -n 2 --scan --pattern "*netbackup*" \
  | xargs -r docker exec -i bulutistan-redis redis-cli -n 2 DEL
curl -X POST "http://10.134.52.250:8000/api/v1/datacenters/DC11/backup/jobs/refresh"
```

## Karar tablosu

| Bulgu | Kök neden | Aksiyon |
|---|---|---|
| A/B'de DC11 host'u **hiç yok** | Toplama durmuş | **Can** ile NiFi akışı / collector target'ı; `hmdl.collector_target` kaydı ekle/onar |
| A/B'de var, `son` eski (>24 sa) | Akış durmuş | Aynı — NiFi processor bulletin'leri (`scripts/_nifi_bulletins.py`) |
| A/B'de güncel veri var, C'de `cikan_dc` NULL | Attribution | **Kod düzeltmesi:** host→DC eşleme tablosu (aşağıya bkz.) |
| API 0 ama SQL dolu | Cache/pencere | Warm-window ve cache invalidation düzeltmesi |

## Attribution düzeltmesi (en olası senaryo)

`_extract_dc_from_text` regex'ini tek başına bırakmayın; **açık eşleme tablosu** ekleyin
(Veeam'deki `VEEAM_IP_TO_DC_SEED` deseninin genelleştirilmiş hâli):

```
config/dc_attribution.yaml
  netbackup:
    host_to_dc:
      "<dc11-media-server-adı>": DC11
    regex_fallback: "(DC\\d+|AZ\\d+|ICT\\d+|UZ\\d+|DH\\d+)"
  aliases:
    DH3: DC13
```
Bu dosyayı `services/datacenter-api/app/utils/` altında tek bir çözümleyiciye bağlayın ve
`zabbix_network.py`'deki gömülü `DH3 → DC13` istisnasını da oraya taşıyın (TASK-02 ile ortak).

## Kabul kriterleri
- [ ] DC11 için ham veri var/yok sorusu **kanıtla** cevaplanmış (A–G çıktıları dosyada)
- [ ] Kök neden dört sınıftan birine atanmış ve dokümante edilmiş
- [ ] Attribution ise: `config/dc_attribution.yaml` devrede, DC11 backup paneli gerçek değer gösteriyor
- [ ] Akış ise: Can ile NiFi/collector düzeltmesi yapılmış, ilk veri geldiği doğrulanmış
- [ ] DC11 API değeri = SQL toplamı (±%1)
- [ ] Regresyon: DC13 değerleri değişmemiş

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, task/query-map/06-backup-dr.md,
docs/erisilemeyen-sanallastirma-datasourceleri.md,
services/datacenter-api/app/services/dc_service.py (_extract_dc_from_text, VEEAM_IP_TO_DC_SEED),
services/datacenter-api/app/db/queries/backup.py

Görev: DC11 backup verisinin 0 görünmesinin kök nedenini bul ve düzelt.

1. scripts/diagnose_dc11_backup.py yaz. TASK-05'teki A-G SQL'lerini ve H API çağrılarını çalıştırıp
   tek bir markdown rapor üretsin: her adım, çıktı, ve dört kök nedenden hangisine işaret ettiği.
   ÖNCE bu raporu üret, kod değiştirme.
2. Rapor "attribution" diyorsa: config/dc_attribution.yaml oluştur (netbackup.host_to_dc,
   regex_fallback, aliases). services/datacenter-api/app/utils/ altında tek bir dc_resolver modülü yaz.
   dc_service.py ve zabbix_network.py'deki gömülü DC çıkarımlarını bu modüle taşı
   (zabbix_network.py'deki DH3->DC13 istisnası dahil).
3. Rapor "akış durmuş" diyorsa: kod değiştirme; hmdl.collector_target kayıtlarını ve son check_log'ları
   listeleyen bir özet çıkar, Can'a iletilecek aksiyon maddesi olarak yaz.
4. tests/: dc_resolver için unit test (bilinen host adları -> beklenen DC, eşleşmeyen -> None ve loglanır).
5. Düzeltme sonrası DC11 ve DC13 için API vs SQL karşılaştırma tablosunu tekrar üret.

Kısıt: DC13 davranışı değişmemeli. Ham veriye yazma yok.
```
