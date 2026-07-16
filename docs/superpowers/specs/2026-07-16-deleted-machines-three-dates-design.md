# Silinen Makineler — 3 tarih + tüm zamanlar

**Date:** 2026-07-16
**Task:** TASK-54, item 2
**Status:** Design → implementation
**Owner:** Arca

## Özet (TR)

Mevcut "silinen makineler" paneli tek kolon (isim) ve zaman aralığına bağlı
(varsayılan 7 gün). Bunu **3 tarih** (talep / planlanan / gerçek) gösteren ve
**tüm zamanları** kapsayan hale getiriyoruz.

## Konvansiyon (canlı DB'de doğrulandı, 2026-07-16)

VM adı: `_<Müşteri>-<VMadı>_Silinecek_GG_AA_YYYY`

- Detection: ad `_` ile başlar (mevcut kural, `customer.py` 4 sorgu).
- Addaki tarih (sondaki `GG_AA_YYYY`) = **planlanan silme tarihi**.
- **Talep tarihi = planlanan − 14 gün** (task: "iki hafta sonrası veriliyor";
  first_seen ile 14-gün farkı %58 birebir doğrulandı).
- **Gerçek silinme = metrik akışının kesildiği an** (last_seen); hâlâ akıyorsa
  "silinmedi".
- Ölçümler: 1281 VMware + 2312 Nutanix `_` adı; %96'sı tarihli; Power'da 0.
- **309 makine planlanan tarihi geçtiği halde hâlâ metrik basıyor** (asıl değer).

### Parse tuzakları (hepsi veride görüldü)
- Kelime typo'ları: `Silinecek/Silenecek/Sİlineek/Slinecek/Silinicek/Silnecek…`
  → **kelimeye güvenme, sondaki tarihe tutun.**
- İki tarihli isim (`..._Restore_29:06_2026_Silinecek_20_07_2026`) → **sondaki**.
- Tarihsiz `_` isim (`_Export-...-Prodsapp1`) → None.
- Ayraçlar `_ - . :` olabilir; tarih DD_MM_YYYY (Türkçe).

## Performans kararı

"Tüm zamanlar" = zaman filtresini kaldır = **84 sn** ölçüldü (leading-`_` +
`ILIKE` seq-scan, 8M satır). Tek müşteriye daraltmak yardım etmiyor (89 sn).
⇒ İstek yolunda çalıştırılamaz.

**Çözüm: `gui_deleted_vm_registry` (webui-db, ~3600 satır).** Scheduler ağır
taramayı offline yapıp doldurur; sayfa minik tablodan anında okur. `first_seen`
kalıcı saklanır → eski metrik verisi düşse bile talep/first tarihleri kaymaz.

## Mimari (3 parça)

### 1. Pure parser — `shared/customer/deleted_vm_parser.py` (yeni, TDD)
```
parse_deleted_vm(name) -> DeletedVmInfo | None
  # DeletedVmInfo(customer, planned_date, request_date)
```
- Sondaki `GG_AA_YYYY`'yi regex ile ayıkla (ayraç `[_\-.:]`, `$`-anchor).
- `planned = date(y,m,d)` (geçersizse None); `request = planned - 14g`.
- customer = `_` at, ilk `-`'den önceki kısım (yoksa None).
- Kelimeye bakma; typo'lardan bağımsız.

### 2. Registry + scheduler
- Migration `gui_deleted_vm_registry(platform, vm_name PK-ish, customer,
  request_date, planned_date, first_seen, last_seen, actual_delete_date,
  updated_at)`.
- Full-history fill (offline, ~84 sn): `_`-adları + MIN/MAX(ts) per name → parse
  → upsert. `first_seen` sadece ilk yazımda set edilir (ON CONFLICT korur).
- Incremental refresh: son pencereyi tara → last_seen ilerlet + yeni `_` yakala.
- `actual_delete_date` = last_seen, eğer son N günde (örn. 3g) metrik yoksa; aksi
  halde NULL ("silinmedi").

### 3. Backend read + GUI
- Registry'den per-müşteri oku (indexli, anında) + endpoint + api_client wrapper.
- `customer_view.py::_deleted_vms_panel` → 4 kolon:
  `Makine adı · Talep · Planlanan · Gerçek silinme`. Geciken satırlar (planlanan
  geçmiş + gerçek NULL) vurgulu. Export'a da ekle.

## Kapsam / güvenlik
- Testler kurgusal isim kullanır (Ornek/Deneme/Acme) — gerçek müşteri verisi
  commit'e girmez ([[public-repo-no-real-customer-data]]).
- Power (ibm_lpar) 0 silinecek → Faz 1 VMware+Nutanix; Power şeması hazır dursun.

## Test
`tests/test_deleted_vm_parser.py`: trailing-date parse; typo bağımsızlığı; iki
tarihli → sondaki; tarihsiz → None; geçersiz tarih → None; request=planned−14;
customer prefix; ayraç varyasyonları; boş/None dayanıklılığı.
