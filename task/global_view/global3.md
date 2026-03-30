# 🌍 GLOBAL MAP VIEW V4 — 3D İnteraktif Küre & Premium Pin UX Planı (global3.md)

> **Versiyon:** 4.1 (3D Orthographic Revision)
> **Tarih:** 2026-03-26
> **Hazırlayan:** Baş Planlayıcı & Sistem Mimarı
> **Hedef:** Global Map View sayfasını 2D carto-positron haritadan 3D İnteraktif Küre'ye (orthographic projection) çevirmek. Premium harita pin marker'ları, siber ızgara, glassmorphism tooltip, küre rotasyonu ile uçuş efekti ve reset mekanizması.

---

## MİMARİ ÖZET

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        app.py (Router + Callbacks)                       │
│                                                                          │
│  ┌─ update_global_info_card ─────────────────────────────────────────┐   │
│  │  Input:  global-map-graph.clickData                               │   │
│  │  State:  app-time-range.data                                      │   │
│  │  Output: global-dc-info-card.children  ← Info Card HTML           │   │
│  │  Output: global-map-graph.figure       ← dash.Patch()             │   │
│  │          geo.projection.rotation + scale (küre döner & yaklaşır)  │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─ reset_global_map_view ───────────────────────────────────────────┐   │
│  │  Input:  global-map-reset-btn.n_clicks                            │   │
│  │  Output: global-map-graph.figure       ← dash.Patch()             │   │
│  │          rotation={lon:28.96, lat:41.01} + scale=1.0              │   │
│  │  Output: global-dc-info-card.children  ← [] (kartı temizle)      │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│              src/pages/global_view.py                                    │
│      ┌────────────────────────────────────────────────────────────────┐  │
│      │  _create_map_figure(df)                                       │  │
│      │    ├─ go.Scattergeo (Shadow — koyu elips, pin gölgesi)        │  │
│      │    ├─ go.Scattergeo (Halo — neon glow, büyük yarı saydam)     │  │
│      │    ├─ go.Scattergeo (Pin Body — radial gradient, ana pin)     │  │
│      │    └─ go.Figure layout (orthographic, siber ızgara)           │  │
│      │                                                               │  │
│      │  build_dc_info_card(dc_id, tr)                                │  │
│      │    └─ "Reset Map View" butonu içerir                          │  │
│      └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Dokunulacak Dosyalar (YALNIZCA 2 Dosya)

| # | Dosya | İşlem |
|---|-------|-------|
| 1 | `src/pages/global_view.py` | **GÜNCELLE** — go.Scattergeo + orthographic küre, 3 katmanlı premium pin marker, siber ızgara, reset butonu |
| 2 | `app.py` | **GÜNCELLE** — Callback'leri güncelle (dash.Patch rotation/scale + reset callback) |

---

## ADIM 1 — 3D Küre Altyapısı (Orthographic Projection)

### 1.1 Amaç

Mevcut 2D `carto-positron` (mapbox) harita altyapısını tamamen bırakarak, `plotly.graph_objects` modülündeki `go.Scattergeo` trace tipi ve `projection_type="orthographic"` ile 3D döner küre görünümüne geçilecek. Küre üzerinde siber ızgara çizgileri, premium renk paleti ve ince ülke sınırları uygulanacak.

### 1.2 Import Değişikliği

`src/pages/global_view.py` dosyasının import bloğu güncellenecek:

**KALDIRILACAK:**
```python
import plotly.express as px
```

**EKLENECEK:**
```python
import plotly.graph_objects as go
import random
```

> **NOT:** `random` modülü, sahte ping değerleri üretmek için (ADIM 2'deki hovertemplate) kullanılacak. Standart kütüphane modülüdür, harici bağımlılık gerektirmez.

Sonuç import bloğu:
```python
import math
import random
import pandas as pd
import plotly.graph_objects as go
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from src.services import api_client as api
from src.utils.time_range import default_time_range
```

### 1.3 Küre Layout Konfigürasyonu

`_create_map_figure(df)` fonksiyonundaki `fig.update_layout` çağrısında mapbox yerine `geo` parametresi kullanılacak:

```python
fig.update_layout(
    geo=dict(
        projection_type="orthographic",
        showland=True,
        landcolor="#F4F7FE",
        showocean=True,
        oceancolor="rgba(255, 255, 255, 0.95)",
        showcountries=True,
        countrycolor="rgba(67, 24, 255, 0.12)",
        countrywidth=0.8,
        showcoastlines=True,
        coastlinecolor="rgba(67, 24, 255, 0.15)",
        coastlinewidth=0.6,
        showlakes=False,
        showrivers=False,
        framecolor="rgba(67, 24, 255, 0.06)",
        framewidth=1,
        showgraticules=True,
        lonaxis=dict(
            showgrid=True,
            gridcolor="rgba(67, 24, 255, 0.06)",
            gridwidth=0.5,
            dtick=15,
        ),
        lataxis=dict(
            showgrid=True,
            gridcolor="rgba(67, 24, 255, 0.06)",
            gridwidth=0.5,
            dtick=15,
        ),
        projection_rotation=dict(lon=28.96, lat=41.01, roll=0),
        projection_scale=1.0,
        bgcolor="rgba(0,0,0,0)",
    ),
    margin=dict(l=0, r=0, t=0, b=0),
    height=650,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    showlegend=False,
)
```

### 1.4 Küre Tasarım Detayları

| Özellik | Değer | Açıklama |
|---------|-------|----------|
| `projection_type` | `"orthographic"` | 3D küre görünümü — dünya bir top gibi |
| `landcolor` | `"#F4F7FE"` | Yumuşak açık mavi/gri — uygulamanın bg rengiyle uyumlu |
| `oceancolor` | `"rgba(255, 255, 255, 0.95)"` | Neredeyse beyaz, ferah ve modern |
| `countrycolor` | `"rgba(67, 24, 255, 0.12)"` | İnce indigo sınırlar — siber estetik |
| `coastlinecolor` | `"rgba(67, 24, 255, 0.15)"` | Kıyı çizgileri, sınırlardan hafif belirgin |
| `showgraticules` | `True` | Enlem/boylam ızgaraları — siber küre hissi |
| `gridcolor` | `"rgba(67, 24, 255, 0.06)"` | Çok ince indigo ızgara — boğmaz, hisseder |
| `dtick` | `15` | Her 15 derecede bir ızgara çizgisi |
| `projection_rotation` | `lon=28.96, lat=41.01` | Başlangıçta İstanbul merkezde |
| `projection_scale` | `1.0` | Varsayılan küre ölçeği — tam küre görünümü |
| `bgcolor` | `"rgba(0,0,0,0)"` | Transparan arka plan — Paper'ın bg'si görünsün |

### 1.5 Görsel Küre Karakteri

```
                    ╭─────────────────────╮
                ╭───│    ORTHOGRAPHIC     │───╮
              ╱     │    3D GLOBE          │     ╲
            ╱       ╰─────────────────────╯       ╲
          │    ┌─────────────────────────────┐      │
          │    │  Land:  #F4F7FE (açık gri)  │      │
          │    │  Ocean: white (transparan)   │      │
          │    │  Borders: indigo (ince)      │      │
          │    │  Grid: indigo (çok ince)     │      │
          │    │  📌 Premium Pin Markers      │      │
          │    └─────────────────────────────┘      │
            ╲                                     ╱
              ╲        Küre döndürülebilir       ╱
                ╰───────────────────────────────╯
```

### 1.6 Çıktı Kriterleri

- [ ] `import plotly.express as px` satırı tamamen kaldırıldı
- [ ] `import plotly.graph_objects as go` ve `import random` eklendi
- [ ] `projection_type="orthographic"` ile 3D küre görünümü aktif
- [ ] Karalar `#F4F7FE`, okyanuslar beyaz/transparan
- [ ] Ülke sınırları ince indigo renginde
- [ ] `showgraticules=True` ile siber ızgara çizgileri aktif
- [ ] Izgara rengi `rgba(67, 24, 255, 0.06)` — çok ince ve elegant
- [ ] Başlangıç rotasyonu İstanbul merkezli (`lon=28.96, lat=41.01`)
- [ ] Tüm mapbox referansları kaldırıldı

---

## ADIM 2 — Premium Pin Marker'lar & Glassmorphism Tooltip

### 2.1 Amaç

Sıradan düz yuvarlak marker'lar yerine, her DC konumunda 3 katmanlı premium harita pin efekti oluşturulacak. Pin'in altında koyu gölge, ortada neon hale, üstte radial gradientli ana gövde olacak. Tooltip glassmorphism etkili HTML kart olarak korunacak.

### 2.2 Referans Görsel — Premium Pin Anatomisi

Paylaşılan Flaticon harita pin ikonundan ilham alınarak:

```
          ┌─ Pin Body (radial gradient)
          │    Dış: health rengi (yeşil/turuncu/kırmızı)
          │    İç:  beyaz parlak merkez (radial gradient)
          │    Border: ince koyu çerçeve
          │
     ╭────┴────╮
     │  ○ iç   │  ← Beyaz/parlak merkez (gradient efekti)
     │  beyaz   │
     ╰────┬────╯
          │
     ╭────┴────╮  ← Halo/Glow (neon pulse)
     │ ░░░░░░░ │     Büyük, yarı saydam, sağlık renginde
     │ ░░░░░░░ │
     ╰────┬────╯
          │
     ═════╧═════  ← Shadow (koyu gölge)
                     Küçük, koyu, opak düşük
```

### 2.3 Renk Hesaplama Yardımcı Fonksiyonu

`_build_map_dataframe` fonksiyonundan sonra, `_create_map_figure` fonksiyonundan önce:

```python
def _health_colors(health_value):
    if health_value >= 70:
        return {
            "pin": "#E85347",
            "pin_rgba": "rgba(232, 83, 71, 0.95)",
            "halo": "rgba(232, 83, 71, 0.18)",
            "shadow": "rgba(120, 30, 20, 0.35)",
            "gradient": "rgba(255, 180, 170, 0.90)",
        }
    if health_value >= 40:
        return {
            "pin": "#FFB547",
            "pin_rgba": "rgba(255, 181, 71, 0.95)",
            "halo": "rgba(255, 181, 71, 0.18)",
            "shadow": "rgba(140, 100, 20, 0.35)",
            "gradient": "rgba(255, 230, 180, 0.90)",
        }
    return {
        "pin": "#05CD99",
        "pin_rgba": "rgba(5, 205, 153, 0.95)",
        "halo": "rgba(5, 205, 153, 0.18)",
        "shadow": "rgba(2, 90, 60, 0.35)",
        "gradient": "rgba(150, 245, 220, 0.90)",
    }
```

**Renk seti açıklaması:**
- `pin`: Ana pin gövde rengi (hex, marker.color)
- `pin_rgba`: Pin gövdesi RGBA (marker.line.color için)
- `halo`: Neon glow rengi (büyük, yarı saydam)
- `shadow`: Gölge rengi (koyu, opak düşük)
- `gradient`: Radial gradient merkez rengi (açık ton, beyaza yakın)

### 2.4 `_create_map_figure(df)` Fonksiyonunun Tam Kodu

Mevcut `_create_map_figure(df)` fonksiyonu tamamen silinip aşağıdaki ile değiştirilecek:

```python
def _create_map_figure(df):
    fig = go.Figure()

    if df.empty:
        fig.update_layout(
            geo=dict(
                projection_type="orthographic",
                showland=True,
                landcolor="#F4F7FE",
                showocean=True,
                oceancolor="rgba(255, 255, 255, 0.95)",
                showcountries=True,
                countrycolor="rgba(67, 24, 255, 0.12)",
                countrywidth=0.8,
                showcoastlines=True,
                coastlinecolor="rgba(67, 24, 255, 0.15)",
                coastlinewidth=0.6,
                showlakes=False,
                showrivers=False,
                framecolor="rgba(67, 24, 255, 0.06)",
                framewidth=1,
                showgraticules=True,
                lonaxis=dict(showgrid=True, gridcolor="rgba(67, 24, 255, 0.06)", gridwidth=0.5, dtick=15),
                lataxis=dict(showgrid=True, gridcolor="rgba(67, 24, 255, 0.06)", gridwidth=0.5, dtick=15),
                projection_rotation=dict(lon=28.96, lat=41.01, roll=0),
                projection_scale=1.0,
                bgcolor="rgba(0,0,0,0)",
            ),
            margin=dict(l=0, r=0, t=0, b=0),
            height=650,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
        )
        return fig

    color_maps = [_health_colors(h) for h in df["health"]]

    shadow_colors = [c["shadow"] for c in color_maps]
    halo_colors = [c["halo"] for c in color_maps]
    pin_colors = [c["pin"] for c in color_maps]
    pin_rgba_colors = [c["pin_rgba"] for c in color_maps]
    gradient_colors = [c["gradient"] for c in color_maps]

    halo_sizes = [max(32, min(60, math.log1p(row["vm_count"]) * 10 + 24)) for _, row in df.iterrows()]
    pin_sizes = [max(14, min(26, math.log1p(row["vm_count"]) * 4 + 10)) for _, row in df.iterrows()]
    shadow_sizes = [max(10, min(18, s * 0.55)) for s in pin_sizes]

    ping_values = [random.randint(8, 180) for _ in range(len(df))]

    hover_template = (
        "<b style='font-size:15px;color:#2B3674;'>%{customdata[1]}</b><br>"
        "<span style='color:#7B8EC8;'>━━━━━━━━━━━━━━━━━━━</span><br>"
        "📍 <span style='color:#A3AED0;'>%{customdata[2]}</span><br>"
        "💻 <b>%{customdata[3]:,}</b> VMs  ·  🖥️ <b>%{customdata[4]:,}</b> Hosts<br>"
        "⚡ Health: <b>%{customdata[5]:.1f}%%</b><br>"
        "<span style='color:#7B8EC8;'>━━━━━━━━━━━━━━━━━━━</span><br>"
        "🏓 <span style='color:#A3AED0;'>Ping: </span><b>%{customdata[6]}ms</b>"
        " · <span style='color:#05CD99;'>Active Route</span>"
        "<extra></extra>"
    )

    customdata_vals = []
    for i, (_, row) in enumerate(df.iterrows()):
        customdata_vals.append([
            row["id"], row["name"], row["location"],
            row["vm_count"], row["host_count"], row["health"],
            ping_values[i],
        ])

    fig.add_trace(go.Scattergeo(
        lat=df["lat"] - 0.3,
        lon=df["lon"] + 0.15,
        mode="markers",
        marker=dict(
            size=shadow_sizes,
            color=shadow_colors,
            opacity=0.3,
            symbol="circle",
        ),
        hoverinfo="skip",
        name="",
    ))

    fig.add_trace(go.Scattergeo(
        lat=df["lat"],
        lon=df["lon"],
        mode="markers",
        marker=dict(
            size=halo_sizes,
            color=halo_colors,
            opacity=0.5,
            symbol="circle",
        ),
        hoverinfo="skip",
        name="",
    ))

    fig.add_trace(go.Scattergeo(
        lat=df["lat"],
        lon=df["lon"],
        mode="markers",
        marker=dict(
            size=pin_sizes,
            color=pin_colors,
            opacity=1.0,
            symbol="circle",
            gradient=dict(
                type="radial",
                color=gradient_colors,
            ),
            line=dict(
                width=2,
                color=pin_rgba_colors,
            ),
        ),
        customdata=customdata_vals,
        hovertemplate=hover_template,
        hoverlabel=dict(
            bgcolor="rgba(255, 255, 255, 0.92)",
            bordercolor="rgba(67, 24, 255, 0.25)",
            font=dict(
                family="DM Sans, sans-serif",
                size=13,
                color="#2B3674",
            ),
            align="left",
        ),
        name="",
    ))

    fig.update_layout(
        geo=dict(
            projection_type="orthographic",
            showland=True,
            landcolor="#F4F7FE",
            showocean=True,
            oceancolor="rgba(255, 255, 255, 0.95)",
            showcountries=True,
            countrycolor="rgba(67, 24, 255, 0.12)",
            countrywidth=0.8,
            showcoastlines=True,
            coastlinecolor="rgba(67, 24, 255, 0.15)",
            coastlinewidth=0.6,
            showlakes=False,
            showrivers=False,
            framecolor="rgba(67, 24, 255, 0.06)",
            framewidth=1,
            showgraticules=True,
            lonaxis=dict(showgrid=True, gridcolor="rgba(67, 24, 255, 0.06)", gridwidth=0.5, dtick=15),
            lataxis=dict(showgrid=True, gridcolor="rgba(67, 24, 255, 0.06)", gridwidth=0.5, dtick=15),
            projection_rotation=dict(lon=28.96, lat=41.01, roll=0),
            projection_scale=1.0,
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        height=650,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )

    return fig
```

### 2.5 Katman Sırası ve Görsel Etki (3 Katman)

```
┌────────────────────────────────────────────────────────┐
│            3D Küre Katman Sırası (alttan üste)         │
├────────────────────────────────────────────────────────┤
│  Katman 3 (üst)  → Pin Body (radial gradient, opak)   │
│                     go.Scattergeo, gradient.type=radial │
│                     Beyaz merkez → health rengi kenar   │
│                     line.width=2 (ince çerçeve)         │
│                                                        │
│  Katman 2 (orta) → Halo / Neon Glow (yarı saydam)     │
│                     go.Scattergeo, büyük, opacity=0.5   │
│                     Sağlık renginin pastel tonu          │
│                                                        │
│  Katman 1 (alt)  → Shadow / Gölge (koyu, küçük)       │
│                     go.Scattergeo, lat-0.3 offset       │
│                     opacity=0.3, koyu ton               │
│                                                        │
│  Katman 0 (taban) → Orthographic Globe                 │
│                     #F4F7FE land, white ocean           │
│                     İndigo sınırlar + siber ızgara      │
└────────────────────────────────────────────────────────┘
```

> **ÖNEMLİ:** Trace ekleme sırası: önce Shadow, sonra Halo, sonra Pin Body. Shadow en altta, Pin Body en üstte kalır. Sadece Pin Body trace'inde `hovertemplate` tanımlıdır.

### 2.6 Pin Marker Detay Tablosu

| Katman | Symbol | Size Range | Opacity | Gradient | Border | Hover |
|--------|--------|-----------|---------|----------|--------|-------|
| **Shadow** | `circle` | 10–18 | 0.3 | — | — | `hoverinfo="skip"` |
| **Halo** | `circle` | 32–60 | 0.5 | — | — | `hoverinfo="skip"` |
| **Pin Body** | `circle` | 14–26 | 1.0 | `radial` (beyaz merkez) | `width=2, color=pin_rgba` | glassmorphism HTML |

### 2.7 Radial Gradient Etkisi

Plotly'nin `marker.gradient` özelliği kullanılarak Pin Body marker'larına 3D küresel görünüm kazandırılacak:

```python
gradient=dict(
    type="radial",
    color=gradient_colors,
)
```

- `type="radial"`: Merkezden dışa doğru renk geçişi
- `gradient.color` → gradient_colors: Her DC için açık ton (beyaza yakın) — merkez rengi
- `marker.color` → pin_colors: Her DC için koyu sağlık rengi — kenar rengi

**Sonuç:** Marker'ın merkezi parlak/beyazımsı, kenarları sağlık renginde olur. Bu, paylaşılan Flaticon pin ikonundaki iç beyaz daire + dış renkli gövde etkisini yaratır.

### 2.8 Gölge (Shadow) Offset Mantığı

Pin'in zemine "oturmuş" hissini vermek için shadow trace'inin koordinatları hafifçe kaydırılır:

```python
lat=df["lat"] - 0.3,    → Güneye kaydır (pinaltı gölge)
lon=df["lon"] + 0.15,    → Hafifçe sağa kaydır (ışık açısı)
```

### 2.9 Sahte Ping Değerleri

`random.randint(8, 180)` ile sayfa her yüklendiğinde her DC için gerçekçi bir ping değeri üretilir. Bu değerler `customdata[6]`'ya eklenir ve hovertemplate'te gösterilir:

```
🏓 Ping: 42ms · Active Route
```

### 2.10 Tooltip Glassmorphism Detayları

| Özellik | Değer | Açıklama |
|---------|-------|----------|
| `bgcolor` | `rgba(255, 255, 255, 0.92)` | Yarı saydam beyaz arka plan |
| `bordercolor` | `rgba(67, 24, 255, 0.25)` | İnce indigo çerçeve |
| `font-family` | `DM Sans, sans-serif` | Premium tipografi |
| `font-size` | `13px` | Okunabilir ama kompakt |
| `emojiler` | 📍 💻 🖥️ ⚡ 🏓 | Görsel zenginlik |
| `separator` | `━━━━━━` | Başlık altı premium ayırıcı |
| `ping` | `%{customdata[6]}ms` | Sahte ama gerçekçi ping |
| `status` | `Active Route` | Yeşil renkli bağlantı durumu |

### 2.11 Çıktı Kriterleri

- [ ] `_health_colors(health_value)` fonksiyonu 5 renk döndürüyor (pin, pin_rgba, halo, shadow, gradient)
- [ ] 3 ayrı `go.Scattergeo` trace ekleniyor: Shadow → Halo → Pin Body
- [ ] Pin Body'de `marker.gradient.type="radial"` aktif (3D küresel görünüm)
- [ ] Pin Body'de `marker.line.width=2` ile ince çerçeve
- [ ] Shadow trace'i `lat-0.3` offset ile yerleştirilmiş
- [ ] Hovertemplate emoji, HTML, glassmorphism stili ve ping bilgisi içeriyor
- [ ] Yalnızca Pin Body trace'inde hover aktif, diğerlerinde `hoverinfo="skip"`
- [ ] `showlegend=False` — gereksiz legend gösterilmiyor
- [ ] `customdata` 7 alan içeriyor: id, name, location, vm_count, host_count, health, ping

---

## ADIM 3 — Smart Rotation Panning / "Küre Uçuşu" Callback'i

### 3.1 Amaç

Kullanıcı küre üzerindeki bir DC pin'ine tıkladığında, kürenin o noktaya doğru akıcı bir şekilde dönmesini ve yakınlaşmasını sağlamak. 2D mapbox'taki `center/zoom` yerine, orthographic projection'ın `rotation` (lon, lat) ve `scale` parametreleri kullanılacak.

### 3.2 Mevcut Callback'in Güncellenmesi

`app.py` dosyasındaki `update_global_info_card` callback'i güncellenerek 2 Output'a çıkarılacak ve `dash.Patch()` ile küre rotasyonu + yakınlaşma yapılacak.

**MEVCUT İMZA (app.py satır 458-474):**
```python
@app.callback(
    dash.Output("global-dc-info-card", "children"),
    dash.Input("global-map-graph", "clickData"),
    dash.State("app-time-range", "data"),
    prevent_initial_call=True,
)
def update_global_info_card(click_data, time_range):
    if not click_data or "points" not in click_data or not click_data["points"]:
        return []
    point = click_data["points"][0]
    custom = point.get("customdata")
    if not custom or not custom[0]:
        return []
    dc_id = custom[0]
    tr = time_range or default_time_range()
    from src.pages.global_view import build_dc_info_card
    return build_dc_info_card(dc_id, tr)
```

**YENİ İMZA:**
```python
@app.callback(
    dash.Output("global-dc-info-card", "children"),
    dash.Output("global-map-graph", "figure"),
    dash.Input("global-map-graph", "clickData"),
    dash.State("app-time-range", "data"),
    prevent_initial_call=True,
)
def update_global_info_card(click_data, time_range):
    if not click_data or "points" not in click_data or not click_data["points"]:
        return [], dash.no_update
    point = click_data["points"][0]
    custom = point.get("customdata")
    if not custom or not custom[0]:
        return [], dash.no_update
    dc_id = custom[0]
    tr = time_range or default_time_range()

    target_lat = point.get("lat", 41.01)
    target_lon = point.get("lon", 28.96)

    patched_fig = dash.Patch()
    patched_fig["layout"]["geo"]["projection"]["rotation"]["lon"] = target_lon
    patched_fig["layout"]["geo"]["projection"]["rotation"]["lat"] = target_lat
    patched_fig["layout"]["geo"]["projection"]["scale"] = 4.5

    from src.pages.global_view import build_dc_info_card
    return build_dc_info_card(dc_id, tr), patched_fig
```

### 3.3 Orthographic Projection Rotation Parametreleri

2D mapbox'tan farklı olarak, orthographic projection'da kamera konumu `rotation` dict'i ile kontrol edilir:

```
patched_fig["layout"]["geo"]["projection"]["rotation"]["lon"] = target_lon
    → Küreyi yatayda döndürür — tıklanan DC'nin boylamı merkeze gelir

patched_fig["layout"]["geo"]["projection"]["rotation"]["lat"] = target_lat
    → Küreyi dikeyde döndürür — tıklanan DC'nin enlemi merkeze gelir

patched_fig["layout"]["geo"]["projection"]["scale"] = 4.5
    → Küreyi 4.5x yakınlaştırır — şehir seviyesi detay
```

**Neden `scale=4.5`?**
- `scale=1.0` → Tam küre görünümü (dünya tamamı)
- `scale=4.5` → Şehir bölgesi yakınlaşması (DC ve çevresi net görünür)
- `scale=10` → Çok yakın, context kaybedilir

### 3.4 dash.Patch() ve Küre Performansı

`dash.Patch()` kullanarak yalnızca 3 sayısal değer güncellenir:
1. `rotation.lon` → Hedef boylam
2. `rotation.lat` → Hedef enlem
3. `scale` → Yakınlaşma seviyesi

Trace verileri (shadow, halo, pin body) hiçbir şekilde yeniden hesaplanmaz. Plotly'nin kendi transition mekanizması küreyi akıcı şekilde döndürür.

### 3.5 Tıklama Veri Akışı

```
Kullanıcı küre üzerinde bir DC pin'ine tıklar
        ↓
clickData.points[0] → { lat, lon, customdata: [dc_id, name, ...] }
        ↓
dc_id → build_dc_info_card(dc_id, tr) → Info Card HTML
lat/lon → dash.Patch()
    → geo.projection.rotation.lon = target_lon
    → geo.projection.rotation.lat = target_lat
    → geo.projection.scale = 4.5
        ↓
Küre akıcı şekilde dönerek DC'yi merkeze alır ve yakınlaşır
Info Card kürenin altında belirir
```

### 3.6 Çıktı Kriterleri

- [ ] `update_global_info_card` callback'i 2 Output'a sahip: `children` + `figure`
- [ ] Boş click durumunda `dash.no_update` döndürülüyor
- [ ] `dash.Patch()` ile `geo.projection.rotation` güncelleniyor (mapbox DEĞİL)
- [ ] Tıklandığında `scale` değeri `4.5`'e çıkıyor
- [ ] `rotation.lon` ve `rotation.lat` tıklanan noktanın koordinatlarına eşitleniyor
- [ ] Sıfırdan render **YAPILMIYOR** — performans korunuyor

---

## ADIM 4 — Reset View Butonu

### 4.1 Amaç

Kullanıcı bir DC'ye yakınlaşıp küreyi döndürdükten sonra, orijinal dünya görünümüne tek tıkla dönebilmesi için "Reset Map View" butonu eklenmesi. Bu buton küreyi İstanbul merkezli orijinal konumuna ve `scale=1.0` ölçeğine geri döndürecek.

### 4.2 Butonun Konumu

"Reset Map View" butonu, `build_dc_info_card` fonksiyonunun döndürdüğü Info Card'ın **header bölümüne** eklenecek. Mevcut "Open Details" butonunun **soluna** yerleştirilecek.

### 4.3 Info Card Header Güncellemesi

`src/pages/global_view.py` → `build_dc_info_card` fonksiyonundaki üst `dmc.Group(justify="space-between")` içindeki sağ taraftaki bileşen güncellenecek:

**MEVCUT (sadece Open Details butonu, satır 351-361):**
```python
dcc.Link(
    dmc.Button(
        "Open Details",
        variant="light",
        color="indigo",
        radius="md",
        rightSection=DashIconify(icon="solar:arrow-right-linear", width=16),
    ),
    href=f"/datacenter/{dc_id}",
    style={"textDecoration": "none"},
),
```

**YENİ (Reset + Open Details yan yana):**
```python
dmc.Group(
    gap="sm",
    children=[
        dmc.Button(
            "Reset Map View",
            id="global-map-reset-btn",
            variant="subtle",
            color="gray",
            radius="md",
            size="sm",
            leftSection=DashIconify(icon="solar:refresh-circle-bold-duotone", width=18),
        ),
        dcc.Link(
            dmc.Button(
                "Open Details",
                variant="light",
                color="indigo",
                radius="md",
                rightSection=DashIconify(icon="solar:arrow-right-linear", width=16),
            ),
            href=f"/datacenter/{dc_id}",
            style={"textDecoration": "none"},
        ),
    ],
),
```

### 4.4 Reset Callback (app.py)

`app.py` dosyasına, `update_global_info_card` callback'inden **sonra**, `if __name__` bloğundan **önce** yeni bir callback eklenecek:

```python
@app.callback(
    dash.Output("global-map-graph", "figure", allow_duplicate=True),
    dash.Output("global-dc-info-card", "children", allow_duplicate=True),
    dash.Input("global-map-reset-btn", "n_clicks"),
    prevent_initial_call=True,
)
def reset_global_map_view(n_clicks):
    if not n_clicks:
        return dash.no_update, dash.no_update
    patched_fig = dash.Patch()
    patched_fig["layout"]["geo"]["projection"]["rotation"]["lon"] = 28.96
    patched_fig["layout"]["geo"]["projection"]["rotation"]["lat"] = 41.01
    patched_fig["layout"]["geo"]["projection"]["scale"] = 1.0
    return patched_fig, []
```

### 4.5 allow_duplicate Zorunluluğu

Bu callback, `global-map-graph.figure` ve `global-dc-info-card.children` Output'larını `update_global_info_card` ile paylaşıyor. Dash, aynı Output'u birden fazla callback'te kullanmaya izin vermez — **AMA** `allow_duplicate=True` parametresi ile bu kısıtlama kaldırılır.

Reset callback'inin **her iki Output'una** da `allow_duplicate=True` eklenmesi **ZORUNLUDUR.**

### 4.6 Reset Akışı

```
Kullanıcı "Reset Map View" butonuna tıklar
        ↓
n_clicks tetiklenir
        ↓
dash.Patch() →
    rotation.lon = 28.96 (İstanbul boylamı)
    rotation.lat = 41.01 (İstanbul enlemi)
    scale = 1.0 (tam küre görünümü)
global-dc-info-card.children → [] (kart temizlenir)
        ↓
Küre akıcı şekilde orijinal İstanbul merkezli konumuna döner
Yakınlaşma sıfırlanır (tam küre)
Info Card kaybolur
```

### 4.7 Orijinal vs Yakınlaşmış Değerler

| Parametre | Orijinal (Reset) | Yakınlaşmış (Click) |
|-----------|-------------------|----------------------|
| `rotation.lon` | `28.96` (İstanbul) | `target_lon` (tıklanan DC) |
| `rotation.lat` | `41.01` (İstanbul) | `target_lat` (tıklanan DC) |
| `scale` | `1.0` (tam küre) | `4.5` (şehir seviyesi) |

### 4.8 Buton Tasarım Detayları

| Özellik | Değer | Açıklama |
|---------|-------|----------|
| `variant` | `subtle` | Arka plansız, hover'da hafif gri |
| `color` | `gray` | Nötr ton — Open Details'ten ayrışır |
| `size` | `sm` | Kompakt, Info Card'ı boğmaz |
| `icon` | `solar:refresh-circle-bold-duotone` | Döngüsel ok — "sıfırla" semantiği |
| `id` | `global-map-reset-btn` | Callback tarafından dinlenen benzersiz ID |

### 4.9 Çıktı Kriterleri

- [ ] Info Card'ın header'ında "Reset Map View" butonu görünüyor
- [ ] Buton `id="global-map-reset-btn"` ile tanımlı
- [ ] `reset_global_map_view` callback'i `app.py`'de tanımlı
- [ ] Callback `dash.Patch()` kullanarak `rotation` ve `scale` güncelliyor (mapbox DEĞİL, geo)
- [ ] Reset sonrasında `rotation={lon:28.96, lat:41.01}` ve `scale=1.0`
- [ ] Reset sonrasında Info Card temizleniyor (`children=[]`)
- [ ] `allow_duplicate=True` her iki Output'ta da mevcut
- [ ] Buton tıklanmadan önce (`n_clicks=None`) `dash.no_update` döndürülüyor

---

## UYGULAMA SIRALAMASI (Executer Checklist)

| Sıra | İşlem | Dosya | Durum |
|------|-------|-------|-------|
| 1 | `import plotly.express as px` → `import plotly.graph_objects as go` + `import random` | `global_view.py` satır 3 | ⬜ |
| 2 | `_health_colors(health_value)` fonksiyonunu ekle (5 renk döndüren dict versiyonu) | `global_view.py` (_build_map_dataframe sonrası) | ⬜ |
| 3 | `_create_map_figure(df)` fonksiyonunu tamamen yeniden yaz (go.Figure + 3 Scattergeo trace + orthographic layout) | `global_view.py` satır 64-138 | ⬜ |
| 4 | `build_global_view` içindeki `dcc.Graph` height'ını "600px" → "650px" güncelle | `global_view.py` satır 261 | ⬜ |
| 5 | `build_dc_info_card` header'ına "Reset Map View" butonu ekle | `global_view.py` satır 351-361 | ⬜ |
| 6 | `update_global_info_card` callback'ini güncelle (2 Output + dash.Patch geo rotation) | `app.py` satır 458-474 | ⬜ |
| 7 | `reset_global_map_view` callback'ini ekle | `app.py` (update_global_info_card sonrası) | ⬜ |
| 8 | Uygulamayı çalıştır ve tüm 4 özelliği test et | Terminal | ⬜ |

---

## KOD YAZIM KURALLARI (Executer İçin)

### ⚠️ CTO'NUN İHLAL EDİLEMEZ YASALARI

#### YASA 1 — Sıfır Yorum Satırı
Executer, Python dosyalarında **TEK BİR** yorum satırı (`#`) veya docstring (`"""..."""`) **BIRAKMAYACAKTIR**. Tüm `.py` dosyaları saf, yorum-sız kod içerecektir. Bu yasanın ihlali halinde kod reddedilir.

#### YASA 2 — Backend Koruması
Sadece `src/pages/global_view.py` ve `app.py` dosyaları güncellenecektir. `backend/`, `services/` (kök dizin), `k8s/`, `src/services/`, `src/components/`, `src/utils/` dizinlerine **DOKUNMAK YASAKTIR.**

#### YASA 3 — API Doğallığını Koruma
API'den gelen veriye müdahale edilmeyecek. `_build_map_dataframe` fonksiyonunun mevcut veri dönüşüm mantığı korunacak. Yeni API çağrısı **YAPILMAYACAK.**

#### YASA 4 — Bağımlılık Koruması
`requirements.txt` dosyasına yeni paket **EKLENMEYECEK**. `plotly.graph_objects` zaten `plotly` paketinin parçasıdır. `random` Python standart kütüphanesidir. Ek kurulum gerekmez.

#### YASA 5 — Mevcut Layout Koruması
`build_global_view` fonksiyonunun genel layout yapısı (Header Paper → Map Paper → Info Card Div) korunacak. Yalnızca referans verilen bileşenler güncellenecek.

---

## YAPISAL DEĞİŞİKLİK ÖZETİ

### global_view.py Değişiklik Haritası

```diff
  import math
+ import random
  import pandas as pd
- import plotly.express as px
+ import plotly.graph_objects as go
  from dash import html, dcc
  import dash_mantine_components as dmc
  from dash_iconify import DashIconify
  from src.services import api_client as api
  from src.utils.time_range import default_time_range

  CITY_COORDINATES = { ... }
  _CITY_OFFSETS = [ ... ]

  def _build_map_dataframe(summaries): ...

+ def _health_colors(health_value): ...       ← 5 renk döndüren dict

- def _create_map_figure(df):                 ← px.scatter_mapbox + carto-positron (SİLİNECEK)
+ def _create_map_figure(df):                 ← go.Figure + 3 Scattergeo trace + orthographic (YENİ)
+     Shadow trace   → lat-0.3 offset, koyu gölge
+     Halo trace     → büyük, yarı saydam neon glow
+     Pin Body trace → radial gradient, ince çerçeve, hovertemplate

  def build_global_view(time_range=None):
-     style={"height": "600px", ...}          ← DEĞİŞECEK
+     style={"height": "650px", ...}          ← YENİ

  def build_dc_info_card(dc_id, tr):
+     ← Header'a "Reset Map View" butonu (EKLENECEK)
```

### app.py Değişiklik Haritası

```diff
  @app.callback(
      dash.Output("global-dc-info-card", "children"),
+     dash.Output("global-map-graph", "figure"),
      dash.Input("global-map-graph", "clickData"),
      dash.State("app-time-range", "data"),
      prevent_initial_call=True,
  )
  def update_global_info_card(click_data, time_range):
-     ...return build_dc_info_card(dc_id, tr)
+     ...patched_fig["layout"]["geo"]["projection"]["rotation"]["lon"] = target_lon
+     ...patched_fig["layout"]["geo"]["projection"]["rotation"]["lat"] = target_lat
+     ...patched_fig["layout"]["geo"]["projection"]["scale"] = 4.5
+     ...return build_dc_info_card(dc_id, tr), patched_fig

+ @app.callback(
+     dash.Output("global-map-graph", "figure", allow_duplicate=True),
+     dash.Output("global-dc-info-card", "children", allow_duplicate=True),
+     dash.Input("global-map-reset-btn", "n_clicks"),
+     prevent_initial_call=True,
+ )
+ def reset_global_map_view(n_clicks):
+     ...patched_fig["layout"]["geo"]["projection"]["rotation"]["lon"] = 28.96
+     ...patched_fig["layout"]["geo"]["projection"]["rotation"]["lat"] = 41.01
+     ...patched_fig["layout"]["geo"]["projection"]["scale"] = 1.0
+     ...return patched_fig, []
```

---

## 2D → 3D GEÇİŞ REFERANS TABLOSU

| Kavram | 2D (Eski - Mapbox) | 3D (Yeni - Orthographic) |
|--------|---------------------|--------------------------|
| **Trace tipi** | `go.Scattermapbox` | `go.Scattergeo` |
| **Harita stili** | `carto-positron` | `projection_type="orthographic"` |
| **Kamera konumu** | `layout.mapbox.center` | `layout.geo.projection.rotation` |
| **Yakınlaşma** | `layout.mapbox.zoom` | `layout.geo.projection.scale` |
| **Başlangıç zoom** | `zoom=4` | `scale=1.0` |
| **Tıklama zoom** | `zoom=10` | `scale=4.5` |
| **Kara rengi** | Mapbox tarafından belirlenir | `landcolor="#F4F7FE"` |
| **Okyanus rengi** | Mapbox tarafından belirlenir | `oceancolor="rgba(255,255,255,0.95)"` |
| **Sınırlar** | Mapbox tarafından belirlenir | `countrycolor="rgba(67,24,255,0.12)"` |
| **Izgara** | Yok | `showgraticules=True` + indigo |

---

> **SON:** Bu plan, Executer ajanın cerrahi hassasiyetle uygulayacağı eksiksiz bir anayasadır.
> Tüm dosya yolları, fonksiyon isimleri, callback ID'leri, trace sıraları, rotation parametreleri ve import satırları kesindir.
> Yalnızca 2 dosya değişecektir: `src/pages/global_view.py` ve `app.py`.
> Network Topology (ağ çizgileri) bu versiyonda **KAPSAM DIŞI** bırakılmıştır.
> Herhangi bir belirsizlik durumunda CTO'ya danışın.
