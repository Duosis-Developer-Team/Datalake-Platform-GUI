# TASK-06 — Customer View Veri Eksiklikleri (IBM sanallaştırma + NetBackup)

**Tip:** Veri / Backend · **Efor:** M · **Öncelik:** Yüksek

## Hedef
Customer View ekranında **IBM sanallaştırma** verileri ve **NetBackup** verileri (kontrolleriyle
birlikte) panele yansımıyor. Bu veriler ekrana getirilecek.

## Kök neden hipotezi (güçlü)

Müşteri → veri kaynağı eşleştirmesi `gui_crm_customer_source_mapping` tablosundaki
`data_source` değerleriyle yapılıyor. Mevcut değerler
(`services/customer-api/app/services/customer_mapping_resolver.py` seed'inden):

```
physical_device · virtualization · netbox_vm_customer · backup_veeam · backup_zerto
backup_netbackup · storage_ibm · s3_icos · itsm_servicecore
```

> **IBM Power / LPAR için ayrı bir `data_source` YOK.** `virtualization` VMware/Nutanix isim desenine
> göre çalışıyor; `ibm_lpar_general.lparname` genelde farklı adlandırma kullanıyor.
> ⇒ IBM sanallaştırmanın müşteriye bağlanamamasının en olası nedeni bu.

NetBackup için `backup_netbackup` **var**, ama varsayılan kural `match_method='contains'`.
NetBackup istemci/politika adları müşteri **prefix**'i taşıyorsa `contains` yanlış eşleşir veya hiç eşleşmez
(→ TASK-16 bu prefix'leri tanımlıyor; iki madde birlikte çözülmeli).

## İlgili kod

| Katman | Dosya |
|---|---|
| Sayfa | `src/pages/customer_view.py` (3861 satır), `customer_view_callbacks.py` |
| NetBackup sekmeleri | `_tab_netbackup` (~1777), `_tab_netbackup_category` (~1812), sekme kurulumu ~2379-2434 |
| IBM/Power bloğu | ~905 `("Power Compute (IBM)", power, "lpar_count")`, ~1611 Power Mimari tab |
| Görünürlük | `src/utils/visibility.py` — `asset_has_usage`, `backup_vendor_has_data` |
| Backend | `services/customer-api/app/db/queries/customer.py`, `services/datacenter-api/app/db/queries/customer.py` |
| Eşleştirme | `services/customer-api/app/services/customer_mapping_resolver.py` |
| Eşleştirme UI | `src/utils/crm_source_mapping_ui.py` → Settings › Integrations › CRM aliases |

⚠️ **Görünürlük tuzağı:** `visibility.py :: is_meaningful_value` varsayılan olarak **0'ı boş sayar**
(`treat_zero_as_empty=True`). Veri gerçekten 0 ise panel hiç render edilmez — "veri gelmiyor" gibi görünür.
Teşhiste önce API cevabına bakın, ekrana değil.

## Yapılacaklar

- [ ] **Teşhis:** Bir örnek müşteri için (VIP bir hesap seçin) API cevabını çıkarın; IBM ve NetBackup
      blokları boş mu, yoksa 0 mı geliyor ayırt edin
- [ ] **IBM için yeni `data_source` ekle:** `power_lpar` (veya `virtualization_ibm`)
      - `customer_mapping_resolver.py`: yeni kaynağı çözümleme zincirine ekle
      - `src/utils/crm_source_mapping_ui.py`: Settings'te yeni kolon/grup göster
      - `customer.py` sorgularında `ibm_lpar_general` filtresini bu kaynağın desenleriyle kur
- [ ] **NetBackup eşleşmesini prefix'e taşı** (TASK-16 ile birlikte)
- [ ] **"Kontroller"i ekle:** NetBackup panelinde job başarı/başarısızlık, dedup oranı ve son job zamanı
      görünsün (`raw_netbackup_jobs_metrics.status`, `dedupratio`, `starttime`)
- [ ] **Boş vs sıfır ayrımı:** veri kaynağı eşleşmesi yoksa "eşleştirme tanımlı değil" rozeti,
      eşleşme var ama değer 0 ise "0" göster. Sessiz gizleme yapma
- [ ] Panel görünürlük kuralını koru (`docs/PROJECT_STANDARDS.md` §3) — ama yukarıdaki ayrımı ekle

## Doğrulama

```sql
-- 1) Örnek müşteri için tanımlı kaynak kuralları (bulutwebui)
SELECT crm_accountid, data_source, match_method, match_value, priority, enabled
FROM   gui_crm_customer_source_mapping
WHERE  crm_accountid = :accountid
ORDER  BY data_source, priority;
-- ⇒ power_lpar / ibm satırı var mı? backup_netbackup satırı hangi match_method ile?

-- 2) IBM LPAR tarafında o müşteriye ait ne var (isim deseni ile arama)
SELECT lparname, lpar_details_servername, lpar_details_state,
       lpar_processor_currentvirtualprocessors AS vcpu,
       ROUND(lpar_memory_logicalmem::numeric/1024,2) AS ram_gb, "time"
FROM   public.ibm_lpar_general
WHERE  "time" > now() - interval '1 day'
  AND  (lparname ILIKE '%'||:musteri||'%' OR lpar_details_servername ILIKE '%'||:musteri||'%')
ORDER  BY lparname;

-- 3) LPAR adlandırma deseni genel görünüm (prefix var mı?)
SELECT split_part(lparname,'-',1) AS ilk_parca, COUNT(DISTINCT lparname) AS lpar
FROM   public.ibm_lpar_general
WHERE  "time" > now() - interval '1 day'
GROUP  BY 1 ORDER BY 2 DESC LIMIT 40;

-- 4) NetBackup'ta o müşterinin işleri
SELECT workloaddisplayname, policytype, jobtype, COUNT(*) AS job,
       SUM(kilobytestransferred)/1024/1024 AS gb, AVG(dedupratio) AS dedup,
       MAX(starttime) AS son_job
FROM   public.raw_netbackup_jobs_metrics
WHERE  starttime > now() - interval '30 days'
  AND  workloaddisplayname ILIKE '%'||:musteri||'%'
GROUP  BY 1,2,3 ORDER BY job DESC;

-- 5) NetBackup adlandırma deseni (prefix analizi — TASK-16 girdisi)
SELECT split_part(workloaddisplayname,'-',1) AS prefix, COUNT(DISTINCT workloaddisplayname) AS istemci
FROM   public.raw_netbackup_jobs_metrics
WHERE  starttime > now() - interval '30 days'
GROUP  BY 1 ORDER BY 2 DESC LIMIT 50;
```

```bash
# API cevabında IBM ve NetBackup blokları
curl -s "http://10.134.52.250:8001/api/v1/customers/<MUSTERI>/resources?range=30d" \
 | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('anahtarlar:', list(d.keys()))
print('power/ibm:', json.dumps(d.get('power') or d.get('ibm'), ensure_ascii=False)[:400])
print('backup:',    json.dumps(d.get('backup_totals') or d.get('totals',{}).get('backup'), ensure_ascii=False)[:400])
"
curl -s "http://10.134.52.250:8001/api/v1/crm/aliases" | python3 -m json.tool | head -60
```

## Kabul kriterleri
- [ ] En az 3 örnek müşteride IBM LPAR verisi Customer View'da görünüyor (vCPU, RAM, LPAR sayısı)
- [ ] NetBackup paneli veri + kontroller (job sayısı, başarı oranı, dedup, son job) gösteriyor
- [ ] "Eşleştirme tanımlı değil" ile "değer 0" ekranda ayrışıyor
- [ ] API değerleri doğrulama SQL'leriyle ±%1 uyumlu
- [ ] Eşleşmesi olmayan müşterilerde eski davranış bozulmamış (regresyon)

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, task/query-map/10-customer-crm.md,
task/query-map/03-ibm-power.md, task/query-map/06-backup-dr.md,
datalake-platform-knowledge-base/adrs/ADR-0008-crm-customer-identity-resolution.md,
services/customer-api/app/services/customer_mapping_resolver.py,
src/pages/customer_view.py, src/utils/visibility.py, src/utils/crm_source_mapping_ui.py

Görev: Customer View'da IBM sanallaştırma ve NetBackup verilerinin görünmemesini düzelt.

1. Teşhis önce: bir örnek müşteri için /api/v1/customers/{name}/resources cevabını dök.
   IBM ve NetBackup bloklarının (a) hiç yok mu (b) boş mu (c) 0 mı olduğunu ayırt et ve raporla.
2. gui_crm_customer_source_mapping'e yeni bir data_source ekle: 'power_lpar'.
   - customer_mapping_resolver.py: ilike_by_source zincirine ekle, sql_pattern_for_match ile uyumlu olsun
   - customer.py sorgularında ibm_lpar_general filtresi bu kaynağın desenlerini kullansın
     (lparname ve lpar_details_servername üzerinde)
   - src/utils/crm_source_mapping_ui.py: Settings ekranında yeni kolon olarak göster
   - Migration: sql/migrations/ altına idempotent bir seed/constraint güncellemesi
3. NetBackup: match_method='prefix' desteğinin uçtan uca çalıştığını doğrula (TASK-16 ile ortak).
4. Customer View'da NetBackup paneline "kontroller" bloğu ekle:
   job sayısı, başarı oranı (status=0 oranı), ortalama dedupratio, son job zamanı.
5. visibility.py kullanımını gözden geçir: "eşleştirme kuralı yok" durumu ile "değer 0" durumunu
   ekranda ayır. Kural yoksa uyarı rozeti + Settings'e link göster.
6. tests/: power_lpar çözümleyicisi ve prefix eşleşmesi için unit test (TDD).

Kısıt: Cross-DB JOIN yok (ADR-0013). Mevcut müşterilerde regresyon olmamalı.
```

## Bağımlılık
TASK-16 (NetBackup prefix'leri) ve TASK-15 (alias düzeltme butonu) bu maddeyle aynı tabloyu kullanır —
üçünü aynı sprintte planlayın.
