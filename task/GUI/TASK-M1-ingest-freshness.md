# TASK-M1 — Ingest Freshness: "Erişim var ama veri geliyor mu?"

**Tip:** Monitoring / Veri sağlığı · **Efor:** L · **Öncelik:** ÇOK YÜKSEK
**Karar:** [K-03](KARARLAR.md#k-03--monitoring-önceliği-m1--ingest-freshness)

## Hedef
Her collector hedefi (IP) için "**bu kaynaktan datalake'e son ne zaman veri düştü**" sorusunu
cevaplayan bir katman kurmak. Bugün sadece *ağ erişimi* izleniyor; port açık ama collector
patlamışsa sistem yeşil görünüyor.

## Monitoring zincirinin dört halkası

```
1. BEKLENEN        2. KONFİGÜRE        3. ERİŞİLEBİLİR      4. VERİ GELİYOR
   NetBox/Loki   →  NiFi config      →  ICMP/TCP check    →  datalake ingest
   ✅ VAR           ✅ VAR              ✅ VAR                ❌ BU TASK
```

## Mevcut altyapı (project-zabake / HMDL) — ne var

| Tablo | İçerik | Yazan |
|---|---|---|
| `hmdl.collector_definition` | Collector kataloğu: `collector_type`, `conf_key`, `ip_field`, **`check_ports`**, `vault_key`, `source_type` | seed |
| `hmdl.collector_target` | collector × IP × proxy; `dc_code`, `tenant_name`, `entity_name`, **`last_check_status`**, `last_check_at`, `last_distributed_at`, `status`, `extra` | AWX JT55 |
| `hmdl.collector_check_log` | ICMP/TCP sonucu; `check_phase` (pre/post reconcile), `latency_ms`, `error_text` | AWX JT55 |
| `hmdl.collector_sync_log` / `collector_diff_log` | Run özeti / IP ekle-çıkar-`removal_blocked` | AWX JT55 |
| `hmdl.proxy_node` | NiFi proxy kaydı, `last_awx_job_id` | AWX JT55 |
| `hmdl.hmdl_datalake_coverage_target` | **IP · platform · dns · network_access · tenant · dc_code · proxy · check_status** | AWX JT63 |
| `hmdl.hmdl_datalake_coverage_cluster` | `source`(vmware\|nutanix) · `cluster_name` · `collected` · `expected` · `is_live` · `last_collected` | AWX JT63 |
| `hmdl.hmdl_datalake_coverage_ibm_host` | IBM host karşılığı | AWX JT63 |

Kaynak: `<repo-kök>/project-zabake/SQL/datalake-collectors/`,
`<repo-kök>/project-zabake/datalake-monitoring/virtualization-monitoring/scripts/sql/`

**Collector tipleri ve portları** (`datalake-collectors/mappings/collector_types.yml`):

| Collector | Port(lar) | NetBox manufacturer eşlemesi |
|---|---|---|
| VmWare | 443 | VMware |
| Nutanix | 9440 | Nutanix, Acropolis |
| IBM-HMC | 12443 | IBM HMC |
| IBM-Virtualize | 22, 7443 | IBM Virtualize |
| **Veeam** | **9419** | Veeam |
| **Zerto** | **9669** | Zerto |
| **Netbackup** | **1556, 443** | Netbackup |
| ILO-Redfish / Inspur-Redfish | 443 | (device) |

> **Önemli:** Backup collector'ları (Veeam/Zerto/NetBackup) **erişim kontrolü kapsamında zaten var**.
> Eksik olan veri seviyesi kapsamı — bu task onu ekliyor.

## Asıl iş: IP ↔ datalake tablosu köprüsü

Her collector için "son veri" farklı tabloda ve farklı kolonda duruyor. Yaptığım kolon incelemesi:

| Collector | Hedef tablo | Host/IP kolonu | Zaman kolonu | Eşleşme kalitesi |
|---|---|---|---|---|
| **Veeam** | `raw_veeam_jobs_states` | **`source_ip`** | `collection_time` | ✅ **doğrudan IP** |
| Zerto | `raw_zerto_vpg_metrics`, `raw_zerto_site_metrics` | `zerto_host`, `source_site` | `collection_timestamp` | ⚠️ isim → IP köprüsü gerek |
| Netbackup | `raw_netbackup_disk_pools_metrics`, `raw_netbackup_jobs_metrics` | `netbackup_host`, `destinationmediaservername` | `collection_timestamp` | ⚠️ isim |
| Nutanix | `nutanix_cluster_metrics` | `cluster_name`, `cluster_uuid` | `collection_time` | ⚠️ dolaylı (cluster) |
| **VmWare** | `vm_metrics`, `cluster_metrics`, `datacenter_metrics` | **vCenter IP kolonu YOK** | `timestamp` | ❌ **sadece cluster üzerinden dolaylı** |
| IBM-HMC | `ibm_server_general`, `ibm_lpar_general` | `server_details_servername` | `time` | ⚠️ isim |
| IBM-Virtualize | `raw_ibm_storage_vdisk` vb. | cihaz adı | `timestamp` | ⚠️ isim |
| S3-ICOS | `raw_s3icos_pool_metrics` | pool/vault adı | `collection_timestamp` | ⚠️ isim |

**Köprü stratejisi:** `collector_target.entity_name` (NetBox platform adı) ↔ datalake host adı
normalize edilerek eşleştirilir (`lower()`, domain eki atılır, `-`/`_` normalize). Eşleşmeyen
hedefler `unmatched` olarak raporlanır — bu liste kendi başına değerli çıktıdır.

## Yapılacaklar

- [ ] **Eşleme kataloğu:** `hmdl.collector_ingest_map` tablosu (veya YAML + seed)
      ```
      collector_type | datalake_table | host_column | ts_column | match_mode(ip|name) | stale_after_hours
      ```
      `stale_after_hours` collector başına farklı olmalı (A-04 kararı bekliyor).
- [ ] **Hesap job'u:** her `collector_target` satırı için son ingest zamanını bulan script
      (project-zabake `datalake-monitoring` altında, JT63 ile aynı ritimde)
- [ ] **Çıktı tablosu:** `hmdl.hmdl_datalake_coverage_endpoint`
      ```
      ip · collector_type · entity_name · dc_code · proxy_id · tenant
      network_access(bool) · check_status · last_check_at
      last_ingest_at · ingest_age_hours · ingest_stale(bool) · verdict
      ```
      `verdict`: `healthy` | `no_network` | `network_ok_no_data` | `stale` | `unmatched`
      > `network_ok_no_data` = bugün göremediğimiz kör nokta. **Bu task'in asıl çıktısı.**
- [ ] **hmdl-api endpoint'i:** `GET /api/v1/collectors/ingest-health` (+ DC/collector filtreleri)
- [ ] **GUI:** Administration › Integrations › HMDL altında yeni sekme veya Sync Health'e kolon ekleme
      (A-05 kararına göre)
- [ ] **Eşleşmeyenler raporu:** `unmatched` hedefler ayrı liste — köprü kuralı eksikliği burada görünür
- [ ] **DC11 doğrulaması:** TASK-05'in kök nedeni bu tabloda görünmeli (kanıt olarak ekle)

## Doğrulama SQL'leri

```sql
-- 1) Bugünkü erişim tablosu (mevcut hâl)
SELECT dc_code, platform, check_status, COUNT(*) AS hedef
FROM   hmdl.hmdl_datalake_coverage_target
GROUP  BY 1,2,3 ORDER BY 1,2;

-- 2) Erişimi olan ama veri gelmeyen adaylar — Veeam örneği (IP eşleşmesi temiz)
SELECT ct.dc_code, host(ct.ip) AS ip, ct.entity_name, ct.last_check_status,
       MAX(v.collection_time) AS son_veri,
       now() - MAX(v.collection_time) AS gecikme
FROM   hmdl.collector_target ct
JOIN   hmdl.collector_definition cd ON cd.id = ct.collector_id AND cd.collector_type = 'Veeam'
LEFT   JOIN public.raw_veeam_jobs_states v ON v.source_ip = host(ct.ip)
WHERE  ct.status = 'active'
GROUP  BY 1,2,3,4
ORDER  BY son_veri NULLS FIRST;
-- ⇒ last_check_status='ok' AMA son_veri NULL/eski olan satırlar = kör nokta

-- 3) NetBackup: isim köprüsü kurulabiliyor mu (normalize deneme)
SELECT DISTINCT lower(split_part(netbackup_host, '.', 1)) AS nb_host_kisa,
       MAX(collection_timestamp) AS son_veri
FROM   public.raw_netbackup_disk_pools_metrics
GROUP  BY 1 ORDER BY 1;

SELECT DISTINCT lower(split_part(ct.entity_name, '.', 1)) AS netbox_kisa, host(ct.ip)
FROM   hmdl.collector_target ct
JOIN   hmdl.collector_definition cd ON cd.id = ct.collector_id AND cd.collector_type = 'Netbackup'
WHERE  ct.status='active' ORDER BY 1;
-- ⇒ iki listeyi karşılaştır: kaçı eşleşiyor?

-- 4) Zerto
SELECT DISTINCT zerto_host, source_site, MAX(collection_timestamp) AS son_veri
FROM   public.raw_zerto_vpg_metrics GROUP BY 1,2 ORDER BY 1;

-- 5) Collector başına genel tazelik (eşiği belirlemek için — A-04)
SELECT 'vmware'    AS kaynak, MAX("timestamp")          AS son FROM public.vm_metrics
UNION ALL SELECT 'nutanix',   MAX(collection_time)      FROM public.nutanix_vm_metrics
UNION ALL SELECT 'ibm_lpar',  MAX("time")               FROM public.ibm_lpar_general
UNION ALL SELECT 'netbackup', MAX(collection_timestamp) FROM public.raw_netbackup_jobs_metrics
UNION ALL SELECT 'veeam',     MAX(collection_time)      FROM public.raw_veeam_jobs_states
UNION ALL SELECT 'zerto',     MAX(collection_timestamp) FROM public.raw_zerto_vpg_metrics
UNION ALL SELECT 's3icos',    MAX(collection_timestamp) FROM public.raw_s3icos_pool_metrics;

-- 6) AWX job sağlığı (veri gelmiyorsa önce buraya bak)
SELECT run_id, proxy_id, awx_job_id, MAX(created_at) AS son
FROM   hmdl.collector_sync_log GROUP BY 1,2,3 ORDER BY son DESC LIMIT 20;
```

## Kabul kriterleri
- [ ] Her aktif `collector_target` satırı için `verdict` üretiliyor
- [ ] `network_ok_no_data` durumundaki hedefler listelenebiliyor
- [ ] Eşleşmeyen (`unmatched`) hedef oranı raporlanmış ve %20'nin altında
- [ ] DC11 backup sorununun kök nedeni bu tabloda görünüyor
- [ ] Job JT63 ile aynı ritimde çalışıyor, `checked_at` her koşuda tazeleniyor
- [ ] hmdl-api endpoint'i 200 dönüyor, GUI'de görünüyor

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, task/GUI/KARARLAR.md,
<repo-kök>/datalake-platform-knowledge-base/wiki/HMDL-Endpoint-And-Data-Health-Monitoring.md,
<repo-kök>/datalake-platform-knowledge-base/wiki/datalake-collectors/HMDL-Collector-Sync.md,
<repo-kök>/datalake-platform-knowledge-base/wiki/Reconciliation-VM-Inventory.md,
<repo-kök>/project-zabake/SQL/datalake-collectors/*.sql,
<repo-kök>/project-zabake/datalake-collectors/mappings/collector_types.yml,
<repo-kök>/project-zabake/datalake-monitoring/virtualization-monitoring/scripts/

Görev: Collector hedefleri için "ingest freshness" (veri geliyor mu) katmanını kur.

ADIM 1 — KEŞİF (kod yazmadan):
  Her collector_type için datalake'teki karşılık tabloyu ve host/IP kolonunu tespit et.
  TASK-M1'deki tabloyu doğrula ve eksikleri tamamla. Özellikle:
  - VmWare: vCenter IP'sini taşıyan bir kolon GERÇEKTEN yok mu? information_schema ile ara.
  - Zerto zerto_host ve NetBackup netbackup_host değerleri collector_target.entity_name ile
    normalize edildiğinde kaç yüzde eşleşiyor? Ölç ve raporla.
  Bu keşif raporu olmadan devam etme.

ADIM 2 — EŞLEME KATALOĞU:
  hmdl.collector_ingest_map (collector_type, datalake_table, host_column, ts_column,
  match_mode, stale_after_hours). Idempotent DDL + seed.
  Normalize kuralı tek bir fonksiyonda toplansın: lower + domain eki at + -/_ birleştir.

ADIM 3 — HESAP JOB'U:
  project-zabake/datalake-monitoring altında, mevcut reconciler desenini (scripts/reconcilers/base.py)
  takip eden bir modül. Her aktif collector_target için son ingest zamanını bulur.
  Çıktı: hmdl.hmdl_datalake_coverage_endpoint (TRUNCATE + reload, coverage_target ile aynı desen).
  verdict alanı: healthy | no_network | network_ok_no_data | stale | unmatched

ADIM 4 — OKUMA YOLU:
  hmdl-api'ye GET /api/v1/collectors/ingest-health (dc, collector_type, verdict filtreleri).
  GUI'de Administration > Integrations > HMDL altında göster.

Kısıt:
- Yazma yolu AWX, okuma yolu hmdl-api standardı korunacak (ADR-0003).
- Ham datalake tablolarına YAZMA yok, sadece okuma.
- Yeni bir collector/NiFi metriği icat etme; mevcut tablolardan türet.
- Eşleşmeyen hedefleri sessizce atma; unmatched olarak raporla.
```

## Sonraki adımlar (bu task'ten sonra)
- **M2** — vCenter parent rollup: `coverage_cluster`'a parent kolonu, "beklenen 3 / toplanan 3 / canlı 2"
- **M3** — Dual-proxy matrisi: `collector_target` `proxy_id` ile "kaç proxy'de tanımlı / kaçından erişiliyor" (yarım günlük iş)
- **M4** — Backup coverage: NetBackup/Veeam/Zerto için beklenen/toplanan/canlı
