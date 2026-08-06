# TASK-94 — Tanım Soruları (Offsite Disk / Backup / Yönetim Hizmetleri)

**Status:** in-progress — 1. ve 2. adım tamamlandı 2026-08-06
**Created:** 2026-08-06
**Level:** 1 — Micro
**Classification gerekçesi:** Çıktı tek bir soru dokümanı; kod, şema, API veya
deployment değişmiyor — 15 sorunun hiçbiri yükseltici tetiklemiyor (taban = L1).

**Kaynak:** Hermes TASK-94 "Tanım Soruları" · Bulutistan / BulutDL · due 2026-08-06
**Task metni:** "Offsite Disk (s3) ve Backup alanları için tanımlar sorulacak.
Yönetim hizmetleri (Veeam, Zerto, Windows vb.) netleştirilerek sorulacak."

## Summary

Bulutistan'a gönderilecek **tanım sorusu seti** üretilir. Soru seti üç aileden
oluşur: (A) Offsite Backup Disk Alanı (S3), (B) Backup alanlarının kapsamı,
(C) Yönetim hizmetleri (Veeam / Zerto / Windows).

Bu bir "bilmiyoruz, sorun" listesi değildir. Repo'da bugün **aynı ürün için
birbiriyle çelişen üç mapping katmanı** var; her soru "bugün şöyle davranıyoruz,
doğrusu bu mu?" biçiminde, kanıtı ve önerdiğimiz varsayılan cevabı ile sorulur.
Amaç: cevap gelmese bile varsayılanla ilerleyebilmek.

## Problem

CRM ürünü → GUI paneli eşlemesi üç ayrı yerde tanımlı ve üçü aynı ürün için
farklı cevap veriyor:

| Katman | Dosya | Ne sürüyor |
|---|---|---|
| page_key kuralları | `shared/service_mapping/embedded_rules.json` | sales-efficiency, CRM potential (`v_gui_crm_product_mapping`) |
| panel kuralları | `shared/sellable/panel_mapping.py` | sellable / sold-vs-used panelleri |
| matching registry | `shared/matching/product_matching_registry.yaml` (ADR-0024) | ürünün ölçülebilir altyapı karşılığı |

Çelişki tek başına bir bug değil — hangisinin doğru olduğunu **iş tarafı**
tanımlamadan düzeltilemez. TASK-94'ün işi bu tanımı yazılı almak.

## Current Behavior

Aşağıdakiler dosyadan okunarak doğrulandı (2026-08-06, `main` @ 7962bbb3).

**Offsite Backup Disk Alanı (S3) — `000BLT-70`**
- `embedded_rules.json:224` (öncelik 61) → `storage_s3`, GUI sekmesi `storage.s3`
  — yani **Storage** ürünü sayılıyor. Aynı kural `IBM ICOS S3` ve `Bulut Depolama`
  ürünlerini de aynı kovaya atıyor.
- `panel_mapping.py:104` → `backup_offsite_s3` — yani **Backup** paneli.
- `product_matching_registry.yaml:93-98` → `match_status: documented`,
  `inventory_group: image_backup`; `usage_source`, `matching_rule` ve
  `infra_tables` **boş** → satılan miktarın karşılığı ölçülmüyor.

**Offsite Backup Disk Alanı (Veeam) — `000BLT-71`**
- `embedded_rules.json:223` (öncelik 60) → `backup_veeam_storage`.
- `panel_mapping.py:105` → `backup_offsite_veeam`.
- `product_matching_registry.yaml:99-104` → `documented`, altyapı kaynağı yok.

**Diğer backup sınırları**
- `embedded_rules.json:222` (öncelik 50): `Remote Backup Hizmeti (Nutanix)` →
  `virt_nutanix` (sanallaştırma). Registry `000BLT-221` ise `capacity` +
  `backup_remote_nutanix` diyor.
- `embedded_rules.json:214` (öncelik 34): `Hyperconverged İmaj Yedekleme` →
  `virt_hyperconverged_storage`. Registry `000BLT-45`: `comparison_only: true`,
  not: *"Hidden from CRM Inventory / unmatched until HC image sellable clarified"*.
- `IBM ICOS S3 Hizmeti` (`registry:175-181`): `documented`, `infra_tables` dolu
  ama `panel_key` **yok** → hiçbir panelde görünmüyor.

**Yönetim hizmetleri**
- `embedded_rules.json`'da `mgmt_*` kategorisi **hiç yok**. Öncelik 70 kuralı
  (`:225`) regex'i birebir `Veeam Replikasyon` içeriyor → *Veeam Replikasyon
  Yönetim Hizmeti* bu katmanda `backup_veeam` kapasitesi sayılıyor. Öncelik 71
  (`:226`) Zerto için aynı.
- `config/crm_service_mapping.yaml:297-377` ve `panel_mapping.py:154-181` ise
  ayrı bir `mgmt.*` ailesi tanımlıyor: `mgmt_replication_veeam` / `_zerto`
  (`Adet`), `mgmt_os_windows` / `_linux` / `_unix` (`per VM`), `mgmt_backup`
  (`Yedekleme Yönetimi`, per VM), `mgmt_security_soc` / `_siem`,
  `mgmt_active_directory`, `mgmt_support_7x24`.
- Registry `000BLT-151` (Veeam Yönetim) → `sold_noted_customer_phase`,
  `infra_tables: [raw_veeam_jobs_states]`. `000BLT-167` (Zerto Yönetim) → aynı
  statü, `usage_source: ""`, `matching_rule: "CRM den gelen data"`.
- **Windows registry'de hiç yok**: 40 kayıtlık registry'de `Windows` geçmiyor.
  Buna karşılık `shared/licensing/reconcile.py:9` ve
  `tests/test_licensed_os_no_double_count.py`, `MS Windows Lisans` ile
  `Standart Windows İşletim Sistemi Yönetim Hizmeti` ürünlerinin **aynı
  miktarlarda** geldiğini ve toplanmaması gerektiğini varsayıyor.

## 1. adım sonucu — 2026-08-06

Ölçüm yapıldı (`bulutlake` CRM tabloları, veri 06.08.2026 13:59). Sayılar teslim
dokümanında yaşıyor, buraya kopyalanmıyor:
`docs/crm/2026-08-06-tanim-sorulari.md`. Planın **üç varsayımı çürüdü**:

1. **`000BLT-70` / `000BLT-71` aktif hiçbir siparişte yok.** Soru "bunu nasıl
   ölçeriz"den "bu ürün hâlâ satışta mı"ya döndü. Aynı durum `000BLT-221` ve 16
   replication kapasite ürününün tamamında geçerli.
2. **Windows 1:1 varsayımı yanlış.** 268 müşterinin yalnız 74'ünde lisans ve
   yönetim hizmeti eşit; 42 müşteride lisans olmadan yönetim hizmeti var.
   `shared/licensing/reconcile.py`'ın dayandığı premise canlı veride tutmuyor.
3. **Asıl ağırlık beklenen yerde değil.** `000BLT-45` Hyperconverged İmaj
   Yedekleme 1,67 PB / 315 müşteri ile en büyük backup kalemi ve bugün CRM
   Inventory'de gizli. Öncelik sırası buna göre değişti (B1 ilk soru).

Ayrıca bir plan hatası düzeltildi: Veeam Yönetim Hizmeti'nin ürün numarası
`000BLT-166` değil **`000BLT-151`**.

**Veri kapsamı uyarısı:** CRM'den gelen 474 siparişin tamamı `Active`;
iptal/kapanmış sipariş ve `submitdate` gelmiyor. Bu yüzden "0" = *bugün aktif
siparişte yok*, "hiç satılmadı" değil. Katalogdaki 275 üründen 99'u aktif.

## Target Behavior

Bulutistan'a gönderilebilir tek bir doküman: **≤12 soru, 3 aile**, her soru için
(1) hangi ürün numarası, (2) bugün ne yapıyoruz + dosya:satır kanıtı,
(3) önerdiğimiz varsayılan cevap, (4) cevap farklı çıkarsa ne değişir.

Cevaplar geldiğinde tek bir yere yazılır (registry `match_status` + `page_key`),
uygulaması TASK-99'un işidir.

## Scope

- Üç ailedeki tanım boşluklarının **kanıtla** çıkarılması.
- Her boşluk için satış verisinden ağırlık ölçümü (kaç ürün, kaç müşteri, hangi UoM).
- ≤12 soruluk teslim dokümanının yazılması ve gönderilmesi.
- Gelen cevapların kaydedileceği yerin ve formatının sabitlenmesi.

## Out of Scope

- `embedded_rules.json`, `panel_mapping.py`, `crm_service_mapping.yaml` veya
  registry'de **kural değiştirmek** → TASK-99 (CRM Inventory düzenlemeleri).
- Yeni `mgmt_*` kategorisi eklemek, seed/override migration yazmak → TASK-99.
- Internal kaynak exclude mantığı → TASK-96.
- Üç mapping katmanını tek katmana indirmek (mimari karar) → cevaplar geldikten
  sonra ayrı planlanır; bu task karar vermez, soruyu sorar.

## Affected Files

- `docs/crm/2026-08-06-tanim-sorulari.md` — **oluşturulacak** teslim dokümanı
  (`docs/crm/` yeni klasör; mevcut tarihli seri idiomu `docs/cache-audit-2026-08-03/`
  ile uyumlu).
- `docs/plans/task-94-tanim-sorulari.md` — bu plan; 1. adımın bulguları
  "Current Behavior" altına eklenir.
- Aşağıdakiler **yalnız okunur, değişmez** (kanıt kaynağı):
  `shared/service_mapping/embedded_rules.json`,
  `shared/sellable/panel_mapping.py`,
  `shared/matching/product_matching_registry.yaml`,
  `config/crm_service_mapping.yaml`,
  `shared/licensing/reconcile.py`,
  `docs/CRM_SERVICE_MAPPING.md`.

## Implementation Steps

### 1. Kanıt boşluklarını kapat (veri)

Erişim yolu **doğrulanmadı** — adımın ilk işi, TASK-92/TASK-99'da kullanılan
bulutlake DB erişiminin (hmdl-api container üzerinden) çalıştığını teyit etmek.
Erişim yoksa: adım atlanır, sorular kural dosyalarındaki kanıtla sorulur ve
dokümanda ilgili satırlar `[miktar doğrulanmadı]` diye işaretlenir — soru seti
bu yüzden geciktirilmez.

Dört sorgu, dördü de `discovery_crm_products` + `salesorderdetails`
(+ `v_gui_crm_product_mapping`) üzerinden:

1. `000BLT-70`, `000BLT-71`, `000BLT-55/56/57` → satır sayısı, toplam miktar,
   `uomid_name`, farklı müşteri sayısı.
2. Adında `Yönetim Hizmeti` geçen tüm ürünler → aynı kolonlar. (Registry'de 40
   üründen yalnız 2'si yönetim hizmeti; CRM'de kaç tane olduğu bilinmiyor.)
3. `MS Windows Lisans` vs `Standart Windows İşletim Sistemi Yönetim Hizmeti` →
   müşteri bazında miktar karşılaştırması; `reconcile.py`'ın dayandığı **1:1
   varsayımı canlı veride tutuyor mu**.
4. Bu ürünlerden hangileri **hiç satılmamış** → satılmayan ürün soru setinden
   çıkarılır (gürültü).

Çıktı: her ürün için tek satırlık ağırlık tablosu, bu plana eklenir.

### 2. Soru dokümanını yaz

Her soru **dört alanla** yazılır, istisnasız:
`Ürün no · Bugünkü davranış (dosya:satır) · Önerdiğimiz varsayılan · Cevap farklıysa ne değişir`

Dil: cümleler Türkçe, teknik terimler İngilizce (`offsite`, `repository`,
`restore point`, `dedup`, `UoM`, `panel`).

**Aile A — Offsite Backup Disk Alanı (S3)**
- **A1** `000BLT-70` bir **object storage** ürünü mü, **backup** ürünü mü? Hangi
  sekmede görünmeli: Storage › Object Storage mı, Backup › Offsite mı?
  *Varsayılan önerimiz:* Backup › Offsite (registry ve panel katmanı böyle diyor;
  `embedded_rules.json:224` tek başına Storage diyor ve düzeltilecek olan o).
- **A2** Satılan miktarın kullanımı hangi altyapı kaynağından ispatlanır?
  `raw_s3icos_pool_metrics` ise, offsite backup bucket'ları normal object storage
  bucket'larından **hangi kurala göre** ayrılıyor (isim şablonu, vault, tenant)?
  *Varsayılan önerimiz:* ayrım kuralı yok → ölçülemez kabul edilir (`documented`).
- **A3** Satılan miktarın birimi ve referansı: **usable TB** mi, raw TB mi;
  dedup + compression **öncesi** mi **sonrası** mı? *Varsayılan önerimiz:*
  usable TB, dedup sonrası (aksi halde satılan/kullanılan hiçbir zaman tutmaz).
- **A4** `IBM ICOS S3 Hizmeti` (`000BLT-57`), `IBM ICOS S3 Ankara/İstanbul` ve
  `Bulut Depolama` aynı ürün ailesi mi? Bugün üçü tek kovada
  (`embedded_rules.json:224`), `000BLT-57`'nin paneli ise yok.

**Aile B — Backup alanları**
- **B1** `000BLT-71` (Veeam offsite) neyi ölçer — Cloud Connect repository kotası
  mı, iş bazlı yedek boyutu mu? Hangi tabloya bakılacak (`raw_veeam_jobs_states`
  bir job durum tablosu; kapasite tablosu değil)?
- **B2** **Replication backup mıdır?** Veeam/Zerto Replication satırları Backup
  toplamına dahil mi, yoksa DR olarak ayrı mı raporlanmalı? *Varsayılan önerimiz:*
  ayrı — replication bir restore point üretmez.
- **B3** `Remote Backup Hizmeti (Nutanix)` (`000BLT-221`) ve
  `Hyperconverged İmaj Yedekleme` (`000BLT-45`) backup mı, sanallaştırma storage'ı
  mı? `000BLT-45` bugün "HC image sellable clarified" notuyla envanterden **gizli** —
  sellable tanımı nedir?
- **B4** Bir backup ürününde **"kullanım" nedir**: korunan VM sayısı mı,
  repository doluluğu mu, geçerli restore point kapsamı mı? Offsite kopyanın
  tüketimi **kaynak DC'ye mi hedef DC'ye mi** yazılır?

**Aile C — Yönetim hizmetleri**
- **C1** `Veeam Replikasyon Yönetim Hizmeti` (`000BLT-166`) ve
  `Zerto Replikasyon Yönetim Hizmeti` (`000BLT-167`) **kapasite** satırı mı,
  **hizmet bedeli** mi? Miktarları Veeam/Zerto toplamına eklenmeli mi?
  *Varsayılan önerimiz:* hizmet bedeli — asla kapasiteye toplanmaz
  (`embedded_rules.json:225-226` bugün topluyor, düzeltilecek olan o).
- **C2** Windows: `MS Windows Lisans` ile
  `Standart Windows İşletim Sistemi Yönetim Hizmeti` her zaman 1:1 mi satılır?
  Biri diğeri olmadan alınabilir mi? **"Kaç Windows VM satıldı"** sorusunda hangisi
  otoritedir? *Varsayılan önerimiz:* lisans otoritedir, yönetim hizmeti ayrı
  gösterilir, ikisi toplanmaz.
- **C3** Hangi yönetim hizmetlerinin ölçülebilir bir altyapı karşılığı **var**?
  AD, SOC/SIEM, 7x24 destek için "sold-only, kullanım ölçülmez" kabul edilebilir mi?
- **C4** CRM Inventory'de yönetim hizmetleri **ayrı bir üst grup** mu olmalı,
  yoksa ilgili teknolojinin kendi sekmesinde ayrı satır mı? (Doğrudan TASK-99 girdisi.)

### 3. İç gözden geçirme

- Kendi verimizden cevaplayabileceğimiz her soru **silinir** — soru sormak
  ölçmemenin mazereti değil.
- Toplam soru sayısı ≤12; aşıyorsa en düşük etkili sorular birleştirilir.
- Her sorunun bir **sahibi** (kime soruluyor) ve cevap tarihi yazılır.

### 4. Teslim ve kayıt

- Doküman gönderilir; Hermes TASK-94'e yorum olarak sorular ve gönderim tarihi
  düşülür.
- Cevap geldikçe **tek yere** yazılır: `product_matching_registry.yaml` içindeki
  ilgili ürünün `match_status` / `panel_key` / `notes` alanları + kısa bir karar
  satırı. Aynı bilgi teslim dokümanına kopyalanmaz.
- Cevapsız kalan sorular için varsayılanımız yürürlüğe girer ve dokümanda
  "varsayımla ilerlendi" diye işaretlenir.

## Validation

- `docs/crm/2026-08-06-tanim-sorulari.md` içinde her sorunun dört alanı da dolu:
  `grep -c "Bugünkü davranış" docs/crm/2026-08-06-tanim-sorulari.md` çıktısı,
  soru sayısına eşit olmalı.
- Dokümandaki her `dosya:satır` referansı gerçek: her referans için
  `sed -n '<satır>p' <dosya>` çalıştırılır, iddia edilen içerik görülür.
- Adım 1 sorguları çalıştıysa: her ürün satırında miktar + müşteri sayısı var;
  çalışmadıysa ilgili satırlar `[miktar doğrulanmadı]` etiketli.
- Kural dosyalarında değişiklik yok: `git diff --name-only` çıktısı yalnız
  `docs/` altını gösterir.

## Acceptance Criteria

1. Soru sayısı ≤12 ve üç aile de temsil ediliyor (A/B/C).
2. Her sorunun önerdiğimiz bir varsayılan cevabı var — cevap gelmezse de
   ilerleyebiliyoruz.
3. Her soru en az bir CRM ürün numarasına (`000BLT-*`) bağlı.
4. Hiçbir soru, elimizdeki veriden kendi cevaplayabileceğimiz bir soru değil.
5. Hiç satılmamış ürün için soru sorulmuyor (adım 1 çalıştıysa).
6. Teslim dokümanı Türkçe cümle / İngilizce terim kuralına uyuyor.
7. TASK-94 Hermes'te yorumla birlikte kapatılabilir durumda.

## Risks

- **Cevap gecikirse** TASK-99 ve TASK-96 tanım bekler. Azaltma: her soruya
  varsayılan cevap konuyor; varsayılanla ilerlenip cevap gelince düzeltilir.
- **Cevap taksonomiyi değiştirirse** (örn. offsite S3 gerçekten Storage'sa)
  `override` tablosunda ve seed'de düzeltme gerekir — TASK-99 kapsamı, bu planın
  değil.
- **Çok soru sorma riski**: 12'yi aşan liste cevapsız kalır. Adım 3 bunun freni.
- **Kanıtsız soru riski**: DB erişimi yoksa ağırlık ölçülemez; sorular yine
  sorulabilir ama "kaç müşteriyi etkiliyor" bilgisi eksik kalır ve öyle işaretlenir.
