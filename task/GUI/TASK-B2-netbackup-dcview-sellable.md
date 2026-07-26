# TASK-B2 — NetBackup'ın DC View'da Satılabilir Alan Olarak Görünmesi

**Tip:** Backend / Feature · **Efor:** M · **Öncelik:** YÜKSEK
**Bağımlılık:** [TASK-B1](TASK-B1-netbackup-fatura-tabani.md) (taban kararı önce)

## Sorun
CRM Inventory'de NetBackup satırı var, **DC View'da yok**. Bir datacenter'a girildiğinde
NetBackup'ın CRM ile eşleştirilmiş satılabilir alan verisi görünmüyor.

## Kök neden — buldum

```python
# services/customer-api/app/services/sellable_service.py:222
# Maps panel family → datacenter-api compute endpoint kind.
_FAMILY_COMPUTE_ENDPOINT: dict[str, str] = {
    "virt_classic":        "classic",
    "virt_hyperconverged": "hyperconverged",
}
```

DC bazlı sellable hesabı **yalnızca bu iki aileyi** tanıyor. Backup panelleri için
`datacenter-api`'de karşılık gelen bir `/compute/{kind}` endpoint'i yok, dolayısıyla
DC kırılımlı hesap yapılamıyor. Global CRM Inventory çalıştığı için orada görünüyor.

Bunu KB de doğruluyor: *"Datacenter sellable: remains virtualization-only (unchanged); notes only"*
(`wiki/CRM-Inventory-Infra-Matching.md`, kapsam kararları).

## Zaten hazır olan parçalar

| Parça | Durum |
|---|---|
| Ürün → panel eşlemesi | ✅ `panel_mapping.py` → `backup_netbackup_storage` ("Veritas" / "NetBackup" kuralı) |
| Politika kırılımı | ✅ `policy_panel_mapping.yaml` (VMWARE → image, diğer → application) |
| DC bazlı NetBackup verisi | ✅ `/datacenters/{dc}/backup/netbackup` + `/backup/netbackup/jobs` |
| DC attribution | ⚠️ `destinationmediaservername` regex — TASK-02/05 ile ortak |
| Sellable pipeline | ✅ `shared/sellable/computation.py` (threshold → ratio → TL) |
| **DC compute endpoint** | ❌ **eksik — bu task** |

## Yapılacaklar

- [ ] **`datacenter-api`'ye backup compute endpoint'i:**
      `GET /datacenters/{dc}/compute/backup-netbackup`
      Dönmesi gereken alanlar (mevcut `/compute/{kind}` sözleşmesiyle uyumlu):
      ```
      stor_cap              → toplam kullanılabilir disk (usablesizebytes)
      stor_provisioned_gb   → kullanılan (B1 kararına göre pre veya post dedup)
      stor_pct              → doluluk %
      ```
      > `_RESOURCE_KIND_TO_COMPUTE_FIELDS` sözleşmesi: `storage` → (`stor_cap`, `stor_provisioned_gb`, `TB`)
- [ ] **`_FAMILY_COMPUTE_ENDPOINT`'e ekle:** `"backup_netbackup": "backup-netbackup"`
- [ ] **Panel tanımı:** `gui_panel_definition`'da `backup_netbackup_storage` için
      `family='backup_netbackup'`, `resource_type='storage'`, `display_unit='GB'` (veya TB)
- [ ] **Infra source kaydı:** `PUT /api/v1/crm/panels/backup_netbackup_storage/infra-source`
- [ ] **Threshold:** `gui_crm_threshold_config`'e backup için satılabilir tavan %
      (virt'ten farklı olmalı — backup disk'i %100 doldurulamaz)
- [ ] **DC View'a panel:** Backup sekmesine "Satılabilir Alan" kartı
      (`src/pages/dc_view.py`, mevcut sellable kart deseni)
- [ ] **Görünürlük:** DC'de NetBackup yoksa panel hiç render edilmesin (`PROJECT_STANDARDS.md` §3)
- [ ] **image / application ayrımı:** iki ayrı panel mi tek panel mi — `000BLT-203` (image) ve
      `000BLT-142` (application) ayrı SKU olduğu için **iki ayrı panel öneriyorum**

## Doğrulama

```sql
-- DC bazlı NetBackup kapasitesi (endpoint'in dönmesi gereken sayı)
WITH latest AS (
  SELECT DISTINCT ON (netbackup_host, name, diskvolumes_name)
         netbackup_host, name, diskvolumes_name,
         usablesizebytes, usedcapacitybytes, availablespacebytes
  FROM   public.raw_netbackup_disk_pools_metrics
  ORDER  BY netbackup_host, name, diskvolumes_name, collection_timestamp DESC
)
SELECT substring(netbackup_host from '(DC[0-9]+|AZ[0-9]+|ICT[0-9]+|UZ[0-9]+|DH[0-9]+)') AS dc,
       ROUND(SUM(usablesizebytes)/1024.0^4, 2)   AS usable_tib,
       ROUND(SUM(usedcapacitybytes)/1024.0^4, 2) AS used_tib,
       ROUND(100.0*SUM(usedcapacitybytes)/NULLIF(SUM(usablesizebytes),0), 1) AS doluluk_pct
FROM   latest GROUP BY 1 ORDER BY 1;

-- Panel tanımı geldi mi (bulutwebui)
SELECT panel_key, family, resource_type, display_unit FROM gui_panel_definition
WHERE  panel_key LIKE 'backup%' ORDER BY 1;
```

```bash
DC=DC13
curl -s "http://10.134.52.250:8000/api/v1/datacenters/$DC/compute/backup-netbackup" | python3 -m json.tool
curl -s "http://10.134.52.250:8070/api/v1/crm/sellable-potential/by-panel?dc_code=$DC" \
  | python3 -c "import json,sys;[print(r) for r in json.load(sys.stdin) if 'backup' in r.get('panel_key','')]"
```

## Kabul kriterleri
- [ ] `/compute/backup-netbackup` endpoint'i DC bazlı doğru kapasite dönüyor (SQL ile ±%1)
- [ ] DC View Backup sekmesinde satılabilir alan kartı görünüyor
- [ ] NetBackup'ı olmayan DC'de panel render edilmiyor
- [ ] CRM Inventory'deki global NetBackup satırı ile DC toplamları tutarlı
- [ ] image / application ayrımı doğru (policy_panel_mapping.yaml'a göre)
- [ ] Kullanılan taban B1 kararına uygun ve kodda yorumla belirtilmiş

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, task/GUI/KARARLAR.md,
task/GUI/TASK-B1-netbackup-fatura-tabani.md, task/query-map/06-backup-dr.md,
task/query-map/05-sellable-potential.md,
services/customer-api/app/services/sellable_service.py (satır ~222 _FAMILY_COMPUTE_ENDPOINT,
  ~248 _RESOURCE_KIND_TO_COMPUTE_FIELDS),
services/datacenter-api/app/db/queries/backup.py,
services/datacenter-api/app/routers/datacenters.py (mevcut /compute/{kind} endpoint'leri),
shared/sellable/{computation.py,panel_mapping.py}, shared/backup/policy_panel_mapping.yaml

Görev: NetBackup'ı DC View'da satılabilir alan olarak göster.

ÖN KOŞUL: TASK-B1 kararı (pre-dedup mu post-dedup mu) verilmiş olmalı. Verilmemişse DUR ve sor.

1. Mevcut /datacenters/{dc}/compute/classic endpoint'inin cevap şeklini incele ve raporla.
   Yeni endpoint AYNI sözleşmeyi kullanacak (stor_cap, stor_provisioned_gb, stor_pct).
2. GET /api/v1/datacenters/{dc}/compute/backup-netbackup ekle.
   Kapasite: raw_netbackup_disk_pools_metrics, latest-per-volume (DISTINCT ON).
   Kullanılan: B1 kararına göre. DC attribution için TASK-05'te oluşturulan dc_resolver'ı kullan,
   yeni bir regex yazma.
3. sellable_service.py: _FAMILY_COMPUTE_ENDPOINT'e "backup_netbackup": "backup-netbackup" ekle.
   Backup ailesi virt gibi CPU/RAM/Storage üçlüsü DEĞİL - sadece storage. constrain_by_ratio
   çağrılmamalı; sadece apply_threshold + compute_potential_tl.
4. gui_panel_definition + infra_source seed'i, idempotent migration.
   image (000BLT-203) ve application (000BLT-142) için AYRI paneller.
5. dc_view.py Backup sekmesine sellable kartı. Veri yoksa panel render edilmesin.
6. tests/: DC toplamlarının global inventory ile tutarlılığı; backup ailesinde ratio
   constraint'in çağrılmadığı.

Kısıt: virt ailelerinin sellable davranışı değişmemeli (regresyon testi).
```
