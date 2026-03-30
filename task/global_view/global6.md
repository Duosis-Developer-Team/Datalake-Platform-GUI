# 🏛️ GLOBAL MAP VIEW V6.0 — Komuta Merkezi Layout Devrimi & Region Menu Bar

> **Versiyon:** 6.0  
> **Tarih:** 2026-03-28  
> **Hazırlayan:** Baş Planlayıcı & Sistem Mimarı  
> **Hedef:** Ana sayfayı "Komuta Merkezi" vizyonuyla yeniden tasarlamak — 3D Küre + Hiyerarşik Region Menu Bar + Alt Detay Paneli — Drilldown sayfasını boşaltmak ve tüm metrikleri tek ekranda birleştirmek.

---

## DOKUNULACAK DOSYALAR

| # | Dosya | İşlem | Tahmini Değişiklik |
|---|-------|-------|--------------------|
| 1 | `src/pages/global_view.py` | **BÜYÜK REVİZYON** | ~250 satır ekleme/değişiklik |
| 2 | `app.py` | **GÜNCELLE** | ~120 satır ekleme/değişiklik |
| 3 | `src/pages/region_drilldown.py` | **BOŞALT** | 265→~30 satır |
| 4 | `assets/style.css` | **GÜNCELLE** | ~50 satır ekleme |

---

## ADIM 1 — Grid / Layout Revizyonu

### 1.1 Mevcut Layout Yapısı (Kaldırılacak)

`build_global_view` (satır 255-385) şu anda döndürüyor:

```
html.Div
  ├── dmc.Paper (Header: başlık + badge)
  ├── dmc.Paper (dcc.Graph "global-map-graph") ← TAM GENİŞLİK
  └── html.Div#global-dc-info-card ← Pin tıklayınca açılan info card
```

### 1.2 Yeni Komuta Merkezi Layout'u

```
html.Div
  ├── dcc.Store(id="selected-region-store", data=None)
  │
  ├── dmc.Paper (Header: başlık + badge) ← KORUNUYOR
  │
  ├── dmc.Grid(gutter="lg")
  │   ├── dmc.GridCol(span=8)
  │   │   └── dmc.Paper(radius="lg")
  │   │       └── dcc.Graph(id="global-map-graph")
  │   │           height: 600px (650→600)
  │   │
  │   └── dmc.GridCol(span=4)
  │       └── dmc.Paper(id="region-menu-panel", radius="lg", h=600)
  │           ├── dmc.Group (header: "Regions" + ikon + "Reset" butonu)
  │           ├── dmc.Divider
  │           └── dmc.ScrollArea(h=520, type="auto")
  │               └── dmc.Accordion(id="region-accordion")
  │                   ← Hiyerarşik menü (ADIM 2)
  │
  └── html.Div(id="global-detail-panel")
      ├── style: padding 0 32px, marginTop 24px
      └── Başlangıçta BOŞ — seçim yapılınca dolar
```

> **🔮 MİMAR NOTU — İLK KEZ `dmc.Grid` KULLANIMI:**
> Proje genelinde `dmc.Grid` henüz hiç kullanılmamış. `dmc.Grid` Mantine'ın 12-sütun grid sistemidir. `gutter` prop'u sütunlar arası boşluğu belirler. `span=8` ve `span=4` toplamda 12 yapar (tam satır). Dash Mantine Components paketinde bu bileşen mevcut — ek kurulum gerekmez.

### 1.3 `dcc.Store` — Neden Gerekli?

Pin tıklama ve menü tıklama farklı bileşenlerden geliyor ama **aynı 2 etkiyi** tetiklemeli: harita zoom + detay paneli. `dcc.Store` bir ara veri deposu olarak kullanılacak.

Mevcut projede `dcc.Store(id="app-time-range")` aynı pattern ile zaten kullanılıyor (app.py satır 162).

Format:
```python
{"region": "ISTANBUL", "lon": 28.96, "lat": 41.01, "scale": 40.0, "ts": 1711644000}
```

> **🔮 MİMAR NOTU — `ts` ALANI (Timestamp) - ÖNEMLİ:**
> Aynı bölgeye art arda 2 kez tıklandığında `dcc.Store` verisi değişmez → callback tetiklenmez. Bunu çözmek için **her tıklamada `ts` alanına `time.time()` değeri** yazılmalı. Böylece aynı bölgeye tekrar tıklandığında store verisi değişir ve callback'ler tekrar tetiklenir. Bu, Dash'in `dcc.Store` ile bilinen bir gotcha'sıdır.

### 1.4 Harita Yüksekliği Ayarı

2 yerde değişiklik:
1. `_create_map_figure` fonksiyonundaki `fig.update_layout(height=650)` → `height=600` (satır 246)
2. `dcc.Graph` style `{"height": "650px"}` → `{"height": "600px"}` (satır 375)
3. Boş harita dalındaki (satır 120) `height=650` → `height=600`

### 1.5 "Reset Map View" Butonu — Yeni Konum

Mevcut durum: `build_dc_info_card` içinde (satır 468-476) — detay paneli açılmadan buton görünmüyor.

Yeni durum: **Region Menu Panel** header'ına taşınacak. Böylece:
- Kullanıcı herhangi bir bölgeyi seçtikten sonra menü panelinden her zaman reset yapabilir
- Detay paneli açılmasa bile reset erişilebilir
- Haritanın sağ üst köşesi temiz kalır

> **🔮 MİMAR NOTU — Reset Butonu UX Sorunu:**
> Eski tasarımda reset butonu sadece pin tıklanınca görünüyordu. Yeni tasarımda menüden zoom yapıldığında da reset'e ihtiyaç var. Bu yüzden reset butonunun her zaman görünür olması gerekiyor. Region Menu Panel'in header'ı bu iş için ideal konum.

### 1.6 CSS Güncellemeleri (`assets/style.css`)

`style.css` dosyasına eklenecek yeni kurallar:

```css
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(16px); }
    to   { opacity: 1; transform: translateY(0); }
}

.region-nav-link {
    border-radius: 8px !important;
    margin-bottom: 4px !important;
    transition: all 0.2s ease;
}

.region-nav-link:hover {
    background-color: rgba(67, 24, 255, 0.05) !important;
    padding-left: 20px !important;
}

.region-nav-link[data-active="true"] {
    background: linear-gradient(135deg, #4318FF 0%, #5630FF 100%) !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
    box-shadow: 0px 6px 16px rgba(67, 24, 255, 0.20) !important;
}

.detail-panel-animate {
    animation: fadeInUp 0.35s ease-out;
}

.region-accordion .mantine-Accordion-control:hover {
    background-color: rgba(67, 24, 255, 0.03) !important;
}

.region-accordion .mantine-Accordion-content {
    padding: 4px 8px !important;
}
```

> **🔮 MİMAR NOTU — `fadeInUp` Zaten Referans Ediliyor:**
> `build_dc_info_card` fonksiyonunda (satır 438) `"animation": "fadeInUp 0.3s ease-out"` zaten kullanılıyor AMA CSS'te bu keyframe tanımlı değil. Bu bir **mevcut bug**. Bu güncelleme ile hem mevcut hem yeni ihtiyaç karşılanacak.

---

## ADIM 2 — Global Region Menu Bar Tasarımı

### 2.1 Hiyerarşik Veri Yapısı

`global_view.py` dosyasına eklenecek sabit:

```python
REGION_HIERARCHY = {
    "Europe": {
        "icon": "solar:earth-bold-duotone",
        "children": {
            "ALMANYA": {"label": "Germany", "flag": "twemoji:flag-germany"},
            "INGILTERE": {"label": "United Kingdom", "flag": "twemoji:flag-united-kingdom"},
            "HOLLANDA": {"label": "Netherlands", "flag": "twemoji:flag-netherlands"},
            "FRANSA": {"label": "France", "flag": "twemoji:flag-france"},
        },
    },
    "Turkey Region": {
        "icon": "twemoji:flag-turkey",
        "children": {
            "ISTANBUL": {"label": "Istanbul"},
            "ANKARA": {"label": "Ankara"},
            "IZMIR": {"label": "Izmir"},
        },
    },
    "Asia & CIS": {
        "icon": "solar:earth-bold-duotone",
        "children": {
            "AZERBAYCAN": {"label": "Azerbaijan", "flag": "twemoji:flag-azerbaijan"},
            "OZBEKISTAN": {"label": "Uzbekistan", "flag": "twemoji:flag-uzbekistan"},
        },
    },
}
```

> **🔮 MİMAR NOTU — Genişletilebilirlik:**
> İleride yeni DC lokasyonları eklendiğinde sadece bu dict'e yeni kayıt eklenmesi yeterli. `CITY_COORDINATES` dict'i ile 1:1 eşleşme sağlanmalı — `REGION_HIERARCHY`'deki her key `CITY_COORDINATES`'ta da bulunmalı. Aksi halde menüde görünür ama haritada pin olmaz.

### 2.2 Zoom Koordinat Haritası

```python
REGION_ZOOM_TARGETS = {
    "ISTANBUL":    {"lon": 28.96, "lat": 41.01, "scale": 40.0},
    "ANKARA":      {"lon": 32.85, "lat": 39.93, "scale": 15.0},
    "IZMIR":       {"lon": 27.13, "lat": 38.42, "scale": 15.0},
    "AZERBAYCAN":  {"lon": 49.87, "lat": 40.41, "scale": 6.0},
    "ALMANYA":     {"lon": 8.68,  "lat": 50.11, "scale": 6.0},
    "INGILTERE":   {"lon": -0.13, "lat": 51.51, "scale": 6.0},
    "OZBEKISTAN":  {"lon": 69.24, "lat": 41.30, "scale": 6.0},
    "HOLLANDA":    {"lon": 4.90,  "lat": 52.37, "scale": 6.0},
    "FRANSA":      {"lon": 2.35,  "lat": 48.85, "scale": 6.0},
}
```

> **🔮 MİMAR NOTU — `CITY_COORDINATES` ile Senkronizasyon:**
> `REGION_ZOOM_TARGETS` koordinatları `CITY_COORDINATES` (satır 11-21) ile birebir aynı olmalı. scale değerleri mevcut clientside callback'ten (app.py satır 501) alınmış. **İstanbul'un 40.0 scale'i** çok agresif bir zoom — eski kodda bu mevcut zaten çalışıyor. Ancak bazı durumlarda kullanıcı deneyimini test ettikten sonra 20.0'a düşürülebilir.

### 2.3 Bileşen Yapısı — `dmc.Accordion` + `dmc.NavLink`

```
dmc.Accordion(id="region-accordion", variant="separated", radius="md",
              chevronPosition="right", multiple=True, value=["Turkey Region"],
              className="region-accordion")
  │
  ├── dmc.AccordionItem(value="Europe")
  │   ├── dmc.AccordionControl
  │   │   └── dmc.Group(gap="sm")
  │   │       ├── DashIconify(icon="solar:earth-bold-duotone", width=20, color="#4318FF")
  │   │       ├── dmc.Text("Europe", fw=700, size="sm", c="#2B3674")
  │   │       └── dmc.Badge("{n} DCs", variant="light", color="gray", size="xs")
  │   └── dmc.AccordionPanel(p="xs")
  │       ├── dmc.NavLink(id={"type":"region-nav","region":"ALMANYA"}, className="region-nav-link")
  │       │   ├── leftSection: DashIconify(icon="twemoji:flag-germany", width=18)
  │       │   ├── label: "Germany"
  │       │   └── rightSection: dmc.Badge("{n} DCs", size="xs", variant="light", color="indigo")
  │       ├── dmc.NavLink(id={"type":"region-nav","region":"INGILTERE"}) ...
  │       ├── dmc.NavLink(id={"type":"region-nav","region":"HOLLANDA"}) ...
  │       └── dmc.NavLink(id={"type":"region-nav","region":"FRANSA"}) ...
  │
  ├── dmc.AccordionItem(value="Turkey Region")
  │   └── ... ISTANBUL, ANKARA, IZMIR
  │
  └── dmc.AccordionItem(value="Asia & CIS")
      └── ... AZERBAYCAN, OZBEKISTAN
```

> **🔮 MİMAR NOTU — İLK KEZ `dmc.Accordion` KULLANIMI:**
> Proje genelinde `dmc.Accordion` henüz kullanılmamış. Mantine'da `variant="separated"` seçildiğinde her AccordionItem arasında boşluk bırakılır ve her biri bağımsız bir kart gibi görünür — premium hissi artırır.

> **🔮 MİMAR NOTU — `multiple=True` ve `value=["Turkey Region"]`:**
> `multiple=True` birden fazla kıtanın aynı anda açık olmasını sağlar. `value=["Turkey Region"]` sayfa yüklendiğinde Türkiye bölgesinin otomatik açık gelmesini sağlar — çünkü DC yoğunluğu en fazla Türkiye'de.

### 2.4 DC Sayısı Hesaplama

`build_global_view` fonksiyonu zaten `summaries` çekiyor. Menü oluşturulmadan önce:

```python
region_dc_counts = {}
for dc in summaries:
    sn = (dc.get("site_name") or "").upper().strip()
    region_dc_counts[sn] = region_dc_counts.get(sn, 0) + 1
```

Bu dict menü builder'a parametre olarak geçecek.

### 2.5 Menü Builder Fonksiyonu İmzası

```python
def _build_region_menu(summaries):
```

- `REGION_HIERARCHY` dict'ini iterate eder
- Her kıta için `dmc.AccordionItem` oluşturur
- Her alt bölge için `dmc.NavLink` oluşturur (Pattern-matching ID ile)
- DC sayısı 0 olan bölgeler **GRİ ve DISABLED** gösterilir → `dmc.NavLink(disabled=True, c="#A3AED0")`
- Sonuç: `dmc.Accordion(...)` döndürür

> **🔮 MİMAR NOTU — 0 DC'li Bölgeler:**
> `REGION_HIERARCHY`'de tanımlı ama o anda API'den DC gelmeyen bir bölge olabilir (Örn: Fransa'da henüz DC kurulmamış veya time range'de veri yok). Bu NavLink'ler disabled olmalı. Aksi halde tıklanınca boş detay paneli gösterilir — kötü UX.

> **🔮 MİMAR NOTU — Kıta Seviyesi Toplam Bilgisi (AccordionControl):**
> Her AccordionControl'ün sağ tarafında o kıtanın **toplam DC sayısı** badge'i gösterilecek. Bu değer, o kıtanın altındaki tüm children'ların DC sayılarının toplamıdır. Böylece kullanıcı accordion'ı açmadan bile hangi kıtada kaç DC olduğunu görebilir.

### 2.6 Pattern-Matching ID Açıklaması

Her `dmc.NavLink`'e atanan ID:
```python
{"type": "region-nav", "region": "ISTANBUL"}
```

Bu Dash'in **Pattern-Matching Callback** sistemidir. `app.py`'da tek bir callback ile TÜM NavLink'lerin `n_clicks` event'i yakalanır:

```python
from dash import ALL
Input({"type": "region-nav", "region": ALL}, "n_clicks")
```

> **🔮 MİMAR NOTU — `from dash import ALL`:**
> Bu import `app.py` satır 2'ye eklenecek. Mevcut: `from dash import Dash, html, dcc, _dash_renderer` → Yeni: `from dash import Dash, html, dcc, _dash_renderer, ALL`

---

## ADIM 3 — Harita Odaklanma / Zoom Callbacks (Menü → Harita)

### 3.1 Callback Zinciri

```
NavLink tıklanır
    → Callback A (server-side): hangi NavLink tıklandı? → selected-region-store güncelle
    → Callback B (clientside): store değişti → harita zoom animasyonu
    → Callback C (server-side): store değişti → detay paneli güncelle
```

### 3.2 Callback A — Menü Tıklama → Store Güncelleme

**Dosya:** `app.py`

```python
@app.callback(
    dash.Output("selected-region-store", "data"),
    dash.Input({"type": "region-nav", "region": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def update_region_store(n_clicks_list):
    import time as _time
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    triggered = ctx.triggered[0]
    if not triggered.get("value"):
        return dash.no_update
    import json
    prop_id = json.loads(triggered["prop_id"].rsplit(".", 1)[0])
    region = prop_id.get("region", "")
    from src.pages.global_view import REGION_ZOOM_TARGETS
    target = REGION_ZOOM_TARGETS.get(region, {})
    if not target:
        return dash.no_update
    return {
        "region": region,
        "lon": target["lon"],
        "lat": target["lat"],
        "scale": target["scale"],
        "ts": _time.time(),
    }
```

> **🔮 MİMAR NOTU — `ctx.triggered` Parsing:**
> Pattern-matching callback'lerde `triggered[0]["prop_id"]` şu formatta gelir: `'{"region":"ISTANBUL","type":"region-nav"}.n_clicks'`. Son `.n_clicks` kısmını kesmek ve JSON parse etmek gerekir. Bu Dash'in standart pattern-matching davranışıdır.

> **🔮 MİMAR NOTU — Hızlı Ardışık Tıklama (Debounce):**
> Kullanıcı menüde hızlıca farklı bölgelere tıklayabilir. Her tıklama yeni bir animasyon başlatır. Clientside callback'teki `requestAnimationFrame` loop'u önceki animasyonun üzerine yazar — bu **doğal bir debounce** sağlar. Ekstra bir önlem gerekmez.

### 3.3 Callback B — Store → Harita Zoom (Clientside)

**Dosya:** `app.py`

```javascript
app.clientside_callback(
    """
    function(storeData) {
        if (!storeData || !storeData.lon) return window.dash_clientside.no_update;
        var outer = document.getElementById('global-map-graph');
        if (!outer) return window.dash_clientside.no_update;
        var gd = outer.querySelector('.js-plotly-plot') || outer;
        if (!gd._fullLayout || !gd._fullLayout.geo) return window.dash_clientside.no_update;
        var rot = gd._fullLayout.geo.projection.rotation;
        var startLon = rot.lon, startLat = rot.lat;
        var startScale = gd._fullLayout.geo.projection.scale || 1.0;
        var tLon = storeData.lon, tLat = storeData.lat, tScale = storeData.scale;
        var dur = 1100, t0 = null;
        function ease(t) { return t<.5 ? 4*t*t*t : 1-Math.pow(-2*t+2,3)/2; }
        function step(ts) {
            if (!t0) t0 = ts;
            var p = Math.min((ts-t0)/dur, 1), e = ease(p);
            window.Plotly.relayout(gd, {
                'geo.projection.rotation.lon': startLon+(tLon-startLon)*e,
                'geo.projection.rotation.lat': startLat+(tLat-startLat)*e,
                'geo.projection.scale':        startScale+(tScale-startScale)*e
            });
            if (p < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
        return window.dash_clientside.no_update;
    }
    """,
    dash.Output("global-map-graph", "figure", allow_duplicate=True),
    dash.Input("selected-region-store", "data"),
    prevent_initial_call=True,
)
```

### 3.4 Mevcut Pin-Click Callbacks — KORUNACAK

| Callback | Satır | Durum |
|----------|-------|-------|
| Pin-click → info card (server-side) | 464-481 | ID güncelle: `global-dc-info-card` → `global-detail-panel` |
| Pin-click → zoom animation (clientside) | 484-521 | **AYNEN KORUNACAK** |
| Reset → clear info card (server-side) | 524-532 | ID güncelle: `global-dc-info-card` → `global-detail-panel` |
| Reset → zoom animation (clientside) | 535-565 | **AYNEN KORUNACAK** |

---

## ADIM 4 — Detay Panelinin Ana Sayfaya Taşınması

### 4.1 Yeni Detay Paneli Hedef ID'si

`id="global-dc-info-card"` → `id="global-detail-panel"`

Bu ID 4 yerde değişecek:
1. `global_view.py` → `build_global_view()` layout'unda (satır 381)
2. `app.py` → `update_global_info_card` callback Output (satır 465)
3. `app.py` → `reset_global_info_card` callback Output (satır 525)
4. `app.py` → Mevcut pin-click callback'lerindeki ID referansları

### 4.2 Callback C — Store → Detay Paneli (Menü Seçimi)

**Dosya:** `app.py`

```python
@app.callback(
    dash.Output("global-detail-panel", "children", allow_duplicate=True),
    dash.Input("selected-region-store", "data"),
    dash.State("app-time-range", "data"),
    prevent_initial_call=True,
)
def update_global_detail_from_menu(store_data, time_range):
    if not store_data or not store_data.get("region"):
        return dash.no_update
    region = store_data["region"]
    tr = time_range or default_time_range()
    from src.pages.global_view import build_region_detail_panel
    return build_region_detail_panel(region, tr)
```

> **🔮 MİMAR NOTU — `allow_duplicate=True` Zorunlu:**
> `global-detail-panel.children` output'una 3 farklı callback yazıyor (pin-click, menü-click, reset). İlki hariç hepsinde `allow_duplicate=True` gerekli. Mevcut kodda bu pattern zaten kullanılıyor (app.py satır 518, 525, 562).

### 4.3 Yeni Fonksiyon: `build_region_detail_panel` (global_view.py)

**İmza:** `def build_region_detail_panel(region, tr):`

Bu fonksiyon:
1. `api.get_all_datacenters_summary(tr)` → region'a ait DC'leri filtrele
2. Her DC için `api.get_dc_details(dc_id, tr)` → detay verisi çek
3. Her DC için bir kart oluştur (Gauge + metrikler)

**Yapı:**

```
html.Div(className="detail-panel-animate")
  └── dmc.Paper(p="xl", radius="lg")
      ├── Header Row (dmc.Group justify="space-between")
      │   ├── Sol: Bölge adı + ikon
      │   └── Sağ: Badge'ler (DC sayısı, toplam VM, toplam Host)
      │
      ├── dmc.Divider(my="md")
      │
      └── dmc.SimpleGrid(cols={"base":1, "sm":2, "lg":3}, spacing="lg")
          └── [Her DC için bir kart — dmc.Paper]
              ├── dmc.Group (DC adı + health badge)
              ├── dmc.SimpleGrid(cols=4, spacing="md")
              │   ├── CPU RingProgress
              │   ├── RAM RingProgress
              │   ├── Storage RingProgress
              │   └── Stats (Host/VM/Energy sayıları)
              └── dmc.Group (Architecture bilgisi)
```

> **🔮 MİMAR NOTU — PERFORMANS UYARISI:**
> Her DC için `api.get_dc_details()` çağrısı yapılıyor. Eğer bir bölgede 5+ DC varsa (Örn: İstanbul'da 4 DC), bu 4 seri HTTP isteği demek. **İlk versiyonda kabul edilebilir**, ama ileride:
> - Backend'e `/api/v1/datacenters/by-region/{site_name}` endpoint'i eklenebilir
> - Veya Python `concurrent.futures.ThreadPoolExecutor` ile paralel istek atılabilir
> - Şimdilik her DC sırayla çekilecek — kullanıcı bunu dmc.LoadingOverlay ile karşılayacak

> **🔮 MİMAR NOTU — Loading State:**
> Detay panelinin yüklenmesi sırasında kullanıcıya geri bildirim verilmeli. `dcc.Loading` wrapper kullanılabilir:
> ```python
> dcc.Loading(
>     id="detail-loading",
>     type="circle",
>     color="#4318FF",
>     children=html.Div(id="global-detail-panel", ...)
> )
> ```
> Bu, Dash'in built-in loading state'idir — callback çalışırken otomatik spinner gösterir.

> **🔮 MİMAR NOTU — Responsive `cols`:**
> `dmc.SimpleGrid(cols={"base":1, "sm":2, "lg":3})` kullanımı ile küçük ekranlarda 1 sütun, orta ekranlarda 2 sütun, büyük ekranlarda 3 sütun gösterilir. Mevcut `region_drilldown.py`'da sabit `cols=3` kullanılıyor — bu mobile'da kötü deneyim yaratır. Yeni tasarım bunu düzeltir.

### 4.4 "Region Drilldown" Butonu — KALDIR

`build_dc_info_card` fonksiyonundan (satır 477-487) tamamen kaldırılacak blok:

```python
dcc.Link(
    dmc.Button(
        "Region Drilldown",
        variant="light",
        color="indigo",
        radius="md",
        rightSection=DashIconify(icon="solar:map-point-wave-bold-duotone", width=18),
    ),
    href=f"/region-drilldown?region={site_name}",
    style={"textDecoration": "none"},
),
```

### 4.5 `build_dc_info_card` — Güncelleme

Bu fonksiyon hâlâ **pin tıklaması** için kullanılacak (tek DC detayı gösterir). Değişiklikler:
- "Region Drilldown" butonu → **KALDIR** (4.4)
- "Reset Map View" butonu → **KALDIR** (menü paneline taşındı, 1.5'e bakınız)
- Fonksiyon artık sadece DC metriklerini gösterir — buton grubu sadeleşir

> **🔮 MİMAR NOTU — İki Farklı Detay Görünümü:**
> Pin tıklaması → `build_dc_info_card(dc_id, tr)` → **Tek DC** detayı
> Menü tıklaması → `build_region_detail_panel(region, tr)` → **Tüm bölge** DC'leri
> Her ikisi de `global-detail-panel` container'ına render edilir. Kullanıcının ne gördüğü, son tıklama kaynağına bağlıdır.

### 4.6 Detay Paneli Boş Durumu (Empty State)

Sayfa ilk yüklendiğinde `global-detail-panel` boştur. Bu **doğru davranıştır** — kullanıcı menüden veya haritadan seçim yapana kadar alt panel gizli kalır.

> **🔮 MİMAR NOTU — Opsiyonel Welcome State:**
> İsteğe bağlı olarak boşken hafif bir "Select a region from the menu or click a pin on the map" mesajı gösterilebilir. Ama CTO'nun istediği "Komuta Merkezi" hissi için boş bırakmak daha temiz. Bu karar Executer'a bırakılabilir.

---

## ADIM 5 — Drilldown Sayfası Boşaltma

### 5.1 `region_drilldown.py` → Reserved Placeholder

Tüm fonksiyon içeriği kaldırılacak. Yerine:

```python
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from dash import html, dcc


def build_region_drilldown(region, time_range=None):
    return html.Div(
        dmc.Paper(
            p="xl",
            radius="lg",
            style={
                "textAlign": "center",
                "marginTop": "80px",
                "background": "rgba(255,255,255,0.90)",
                "boxShadow": "0 8px 32px rgba(67,24,255,0.10)",
            },
            children=[
                DashIconify(icon="solar:lock-keyhole-bold-duotone", width=64, color="#A3AED0"),
                html.H3("Reserved", style={"color": "#2B3674", "marginTop": "16px"}),
                dmc.Text(
                    "This page is reserved for future hardware/rack data from loki_racks.",
                    c="#A3AED0",
                    size="sm",
                ),
                dcc.Link(
                    dmc.Button(
                        "Back to Global View",
                        variant="light",
                        color="indigo",
                        radius="md",
                        mt="lg",
                    ),
                    href="/global-view",
                    style={"textDecoration": "none"},
                ),
            ],
        ),
    )
```

### 5.2 Routing ve Sidebar

- `app.py` → `/region-drilldown` route'u **KORUNACAK** (sayfa erişilebilir, placeholder gösterir)
- `sidebar.py` → Değişiklik **YOK** (Region Drilldown sidebar'da zaten yok)

---

## ADIM 6 — Tam Callback Haritası (app.py Final Durum)

### 6.1 Global View ile İlgili TÜM Callback'ler

| # | Fonksiyon | Input | Output | Tür | Durum |
|---|-----------|-------|--------|-----|-------|
| 1 | `update_global_detail_from_pin` | `global-map-graph.clickData` | `global-detail-panel.children` | Server | **GÜNCELLE** (ID değişikliği) |
| 2 | Pin-click zoom | `global-map-graph.clickData` | `global-map-graph.figure` | Clientside | **KORU** |
| 3 | `update_region_store` | `{"type":"region-nav"}.n_clicks` | `selected-region-store.data` | Server | **YENİ** |
| 4 | Menu-click zoom | `selected-region-store.data` | `global-map-graph.figure` | Clientside | **YENİ** |
| 5 | `update_detail_from_menu` | `selected-region-store.data` | `global-detail-panel.children` | Server | **YENİ** |
| 6 | `reset_global_detail` | `global-map-reset-btn.n_clicks` | `global-detail-panel.children` | Server | **GÜNCELLE** (ID değişikliği) |
| 7 | Reset zoom | `global-map-reset-btn.n_clicks` | `global-map-graph.figure` | Clientside | **KORU** |

### 6.2 `allow_duplicate` Haritası

`global-detail-panel.children` → 3 callback yazıyor:
- Callback #1: `allow_duplicate` yok (ilk tanım)
- Callback #5: `allow_duplicate=True`
- Callback #6: `allow_duplicate=True`

`global-map-graph.figure` → 3 callback yazıyor:
- Callback #2: `allow_duplicate=True` (mevcut)
- Callback #4: `allow_duplicate=True`
- Callback #7: `allow_duplicate=True` (mevcut)

### 6.3 Import Güncellemesi

```python
from dash import Dash, html, dcc, _dash_renderer, ALL
```

---

## ADIM 7 — Veri Akışı Diyagramı

```
┌─────────────────────────────────────────────────────────────────────┐
│                      build_global_view(tr)                          │
│  summaries = api.get_all_datacenters_summary(tr)                    │
│       ↓                              ↓                              │
│  _build_map_dataframe(summaries)  _build_region_menu(summaries)     │
│       ↓                              ↓                              │
│  _create_map_figure(df)          dmc.Accordion + dmc.NavLink        │
│       ↓                              ↓                              │
│  dcc.Graph (3D Globe)            Region Menu Panel                  │
└─────┬───────────────────────────────┬───────────────────────────────┘
      │ clickData                     │ n_clicks (Pattern-Matching)
      │                               │
      │                     ┌─────────┴──────────┐
      │                     │ update_region_store  │
      │                     │  → store.data        │
      │                     └────┬─────────┬──────┘
      │                          │         │
      ↓                          ↓         ↓
┌─────────────┐  ┌──────────────────┐  ┌──────────────────────────┐
│ Pin Zoom    │  │ Menu Zoom        │  │ update_detail_from_menu  │
│ (clientside)│  │ (clientside)     │  │  → detail panel          │
│ (MEVCUT)    │  │ (YENİ)           │  │  → build_region_detail.. │
└─────────────┘  └──────────────────┘  └──────────────────────────┘
      │
      ↓
┌──────────────────────────┐
│ update_detail_from_pin   │
│  → global-detail-panel   │
│  → build_dc_info_card    │
└──────────────────────────┘

Reset Button (global-map-reset-btn) — Region Menu Panel header'ında
      │ n_clicks
      ├──→ reset_global_detail → global-detail-panel.children = []
      └──→ Reset Zoom (clientside) → İstanbul, scale=1.0
```

---

## UYGULAMA SIRALAMASI (Executer Checklist)

| Sıra | İşlem | Dosya | Durum |
|------|-------|-------|-------|
| 1 | `REGION_HIERARCHY` dict ekle | `global_view.py` | ⬜ |
| 2 | `REGION_ZOOM_TARGETS` dict ekle | `global_view.py` | ⬜ |
| 3 | `_build_region_menu(summaries)` fonksiyonu yaz | `global_view.py` | ⬜ |
| 4 | `build_region_detail_panel(region, tr)` fonksiyonu yaz | `global_view.py` | ⬜ |
| 5 | `build_global_view()` layout → Grid yapısına dönüştür + dcc.Store + dcc.Loading | `global_view.py` | ⬜ |
| 6 | `_create_map_figure()` height 650→600 (3 yerde) | `global_view.py` | ⬜ |
| 7 | `build_dc_info_card()` → Region Drilldown butonu kaldır + Reset butonu kaldır | `global_view.py` | ⬜ |
| 8 | CSS: `fadeInUp`, `.region-nav-link`, `.region-accordion` + `.detail-panel-animate` | `style.css` | ⬜ |
| 9 | `from dash import ALL` ekle | `app.py` | ⬜ |
| 10 | Callback A: menü → store | `app.py` | ⬜ |
| 11 | Callback B: store → harita zoom (clientside) | `app.py` | ⬜ |
| 12 | Callback C: store → detay paneli | `app.py` | ⬜ |
| 13 | Mevcut pin-click callback → ID güncelle `global-dc-info-card`→`global-detail-panel` | `app.py` | ⬜ |
| 14 | Mevcut reset callback → ID güncelle | `app.py` | ⬜ |
| 15 | `region_drilldown.py` → Reserved placeholder | `region_drilldown.py` | ⬜ |
| 16 | Test: Menüden Germany tıkla → harita zoom + detay panel | Tarayıcı | ⬜ |
| 17 | Test: Menüden Istanbul tıkla → yüksek zoom + 4 DC kartı | Tarayıcı | ⬜ |
| 18 | Test: Pin tıkla → eski davranış korunsun (tek DC detay) | Tarayıcı | ⬜ |
| 19 | Test: Aynı bölgeye 2 kez tıkla → tekrar tetiklensin (ts) | Tarayıcı | ⬜ |
| 20 | Test: Reset → harita sıfırlansın + detay kapansın | Tarayıcı | ⬜ |
| 21 | Test: 0 DC'li bölge → disabled NavLink, tıklanamaz | Tarayıcı | ⬜ |
| 22 | Test: `/region-drilldown` → Reserved placeholder | Tarayıcı | ⬜ |
| 23 | Test: Loading spinner → detay paneli yüklenirken görünsün | Tarayıcı | ⬜ |

---

## ⚠️ CTO'NUN İHLAL EDİLEMEZ YASALARI

### YASA 1 — SIFIR YORUM SATIRI
Executer'ın yazacağı kodlarda **TEK BİR** açıklama satırı (`#`) veya docstring (`"""..."""`) **BULUNMAYACAKTIR**. Sadece saf Python/JavaScript kodu. İhlal = tüm kodun reddi.

### YASA 2 — MEVCUT VERİ AKIŞINI KORUMA
`loki_locations` → `api.get_all_datacenters_summary()` → `summaries` → `site_name` akışı **BOZULMAYACAK**. Yeni menü bu akışın **üzerine** inşa edilecek.

### YASA 3 — 3D KÜRE BÜTÜNLÜĞÜ
`_build_map_dataframe`, `_create_map_figure`, pin/tooltip/halo trace'leri → **DOKUNULMAZ**. Sadece `height` parametresi değişecek.

### YASA 4 — PIN TIKLAMA DAVRANIŞI KORUNACAK
Harita pin tıklama → zoom + detay **AYNEN ÇALIŞMAYA DEVAM EDECEK**. Menü ek bir yol olarak eklenecek.

---

## 🔮 MİMAR'IN EK TAVSİYELERİ (Planda Bulunmayan Ama Düşünülmesi Gerekenler)

### T1 — Accordion Kıta Tıklama → Kıta Seviyesi Zoom
Şu an sadece alt bölge (ülke/şehir) NavLink'leri callback tetikliyor. İleride `AccordionControl` tıklaması da kıta seviyesi zoom yapabilir (Örn: Europe tıkla → tüm Avrupa'yı göster). Bu V6.0 kapsamında **değil**, ama yapı buna hazır olmalı.

### T2 — Active State Yönetimi
Menüden bir bölge seçildiğinde ilgili NavLink'in `active=True` olması gerekir. Ancak `dmc.NavLink` bir `active` prop alır ve bu statik render'da belirlenir. Dinamik olarak değiştirmek için ek bir callback veya `className` tabanlı stil gerekir. **Çözüm:** `selected-region-store` verisi değiştiğinde NavLink'lerin `active` state'ini güncelleyen bir callback. Ancak Pattern-Matching Output'lar daha karmaşık. **Basit alternatif:** NavLink'lere `className="region-nav-link"` verin, CSS ile `:focus` veya `data-active` yönetin.

### T3 — URL Senkronizasyonu (Bookmark Desteği)
Kullanıcı bir bölge seçtiğinde URL querystring'e `?region=ISTANBUL` eklenebilir. Böylece sayfa yenilendiğinde aynı bölge seçili kalır. V6.0 kapsamında **değil** ama gelecek için `dcc.Location` ile implemente edilebilir.

### T4 — Menü Panel Yüksekliği Mobile Uyumluluk
`dmc.Grid` span değerleri mobilde çakışabilir. `span={"base":12, "md":8}` ve `span={"base":12, "md":4}` kullanımı düşünülebilir. Bu durumda mobilde harita tam genişlik, altına menü tam genişlik gelir. **Ancak** dashboard genelde masaüstünden kullanılır — bu opsiyoneldir.

### T5 — Backend Endpoint Optimizasyonu (Gelecek)
`build_region_detail_panel` her DC için ayrı API çağrısı yapıyor. Performans problemi olursa backend'e `/api/v1/regions/{site_name}/details` şeklinde tek bir endpoint eklenebilir. Bu V6.0 backend scope'u dışında.

---

> **SON:** Bu plan 4 dosyada (~400+ satır) kapsamlı bir Layout devrimi gerektirir.
> - `src/pages/global_view.py` → Grid layout, Region Menu Bar, Detail Panel, 2 yeni fonksiyon, 2 yeni dict
> - `app.py` → 3 yeni callback + 2 ID güncelleme + 1 import
> - `src/pages/region_drilldown.py` → Reserved placeholder
> - `assets/style.css` → Animasyonlar, menü stilleri, accordion stilleri
> Mevcut 3D küre, pin tıklama, zoom animasyonu ve `site_name` veri akışı **%100 korunur**.
