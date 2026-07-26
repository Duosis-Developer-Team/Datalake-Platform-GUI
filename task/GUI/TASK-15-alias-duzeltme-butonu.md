# TASK-15 — Müşteri Alias Eşleştirme ve Düzeltme Butonu

**Tip:** Feature / UX · **Efor:** M · **Öncelik:** Orta-Yüksek (operasyonel kazanç yüksek)

## Hedef
"Eşleşmeyen Veriler" (Sahipsiz Sanal Makineler) tablosunda satırların sağına bir **buton** eklenecek.
Ekip, makinelere alias ekleyerek doğrudan bu ekrandan hataları düzeltebilecek.

## Mevcut durum

| Katman | Yer |
|---|---|
| Sayfa | `src/pages/unmapped_resources.py` (173 satır), `ACCOUNT_NAME = "Eşleşmeyen Veriler"`, `_TABLE_ID = "unmapped-vm-table"` |
| Sınıflandırma | `shared/customer/unmapped_classifier.py` — iki sebep: `alias_gap` ("Alias eksik") ve `orphan` ("Sahipsiz") |
| Sorgular | `services/customer-api/app/db/queries/unmapped.py` — `UNMAPPED_VMWARE_NAMES`, `UNMAPPED_NUTANIX_NAMES`, `CRM_ACCOUNT_NAMES` |
| Endpoint | `GET /api/v1/customers/unmapped/resources` |
| Tablo kolonları | `guessed_owner`, `name`, `platform`, `reason` |

**En değerli kısım zaten var:** `guessed_owner` — bulanık eşleştirmeyle tahmin edilen müşteri.
Buton bu tahmini tek tıkla kurala çevirecek.

Yazma tarafı da hazır:
```
PUT /api/v1/crm/aliases/{crm_accountid}/source-mappings   → gui_crm_customer_source_mapping
PUT /api/v1/crm/aliases/{crm_accountid}                    → gui_crm_customer_alias
GET /api/v1/crm/aliases
```
UI referansı: `src/utils/crm_source_mapping_ui.py` (Settings › Integrations › CRM aliases)

## Tasarım

```
┌ Eşleşmeyen Veriler ───────────────────────────────────────────────────────┐
│ Tahmini Sahip │ Makine Adı      │ Platform │ Sebep       │           │
│ Boyner (%87)  │ boyner-app-01   │ VMware   │ Alias eksik │ [Eşleştir]│
│ —             │ test-vm-99      │ Nutanix  │ Sahipsiz    │ [Eşleştir]│
└───────────────────────────────────────────────────────────────────────────┘
        │ [Eşleştir] tıklanınca modal:
        ▼
┌ Alias Ekle ───────────────────────────────────────────────┐
│ Makine:        boyner-app-01  (VMware)                    │
│ Müşteri:       [Boyner ▾]  ← guessed_owner önseçili       │
│ Veri kaynağı:  [virtualization ▾]                         │
│ Eşleşme türü:  ( ) exact  (•) prefix  ( ) contains        │
│ Değer:         [boyner-        ]  ← isimden türetilmiş     │
│ Öncelik:       [20]                                        │
│                                                            │
│ ⓘ Bu kural N makineyi eşleştirecek:  ← CANLI ÖNİZLEME     │
│   boyner-app-01, boyner-db-02, boyner-web-03 … (+12)      │
│                                                            │
│              [İptal]  [Kaydet ve Yeniden Hesapla]         │
└────────────────────────────────────────────────────────────┘
```

**Kritik özellik: canlı önizleme.** Kural kaydedilmeden önce "kaç makineyi yakalar, hangileri" gösterilmeli.
Aksi halde `contains` ile aşırı geniş kural yazılıp başka müşterinin makineleri yanlış eşleşir.

## Yapılacaklar

- [ ] `unmapped_resources.py` tablosuna aksiyon kolonu (`dash_table` `presentation:"markdown"` veya
      satır seçimi + tek buton — Dash'te satır içi buton için markdown link deseni kullanın)
- [ ] Modal: müşteri seçici (CRM hesap listesi), data_source seçici, match_method radio, değer, öncelik
- [ ] `guessed_owner` ve isimden türetilmiş prefix önerisi otomatik doldurulsun
- [ ] **Önizleme endpoint'i:** `POST /api/v1/crm/aliases/preview-match`
      → verilen `(data_source, match_method, match_value)` kaç ve hangi kaynağı yakalar (limit 50)
- [ ] Kaydet → `PUT /crm/aliases/{accountid}/source-mappings` (mevcut kuralları ezmeden **ekle**)
- [ ] Kaydet sonrası: ilgili müşterinin cache'ini invalide et (`mapping_cache_invalidator.py`),
      Eşleşmeyen tablosunu yenile
- [ ] **Çakışma kontrolü:** aynı `match_value` başka bir müşteride tanımlıysa uyar, kaydettirme
- [ ] Yetki: yalnızca operasyon/admin rolü (`action:` düğümü ekle)
- [ ] Denetim izi: `updated_by`, `updated_at`, `source='ui'` alanları doldurulsun
- [ ] Toplu işlem (nice-to-have): aynı `guessed_owner`'a sahip tüm satırları tek kuralla eşleştir

## Doğrulama SQL'leri

```sql
-- 1) Eşleşmeyen makine sayısı (öncesi durum)
SELECT COUNT(DISTINCT vmname) FROM public.vm_metrics
WHERE "timestamp" > now() - interval '1 day' AND LEFT(vmname,1) <> '_';

-- 2) Mevcut kural sayısı ve dağılımı (bulutwebui)
SELECT data_source, match_method, COUNT(*) AS kural
FROM   gui_crm_customer_source_mapping WHERE enabled
GROUP  BY 1,2 ORDER BY 3 DESC;

-- 3) Çakışma kontrolü: aynı match_value birden fazla müşteride mi
SELECT data_source, lower(match_value) AS deger, COUNT(DISTINCT crm_accountid) AS musteri
FROM   gui_crm_customer_source_mapping WHERE enabled
GROUP  BY 1,2 HAVING COUNT(DISTINCT crm_accountid) > 1;

-- 4) Yeni kuralın kapsamı (önizleme mantığının SQL karşılığı — prefix örneği)
SELECT COUNT(DISTINCT vmname) AS yakalanan
FROM   public.vm_metrics
WHERE  "timestamp" > now() - interval '1 day'
  AND  LEFT(vmname,1) <> '_'
  AND  lower(vmname) LIKE lower(:prefix) || '%';

-- 5) Kural sonrası eşleşmeyen sayısı (sonrası durum — 1 ile karşılaştır)
```

```bash
curl -s "http://10.134.52.250:8001/api/v1/customers/unmapped/resources?range=1d" \
 | python3 -c "
import json,sys;d=json.load(sys.stdin)
print('toplam:',d.get('total'),'alias_gap:',d.get('alias_gap_count'),'orphan:',d.get('orphan_count'))
for r in (d.get('rows') or [])[:10]: print(' ', r)
"
```

## Kabul kriterleri
- [ ] Her satırda buton var; tıklayınca modal `guessed_owner` önseçili açılıyor
- [ ] Önizleme kaydetmeden önce yakalanacak kaynak sayısını ve örnek listesini gösteriyor
- [ ] Kaydet sonrası makine ilgili müşterinin Customer View'ında görünüyor (uçtan uca doğrulandı)
- [ ] Çakışan `match_value` engelleniyor / uyarılıyor
- [ ] Yetkisiz kullanıcı butonu göremiyor
- [ ] `alias_gap` sayısı düzeltmeler sonrası ölçülebilir şekilde azalıyor (önce/sonra rapor)

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md,
datalake-platform-knowledge-base/adrs/ADR-0008-crm-customer-identity-resolution.md,
src/pages/unmapped_resources.py, shared/customer/unmapped_classifier.py,
services/customer-api/app/db/queries/unmapped.py, services/customer-api/app/routers/sales.py
(crm/aliases endpoint'leri), services/customer-api/app/services/{customer_mapping_resolver.py,
mapping_cache_invalidator.py}, src/utils/crm_source_mapping_ui.py

Görev: "Eşleşmeyen Veriler" tablosuna satır bazlı alias düzeltme butonu ekle.

1. Yeni endpoint: POST /api/v1/crm/aliases/preview-match
   Body: {data_source, match_method, match_value}
   Döner: {matched_count, sample_names[<=50], conflicts:[{crm_accountid, match_value}]}
   Çakışma = aynı data_source + aynı/örtüşen match_value başka bir müşteride tanımlı.
2. unmapped_resources.py: tabloya aksiyon kolonu ve modal ekle.
   Modal alanları: müşteri (CRM hesap listesi, guessed_owner önseçili), data_source,
   match_method (exact/prefix/contains/suffix), match_value (makine adından türetilmiş öneri), priority.
   Değer değiştikçe preview-match çağrılsın (debounce) ve "N kaynak yakalanacak" gösterilsin.
3. Kaydet: PUT /api/v1/crm/aliases/{crm_accountid}/source-mappings ile kuralı EKLE
   (mevcut kuralları ezme). source='ui', updated_by=oturum kullanıcısı.
4. Kaydet sonrası mapping_cache_invalidator ile SADECE o müşterinin cache'ini invalide et,
   tabloyu yenile ve toast göster.
5. Yetki: src/auth/permission_catalog.py'ye action:unmapped:fix düğümü; yetkisizde buton render edilmesin.
6. tests/: preview-match doğruluğu, çakışma tespiti, kaydetmenin mevcut kuralları ezmediği.

Kısıt: Çakışan kural sessizce kaydedilmemeli. Yanlış geniş kural (tek harflik contains gibi)
için uyarı eşiği koy (örn. >500 kaynak yakalıyorsa ekstra onay iste).
```

## İlgili
TASK-06 ve TASK-16 aynı tabloyu (`gui_crm_customer_source_mapping`) kullanıyor.
Bu buton, o iki maddenin **operasyonel çözümü** — birlikte planlayın.
