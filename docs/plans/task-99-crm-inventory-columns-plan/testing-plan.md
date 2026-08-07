# Testing Plan — TASK-99

Requirement ve acceptance ID'leri `spec.md`'den, adım numaraları
`implementation-plan.md` §3'ten gelir. Burada metin tekrarlanmaz.

**Koşum ortamı:** `FACT` — repo kökünde `.venv` var, Python **3.11.15**.
Sistem `python3` (3.9) bu testleri kırar.

```bash
.venv/bin/python -m pytest tests/ -q
```

**Baseline:** `FACT` — 2026-08-07'de çalıştırıldı, ilgili beş dosyada
**58 test yeşil** (0,80 sn):

```
tests/test_crm_inventory_report.py             37
tests/test_crm_inventory_replication_columns.py  7
tests/test_crm_inventory_overview_page.py        6
tests/test_crm_inventory_os_licence_columns.py   5
tests/test_crm_inventory_export.py               3
```

---

## Yazma kuralı

Her testin yanında **hangi bozulmayı yakaladığı** yazılıdır. Bu cümleyi
kuramadığın testi yazma — tautoloji, sözleşmenin kopyası veya iç yapı testi olur.

Özellikle: kolon testleri beklenen listeyi **elle yazmaz**, `_SPINE` sabitinin
kendisiyle karşılaştırır. Elle yazılmış liste sözleşmenin ikinci bir kopyasıdır;
sözleşme bozulduğunda test de beraber bozulur ve hiçbir şey yakalamaz.

---

## 1. Unit — kolon üretimi

| # | Test | Hangi bozulmayı yakalar |
|---|---|---|
| `TEST-U-001` | Dokuz profilin her biri için `columns_for_family()` çıktısının ilk 7 slotu `_SPINE` ile birebir eşleşir (`AC-001`) | Bir profil omurgadan sapar; kolon konumu yine gruba göre kayar — task'ın çözmeye geldiği şey geri gelir |
| `TEST-U-002` | Dokuz profilin hepsinde son kolonun `id`'si `unit_price_fmt` (`AC-002`) | `os_licence`'taki bugünkü sapma (Birim Fiyat sondan ikinci) düzeltilmeden kalır veya yeni bir profil aynı hatayı tekrarlar |
| `TEST-U-003` | Gruba özel kolonların hepsi slot 7 ile son kolon arasında; hiçbiri omurga slotlarının arasında değil (`AC-003`) | NetBackup dedup üçlüsü bugünkü gibi Used↔Free arasında bırakılır; omurga kâğıt üstünde kalır |
| `TEST-U-004` | `_SPINE_OVERRIDES` ve `_GROUP_BLOCKS` içindeki **her** `id`'nin `prepare_service_row()` çıktısında karşılığı var | `BUG-001`'in tekrarı — üreticisi olmayan bir kolon eklenir ve ekranda sessizce boş render olur |
| `TEST-U-005` | `virt_*` profilinde `Used` kolonu **listede var** ve hücre `—` (`REQ-F-004`, D-6) | `hide_used` kolon düşürmeyi bıraktığında hücre ezilmez; sanallaştırma tablolarında bilinçli gizlenmiş sayı geri gelir |
| `TEST-U-006` | `os_licence` slot 4'te `licence_detected_fmt`, slot 7'de `licence_gap_fmt` (`REQ-F-005`) | Slot yeniden kullanımı yerine kolon ekleme yapılır; OS Licence tablosu omurgadan dört kolon sapar |

## 2. Unit — `delta_fmt` (`BUG-001`)

| # | Test | Hangi bozulmayı yakalar |
|---|---|---|
| `TEST-U-007` | `used_qty=12, crm_sold_qty=10, unit="vCPU"` → `delta_fmt` işaretli fark gösterir (`AC-007`) | Kolon tanımlı kalıp üreticisi eksik kalır — bugünkü hata |
| `TEST-U-008` | `used_qty=None` veya `crm_sold_qty=None` → `delta_fmt == "—"` | Eksik veride sayı uydurulur veya `None`/`nan` ekrana basılır |

## 3. Contract — flat view ve export

| # | Test | Hangi bozulmayı yakalar |
|---|---|---|
| `TEST-C-001` | `flat_columns()` 19 kolonu `REQ-F-006` sırasıyla döndürür (`AC-004`) | Flat tablo yine eksik kalır; task'ın ikinci cümlesi karşılanmaz |
| `TEST-C-002` | Flat'te `total_fmt` ve `licence_detected_fmt` **ayrı** kolonlar (slot yeniden kullanımı uygulanmaz) | Grouped'a ait slot eşlemesi flat'e sızar; karışık satır taşıyan tabloda tek kolon iki farklı anlam taşır |
| `TEST-C-003` | Export `Services` sayfasının kolon başlıkları `flat_columns()` başlıklarıyla ve sırasıyla birebir (`AC-005`) | Rapor ekrandan ayrışır; bugünkü ham anahtar başlıkları (`crm_sold_fmt`) geri gelir |
| `TEST-C-004` | `Services` sayfasında `panel_key`, `sellable_profile`, `has_infra_source`, `inventory_free_mode`, `data_quality`, `used_is_allocation` **yok** (`AC-005`) | İç alanlar müşteriye giden rapora sızmaya devam eder |
| `TEST-C-005` | `Services_raw` sayfası var ve ham alanları taşıyor (`AC-006`) | Ham sayıya erişim sessizce kaybolur; analiz yapan taraf veri kaybeder |
| `TEST-C-006` | Export hücrelerinde `\n` yok; blok değerler ` · ` ile düzleşmiş (D-11) | Excel'de hücre kırılır, PDF `cell()` render'ı bozulur |
| `TEST-C-007` | `filter_mode="infra"` ile export yalnız infra satırlarını içerir (`REQ-F-009`) | Kolon işi sırasında filtre akışı kırılır — mevcut `test_build_inventory_export_sheets_respects_filter` bunu zaten koruyor, kapsam genişletilir |

## 4. Regression

| # | Test | Hangi bozulmayı yakalar |
|---|---|---|
| `TEST-R-001` | Mevcut **58 test** yeşil; kırılanlar yeni sözleşmeye göre **güncellenir, silinmez** (`AC-009`) | Kolon sırası değişikliği yan etkiyle başka davranışı bozar ve test silinerek örtülür |
| `TEST-R-002` | `INVENTORY_REPORT_SCHEMA_VERSION` `v5` değil (`AC-008`) | Sürüm artırılmadan çıkılır; tarayıcıda eski DataTable state'i yeni kolon setine yapışır (`RISK-002`) |

**Kırılması beklenenler:** `test_crm_inventory_os_licence_columns.py` (5) ve
`test_crm_inventory_replication_columns.py` (7) kolon sırasını doğrudan kilitliyor;
Birim Fiyat ve slot değişikliğiyle kırılmaları **beklenen** davranıştır.
`test_crm_inventory_export.py` (3) Adım 7'de güncellenecek.

## 5. Acceptance validation — tarayıcı

`FACT` — Kolon konumu ve PDF okunabilirliği koddan doğrulanamaz; ikisi de
görsel özellik.

| # | Doğrulama | Hangi bozulmayı yakalar |
|---|---|---|
| `TEST-A-001` | `/crm/inventory-overview` açılır, dokuz grubun accordion'u açılır, ortak kolonların aynı indekste olduğu görsel kontrol edilir | Testler yeşil ama ekranda kolonlar hâlâ kaymış — sözleşme doğru, uygulama yanlış |
| `TEST-A-002` | Flat görünüme geçilir; 19 kolon görünür ve yatay scroll çalışır | Kolon taşması tabloyu kullanılamaz hale getirir |
| `TEST-A-003` | Excel indirilir, `Services` sayfası ekrandaki tabloyla karşılaştırılır | Kolon eşleşmesi testte geçer ama gerçek dosyada bozuk çıkar |
| `TEST-A-004` | PDF indirilir, 19 kolonun okunabilirliği kontrol edilir (`REQ-NF-005`) | Landscape A4'te 19 kolon ≈14,4 mm/kolon; hücre metni sığmazsa okunamaz |

**PDF için not:** `FACT` — bugünkü export ham + formatlanmış alanları birleştirdiği
için 60+ kolon üretiyor, yani PDF **zaten okunamaz** durumda. 19 kolona inmek bunu
iyileştiriyor; `TEST-A-004` bir regresyon kontrolü değil, kazanımın teyidi.

---

## 6. Rollback

Bu iş **tek commit serisiyle geri alınabilir** — migration yok, şema değişikliği
yok, veri yazılmıyor, feature flag gerekmiyor.

| Senaryo | Aksiyon |
|---|---|
| Kolon sırası canlıda yanlış görünüyor | `git revert` — sunum katmanı, yan etkisi yok |
| Yalnız export bozuk, ekran doğru | Forward-fix: Adım 7 commit'i tek başına revert edilir; Adım 1-6 bağımsız |
| `Used` kolonu sanallaştırmada yanlış sayı gösteriyor (D-6 kaçırılmış) | Forward-fix: `build_report_table` hücre ezme satırı eklenir; revert gerekmez |
| Tarayıcıda eski tablo state'i yapıştı | Şema sürümü artırılmamış demektir; `INVENTORY_REPORT_SCHEMA_VERSION` bump'ı ile forward-fix |

**Deploy notu:** `FACT` — dc13 k8s değil docker compose (`/opt/Datalake-Platform-GUI`,
GUI `:8050`). Rollback = önceki imajla yeniden build. Statik varlık ya da JS bundle
üretimi bu işte yok; değişiklik saf Python.

---

## 7. Kayda değer yan bulgu

`FACT` — Test koşumunda uyarı: `dash_table.DataTable` ileride Dash'ten
kaldırılacak, `dash-ag-grid` öneriliyor. Bu iş kapsamında **değil**; ama kolon
sözleşmesi tek bir omurgada toplandığı için ileride ag-grid'e geçiş bugünkünden
ucuz olur.
