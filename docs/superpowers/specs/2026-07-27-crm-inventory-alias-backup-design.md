# CRM Inventory temizliği + Alias ekleme butonu + Backup eşleşmeyen veriler

**Tarih:** 2026-07-27
**Branch:** `worktree-crm-alias-backup-tabs` (main'den açıldı, 034f12dc)
**Kapsam:** Dört bağımsız iş. A ve B görsel sadeleştirme; C ve D yeni yetenek.

---

## A · CRM Inventory'de Power tablosunu gizle

### Amaç

`/crm/inventory-overview` sayfasında "Power" family tablosu görünmeyecek. "Power HANA" aynen kalacak.

### Bağlam

`virt_power` ve `virt_power_hana`, `inventory_overview_service.py:53` `_VIRT_FAMILY_LABELS` içinde tanımlı iki ayrı family. İkisi aynı IBM Power altyapısını paylaşıyor (`sellable_service.py:261`), dolayısıyla ikisi birlikte gösterildiğinde altyapı iki kez okunuyor.

### Karar

Filtre **sunucu tarafında**, `services/customer-api/app/services/inventory_overview_service.py` içinde uygulanır. `virt_power` ait paneller `families`, `panels` ve `summary` hesaplanmadan **önce** elenir.

Gerekçe: KPI rakamları sunucuda `summary`'den geliyor, tablo ise `families`'ten. Filtreyi arayüzde uygularsak tablo boşalır ama KPI'lar Power'ı saymaya devam eder — kullanıcıya "eksik satır" gibi görünür. Tek noktada elemek iki tarafı yapısal olarak tutarlı tutar.

`GET /crm/inventory-overview` endpoint'ini yalnızca `src/pages/crm_inventory_overview.py` tüketiyor (doğrulandı). DC View (`dc_view.py:1832`) ve Sellable Potential (`crm_sellable_potential.py:245`) ayrı yollardan besleniyor ve **etkilenmez**.

### Uygulama

- `inventory_overview_service.py`: modül seviyesinde `_INVENTORY_HIDDEN_FAMILIES: frozenset[str] = frozenset({"virt_power"})` sabiti. Adı ve tek elemanlı oluşu bilinçli — ileride başka family gizlenirse tek yer değişir.
- Panel listesi kurulurken bu kümedeki family'ler atlanır; `summary` kalan panellerden hesaplanır.
- Sabitin yanına neden yorumu: Power ve Power HANA aynı IBM altyapısını paylaşır, ikisi birlikte gösterilmek istenmiyor.

### Doğrulama

- `virt_power` panelleri olan bir payload ile: dönen `families` içinde `virt_power` yok, `virt_power_hana` var.
- `summary` içindeki panel sayısı ve TL toplamları `virt_power` panellerini içermiyor.
- Mevcut `tests/test_crm_inventory_overview_page.py` ve `services/customer-api/tests/test_inventory_overview_service.py` yeşil kalıyor.

---

## B · Product Matching tablosundan üç kolon kaldır

### Amaç

`Usage Source`, `Infra Total`, `Infra Used` kolonları hem ekrandan hem Excel export'undan silinecek.

### Bağlam

Bu üç alan tek bir tabloda kullanılıyor: `src/components/crm_inventory_report.py:82` `_PRODUCT_MATCHING_COLUMNS`. Başka hiçbir tabloda geçmiyor (doğrulandı).

Ekran ve export **ayrı yollardan** besleniyor:
- Ekran: `_PRODUCT_MATCHING_COLUMNS` → `build_product_matching_section()` (satır 766)
- Export: `prepare_product_matching_row()` (satır 712) → `records_to_dataframe()` → "Product_matching" sheet

Sadece kolon listesini düzenlemek export'u değiştirmez.

### Karar

İkisinden de silinir. Kullanıcı kararı: "tabloda görmek istemiyorlarsa Excel'de de görmek istemezler."

### Uygulama

- `_PRODUCT_MATCHING_COLUMNS`'tan `usage_source`, `infra_total_fmt`, `infra_used_fmt` girdileri çıkarılır.
- `prepare_product_matching_row()` bu üç anahtarı artık üretmez (satır 735, 736, 739).
- `filter_product_matching_rows()` içindeki `usage_source` arama koşulu (satır 760) kaldırılır — üretilmeyen alanda arama yapmak sessiz ölü koddur.
- `Tables` (`infra_tables_fmt`) kolonu **kalır** — silinme listesinde yok.

### Doğrulama

- `tests/test_crm_inventory_product_matching.py` güncellenir: hazırlanan satırda üç anahtar yok, kolon listesinde üç kolon yok.
- `tests/test_crm_inventory_export.py`: export sheet'inde üç kolon yok.

---

## C · Eşleşmeyen Veriler sayfasına "Alias ekle" butonu

### Amaç

`/unmapped-resources` sayfasındaki "Alias eksik" satırlarında tek tıkla, tahmin edilen müşteriye alias kuralı eklenebilecek. Kayıttan sonra satır listeden düşecek ve kural Customer Aliases ekranında görünecek.

### Mevcut eşleştirme nasıl çalışıyor (tespit)

`shared/customer/unmapped_classifier.py:80` `guess_owner()` — **prefix tabanlı**, suffix hiç kullanılmıyor:

1. VM adının ilk `-` öncesindeki parça Türkçe-katlanıp (`norm()`) CRM hesap anahtarlarında **birebir** aranır. Bulunursa güçlü eşleşme.
2. Bulunamazsa en uzun anahtar kazanacak şekilde iki yönde arama: katlanmış tam ad bir hesap anahtarıyla **başlıyor** mu, ya da VM prefix'i bir hesap anahtarının **başı** mı. Minimum anahtar uzunluğu 4 (`_MIN_STARTSWITH_KEY`).

Örnek: `Abrak_Enerji-Sophos` → prefix `abrakenerji` → `ABRAK ENERJİ ELEKTRİK ÜRETİM ANONİM ŞİRKETİ` anahtarının başı → eşleşir.
Örnek: `Ada_Gross_Cloud-Appsrv_Restored_20_05_2026` → tam ad `adagross` ile başlar → `ADA GROSS`.

### Karar: buton hangi kuralı yazar

`data_source = "virtualization"`, `match_method = "prefix"`, `match_value = <VM adının ilk '-' öncesi>`.

`Ada_Gross_Cloud-Appsrv_...` için yazılan değer **`Ada_Gross_Cloud`** olur — eşleşmeyi sağlayan `Ada_Gross` anahtarı değil.

Gerekçe: butona basıldığında ekranda görünen satır grubu bağlanır, fazlası değil. `Ada_Gross` yazılsaydı `Ada_Gross-*` ile başlayan, kullanıcının o an görmediği makineler de sessizce bağlanırdı. Daha geniş kural gerekiyorsa Customer Aliases ekranından elle genişletilir; ters yön (fazla bağlananı geri almak) daha pahalı.

**Tiresiz adlar.** VM adında `-` yoksa (`Deneme_Kredi_LOG_Server`) prefix tüm addır ve `prefix` kuralı fiilen `exact` gibi davranır — yalnızca o tek makineyi bağlar. Bu kabul edilir davranıştır: tek makine bağlamak, uydurulmuş bir kesme noktasıyla bilinmeyen sayıda makine bağlamaktan iyidir. Kullanıcıya ayrı bir uyarı gösterilmez; kural Customer Aliases ekranında zaten okunabilir haldedir.

### Sunucu tarafı

`services/customer-api/app/db/queries/unmapped.py` → `CRM_ACCOUNT_NAMES` sorgusu `accountid` de döndürür (`discovery_crm_accounts.accountid` mevcut, doğrulandı).

`shared/customer/unmapped_classifier.py` → hesap anahtarı indeksi `norm(name) -> (display_name, accountid)` taşır. `UnmappedRow` ve payload satırları üç yeni alan kazanır:

| Alan | İçerik |
|---|---|
| `guessed_owner_id` | CRM accountid (yoksa `None`) |
| `suggested_alias` | VM adının ilk `-` öncesi |
| `suggested_method` | `"prefix"` |

Tahmini zaten yapan modül bu alanları üretir. Arayüz kendi başına prefix türetmez — aksi halde iki taraf zamanla birbirinden kayar (bu kod tabanında `match.py` başlığında yazılı, daha önce yaşanmış bir hata sınıfı).

### Arayüz

`src/pages/unmapped_resources.py`:

- Tabloya `"İŞLEM"` (`action`) kolonu eklenir. `alias_gap` satırlarında hücre metni `"Alias ekle"`, diğerlerinde boş.
- **Buton yerine `active_cell`**: `dash_table.DataTable` hücre içinde gerçek bir bileşen barındıramaz. Tabloyu elle `html.Table`'a çevirmek kolon filtreleme ve sıralamayı kaybettirir — sayfa bunları metinle vaat ediyor (`unmapped_resources.py:132`). Bu yüzden hücre buton gibi biçimlendirilir (`style_data_conditional` ile renk/kalınlık/pointer) ve tıklama `active_cell` callback'i ile yakalanır.
- Satır kimliği için tabloya gizli `row_key` kolonu eklenir; `active_cell` yalnızca satır indeksi verir, sıralama/filtreleme sonrası indeks kayabilir. `derived_viewport_data` üzerinden okunur.
- Yeni dosya: `src/pages/unmapped_resources_callbacks.py`, `app.py`'de `# noqa: F401` ile import edilir (mevcut kalıp: satır 163-197).

### Yazma yolu

`PUT /crm/aliases/{id}/source-mappings` o hesabın **tüm** mapping'lerini değiştirir (`sales.py:197`). Dolayısıyla callback:

1. Hesabın mevcut mapping'lerini okur.
2. Aynı `(data_source, match_method, match_value)` üçlüsü zaten varsa hiçbir şey yazmaz, "zaten ekli" bildirimi verir (idempotent).
3. Yoksa listeye ekler ve **birleşimi** PUT eder.

Bu adım atlanırsa müşterinin diğer tüm alias'ları silinir.

### Cache — iki katman, biri eksik

Sunucu tarafı zaten doğru: her mapping yazımında `cache.delete_prefix("unmapped_resources:")` çalışıyor (`customer_service.py:966`).

GUI tarafında **eksik var**: `api_client.py:797` `get_unmapped_resources()` sonucu `api:unmapped_resources:<tr>` anahtarında tutuluyor, ama `_invalidate_customer_views_cache()` (satır 2467) bu prefix'i silmiyor. Bu haliyle buton kaydetse bile sayfa bayat listeyi gösterir ve satır ekranda kalır.

Düzeltme: `_invalidate_customer_views_cache()` içine `_api_response_cache.delete_prefix("api:unmapped_resources:")` eklenir. Bu fonksiyon `put_crm_source_mappings()` tarafından zaten çağrılıyor, yani Customer Aliases ekranından yapılan elle düzenlemeler de aynı düzeltmeden faydalanır.

### Kayıt sonrası davranış

- Satır tablodan düşer (veri yeniden çekilir).
- Üstteki KPI'lar (`Toplam eşleşmeyen`, `Alias eksik`, `Sahipsiz`) yeniden hesaplanır.
- Kural Administration › CRM Dynamics 365 › Customer Aliases'ta ilgili müşterinin Virtualization sütununda görünür.
- Başarı / "zaten ekli" / hata durumları kullanıcıya bildirilir. `cache_warning` dönerse kayıt başarılı sayılır ama uyarı gösterilir (endpoint sözleşmesi böyle).

### Yan düzeltme

Sayfadaki bilgi kutusu kullanıcıyı İç Alias ekranına yönlendiriyor (`unmapped_resources.py:109`, `/settings/integrations/crm/internal-aliases`). İç Alias yalnızca `INTERNAL` rezerve hesabı içindir; gerçek müşteri alias'ı oraya yazılmaz. Link Customer Aliases sayfasına düzeltilir.

### Doğrulama

- Tahmin: bilinen bir hesap listesi ile `guessed_owner_id` ve `suggested_alias` beklenen değerleri üretir; tahmini olmayan satırlarda `None`.
- Birleştirme: mevcut iki mapping'i olan hesaba ekleme yapıldığında PUT gövdesinde üç mapping olur; hiçbiri kaybolmaz.
- İdempotans: aynı kural ikinci kez eklendiğinde PUT çağrılmaz.
- `orphan` satırında işlem hücresi boştur ve tıklama hiçbir şey yazmaz.
- Cache: `_invalidate_customer_views_cache()` çağrıldıktan sonra `api:unmapped_resources:*` anahtarı yok.

---

## D · Eşleşmeyen Veriler'e Backup sekmesi

### Amaç

`Sanallaştırma` sekmesinin yanına `Backup` sekmesi. Hiçbir müşteriye bağlanmayan NetBackup policy'leri, sanallaştırma tarafındaki aynı iş listesi mantığıyla gösterilir.

### Backup adlandırma standardı (Excel'den türetildi, canlı veriyle doğrulandı)

`backup-musteri-isim.xlsx` › `AD-KARŞILIĞI` sayfası: 189 müşteri, 233 policy token'ı.

**Standart:** policy adı `<ilk4(kelime1)>[-<ilk4(kelime2)>]-<workload>-<env>-<tip>`, Türkçe-katlanmış küçük harf.

Doğrulama sonuçları:
- Excel'in 233 token'ının **215'i (%92)** bu kurala uyuyor.
- Token'ın ilk parçası vakaların %76'sında tam 4 karakter.
- Canlı NetBackup verisi kuralı doğruluyor: `abc-dete-s4hana-prd-log`, `alki-kagi-alerpprodhana-full`, `ayak-duny-vm-image`.

Uymayan %8: ünsüz-sıkıştırma (`trkn` ← Turkon, `tma` ← Temsa, `milg` ← Milangaz) ve müşteri adıyla hiç ilgisi olmayan kodlar (`visa01`, `ema-agito` ← Gateway Holding). Bunlar kuralla türetilemez; Excel bunlar için tek kaynaktır.

### Standardın sınırı — ölçüldü, tasarımı belirliyor

7 günlük pencerede **1.294 farklı policy**, **2.668 CRM hesabı**na karşı çalıştırıldı:

| Sonuç | Adet | Oran |
|---|---|---|
| Tek müşteriye eşleşti | 764 | %59 |
| **Belirsiz (>1 aday müşteri)** | 347 | **%27** |
| Tahmin yok | 183 | %14 |

Belirsizlik gerçek: `avro-*` hem AVROMED hem AVRORA LLC'ye uyuyor; `alis-*` hem ALIŞAN LOJİSTİK hem ALIŞAN DEN HARTOGH'a. 4 karakterlik token bunları ayıramaz — ama Excel ayırabiliyor (`Avrora → avro,avrora`; `Alisan lojistik → alis,alis-logo`).

**Sonuç: standart tek başına yeterli değil, Excel kesin kaynak.** Bu yüzden iki parça birlikte yapılır.

### D1 · Excel seed (kesin kaynak)

`AD-KARŞILIĞI`'ndaki 189 müşteri / 233 token, `backup_netbackup` kaynağında `prefix` kuralı olarak yüklenir.

Zorluk: Excel adları kısa ("Aksular"), CRM adları resmî unvan ("AKSULAR GIDA..."). Eşleştirme `unmapped_classifier.norm()` ile aynı Türkçe-katlama mantığını kullanır — ayrı bir normalizasyon yazılmaz.

**Çözülemeyen satırlar sessizce atlanmaz.** Seed betiği üç grup raporlar:
- bağlanan müşteriler (accountid ile),
- CRM'de karşılığı bulunamayanlar,
- birden fazla CRM hesabına uyanlar (elle karar gerekir).

Seed idempotenttir: aynı `(accountid, data_source, match_method, match_value)` ikinci çalıştırmada tekrar yazılmaz. Mevcut mapping'ler korunur (C bölümündeki birleştirme kuralı burada da geçerli).

Virgülle ayrılmış çoklu token'lar (`aksu,aksular`) ayrı kurallara açılır.

### D2 · Standart tabanlı sezgisel tahmin

`shared/customer/unmapped_classifier.py` policy adları için genişletilir:

1. Policy adının ilk **iki** segmenti (`abc-dete`) hesap anahtarı indeksinde aranır.
2. Bulunamazsa ilk **bir** segment (`avro`).
3. İndeks hesap adlarından standartla üretilir: `ilk4(kelime1)`, `ilk4(kelime1)-ilk4(kelime2)`, ve yeterince uzunsa tam ilk kelime. Unvan gürültüsü (`ANONİM`, `ŞİRKETİ`, `LTD`, `SAN`, `TİC`, `HOLDİNG` vb.) elenir.

Excel'de olmayan yeni müşteriler için çalışmaya devam eder — seed statik, sezgisel canlı.

### Belirsizlik dürüstçe gösterilir

Bir token birden fazla hesaba uyduğunda **tek müşteri tahmin edilmez**. Satır `ambiguous` nedeniyle işaretlenir, "Belirsiz (N aday)" olarak gösterilir ve **tek tık butonu sunulmaz**; kullanıcı Customer Aliases ekranından karar verir.

Gerekçe: yanlış müşteriye backup bağlamak, boş bırakmaktan kötüdür — faturalamaya ve kapasite raporlarına yanlış veri girer. Seed yüklendikten sonra bu satırların büyük kısmı zaten eşleşmiş olur.

### Veri kaynağı

`public.raw_netbackup_jobs_metrics`, `policyname` kolonu, `starttime` ile pencerelenir. Sanallaştırma tarafındaki gibi `DISTINCT`.

Tazelik doğrulandı: son kayıt 2026-07-27 09:37 UTC. (2026-06-10'da başlayan 43 günlük backup toplama kesintisi kapanmış.)

Sahiplik testi `backup_veeam`, `backup_zerto`, `backup_netbackup` kaynaklarındaki tüm mevcut kurallara karşı yapılır — bunlardan herhangi biri policy'yi sahipleniyorsa satır listeye girmez.

### Arayüz

```
Sanallaştırma | Backup
```

Backup kolonları: `TAHMİNİ SAHİP | POLICY ADI | KAYNAK | NEDEN | İŞLEM`

`KAYNAK`, sanallaştırma sekmesindeki `PLATFORM` kolonunun karşılığıdır ve şimdilik tek değer alır: `NetBackup`. Kolon bugün tek değerli olsa da bırakılır — Veeam/Zerto eklendiğinde tablo şeması değişmeden genişler.

`NEDEN` değerleri: `Alias eksik` / `Belirsiz (N aday)` / `Sahipsiz`.

`İŞLEM` yalnızca `Alias eksik` satırlarında aktif. Yazdığı kural: `data_source="backup_netbackup"`, `match_method="prefix"`, `match_value=<eşleşmeyi sağlayan hesap token'ı>` — yani `abc-dete-s4hana-prd-log` satırı için `abc-dete`, policy adının tamamı değil. C'deki daralt-değil-genişlet mantığının tersi gibi görünse de değil: burada token zaten müşteriye ait sabit önektir, policy'nin geri kalanı workload/env/tip kuyruğudur ve müşteriyle ilgisi yoktur.

KPI kartları hangi sekmenin açık olduğuna bakmaksızın **her iki kaynağın toplamını** gösterir; sekme başına dağılım sekme etiketinde rozet olarak verilir. Gerekçe: KPI'ların sekmeyle değişmesi, aynı sayfada iki farklı "toplam" okuması yaratır.

### Kapsam dışı

**Veeam ve Zerto.** Excel yalnızca NetBackup policy adlandırmasını belgeliyor; Veeam job / Zerto VPG adları için doğrulanmış bir standart yok. Uydurulmuş bir kural, D2'deki %27 belirsizlikten daha kötü sonuç verir. Ayrı iş olarak, kendi veri incelemesiyle eklenir.

### Doğrulama

- Standart: Excel'in doğrulanmış örnekleri (`ABC Deterjan → abc-dete`, `Ayakkabı Dünyası → ayak-duny`, `Çelebi Holding → cele-hold`) beklenen token'ı üretir.
- Türkçe katlama: `Çapa Medikal → capa-medi`, `Alkim Kağıt → alki-kagi`.
- Belirsizlik: iki hesabın aynı token'ı ürettiği durumda satır `ambiguous`, işlem hücresi boş.
- Sahiplik: mevcut `backup_netbackup` kuralıyla sahiplenilen policy listeye girmez.
- Seed idempotans: iki kez çalıştırıldığında ikinci sefer sıfır yazma.
- Seed raporu: CRM'de bulunamayan ve çoklu eşleşen müşteriler adlarıyla raporlanır.

---

## Bağımlılıklar

A, B, C, D birbirinden bağımsız; ayrı ayrı sevk edilebilir.

Tek iç bağımlılık: **D2, C'nin işlem-kolonu altyapısını yeniden kullanır** — C'den sonra yapılmalı.

D1 (seed) ile D2 (sezgisel) birbirinden bağımsızdır; seed önce yüklenirse D2'nin listesi baştan daha kısa çıkar.

## Kayıtlı kararlar

| Karar | Seçim | Gerekçe |
|---|---|---|
| Power filtresi nerede | Sunucu tarafı | Tablo ile KPI tek kaynaktan, kayma imkânsız |
| Power toplamlardan düşsün mü | Evet | Tablo yokken rakamda durması "eksik satır" gibi okunur |
| Buton hangi değeri yazar | VM prefix'i (dar) | Görünen satır grubunu bağlar; genişletmek geri almaktan ucuz |
| Kolonlar export'ta kalsın mı | Hayır | Ekranda istenmeyeni Excel'de tutmak tutarsız |
| Buton mu `active_cell` mi | `active_cell` | DataTable buton alamaz; tabloyu değiştirmek filtre/sıralamayı kaybettirir |
| Belirsiz backup satırı | Tahmin edilmez, buton sunulmaz | Yanlış müşteriye backup bağlamak boş bırakmaktan kötü |
| Veeam / Zerto | Kapsam dışı | Doğrulanmış adlandırma standardı yok |
