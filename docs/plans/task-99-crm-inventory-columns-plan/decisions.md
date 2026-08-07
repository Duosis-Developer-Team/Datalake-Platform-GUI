# Decisions — TASK-99

Bu paketteki mimari kararlar. Numaralar paket içinde tekildir ve yeniden kullanılmaz.

---

# ADR-001 — Kanonik kolon omurgası ve silme yasağı

## Status

`proposed` — 2026-08-07

## Context

CRM Inventory Overview'da hizmet tabloları dokuz farklı efektif kolon setiyle
render ediliyor (`columns_for_family()`, `crm_inventory_report.py:194`). Ortak
kolonların indeksi profile göre kayıyor: 5. kolon profile göre Used / Allocated /
Free / Lisanslanmalı olabiliyor, `Birim Fiyat` sekiz profilde son kolonken
`os_licence`'ta sondan ikinci. Kullanıcı accordion grupları arasında geçiş yaptığında
aynı bilgiyi aynı yerde bulamıyor — TASK-99'un doğduğu şikâyet bu.

Bağlı requirement'lar: `REQ-F-001` · `REQ-F-002` · `REQ-F-003` · `REQ-F-004` ·
`REQ-F-005` (bkz. `spec.md`).

Kısıt: iş yarına teslim, tek oturumluk. 58 mevcut test bu alanı çevreliyor.
Backend'e dokunulmayacak (`REQ-NF-001`).

## Decision

Tek bir **kanonik kolon omurgası** tanımlanır — `[Family] · Service · Unit ·
CRM Sold · Total · Used · Free · Unsold · «gruba özel blok» · Birim Fiyat` — ve
dokuz profilin hepsi bu omurgayı **aynı sırada** kullanır. Bir profil için anlamsız
olan omurga kolonu **listeden silinmez**; yerinde kalır ve `—` gösterir. Gruba özel
kolonlar yalnız `Unsold` ile `Birim Fiyat` arasına girer, omurga slotlarının arasına
sokulamaz. Bir profil bir omurga slotunu kendi alanıyla yeniden kullanabilir — slot
konumu sabit kalır, yalnız `id` ve başlık değişir — ve izin verilen yeniden
kullanımlar `spec.md` `REQ-F-005`'teki kapalı listeyle sınırlıdır.

## Alternatives Considered

**Alternatif 1 — Sadece göreli sıra sabit, silme serbest.** Omurga kolonlarının
birbirine göre sırası korunur ama profil için ilgisiz olan kolon tablodan çıkarılır.
Tablolar dar kalır, boş kolon olmaz.
*Seçilmedi:* silme kaydırma yapıyor. `virt_*`'ta Used silinince Free 5. sıraya
çıkıyor, `standard`'da 6. sırada kalıyor. Kullanıcı yine aynı yerde aynı bilgiyi
bulamıyor — yani asıl şikâyeti çözmüyor. Standardizasyonun tanımı "sıra korunur"
değil, "konum korunur".

**Alternatif 2 — Tek tip tablo: her grup 19 kolonu birden gösterir.** Grouped ve
flat aynı kolon setini kullanır, `columns_for_family()` neredeyse tamamen silinir.
Mutlak tutarlılık.
*Seçilmedi:* her accordion'a 6-8 boş kolon ekliyor. NetBackup dışı gruplarda dedup
üçlüsü, OS Licence dışı gruplarda lisans üçlüsü sürekli `—`. Standardizasyon
kazanılırken okunabilirlik kaybediliyor; grouped görünümün var olma sebebi
(dar, aileye özel tablo) ortadan kalkıyor.

## Consequences

**Kolaylaştırdığı:**
- Kolon konumu artık profile bağlı değil; yeni bir aile eklendiğinde kolon sırası
  kendiliğinden doğru geliyor.
- Kolon tanımı tek bir omurga + eklenti kuralına iniyor; bugün 12 elle yazılmış
  liste var, bakım maliyeti düşüyor.
- Flat superset (`REQ-F-006`) ve rapor eşitleme (`REQ-F-007`) aynı omurgadan
  türetilebiliyor — üç iş tek kaynağa bağlanıyor.

**Zorlaştırdığı:**
- Bazı tablolar boş kolon taşıyor. En kötü durum `os_licence`: slot yeniden
  kullanımından sonra bile `Used` ve `Free` ölü kalıyor (2 kolon).
- Tablolar bugünkünden geniş; yatay scroll daha sık devreye girecek
  (`_TABLE_STYLE_TABLE` zaten `overflowX: auto`).

**Yarattığı borç:**
- Slot yeniden kullanım listesi kapalı tutulmalı. Her yeni profil kendi slot
  eşlemesini uydurursa omurga anlamını yitirir — yeni eşleme yeni ADR ister.
- `os_licence`'taki iki ölü kolon, ileride "kapasite tablosu / lisans tablosu"
  ayrımı yapılırsa temizlenebilir. Bu iş bu task'ın kapsamında değil.

## Risks

**`RISK-001`** — Kolon sırası değişince mevcut testlerin bir kısmı kırılır.
*Değerlendirme:* bu risk değil, güvenlik ağı. Kırılan test yeni sözleşmeye göre
güncellenir, silinmez (`AC-009`).

**`RISK-002`** — Tarayıcıda eski DataTable state'i yeni kolon setine yapışabilir.
*Azaltma:* `INVENTORY_REPORT_SCHEMA_VERSION` artırılır (`REQ-NF-003`, `AC-008`);
bu sabit tablo `id`'lerine gömülü.

**`RISK-003`** — `comparison_only` profiline omurga gereği eklenen `Free`/`Unsold`
kolonları anlamsız değer gösterebilir.
*Azaltma:* `spec.md` §10'da açık uç olarak kayıtlı. Değer anlamsız çıkarsa düzeltme
yeri kolon listesi değil `prepare_service_row`'dur ve ayrı bir iştir.

## Validation

1. `AC-001`, `AC-002`, `AC-003` testleri: dokuz profil için `columns_for_family()`
   çıktısının ilk 8 slotu ve son kolonu programatik olarak doğrulanır — tek tek
   elle yazılmış beklenti listesiyle değil, omurga sabitiyle karşılaştırarak.
2. Tarayıcıda dokuz grubun accordion'u açılıp ortak kolonların aynı indekste olduğu
   görsel olarak doğrulanır.
3. Karar doğru değilse belirti nettir: bir profil omurgadan sapmak için özel bir
   `if` dalı gerektirir. Böyle bir dal yazma ihtiyacı doğarsa implementation durur
   ve karar yeniden değerlendirilir.

## Supersedes

—

## Superseded By

—
