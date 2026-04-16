# Executor Prompt — Global View Entegrasyonu (Mock Dashboard)

## Görev

Mevcut **mock dashboard** projesindeki **Global View** sayfasını, production dashboard'daki (`Datalake-Platform-GUI`) güncel Global View implementasyonuyla birebir aynı **UI yapısına** getir. Referans dokümanı: `task/changes_for_mock_dashboard/full_changes.md`

---

## Bağlam

- **Kaynak proje (production):** `Datalake-Platform-GUI` — Dash + dash-mantine-components + custom DashGlobe (MapLibre) component kullanan bir datacenter monitoring dashboard. Gerçek veritabanı ve API'lere bağlı.
- **Hedef proje (mock):** Aynı teknoloji stack'ine sahip mock/demo versiyonu. **Kendi mock data altyapısı var** (statik JSON, in-memory dict, mock service katmanı vs.). Bu mock data'yı olduğu gibi kullanacağız.
- **Sorun:** Mock dashboard'daki Global View sayfası eski görünüm/yapıya sahip. Production'daki güncel UI yapısı mock'a henüz taşınmamış.

> **ÖNEMLİ:** Yeni mock data oluşturma, production verilerini kopyalama veya production API'lerine bağlanma **YAPMA**. Mock dashboard'un kendi mevcut data katmanını keşfet ve onu kullan.

---

## Referans Dosya

`@task/changes_for_mock_dashboard/full_changes.md` dosyasını **baştan sona dikkatlice oku**. Bu dosya şunları içeriyor:

1. **Mimari şema** — Globe → Building Reveal → Floor Map state machine akışı
2. **DashGlobe custom component** — React kaynak kodu, Python wrapper, webpack config, npm bağımlılıkları, setup.py
3. **`global_view.py`** — Tüm fonksiyonlar: koordinat haritaları, `_build_globe_data()`, `_build_region_menu()`, `build_region_detail_panel()`, `build_global_view()`, `build_dc_info_card()`, `build_3d_rack_overlay()`, export fonksiyonları
4. **`floor_map.py`** — Rack grid çizim sistemi, hall zone layout, tüm sabitler
5. **`region_drilldown.py`** — Stub sayfa
6. **11 adet callback** — `app.py`'de yer alan tüm Global View callback'leri (pin click, double-click → building reveal, timer → floor map, 3D hologram modal açma/kapama, region menu click, camera zoom, reset, CSV/Excel/PDF export)
7. **Sidebar navigation** — Global View NavLink tanımı
8. **CSS kuralları** — ~300 satır (pin animasyonları, hologram overlay, building reveal, floor map, MapLibre popup, rack unit diagram)
9. **API response kontratları** — `/datacenters/summary`, `/datacenters/{id}`, `/racks`, `/devices` endpoint'lerinin döndüğü JSON yapıları
10. **Store & Interval listesi** — 5 dcc.Store + 1 dcc.Download + 1 dcc.Interval
11. **Tüm bağımlılıklar** — Python packages, npm packages, CDN kaynakları

---

## Uygulama Adımları

### Adım 1 — Mock Projeyi Keşfet (EN KRİTİK ADIM)

1. Mock dashboard projesinin dizin yapısını **baştan sona** incele
2. **Mock data katmanını keşfet:** Mock proje verileri nereden alıyor? (statik JSON dosyaları, in-memory dict'ler, mock service fonksiyonları, fake API client?) Bu yapıyı tam olarak anla.
3. Mevcut Global View sayfasını bul — eski yapının hangi mock data fonksiyonlarını çağırdığını anla
4. Diğer sayfaların (Home, Datacenters, DC View vb.) mock data'yı nasıl kullandığını incele — aynı pattern'i Global View için de kullanacaksın
5. Mock data'da datacenter summary, DC detail, rack ve device verileri mevcut mu kontrol et. **Eksik olan mock data varsa, mevcut mock data yapısına uygun şekilde ekle** (production verisini kopyalama, mock formatında tut)
6. Mevcut sidebar, CSS, ve callback yapısını anla

### Adım 2 — DashGlobe Component'i Entegre Et

1. `dash_globe_component/` dizinini mock projeye kopyala (veya zaten varsa güncelle)
2. Eğer component build edilmemişse: `cd dash_globe_component && npm install && npm run build`
3. Mock projenin `setup.py` veya `requirements.txt`'inde `dash_globe_component`'in yüklü olduğundan emin ol

### Adım 3 — Mock Data Katmanını Bağla

**Yeni mock data oluşturma!** Mock dashboard'un mevcut data katmanını kullan.

1. Mock projede datacenter listesi / summary verisi hangi fonksiyon/dosyadan geliyor? Onu tespit et.
2. DC detail verisi hangi fonksiyondan geliyor? Onu tespit et.
3. Rack ve device verileri mevcut mu? Kontrol et.
4. `full_changes.md §10`'daki response formatlarını referans alarak, mock data'nın döndüğü format ile production formatı arasındaki **alan adı farklarını** belirle (örn: mock'ta `"name"` production'da `"id"` olabilir)
5. Gerekirse küçük bir adapter/mapper fonksiyonu yaz — ama mock data'nın kendisini değiştirme
6. Eğer mock data'da rack/device verisi yoksa, mock data yapısına **uygun formatta** minimal veri ekle (production verisini kopyalama, yapısal olarak tutarlı sahte veri üret)

### Adım 4 — `global_view.py` Güncelle

full_changes.md'deki production kodunu referans alarak mock projedeki `global_view.py`'yi güncelle:

1. Tüm import'ları ekle (özellikle `dash_globe_component`)
2. Coordinate map'leri ekle: `CITY_COORDINATES`, `DC_COORDINATES`, `REGION_HIERARCHY`, `REGION_ZOOM_TARGETS`, `_CITY_OFFSETS`
3. Helper fonksiyonları ekle: `_build_globe_data()`, `_health_colors()`, `_pct_color()`, `_build_region_menu()`
4. Panel builder'ları ekle: `build_region_detail_panel()`, `build_dc_info_card()`, `build_3d_rack_overlay()`
5. Ana layout builder'ı ekle: `build_global_view()`
6. Export fonksiyonlarını ekle: `_global_export_table()`, `export_global_view()` callback
7. **API çağrılarını mock dashboard'un kendi data fonksiyonlarıyla değiştir** — production'daki `api.get_all_datacenters_summary(tr)` çağrısını mock projenin mevcut data katmanındaki karşılığıyla değiştir

### Adım 5 — `floor_map.py` Ekle/Güncelle

1. Tüm sabitler: `RACK_W`, `RACK_H`, `GAP_X`, `AISLE_H`, `STATUS_FILL`, vs.
2. Tüm fonksiyonlar: `_parse_row_col()`, `_hall_dimensions()`, `_draw_rack()`, `_draw_hall_zone()`, `build_floor_map_figure()`, `build_floor_map_layout()`
3. full_changes.md §5'teki yapıyı birebir uygula

### Adım 6 — `region_drilldown.py` Ekle

full_changes.md §6'daki stub kodu ekle.

### Adım 7 — Callback'leri Ekle

Mock projenin `app.py`'sine (veya callback dosyasına) şu 11 callback'i ekle:

| # | Callback | Input → Output |
|---|----------|---------------|
| 1 | `handle_globe_pin_click` | `global-map-graph.clickedPoint` → `global-detail-panel`, `last-clicked-dc-id`, `current-view-mode`, `selected-building-dc-store` |
| 2 | `open_3d_hologram_modal` | `{"type":"open-3d-hologram-btn","index":ALL}.n_clicks` → `global-3d-modal-container` children & style |
| 3 | `close_3d_hologram_modal` | `close-3d-overlay-btn.n_clicks` → `global-3d-modal-container` style |
| 4 | `view_controller` | `current-view-mode.data` → `globe-layer`, `building-reveal-layer`, `floor-map-layer` styles + timer |
| 5 | `advance_to_floor_map` | `building-reveal-timer.n_intervals` → `current-view-mode`, `floor-map-layer` children |
| 6 | `back_to_globe` | `back-to-global-btn.n_clicks` → `current-view-mode`, `last-clicked-dc-id` |
| 7 | `show_rack_detail` | `floor-map-graph.clickData` → `floor-map-rack-detail` children |
| 8 | `reset_global_detail` | `global-map-reset-btn.n_clicks` → `global-detail-panel`, `global-map-graph.focusRegion` |
| 9 | `update_region_store` | `{"type":"region-nav","region":ALL}.n_clicks` → `selected-region-store` |
| 10 | `update_globe_camera` | `selected-region-store.data` → `global-map-graph.focusRegion` |
| 11 | `update_global_detail_from_menu` | `selected-region-store.data` → `global-detail-panel` children |

Ek: PDF export clientside callback'i ve CSV/Excel export callback'i.

Her callback'teki `api.*` çağrılarını **mock dashboard'un kendi mevcut data katmanındaki fonksiyonlarla** değiştir. Yeni mock data oluşturma.

### Adım 8 — CSS Ekle

full_changes.md §9'daki tüm CSS kurallarını mock projenin stylesheet'ine ekle:

- Region nav links (§9.2)
- Detail panel animation (§9.3)
- Region accordion (§9.4)
- DC detail card hover (§9.5)
- 3D Hologram overlay (§9.6) — `hologram-scene`, `dc-hologram-base`, `hall-layer`, `rack-micro-grid`, `rack-micro-card` + 3 keyframe animasyonu
- Building reveal layer (§9.7) — `building-reveal-inner`, `building-reveal-icon`, `brd-dot` + 4 keyframe animasyonu
- MapLibre DC pins (§9.8) — `dc-map-pin`, `dc-pin-dot`, `dc-pin-pulse` + `pinPulse` keyframe
- MapLibre controls override (§9.9)
- MapLibre premium popup (§9.10) — `dc-popup-inner`, `dc-popup-header`, `dc-popup-stats`
- Floor map page (§9.11) — `floor-map-page`, `floor-map-header`, `floor-map-canvas-wrap`, `floor-map-detail-panel`
- Rack unit diagram (§9.12) — `rack-unit-cabinet`, `rack-rail`

### Adım 9 — Sidebar Güncelle

Sidebar'da "Global View" link'inin doğru şekilde tanımlı olduğundan emin ol:
```python
dmc.NavLink(
    label="Global View",
    leftSection=DashIconify(icon="solar:global-bold-duotone", width=20),
    href="/global-view",
    className="sidebar-link",
    active=active_path == "/global-view",
    variant="subtle",
    color="indigo",
    style={"borderRadius": "8px", "fontWeight": "500", "marginBottom": "5px"},
)
```

### Adım 10 — Route Tanımı

Mock projenin route handler'ında `/global-view` path'ini ekle:
```python
if pathname == "/global-view":
    return global_view.build_global_view(tr)
```

### Adım 11 — Test Et

1. Mock dashboard'u çalıştır
2. `/global-view` sayfasına git
3. Şunları doğrula:
   - ✅ MapLibre harita yükleniyor, pin'ler doğru konumlarda
   - ✅ Pin hover → premium popup görünüyor
   - ✅ Pin click → DC info card açılıyor (RingProgress gauges + host/VM/kW bilgileri)
   - ✅ Aynı pin'e tekrar click → Building reveal animasyonu → 1.8s sonra Floor Map
   - ✅ Floor map'te rack click → sağ panelde rack detayı
   - ✅ "Back" butonu → Globe'a dönüş
   - ✅ Region accordion menüsü çalışıyor
   - ✅ Region click → harita zoom + detail panel güncelleniyor
   - ✅ "Detail" butonu → 3D Hologram modal açılıyor
   - ✅ Reset butonu → varsayılan zoom'a dönüş
   - ✅ Export butonları (CSV/Excel/PDF) çalışıyor
   - ✅ Tüm CSS animasyonları düzgün render ediliyor

---

## Kurallar

1. **Kod içine yorum yazma** — Production kodda yorum yok, mock'ta da olmamalı
2. **Yapıyı birebir koru** — Component ID'leri, class name'leri, style değerleri, renk kodları production ile aynı olmalı
3. **Sadece API/data katmanını değiştir** — Production'daki `api.get_*()` çağrılarını mock dashboard'un kendi mevcut data fonksiyonlarıyla değiştir, UI koduna dokunma
4. **Yeni mock data oluşturma** — Mock dashboard'un halihazırda sahip olduğu veri altyapısını kullan. Production'dan veri kopyalama
5. **Mock data formatı uyuşmuyorsa** — Küçük adapter fonksiyonları yazabilirsin ama mock data'nın kendisini değiştirme
6. **Eksik kalmasın** — 11 callback, tüm CSS kuralları, tüm fonksiyonlar eksiksiz olmalı
7. **Bağımlılıkları kontrol et** — `dash_globe_component`, `dash-mantine-components`, `dash-iconify`, `plotly`, `pandas` yüklü olmalı

---

## Öncelik Sırası

Eğer zaman kısıtlıysa, şu sırayla ilerle:

1. 🔴 **Kritik:** `build_global_view()` layout + DashGlobe component + pin data
2. 🔴 **Kritik:** Globe pin click → info card callback
3. 🟠 **Yüksek:** Region menu + camera zoom callbacks
4. 🟠 **Yüksek:** Tüm CSS kuralları
5. 🟡 **Orta:** Building reveal → Floor map transition
6. 🟡 **Orta:** 3D Hologram modal
7. 🟢 **Düşük:** Export (CSV/Excel/PDF)
8. 🟢 **Düşük:** Region drilldown stub
