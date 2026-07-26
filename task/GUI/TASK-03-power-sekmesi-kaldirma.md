# TASK-03 — Power Sekmesinin Kaldırılması

**Tip:** UI temizliği · **Efor:** S · **Öncelik:** Yüksek (hızlı kazanım)

## Hedef
Arayüzdeki "Power" ile ilgili bölüm (Power Mimari, SAP Power HANA vb.) tamamen kaldırılacak.

## ⚠️ Önemli tasarım kararı: kaldırma değil, feature-flag ile gizleme

Power, UI'da tek bir sekme değil; **veri modelinin içine gömülü bir aile**:

- Aileler: `virt_power`, `virt_power_hana` (`_ALLOC_ONLY_FAMILIES`, `_INVENTORY_VIRT_FAMILIES`)
- Panel key'ler: `virt_power_hana_cpu`, `virt_power_hana_ram`
- CRM ürünleri: `000BLT-*` SAP Power HANA CPU / RAM (bkz. `shared/matching/product_matching_registry.yaml` "SAP / Power" bölümü)
- Mimari karar: **ADR-0022 — power allocation-only sellable track**

Kodu silmek sellable hesabını, permission ağacını ve inventory satırlarını kırar.
**Önerilen:** tek bir bayrakla (`FEATURE_POWER_ENABLED=false`) UI'dan gizle, hesap katmanını dokunulmadan bırak.
Ekip "veri de gitsin" derse ikinci fazda registry/panel temizliği yapılır.

## Dokunulacak yerler

| Yer | Ne var |
|---|---|
| `src/pages/dc_view.py` | Power sekmesi + panelleri |
| `src/pages/customer_view.py` | `_tab` ~1611 "Power Mimari (IBM LPAR) billing tab", ~1689 "IBM LPARs", ~905 `("Power Compute (IBM)", power, "lpar_count")` |
| `src/pages/home.py`, `src/pages/global_view.py`, `src/pages/datacenters.py` | Power KPI/kart referansları |
| `src/pages/dc_summary_sellable.py`, `src/pages/crm_sellable_potential.py` | `virt_power*` aileleri |
| `src/components/crm_inventory_report.py` | satır 33-34: `"virt_power"`, `"virt_power_hana"` |
| `src/components/customer_summary_panel.py` | Power özet kartı |
| `src/auth/permission_catalog.py` | Power ile ilgili `sec:`/`sub:` düğümleri |
| `services/customer-api/app/services/inventory_overview_service.py` | `_ALLOC_ONLY_FAMILIES`, `_VIRT_FAMILY_LABELS["virt_power"/"virt_power_hana"]` |
| `src/utils/datacenters_virt_sellable.py` | Power payı |

## Yapılacaklar

- [ ] Önce **envanter çıkar:** `grep -rn "virt_power\|Power Mimari\|Power HANA\|lpar_count" src services shared` çıktısını dosyaya yaz
- [ ] `src/utils/feature_flags.py` (yoksa oluştur) → `POWER_ENABLED = os.getenv("FEATURE_POWER_ENABLED","false").lower()=="true"`
- [ ] UI: sekme/kart/KPI render'larını bayrağa bağla. **Panel görünürlük kuralı** (`docs/PROJECT_STANDARDS.md` §3):
      sekme hiç eklenmez, boş sekme gösterilmez
- [ ] Permission: Power düğümlerini katalogdan gizle (silme — mevcut rol atamaları kırılmasın)
- [ ] Inventory/Sellable: `virt_power*` satırları UI listesinden filtrelensin; hesap katmanı çalışmaya devam etsin
- [ ] Export (Excel/PDF) sayfalarında Power sheet'i çıkar (`src/utils/export_helpers.py` kullanan yerler)
- [ ] Chatbot/knowledge katalogunda Power referansları varsa not düş (`docs/chatbot-knowledge`)
- [ ] Snapshot/regression testleri güncelle

## Doğrulama

```bash
# UI'da hiçbir yerde Power geçmiyor mu
curl -s http://10.134.52.250:8050/ | grep -i "power" || echo "temiz"

# API hâlâ sağlıklı (hesap katmanı bozulmadı)
curl -s http://10.134.52.250:8070/api/v1/crm/sellable-potential/by-family | python3 -m json.tool | head -40
curl -s "http://10.134.52.250:8070/api/v1/crm/inventory-overview?dc_code=*" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print([r.get('family_label') for r in d.get('rows',[])][:20])"
```

```sql
-- Power'ın veri tarafında hâlâ var olduğunu doğrula (silmedik, gizledik)
SELECT COUNT(*) FROM public.ibm_lpar_general WHERE "time" > now() - interval '1 day';
SELECT page_key, category_label FROM gui_crm_service_pages WHERE page_key ILIKE '%power%';  -- bulutwebui
```

## Kabul kriterleri
- [ ] DC View, Customer View, Home, Global View, Sellable ve Inventory ekranlarının hiçbirinde Power görünmüyor
- [ ] `FEATURE_POWER_ENABLED=true` ile eski davranış birebir geri geliyor (geri alınabilirlik)
- [ ] Hiçbir sayfada boş sekme / boş grafik / JS konsol hatası yok
- [ ] Sellable ve Inventory API'leri 200 dönüyor, toplamlar Power hariç tutarlı

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, docs/PROJECT_STANDARDS.md (§3 panel görünürlük),
datalake-platform-knowledge-base/adrs/ADR-0022-power-allocation-only-sellable-track.md

Görev: Arayüzden Power (Power Mimari, SAP Power HANA, IBM LPAR billing) bölümlerini kaldır.

Yaklaşım: KOD SİLME. src/utils/feature_flags.py içinde POWER_ENABLED bayrağı
(env FEATURE_POWER_ENABLED, varsayılan false) tanımla ve UI render noktalarını buna bağla.
Hesap/servis katmanına (inventory_overview_service, sellable) dokunma — sadece UI'da gizle.

1. Önce grep ile tam envanter çıkar: virt_power, virt_power_hana, "Power Mimari", "Power HANA",
   lpar_count, Power Compute. Bulduğun her noktayı listele.
2. dc_view.py / customer_view.py / home.py / global_view.py / datacenters.py /
   dc_summary_sellable.py / crm_sellable_potential.py / components/crm_inventory_report.py /
   components/customer_summary_panel.py içindeki Power render'larını bayrağa bağla.
   Sekme, "boş sekme" olarak değil, HİÇ eklenmeyecek şekilde kaldırılsın.
3. src/auth/permission_catalog.py: Power düğümlerini bayrağa bağlı gizle, silme.
4. Export helper'ları kullanan yerlerde Power sheet'ini bayrağa bağla.
5. FEATURE_POWER_ENABLED'i .env.example ve docker-compose.yml'e dokümante et.
6. tests/: bayrak false iken Power sekmesinin render edilmediğini, true iken edildiğini doğrulayan test yaz.

Sonuç: bayrak true yapıldığında eski davranış birebir dönmeli.
```

## Risk
- Power kaldırılınca inventory toplamları düşer → paydaşlara "kapsam değişti" bilgisi verilmeli
- TASK-02'deki Power doğrulaması hâlâ geçerli (veri arka planda kullanılıyor)
- **TASK-04'ten önce yapılmalı** (kaldırılacak aileyi düzeltmekle vakit kaybetmeyelim)
