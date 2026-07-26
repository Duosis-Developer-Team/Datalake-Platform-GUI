# TASK-12 — Backup İnternet Kullanımı Faturalandırması

**Tip:** Feature · **Efor:** ? · **Durum: NETLEŞTİRİLECEK** — isterler net değil

## Hedef (bilinen kadarıyla)
Backup internet kullanımının faturalandırılması süreci değerlendirilecek. İsterler ve detaylar net değil,
ek bilgi talep edilecek.

## Toplantıda sorulacaklar

1. **Ne ölçülüyor?** Backup trafiğinin internet üzerinden geçen kısmı mı, yoksa toplam yedeklenen veri mi?
2. **Nerede ölçülüyor?** Hangi cihaz/arayüz? (backup media server uplink'i? DC erişim hattı?)
3. **Birim ne?** Mbit (95p) mi, GB (transfer) mi, TB-ay (saklama) mı?
4. **Hangi CRM kalemi?** Mevcut bir SKU'ya mı yazılacak, yeni SKU mu açılacak?
5. **Kim faturalanacak?** Müşteri bazlı mı, DC bazlı mı?
6. **Mevcut DC erişim faturalandırmasından farkı ne?** (`000BLT-208 Veri Merkezi Erişim ve L3 DDoS`, Mbit)

## Elimizde ne var — üç olası ölçüm yolu

### Yol A: NetBackup transfer hacmi (en kolay)
```sql
SELECT date_trunc('day', starttime) AS gun,
       destinationmediaservername,
       SUM(kilobytestransferred)/1024/1024 AS gb_transfer,
       AVG(dedupratio) AS ort_dedup,
       COUNT(*) AS job
FROM   public.raw_netbackup_jobs_metrics
WHERE  starttime > now() - interval '30 days'
GROUP  BY 1,2 ORDER BY 1 DESC, 3 DESC;
```
**Sınır:** Bu "internet kullanımı" değil, toplam yedekleme trafiği. LAN/WAN ayrımı yok.

### Yol B: Zabbix interface 95p (mevcut network billing altyapısı)
`shared/network/backbone_billing.py` + `/datacenters/{dc}/network/95th-percentile`
```python
p95_bps_to_mbit(p95_total_bps)                      # bps -> Mbit/s
estimate_backbone_cost_tl(p95_bps, unit_price_tl)   # (p95/1e6) * birim_fiyat
```
**Gerekli:** Backup trafiğini taşıyan interface'lerin **etiketlenmesi** (NetBox rol/tag veya
Zabbix host grubu). Bu etiketleme yoksa ayrıştırılamaz. → **Altyapı ekibinden istenmeli.**

### Yol C: S3 / iCOS (offsite backup)
`raw_s3icos_pool_metrics`, `raw_s3icos_vault_metrics`, `raw_s3icos_vault_inventory`; `services/datacenter-api/app/db/queries/s3.py`.
Offsite yedek internetten gidiyorsa asıl ölçüm burada olabilir.

## Ön analiz (toplantıdan önce yapılabilir)

```sql
-- 1) NetBackup transfer hacmi büyüklük mertebesi
SELECT SUM(kilobytestransferred)/1024/1024/1024 AS tb_30gun
FROM public.raw_netbackup_jobs_metrics WHERE starttime > now() - interval '30 days';

-- 2) S3 iCOS kullanım
SELECT * FROM information_schema.tables WHERE table_name ILIKE '%s3icos%';

-- 3) Zabbix interface'lerinde backup ile ilişkilendirilebilir isim var mı
SELECT DISTINCT interface_name, loki_id
FROM   public.raw_zabbix_network_interface_metrics_v
WHERE  collection_timestamp > now() - interval '1 day'
  AND  (interface_name ILIKE '%backup%' OR interface_name ILIKE '%bck%' OR interface_name ILIKE '%nbu%')
LIMIT  50;

-- 4) NetBox'ta backup rolü/tag'i olan cihazlar
SELECT name, device_type_model, site_name, tenant_name
FROM   public.discovery_netbox_inventory_device
WHERE  name ILIKE '%nbu%' OR name ILIKE '%backup%' OR name ILIKE '%media%';
```

## Öneri: bu hafta = fizibilite notu, kod yok

- [ ] Üç yolun her biri için "ölçülebilir mi / hangi veriyle / hangi eksikle" tablosunu doldur
- [ ] Eksik etiketleme varsa altyapı ekibine somut talep yaz (hangi interface'e hangi tag)
- [ ] Toplantıda birim + SKU + faturalama tarafını kilitle
- [ ] Sonra TASK-12b olarak uygulama planı yaz (TASK-14'ün cache/hesap altyapısını kullanacak)

## Cursor / Claude Code prompt (fizibilite fazı)

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, task/query-map/{06-backup-dr.md,08-zabbix-monitoring.md},
shared/network/backbone_billing.py, services/datacenter-api/app/db/queries/{backup.py,zabbix_network.py,s3.py}

Görev: Backup internet kullanımı faturalandırması için FİZİBİLİTE raporu üret. KOD YAZMA.

scripts/feasibility_backup_internet_billing.py:
1. NetBackup transfer hacmini (kilobytestransferred) DC ve müşteri kırılımında 30 gün için çıkar.
2. Zabbix interface tablosunda backup trafiğini ayırt etmeye yarayacak bir sinyal var mı
   (interface adı, NetBox rolü/tag'i, host grubu) - ara ve raporla.
3. S3 iCOS pool/vault metriklerinden offsite backup hacmi çıkarılabiliyor mu kontrol et.
4. Her yol için: ölçülebilir mi / hangi tabloyla / hangi birim / eksik olan ne - tablo halinde yaz.

Çıktı: task/GUI/reports/backup-internet-billing-fizibilite.md
Rapor sonunda "paydaşa sorulacaklar" ve "altyapı ekibinden istenecekler" bölümleri olsun.
```
