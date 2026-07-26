# GUI — Haftalık Çalışma Planı (Datalake Platform Web UI)

**Hazırlanma:** 2026-07-26 · **Kapsam:** `Datalake-Platform-GUI` (Dash frontend + FastAPI mikroservisleri)
**Uygulayıcı:** Cursor / Claude Code (her madde için hazır prompt bloğu var)
**Ortam/doğrulama rehberi:** [`00-ortam-ve-dogrulama-rehberi.md`](00-ortam-ve-dogrulama-rehberi.md)
**Kararlar kütüğü:** [`KARARLAR.md`](KARARLAR.md) — kapsam tartışması burada kapanır, önce buraya bakın

---

## 1. Bu haftanın maddeleri (19 kalem)

| # | Madde | Tip | Efor | Durum | Dosya |
|---|-------|-----|------|-------|-------|
| 01 | CRM Inventory cache optimizasyonu (sayfa çöküyor) | Perf/Backend | M | Net | [TASK-01](TASK-01-crm-inventory-cache.md) |
| 02 | Endpoint kontrolü + veri doğruluğu (Loki baseline) | Veri doğrulama | L | Net | [TASK-02](TASK-02-endpoint-loki-baseline.md) |
| 03 | Power sekmesinin kaldırılması | UI temizliği | S | Net | [TASK-03](TASK-03-power-sekmesi-kaldirma.md) |
| 04 | Hyperconverged unit / unit price mantık hatası | Hesaplama | M | Net | [TASK-04](TASK-04-hyperconverged-unit-price.md) |
| 05 | DC11 backup veri akışı (0 geliyor) | Veri akışı | M | Net | [TASK-05](TASK-05-dc11-backup-akis.md) |
| 06 | Customer View: IBM sanallaştırma + NetBackup eksikleri | Veri/Backend | M | Net | [TASK-06](TASK-06-customer-view-eksik-veri.md) |
| 07 | CRM fatura görüntüleme + manuel güncelleme akışı | Feature | L | Net | [TASK-07](TASK-07-crm-fatura-akisi.md) |
| 08 | ITSM mapping analizi | Analiz | ? | **Netleştirilecek** | [TASK-08](TASK-08-itsm-mapping-analizi.md) |
| 09 | VMware / Zerto (sarı alanlar) çevrimi | Entegrasyon | M | Net | [TASK-09](TASK-09-vmware-zerto-cevrim.md) |
| 10 | CRM Inventory'e network + switch eklenmesi | Feature | M | Net | [TASK-10](TASK-10-crm-inventory-network-switch.md) |
| 11 | DC View Network sayfası performans + loading | Perf/UX | M | Net | [TASK-11](TASK-11-dcview-network-perf.md) |
| 12 | Backup internet kullanımı faturalandırması | Feature | ? | **Netleştirilecek** | [TASK-12](TASK-12-backup-internet-faturalama.md) |
| 13 | Customer ekranında altyapı bilgilerinin gizlenmesi | Yetki/UI | S | Net | [TASK-13](TASK-13-customer-altyapi-gizleme.md) |
| 14 | Network faturalandırma: veri-bazlı hesap + yarı cache | Hesaplama/Cache | M | Net | [TASK-14](TASK-14-network-faturalama-cache.md) |
| 15 | Alias eşleştirme düzeltme butonu (Eşleşmeyen Veriler) | Feature/UX | M | Net | [TASK-15](TASK-15-alias-duzeltme-butonu.md) |
| 16 | NetBackup müşteri prefixleri | Veri/Config | S | Net | [TASK-16](TASK-16-netbackup-prefixleri.md) |
| 17 | Domain hizmeti hesaplama altyapısı | Feature | M | Kısmen net | [TASK-17](TASK-17-domain-hizmeti.md) |
| 18 | Colocation hizmeti hesaplama altyapısı | Feature | M | Net | [TASK-18](TASK-18-colocation-hizmeti.md) |
| 19 | USB Port hizmetinin eklenmesi | Feature | S | **Netleştirilecek** | [TASK-19](TASK-19-usb-port-hizmeti.md) |

Efor: S ≈ yarım gün · M ≈ 1–2 gün · L ≈ 3+ gün

### İki ana eksen (2026-07-26 oturumu)

Yukarıdaki 19 maddeye ek olarak, iki stratejik iş kalemi tanımlandı:

| # | Madde | Tip | Efor | Durum | Dosya |
|---|-------|-----|------|-------|-------|
| **M1** | Ingest freshness — "erişim var ama veri geliyor mu?" | Monitoring | L | Karar verildi (K-03) | [TASK-M1](TASK-M1-ingest-freshness.md) |
| **B1** | NetBackup faturalama tabanı mutabakatı | Analiz | S | Karar bekliyor (K-01) | [TASK-B1](TASK-B1-netbackup-fatura-tabani.md) |
| **B2** | NetBackup DC View satılabilir alan | Backend | M | Net | [TASK-B2](TASK-B2-netbackup-dcview-sellable.md) |
| **B3** | Veeam / Zerto replikasyon eşleştirmesi | Hesaplama | L | Karar verildi (K-02) | [TASK-B3](TASK-B3-veeam-zerto-replikasyon.md) |
| **B4** | Nutanix backup eşleştirmesi | Hesaplama | M | Net | [TASK-B4](TASK-B4-nutanix-backup.md) |

Sonraki monitoring adımları (M1'den sonra): **M2** vCenter parent rollup · **M3** dual-proxy matrisi (yarım günlük) · **M4** backup coverage.

---

## 2. Neden bu sıra — bağımlılık grafiği

```
TASK-M1 (ingest freshness)  ← monitoring zincirinin 4. halkası
   ├── TASK-05 (DC11 backup) ← kök nedeni burada görünür
   └── TASK-B2/B3/B4         ← backup verisinin güvenilirliği buna bağlı

TASK-B1 (NetBackup fatura tabanı — ANALİZ)
   ├── TASK-B2 (NetBackup DC View)
   └── TASK-B4 (Nutanix backup — aynı soru)

TASK-16 (NetBackup prefix) ─┬─ TASK-06 (Customer View)
                            └─ TASK-B1 (müşteri bazlı mutabakat)

TASK-02 (Loki baseline endpoint kontrolü)
   ├── TASK-05 (DC11 backup)        ← aynı doğrulama yöntemi
   ├── TASK-06 (Customer View eksik)← aynı kaynak/eşleşme sorusu
   └── TASK-16 (NetBackup prefix)   ← eşleşmenin config tarafı

TASK-01 (Inventory cache)  → TASK-10 (network/switch satırları eklenince yük artar)
TASK-03 (Power kaldır)     → TASK-04'ten ÖNCE (kaldırılan aileyi düzeltmeyelim)
TASK-14 (network billing)  → TASK-11 (aynı endpoint ailesi, birlikte test edilir)
TASK-15 (alias butonu)     → TASK-16 ve TASK-06'nın operasyonel çözümü
TASK-17/18/19              → TASK-10 ile aynı registry/mapping altyapısını kullanır
```

### Önerilen haftalık akış

| Gün | Odak |
|-----|------|
| **1** | TASK-02 (baseline kontrol, Can ile), TASK-03 (Power kaldırma — hızlı kazanım), TASK-05 tanı |
| **2** | TASK-01 (inventory cache), TASK-05 düzeltme, TASK-16 |
| **3** | TASK-04, TASK-06, TASK-13 |
| **4** | TASK-11 + TASK-14 (network ikilisi), TASK-15 |
| **5** | TASK-10 + TASK-17/18 (registry genişletme), TASK-09 |
| **Sürekli** | TASK-07 (uzun soluklu), TASK-08/12/19 için istek toplama toplantısı |

> **Güncel öncelik (2026-07-26 sonrası):** TASK-B1 (yarım gün analiz) ve TASK-M1 (ingest freshness)
> haftanın başına alınmalı — ikisi de aşağı akıştaki birçok maddeyi blokluyor.
> TASK-03 ve TASK-M3 hızlı kazanım olarak araya sıkıştırılabilir.

---

## 3. Ortak mimari bilgisi (her madde bunu varsayar)

```
Tarayıcı → Dash (app.py, src/pages/*) → src/services/api_client.py (HTTP)
        → FastAPI servisi (datacenter-api / customer-api / crm-engine / query-api / admin-api)
        → app/services/*_service.py  (orkestrasyon + hesap)
        → app/adapters/*             (şema köprüsü)
        → app/db/queries/*.py        (SQL)
        → PostgreSQL
```

**İki veritabanı vardır — karıştırmayın:**

| DB | İçerik | Örnek tablolar |
|----|--------|----------------|
| **bulutlake** (datalake, `10.134.16.6:5000`) | Ham telemetri + discovery | `vm_metrics`, `nutanix_vm_metrics`, `ibm_lpar_general`, `raw_netbackup_*`, `raw_zerto_*`, `raw_veeam_*`, `discovery_crm_*`, `discovery_netbox_*`, `loki_locations`, `raw_zabbix_network_*` |
| **bulutwebui** (WebUI DB) | Uygulamaya özel konfig | `gui_crm_service_pages`, `gui_crm_service_mapping_seed/_override`, `gui_crm_customer_alias`, `gui_crm_customer_source_mapping`, `gui_crm_price_override`, `gui_crm_threshold_config`, `gui_panel_definition`, `gui_panel_result_snapshot` |

**Cross-DB JOIN yoktur** — CRM ↔ altyapı eşleştirmesi Python katmanında yapılır (ADR-0013).

**Servis portları:** app 8050 · datacenter-api 8000 · customer-api 8001 · query-api 8002 · chatbot 8010 · admin-api 8060 · crm-engine 8070 · hmdl-api 8080

---

## 4. CRM ↔ altyapı eşleştirmesi nasıl çalışıyor (kritik — 6 maddeyi ilgilendirir)

Üç ayrı eşleştirme ekseni var; hangi maddede hangisine dokunacağınızı karıştırmayın:

### ⚠️ İki paralel eşleştirme sistemi var — karıştırmayın

| Sistem | Kapsam | Ne taşır |
|---|---|---|
| `shared/sellable/panel_mapping.py` | **~222 SKU'nun hepsi** (backup, network, colocation, DNS, lisanslar dahil) | isim kuralı → `panel_key` |
| `shared/matching/product_matching_registry.yaml` (ADR-0024) | **36 SKU** | `panel_key` + **`infra_tables`** + `match_status` |
| `gui_panel_definition` + infra_source | panel → altyapı sorgusu | DC bazlı hesap |

Backup için ürün→panel eşlemesi **zaten var** (`backup_netbackup_storage`,
`backup_veeam_replication_*`, `backup_zerto_replication_*`, `backup_image_hyperconverged`,
`backup_remote_nutanix`). Eksik olan panel→altyapı bağlantısı ve DC compute endpoint'i —
`_FAMILY_COMPUTE_ENDPOINT` yalnızca `virt_classic` ve `virt_hyperconverged` tanıyor.
**DC View'da backup satılabilir alanının görünmemesinin kök nedeni budur** (TASK-B2).

### (a) Ürün → panel eşleştirmesi (*hangi CRM ürünü hangi altyapı metriğiyle karşılaştırılır*)

```
config/crm_service_mapping.yaml         (insan-okur registry)
        ↓ shared/service_mapping/generate_seed_sql.py
gui_crm_service_mapping_seed  +  gui_crm_service_pages     (DB seed)
        ↓ operatör override (Settings › CRM › Service mapping)
gui_crm_service_mapping_override
        ↓
v_gui_crm_product_mapping   ← efektif eşleşme view'ı
```
Ek olarak **`shared/matching/product_matching_registry.yaml`** (ADR-0024) her `productnumber` için
`panel_key`, `family`, `match_status`, `infra_tables` tutar. **Şu an 222 CRM ürününden yalnızca 36'sı kayıtlı.**
TASK-10 / 17 / 18 / 19 doğrudan bu dosyayı genişletir.

### (b) CRM hesabı → müşteri kimliği (*hangi CRM account hangi kanonik müşteri*)

`gui_crm_customer_alias` (ADR-0008): `crm_accountid ↔ canonical_customer_key ↔ netbox_musteri_value`

### (c) Müşteri → veri kaynağı kuralları (*müşterinin verisi her kaynakta nasıl bulunur*)

`gui_crm_customer_source_mapping`: `(crm_accountid, data_source, match_method, match_value, priority)`

Mevcut `data_source` değerleri:
`physical_device`, `virtualization`, `netbox_vm_customer`, `backup_veeam`, `backup_zerto`,
`backup_netbackup`, `storage_ibm`, `s3_icos`, `itsm_servicecore`

`match_method`: `exact` · `contains` · `prefix` · `suffix` · `id_exact`

> **Tespit:** IBM Power / LPAR için ayrı bir `data_source` **yok** — Customer View'da IBM
> sanallaştırma verisinin gelmemesinin en olası kök nedeni bu (bkz. TASK-06).
> NetBackup prefix'leri de bu tabloya `data_source='backup_netbackup', match_method='prefix'`
> olarak yazılacak (bkz. TASK-16).

Çözümleyici: `services/customer-api/app/services/customer_mapping_resolver.py`
UI: `src/utils/crm_source_mapping_ui.py` → Settings › Integrations › CRM aliases
API: `GET/PUT /api/v1/crm/aliases`, `PUT /api/v1/crm/aliases/{crm_accountid}/source-mappings`

---

## 5. Ortak çalışma kuralları (her madde için geçerli — DoD)

1. **Önce ölç, sonra kodla.** Her madde için `00-ortam-ve-dogrulama-rehberi.md`'deki SQL/curl kontrolünü çalıştırıp
   *mevcut* değeri not alın; düzeltme sonrası aynı kontrolü tekrarlayın. Öncesi/sonrası aynı dosyaya yazılır.
2. **Şemayı varsayma, doğrula.** Tablo/kolon adları branch'e göre değişmiş olabilir
   (`datacenter_metrics` ↔ `*_performance_metrics` geçişi sürüyor). Kod yazmadan önce
   `information_schema.columns` ile kontrol edin.
3. **Test → Prod.** Her değişiklik önce `10.134.52.250`'de smoke edilir, sonra aynı commit `10.134.52.251`'e promote edilir.
   Prod'a doğrudan deploy yok.
4. **Cache semantiği bozulmayacak.** "Yeni veri gelmeden eski veri silinmez" ilkesi (`docs/CACHE_STRATEGY_COMPARISON.md` §4a).
   TTL ≥ 4 × refresh aralığı; `{key}:last_good` shadow key korunur.
5. **Panel görünürlük kuralı.** Kapsamda (DC/müşteri) veri yoksa panel/sekme **hiç render edilmez**, boş grafik gösterilmez
   (`docs/PROJECT_STANDARDS.md` §3).
6. **TDD.** `tests/` altında ilgili testi önce yazın; `shared/` içindeki saf hesap fonksiyonları unit test edilebilir.
7. **Migration'lar idempotent.** WebUI DB değişiklikleri `sql/migrations/` + `gui_schema_migrations` üzerinden.
8. **Loading UX.** Yeni bekleme durumları `docs/LOADING_UX_DESIGN.md` standardına uyar (skeleton + iki fazlı shell).
9. **Dil.** Yeni UI metinleri İngilizce (repo İngilizce'ye geçiş halinde); mevcut Türkçe etiketlere dokunulan yerde İngilizceye çevirin.
10. **Commit formatı:** `feat(alan): …` / `fix(alan): …` / `perf(alan): …` / `docs(alan): …` — mevcut git geçmişiyle aynı.

---

## 6. Netleştirilmesi gereken konular (toplantı gündemi)

| Madde | Kime sorulacak | Sorulacak soru |
|-------|----------------|----------------|
| TASK-02 | **Murat Bey / Can** | Loki baseline: hangi tablo/endpoint referans alınacak, sapma toleransı ne? |
| TASK-05 | **Can** | DC11 NiFi akışları duruyor mu, yoksa DC attribution regex mi hatalı? |
| ~~TASK-07~~ | ~~Satış / CRM~~ | ✅ **K-04: sales order** — karar verildi |
| TASK-B1 | **Satış** | NetBackup GB'si pre-dedup mu post-dedup mu faturalanıyor? (önce mutabakat raporu) |
| TASK-B3 | **Altyapı / Satış** | Zerto disk = hedef disk mi, journal dahil mi? Replika VM'ler billable virt'ten düşülüyor mu? |
| TASK-B4 | **Satış** | `000BLT-45` ve `000BLT-221` ayrı mı hesaplanacak? |
| TASK-M1 | **Can** | "Veri gelmiyor" eşiği collector başına ne? Ekran hangi repoya? Alarm istenecek mi? |
| TASK-08 | **?** | ITSM mapping analizinin çıktısı ne — rapor mu, otomatik eşleştirme mi? |
| TASK-12 | **?** | Backup internet kullanımı hangi metrikten ölçülecek, birim ve fiyat kalemi ne? |
| TASK-13 | **Can / Sezgin Bey** | Müşteriden gizlenecek alanların tam listesi (switch portları + ne?) |
| TASK-19 | **Satış / CRM** | USB Port hizmeti CRM kataloğunda **yok** (222 üründe eşleşme çıkmadı) — yeni SKU mu açılacak? |

---

## 7. Riskler

| Risk | Etki | Önlem |
|------|------|-------|
| Prod cache refresh ~15 dk sürüyor | Deploy penceresi uzuyor | Mesai dışı promote; `--skip-cache` ile ayrı adım |
| `discovery_crm_*` snapshot'ı bayat (elimizdeki CSV 2026-05-04) | Yanlış SKU/eşleşme | Registry değişikliği öncesi canlı `discovery_crm_products` sorgulanır |
| CRM ürün kataloğu ile satış satırları arasında 19 orphan productid | Inventory'de "unmapped" şişer | TASK-10/17/18'de orphan listesi ayrıca raporlanır |
| Power kaldırma (TASK-03) sellable/permission zincirini kırabilir | DC/Customer sayfaları patlar | Kaldırma değil **feature-flag** ile gizleme önerilir (TASK-03'e bkz.) |
| NetBox VM tablosunda 19.479 duplike isim | Sayımlar şişer | Her join öncesi `DISTINCT ON (lower(name))` |
