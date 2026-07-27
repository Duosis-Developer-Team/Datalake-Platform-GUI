# Licensed OS — DC View + Customer View + CRM Inventory

Branch: `worktree-licensed-os-dc-and-customer` (main @ 034f12dc)
Tarih: 2026-07-27

## Hedef

1. Licensed OS'u sidebar'dan kaldır, DC View › Virtualization altına taşı; klasik /
   hyperconverged / power kırılımında lisanslı OS sayıları.
2. Customer View: müşterinin VM'lerinin OS'i + Resource Overusage tablosuna lisans
   satırı (Satılan / Kullanılan / Ekstra Kullanım).
3. Customer perspektifinde virtualization tablolarında Source + Cluster kolonlarını gizle.
4. CRM Inventory Overview › Flat table: "Os" satırlarının telemetri kolonları dolsun.

## Kabul edilen kararlar (kullanıcı onayı 2026-07-27)

- Windows "Satılan" = **sadece `MS Windows Lisans`** (per VM). Yönetim hizmetleri
  (`Standart Windows İşletim Sistemi Yönetim Hizmeti`), SQL Server ve RDS CAL
  Windows OS lisansı sayılmaz.
- Datacenter/Standart lisans ayrımı YOK — tek "Windows" satırı.
- Customer tarafında sanallaştırma türüne göre ayrım YOK; DC tarafında VAR.
- DC tarafında CRM eşleştirmesi zorunlu değil ama yapılabiliyorsa yapılacak.
- DC View'da hem 4. alt-sekme (üçü yan yana) hem her alt-sekmede kendi OS kartı.

---

## Veri gerçekliği (canlı test-pit, 2026-07-27)

### guest_os kaynakları

| Tablo | Kolon | Tazelik | Doluluk |
|---|---|---|---|
| `vm_metrics` | `guest_os` | 2026-07-27 09:15 | **%100** (1.7M satır, hiç boş yok) |
| `discovery_netbox_virtualization_vm` | `custom_fields_guest_os` | günlük | 39.358 / 42.751 |
| `discovery_nutanix_inventory_vm` | `guest_os` | — | 16.176 / 16.977 (guestId enum) |
| `nutanix_vm_metrics` | `guest_os` | 2026-07-27 11:55 | **0 / 371M — hep boş, kullanılamaz** |
| `ibm_lpar_general` | `lpar_details_ostype` | taze | Power LPAR OS tipi |

### Kapsama (VM kimliğine göre tekilleştirilmiş, vCLS hariç)

| Kova | VM | OS var | OS yok |
|---|---|---|---|
| KM (Klasik) | 2.749 | 2.749 (%100) | 0 |
| non-KM (Hyperconverged) | 15.878 | 15.248 (%96) | 630 |
| **AHV (Pure Nutanix)** | **1.531** | **48 (%3)** | **1.483** |

> **Kör nokta:** Pure Nutanix (AHV) VM'leri için datalake'te hiçbir kaynakta guest OS
> yok. Bu VM'ler dürüstçe "OS telemetrisi yok" olarak gösterilecek — uydurulmayacak.

### Power (IBM LPAR) — `lpar_details_ostype`

| ostype | LPAR |
|---|---|
| Linux - SUSE | 300 |
| Linux | 21 |
| Unknown | 20 |
| AIX | 14 |
| AIX/Linux | 3 |

CRM'de satılan SUSE toplam: `SUSE Lisans Bedeli` 6,1 adet + `SUSE for SAP HANA
Yönetimi` 39,2. Yani Power tarafında büyük bir fark var.

### DC × mimari × OS (vm_metrics, son 2 gün, tekilleştirilmiş)

| datacenter | mimari | VM | Windows | RHEL | SUSE |
|---|---|---|---|---|---|
| DC13-Nutanix-vDC | hyperconv | 5.214 | 2.412 | 160 | 52 |
| DC13-KM-vDC | classic | 1.652 | 860 | 136 | 44 |
| DC11-Nutanix-nvDC | hyperconv | 1.450 | 891 | 20 | 45 |
| DC13-KM-SSD-vDC | classic | 211 | 91 | 16 | 37 |
| DC12-vDC | hyperconv | 153 | 50 | 1 | 3 |
| DC14-Intel-vDC | classic | 151 | 56 | 6 | 0 |
| LONDON-ICT21 | classic | 42 | 15 | 0 | 7 |
| UZ11-DC | classic | 25 | 9 | 1 | 4 |
| AZ11-KM-vDC | classic | 13 | 8 | 0 | 0 |

### CRM lisans ürünleri (gerçek satış miktarları)

| Ürün | UoM | Satır | Toplam qty |
|---|---|---|---|
| **MS Windows Lisans** | per VM | 296 | **1.294,4** |
| Standart Windows İşletim Sistemi Yönetim Hizmeti | per VM | 168 | 743,1 |
| SPLA - RDP Kullanıcı Lisans (RDS User CAL) | Adet | 74 | 611,8 |
| SPLA - MS SQL Server Standart 2 Core | Adet | 52 | 204,2 |
| SPLA - MS Windows Server Standard 2 Core | Adet | 11 | 78,0 |
| SPLA - MS Windows Server Datacenter 2 Core | Adet | — | — |
| SUSE for SAP HANA on Power Yönetim Hizmeti | per VM | 25 | 39,2 |
| SUSE Lisans Bedeli | Adet | 5 | 6,1 |
| CCSP-RH* (Red Hat) | Adet/vCPU | 0 | 0 |

### CRM sipariş durumu

Tüm 474 sipariş `statecode = 0` (açık). `sales/efficiency-by-category` uçları
`statecode IN (3,4)` filtreli → **canlıda 0 satır dönüyor**. `sales/resource-compliance`
(0,1,3,4) çalışıyor. Lisans satırları **resource-compliance** hattına eklenecek.

### Per-DC müşteri atfı

`discovery_netbox_virtualization_vm.custom_fields_musteri` doluluk: ISTANBUL %96,
ANKARA %94, IZMIR %100. `crm_potential.DC_TENANT_VALUES` + `DC_SOLD_RAW_BY_PRODUCT_FOR_DC`
zaten bu hattı kuruyor → DC bazlı satılan lisans **ucuz**. Uyarı: NetBox `site_name`
şehir seviyesinde (ISTANBUL/ANKARA), DC kodu seviyesinde değil.

---

## Düzeltilecek iki mevcut hata

### H1 — Müşteri bazlı OS tespiti fiilen çalışmıyor

`dc_service.get_licensed_os_for_customer` VM adını müşterinin tam ticari unvanıyla
eşleştiriyor:

```python
pattern = f"%{name}%"   # "%GAMA ENERJİ A.Ş.%"
... WHERE name ILIKE %s
```

Canlı doğrulama: GAMA → `{windows:0, rhel:0, suse:0}`; 4A Kozmetik → 22 VM, hepsi
`unknown`. Sebep: NetBox'ta iki isimlendirme var —

- `4a_Kozmetik-Srv19` (guest_os dolu)
- `4A KOZMETİK SANAYİ VE TİCARET ANONİM ŞİRKETİ-melisa` (AHV, guest_os boş)

Tam unvan sadece ikinciyi yakalıyor. Doğrusu customer-api'deki alias/pattern
çözücüsü (`_resolve_patterns(source_patterns, "virtualization", fallback)`).

### H2 — Windows "satılan" 2× şişiyor

`shared/licensing/reconcile.py`:

```python
"windows": ("license_microsoft_spla", "license_microsoft_csp", "mgmt_os_windows"),
```

218 müşteriden 88'i hem `MS Windows Lisans` hem `Standart Windows İşletim Sistemi
Yönetim Hizmeti` alıyor, miktarlar birebir aynı (44/44, 29/29, 21/21, 19/19, 18/18,
17/17). SUM aynı VM'i iki kez sayıyor. Ayrıca `starts_with("SPLA -")` kuralı SQL
Server (204) ve RDS CAL'ı (612) da Windows OS lisansı sayıyor.

Karar: Windows sold = sadece `MS Windows Lisans`.

---

## Uygulama planı

### Faz 0 — Ortak çekirdek

- `shared/licensing/os_classifier.py` — dokunulmuyor (kural tablosu yeterli).
- `shared/licensing/os_source.py` (**yeni**): guest-OS kaynak önceliği + mimari kovası
  (`classic` / `hyperconverged` / `pure_nutanix` / `power`) tek yerde.
- `shared/sellable/panel_mapping.py`: `license_windows_os` kuralı eklenir
  (`equals=("MS Windows Lisans",)`), SPLA prefix kuralından **önce**.
- `shared/licensing/reconcile.py`: `FAMILY_TO_SOLD_CATEGORIES` →
  `windows: ("license_windows_os",)`, `suse: ("license_suse",)`,
  `rhel: ("license_redhat",)`. Yönetim hizmeti panelleri ayrı kalır.
- webui migration `030_licensed_os_panels.sql`: `gui_panel_definition` içine
  `license_windows_os` (family `license_microsoft`, unit `per VM`) + seed remap.

### Faz 1 — Customer View

1. `services/customer-api/app/db/queries/customer.py`:
   `CUSTOMER_CLASSIC_VM_LIST`, `CUSTOMER_HYPERCONV_VM_LIST`,
   `CUSTOMER_PURE_NUTANIX_VM_LIST`, `CUSTOMER_INTEL_VM_DETAIL_LIST` →
   `guest_os` kolonu eklenir (vm_metrics'te hazır; Nutanix tarafı NULL).
2. `customer_adapter.py`: vm dict'lerine `guest_os` + `os_family`.
3. Müşteri OS tally'si customer-api'de, aynı VM listelerinden türetilir
   (tabloda görünenle sayılan birebir aynı olur). Sanallaştırma türüne göre
   ayrım yok — tek toplam.
4. `usage_comparison.build_*_compliance` → lisans satırları eklenir
   (`license_windows_os`, `license_suse`, `license_redhat`):
   entitled = CRM qty, used = tespit edilen VM sayısı, overage = max(used−entitled, 0).
5. `src/pages/customer_view.py`: VM tablolarına "İşletim Sistemi" kolonu.
6. H1 düzeltmesi: customer view artık datacenter-api'nin bozuk müşteri ucunu
   kullanmaz.

Sonuç: Summary › Resource Overusage tablosunda
`Windows Lisans | 10 | 15 | 5` satırı (görseldeki Hizmet/Satılan/Kullanılan/Ekstra).

### Faz 2 — Manager / Customer perspektifi

`_tab_classic`, `_tab_hyperconv`, `_tab_pure_nutanix` → `show_infra_columns: bool`
parametresi. `render_virtualization_tab` içinde
`show_infra_columns=(perspective == PERSPECTIVE_MANAGER)` ile Source + Cluster
kolonları customer perspektifinde gizlenir. Export tarafında da aynı filtre.

### Faz 3 — DC View

1. `src/components/sidebar.py`: `/licensed-os` NAV_ITEM_SPECS'ten çıkar.
   Route + `page:licensed_os` izni deep-link için kalır.
2. datacenter-api: `GET /api/v1/datacenters/{dc_id}/licensed-os`
   → `{classic: {...}, hyperconverged: {...}, pure_nutanix: {...}, power: {...}}`
   Kaynak: vm_metrics (VMware, `cluster ILIKE '%KM%'` ile klasik/hyperconv ayrımı)
   + ibm_lpar_general (`lpar_details_ostype`) + AHV için açık "telemetri yok" sayacı.
3. DC View › Virtualization'a 4. alt-sekme "Lisanslı OS" (üç mimari yan yana)
   **ve** classic / hyperconv / power alt-sekmelerinin her birine kendi OS kartı.
4. Yeni izin: `sub:dc_view:virt:licensed_os`.
5. DC-CRM eşleştirmesi: `crm_potential.DC_TENANT_VALUES` +
   `DC_SOLD_RAW_BY_PRODUCT_FOR_DC` üzerinden DC bazlı satılan lisans; tabloda
   "Satılan (DC'ye atfedilen)" olarak, şehir-seviyesi site uyarısıyla.

### Faz 4 — CRM Inventory Overview flat table

`sellable_service` içinde mevcut escape-hatch kalıbı (`backup_netbackup_storage`,
`dc_hosting_u`) örnek alınarak `_query_licensed_os_totals` eklenir; OS panelleri
(`license_windows_os`, `license_suse`, `license_redhat`, `mgmt_os_*`) buna bağlanır.
Sonuç: "(CRM entitled — infra telemetry pending)" etiketi ve "—" kolonları gerçek
tespit sayılarıyla dolar.

---

## Test stratejisi

TDD; her faz kendi testleriyle:

- `tests/test_os_classifier.py` — mevcut, korunur.
- `tests/test_licensed_os_source.py` — kaynak önceliği + mimari kovası (yeni).
- `tests/test_licensed_os_reconcile.py` — H2 regresyonu: aynı VM iki SKU'dan
  sayılmamalı (genişletilir).
- `tests/test_customer_view_licensed_os.py` — overusage satırı üretimi (genişletilir).
- `tests/test_dc_view_licensed_os.py` — DC kırılımı + AHV "telemetri yok" (yeni).
- `services/customer-api/tests/` — compliance satırları + guest_os kolonu.
- `tests/test_customer_view_perspective.py` — customer perspektifinde Source/Cluster
  kolonlarının olmadığı (yeni).

---

## Sonuç (2026-07-27, tamamlandı)

| Commit | Kapsam |
|---|---|
| `9c6b7633` | Faz 0 — lisans paneli ayrımı, çift sayım düzeltmesi, `shared/licensing/os_source.py` |
| `319f53c5` | Faz 1 — customer-api guest OS + overusage satırı |
| `becbf32c` | Faz 2 — Customer View OS kolonu + perspektif gizleme |
| `145020c3` | Faz 3 — DC View "Lisanslı OS" + DC-CRM atfı |
| `9a6a087d` | Faz 4 — CRM Inventory "Os" satırları |

### Plandan sapmalar

- **DC-CRM atfı yapıldı** (planda "opsiyonel" idi). İki hata düzeltilmesi gerekti:
  mevcut hat NetBox `site_name` (şehir seviyesi) kullandığı için DC kodunda 0
  tenant dönüyordu; ve DC-scoped ile global tenant sayımları farklı dedupe
  ettiği için bir tenant DC13'te 350, platform genelinde 342 görünüyordu (payı
  %100'ün üstünde). İkisi de düzeltildi, 5 DC'de 0 ihlal doğrulandı.
- **CRM Inventory panelleri NetBox'tan besleniyor**, `vm_metrics`'ten değil —
  platform toplamı iddiasında olan bir satır Nutanix-only 5.800 makineyi
  kaçıramaz (Windows 4.956 vs 8.061).
- **Detection SQL `shared/licensing/os_sql.py`'a taşındı** — üç yüzeyin aynı
  envanter için üç farklı sayı göstermemesi için.
- **Power OS eklendi** (planda yoktu): `lpar_details_ostype`, 383 SUSE LPAR.

### Canlı doğrulanan sayılar

Müşteri (needle çözümlemesiyle): GAMA 88 Windows tespit / 62 satılan;
ANKUTSAN 68 / 44; 4A Kozmetik 29 makinenin 17'si AHV → OS yok.

DC13: klasik 952 Windows / 157 RHEL / 86 SUSE · hyperconverged 2.458 / 171 / 52 ·
power 193 SUSE · 812 AHV makine OS telemetrisi yok.

Platform: Windows 8.061 · SUSE 802 · RHEL 523 · ücretsiz 5.820 · bilinmiyor 4.963.

### Test durumu

Yeni: 44 (GUI shared/DC) + 27 (customer-api) + 12 (datacenter-api).
Pre-existing kırmızılar (base commit `034f12dc`'de de kırmızı, dokunulmadı):
customer-api 1 (`test_sellable_service` host fallback), datacenter-api 2,
GUI 13 (`test_dc_view_visibility` 7, `test_network_eager_load` 2,
`test_dc_view_capacity_table` 2, `test_dc_view_lazy_tabs` 2 — hepsi `FakeApi`
fixture drift'i).

### Yapılmadı

- Migration'lar yerel webui-db'ye uygulandı ve doğrulandı; **prod'a uygulanmadı**.
- Hiçbir şey push edilmedi, main'e merge edilmedi.
- `/licensed-os` sayfası deep-link olarak duruyor ama müşteri seçimi hâlâ eski
  isim-eşleştirme yolunu kullanıyor (H1). Customer View artık onu kullanmıyor;
  sayfanın kendisi ayrı bir temizlik işi.

## Bilinçli kabul edilen sınırlar

- Pure Nutanix (AHV) 1.483 VM: OS bilinmiyor, "telemetri yok" olarak gösterilir.
- DC-CRM atfı NetBox `site_name` şehir seviyesinde; DC kodu granülaritesi değil.
- CRM siparişlerinin tamamı `statecode=0`; entitlement tabanı 0,1,3,4 kullanan
  `resource-compliance` hattıdır.
