# 🌍 GLOBAL MAP VIEW — MVP İcra Planı (global1.md)

> **Versiyon:** 1.0  
> **Tarih:** 2026-03-25  
> **Hazırlayan:** Baş Planlayıcı & Sistem Mimarı  
> **Hedef:** Backend'e ve veritabanına dokunmadan, tamamen Frontend (src/) içinde çalışan bir Dünya Haritası sayfası oluşturmak.

---

## MİMARİ ÖZET

```
┌──────────────────────────────────────────────────────────────────┐
│                        app.py (Router)                          │
│  render_main_content callback → pathname == "/global-view"      │
│                           ↓                                     │
│              src/pages/global_view.py                            │
│      ┌────────────────────────────────────────────┐              │
│      │  DC_COORDINATES  (statik lat/lon sözlüğü)  │              │
│      │  build_global_view(tr)                      │              │
│      │    ├─ api.get_all_datacenters_summary(tr)   │              │
│      │    ├─ merge → DataFrame (name,lat,lon,kpi)  │              │
│      │    ├─ px.scatter_mapbox (carto-positron)    │              │
│      │    └─ info_card (clickData callback)        │              │
│      └────────────────────────────────────────────┘              │
│                                                                  │
│  src/components/sidebar.py → "🌍 Global View" NavLink eklenir   │
└──────────────────────────────────────────────────────────────────┘
```

### Dokunulacak Dosyalar (YALNIZCA src/ İçi)

| # | Dosya | İşlem |
|---|-------|-------|
| 1 | `src/pages/global_view.py` | **YENİ** — Harita sayfası + koordinat mapping |
| 2 | `src/components/sidebar.py` | **GÜNCELLE** — NavLink ekleme |
| 3 | `app.py` | **GÜNCELLE** — import + route + callback |

---

## ADIM 1 — Data & Mapping Katmanı

### 1.1 Amaç

Veritabanında coğrafi koordinat bilgisi bulunmadığı için, API'den dönen DC kodlarını (id alanı) Enlem/Boylam çiftlerine eşleştiren statik bir Python sözlüğü oluşturulacaktır. Bu sözlük `src/pages/global_view.py` dosyasının en üstünde tanımlanacaktır.

### 1.2 Koordinat Sözlüğü Tanımı

`src/pages/global_view.py` dosyasının başında aşağıdaki sözlük tanımlanacaktır:

```python
DC_COORDINATES = {
    "DC11": {"lat": 41.0082, "lon": 28.9784, "city": "Istanbul"},
    "DC12": {"lat": 41.0122, "lon": 28.9760, "city": "Istanbul"},
    "DC13": {"lat": 41.0055, "lon": 28.9530, "city": "Istanbul"},
    "DC14": {"lat": 41.0190, "lon": 29.0600, "city": "Istanbul"},
    "DC21": {"lat": 39.9208, "lon": 32.8541, "city": "Ankara"},
    "DC31": {"lat": 38.4192, "lon": 27.1287, "city": "Izmir"},
    "Equinix": {"lat": 50.1109, "lon": 8.6821, "city": "Frankfurt"},
    "Maincubes": {"lat": 50.0980, "lon": 8.6320, "city": "Frankfurt"},
    "E-Shelter": {"lat": 50.1020, "lon": 8.6490, "city": "Frankfurt"},
    "Interxion": {"lat": 52.3030, "lon": 4.9390, "city": "Amsterdam"},
}
```

> **NOT:** Bu liste daha sonra genişletilebilir. Yeni DC eklendiğinde sadece bu sözlüğe yeni bir satır eklenmesi yeterlidir. Eğer API'den gelen bir DC kodu bu sözlükte yoksa, varsayılan bir koordinat kullanılacaktır (Istanbul merkezi: 41.0082, 28.9784).

### 1.3 Veri Birleştirme Mantığı

`build_global_view(tr)` fonksiyonu içinde şu adımlar izlenecektir:

1. `api.get_all_datacenters_summary(tr)` çağrılarak DC listesi alınır
2. Her DC için `DC_COORDINATES` sözlüğünden koordinat eşleştirmesi yapılır
3. Eşleştirme bulunamazsa `_FALLBACK_COORDS = {"lat": 41.0082, "lon": 28.9784, "city": "Unknown"}` kullanılır
4. Sonuç, Plotly'nin scatter_mapbox için beklediği formata dönüştürülür

```python
import pandas as pd

def _build_map_dataframe(summaries):
    _FALLBACK = {"lat": 41.0082, "lon": 28.9784, "city": "Unknown"}
    rows = []
    for dc in summaries:
        dc_id = dc.get("id", "")
        coords = DC_COORDINATES.get(dc_id, _FALLBACK)
        stats = dc.get("stats", {})
        cpu_pct = stats.get("used_cpu_pct", 0.0)
        ram_pct = stats.get("used_ram_pct", 0.0)
        health = (cpu_pct + ram_pct) / 2.0 if (cpu_pct + ram_pct) > 0 else 0.0
        rows.append({
            "id": dc_id,
            "name": dc.get("name", dc_id),
            "location": dc.get("location", coords["city"]),
            "lat": coords["lat"],
            "lon": coords["lon"],
            "host_count": dc.get("host_count", 0),
            "vm_count": dc.get("vm_count", 0),
            "platform_count": dc.get("platform_count", 0),
            "cluster_count": dc.get("cluster_count", 0),
            "cpu_pct": round(cpu_pct, 1),
            "ram_pct": round(ram_pct, 1),
            "health": round(health, 1),
            "total_energy_kw": float(stats.get("total_energy_kw", 0.0) or 0.0),
        })
    return pd.DataFrame(rows)
```

### 1.4 Çıktı Kriterleri

- [x] `DC_COORDINATES` sözlüğü en az 10 DC kodunu içerir
- [x] Bilinmeyen DC'ler için fallback koordinat mekanizması vardır
- [x] DataFrame en az şu sütunları içerir: `id, name, lat, lon, host_count, vm_count, cpu_pct, ram_pct, health`

---

## ADIM 2 — Map Render (Harita Çizimi)

### 2.1 Amaç

Plotly Express `scatter_mapbox` kullanılarak (token gerektirmeyen `carto-positron` stili ile) DC noktalarının dünya haritası üzerinde gösterilmesi.

### 2.2 Harita Fonksiyonu

`src/pages/global_view.py` içinde `_create_map_figure(df)` fonksiyonu tanımlanacaktır:

```python
import plotly.express as px

def _create_map_figure(df):
    if df.empty:
        fig = px.scatter_mapbox(
            lat=[41.0082],
            lon=[28.9784],
            zoom=4,
        )
        fig.update_layout(
            mapbox_style="carto-positron",
            margin=dict(l=0, r=0, t=0, b=0),
            height=600,
            paper_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    max_vms = df["vm_count"].max() if df["vm_count"].max() > 0 else 1

    fig = px.scatter_mapbox(
        df,
        lat="lat",
        lon="lon",
        size="vm_count",
        size_max=40,
        color="health",
        color_continuous_scale=[
            [0.0, "#05CD99"],
            [0.5, "#FFB547"],
            [1.0, "#E85347"],
        ],
        range_color=[0, 100],
        hover_name="name",
        hover_data={
            "location": True,
            "host_count": True,
            "vm_count": True,
            "cpu_pct": ":.1f",
            "ram_pct": ":.1f",
            "lat": False,
            "lon": False,
            "health": False,
        },
        custom_data=["id"],
        zoom=4,
        center={"lat": 45.0, "lon": 20.0},
    )

    fig.update_layout(
        mapbox_style="carto-positron",
        margin=dict(l=0, r=0, t=0, b=0),
        height=600,
        paper_bgcolor="rgba(0,0,0,0)",
        coloraxis_colorbar=dict(
            title="Utilization %",
            thickness=12,
            len=0.5,
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="rgba(67,24,255,0.1)",
            borderwidth=1,
            tickfont=dict(size=11, family="DM Sans, sans-serif"),
            titlefont=dict(size=12, family="DM Sans, sans-serif"),
        ),
    )

    fig.update_traces(
        marker=dict(
            opacity=0.85,
            sizemin=8,
        )
    )

    return fig
```

### 2.3 Nokta Boyut ve Renk Mantığı

| Özellik | Kaynak | Açıklama |
|---------|--------|----------|
| **Boyut (size)** | `vm_count` | DC'deki VM sayısına göre nokta büyüklüğü. Daha fazla VM = daha büyük nokta |
| **Renk (color)** | `health` | `(cpu_pct + ram_pct) / 2` ortalaması. Yeşil(0%) → Sarı(50%) → Kırmızı(100%) |
| **Opaklık** | Sabit `0.85` | Hafif transparan, arkadaki harita görünsün |
| **Min boyut** | `sizemin=8` | VM'si az olan DC'ler de haritada görünür olsun |

### 2.4 Harita Stili

- **Stil:** `carto-positron` (ücretsiz, Mapbox token gerektirmez)
- **Merkez:** `lat=45.0, lon=20.0` (Türkiye + Avrupa birlikte görünsün)
- **Zoom:** `4` (tüm DC'ler tek bakışta görünecek seviye)

### 2.5 Sayfa İskeleti — `build_global_view(tr)`

```python
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from src.services import api_client as api
from src.utils.time_range import default_time_range

def build_global_view(time_range=None):
    tr = time_range or default_time_range()
    summaries = api.get_all_datacenters_summary(tr)
    df = _build_map_dataframe(summaries)
    map_fig = _create_map_figure(df)

    return html.Div([
        dmc.Paper(
            p="xl",
            radius="md",
            style={
                "background": "rgba(255, 255, 255, 0.80)",
                "backdropFilter": "blur(12px)",
                "WebkitBackdropFilter": "blur(12px)",
                "boxShadow": "0 4px 24px rgba(67, 24, 255, 0.07), 0 1px 4px rgba(0, 0, 0, 0.04)",
                "borderBottom": "1px solid rgba(255, 255, 255, 0.6)",
                "marginBottom": "28px",
            },
            children=[
                dmc.Group(
                    justify="space-between",
                    align="center",
                    children=[
                        dmc.Stack(
                            gap=10,
                            children=[
                                dmc.Group(
                                    gap="sm",
                                    align="center",
                                    children=[
                                        DashIconify(
                                            icon="solar:globe-bold-duotone",
                                            width=28,
                                            color="#4318FF",
                                        ),
                                        html.H2(
                                            "Global View",
                                            style={
                                                "margin": 0,
                                                "fontWeight": 900,
                                                "letterSpacing": "-0.02em",
                                                "lineHeight": 1.2,
                                                "fontSize": "1.75rem",
                                                "background": "linear-gradient(90deg, #1a1b41 0%, #4318FF 100%)",
                                                "WebkitBackgroundClip": "text",
                                                "WebkitTextFillColor": "transparent",
                                                "backgroundClip": "text",
                                            },
                                        ),
                                    ],
                                ),
                                dmc.Badge(
                                    children=[
                                        dmc.Group(
                                            gap=6,
                                            align="center",
                                            children=[
                                                DashIconify(
                                                    icon="solar:calendar-mark-bold-duotone",
                                                    width=13,
                                                ),
                                                f"{tr.get('start', '')} – {tr.get('end', '')}",
                                            ],
                                        )
                                    ],
                                    variant="light",
                                    color="indigo",
                                    radius="xl",
                                    size="md",
                                    style={"textTransform": "none", "fontWeight": 500, "letterSpacing": 0},
                                ),
                            ],
                        ),
                        dmc.Badge(
                            children=[
                                dmc.Group(
                                    gap=6,
                                    align="center",
                                    children=[
                                        DashIconify(
                                            icon="solar:check-circle-bold-duotone",
                                            width=15,
                                            color="#05CD99",
                                        ),
                                        f"{len(summaries)} Active DCs",
                                    ],
                                )
                            ],
                            variant="light",
                            color="teal",
                            radius="xl",
                            size="lg",
                            style={
                                "textTransform": "none",
                                "fontWeight": 600,
                                "letterSpacing": 0,
                                "padding": "8px 14px",
                            },
                        ),
                    ],
                ),
            ],
        ),

        dmc.Paper(
            radius="lg",
            style={
                "margin": "0 32px",
                "overflow": "hidden",
                "boxShadow": "0 2px 16px rgba(67, 24, 255, 0.06), 0 1px 4px rgba(0,0,0,0.04)",
                "border": "1px solid rgba(255, 255, 255, 0.7)",
            },
            children=[
                dcc.Graph(
                    id="global-map-graph",
                    figure=map_fig,
                    config={
                        "displayModeBar": False,
                        "scrollZoom": True,
                    },
                    style={"height": "600px", "borderRadius": "12px"},
                ),
            ],
        ),

        html.Div(
            id="global-dc-info-card",
            style={"padding": "0 32px", "marginTop": "24px"},
            children=[],
        ),
    ])
```

### 2.6 Çıktı Kriterleri

- [x] Harita `carto-positron` stili ile render olur (token gerekmez)
- [x] Noktaların boyutu VM sayısına göre değişir
- [x] Noktaların rengi sağlık/doluluk oranına göre Yeşil→Sarı→Kırmızı gradyan izler
- [x] Hover'da DC adı, lokasyon, host/VM sayısı, CPU%, RAM% görünür
- [x] Türkiye ve Avrupa haritada birlikte görünür

---

## ADIM 3 — Interactivity & Callbacks

### 3.1 Amaç

Kullanıcı haritadaki bir DC noktasına tıkladığında, o DC'nin detay bilgilerini gösteren şık bir "Bilgi Kartı" haritanın altında görüntülenecektir.

### 3.2 Callback Tanımı

Bu callback `app.py` dosyasına eklenecektir (diğer callback'ler ile aynı pattern):

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

### 3.3 Bilgi Kartı Fonksiyonu

`src/pages/global_view.py` içinde `build_dc_info_card(dc_id, tr)` fonksiyonu:

```python
def build_dc_info_card(dc_id, tr):
    data = api.get_dc_details(dc_id, tr)
    meta = data.get("meta", {})
    intel = data.get("intel", {})
    power = data.get("power", {})
    energy = data.get("energy", {})
    platforms = data.get("platforms", {})

    dc_name = meta.get("name", dc_id)
    dc_location = meta.get("location", "—")

    cpu_cap = intel.get("cpu_cap", 0.0)
    cpu_used = intel.get("cpu_used", 0.0)
    cpu_pct = round(cpu_used / cpu_cap * 100, 1) if cpu_cap > 0 else 0.0
    ram_cap = intel.get("ram_cap", 0.0)
    ram_used = intel.get("ram_used", 0.0)
    ram_pct = round(ram_used / ram_cap * 100, 1) if ram_cap > 0 else 0.0
    storage_cap = intel.get("storage_cap", 0.0)
    storage_used = intel.get("storage_used", 0.0)
    storage_pct = round(storage_used / storage_cap * 100, 1) if storage_cap > 0 else 0.0

    nutanix = platforms.get("nutanix", {})
    vmware = platforms.get("vmware", {})
    ibm = platforms.get("ibm", {})

    arch_items = []
    if vmware.get("clusters", 0) > 0 or vmware.get("hosts", 0) > 0:
        arch_items.append(f"VMware ({vmware.get('clusters', 0)} cluster, {vmware.get('hosts', 0)} host)")
    if nutanix.get("hosts", 0) > 0:
        arch_items.append(f"Nutanix ({nutanix.get('hosts', 0)} host)")
    if ibm.get("hosts", 0) > 0:
        arch_items.append(f"IBM Power ({ibm.get('hosts', 0)} host, {ibm.get('lpars', 0)} LPAR)")
    arch_text = " · ".join(arch_items) if arch_items else "—"

    def _pct_color(v):
        if v >= 80:
            return "red"
        if v >= 50:
            return "orange"
        return "teal"

    return dmc.Paper(
        p="xl",
        radius="lg",
        style={
            "background": "rgba(255, 255, 255, 0.90)",
            "backdropFilter": "blur(14px)",
            "WebkitBackdropFilter": "blur(14px)",
            "boxShadow": "0 8px 32px rgba(67, 24, 255, 0.10), 0 2px 8px rgba(0,0,0,0.04)",
            "border": "1px solid rgba(67, 24, 255, 0.08)",
            "animation": "fadeInUp 0.3s ease-out",
        },
        children=[
            dmc.Group(
                justify="space-between",
                align="flex-start",
                children=[
                    dmc.Group(
                        gap="md",
                        align="center",
                        children=[
                            dmc.ThemeIcon(
                                size="xl",
                                radius="md",
                                variant="light",
                                color="indigo",
                                children=DashIconify(icon="solar:server-square-bold-duotone", width=24),
                            ),
                            dmc.Stack(
                                gap=0,
                                children=[
                                    dmc.Text(dc_name, fw=800, size="xl", c="#2B3674"),
                                    dmc.Text(dc_location, size="sm", c="#A3AED0", fw=500),
                                ],
                            ),
                        ],
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
            dmc.Divider(my="md", color="rgba(67, 24, 255, 0.08)"),
            dmc.SimpleGrid(
                cols=4,
                spacing="lg",
                children=[
                    dmc.Stack(
                        gap=4,
                        align="center",
                        children=[
                            dmc.RingProgress(
                                size=90,
                                thickness=8,
                                roundCaps=True,
                                sections=[{"value": cpu_pct, "color": _pct_color(cpu_pct)}],
                                label=dmc.Text(f"{cpu_pct:.0f}%", ta="center", fw=700, size="sm"),
                            ),
                            dmc.Text("CPU", size="xs", fw=600, c="#A3AED0"),
                        ],
                    ),
                    dmc.Stack(
                        gap=4,
                        align="center",
                        children=[
                            dmc.RingProgress(
                                size=90,
                                thickness=8,
                                roundCaps=True,
                                sections=[{"value": ram_pct, "color": _pct_color(ram_pct)}],
                                label=dmc.Text(f"{ram_pct:.0f}%", ta="center", fw=700, size="sm"),
                            ),
                            dmc.Text("RAM", size="xs", fw=600, c="#A3AED0"),
                        ],
                    ),
                    dmc.Stack(
                        gap=4,
                        align="center",
                        children=[
                            dmc.RingProgress(
                                size=90,
                                thickness=8,
                                roundCaps=True,
                                sections=[{"value": storage_pct, "color": _pct_color(storage_pct)}],
                                label=dmc.Text(f"{storage_pct:.0f}%", ta="center", fw=700, size="sm"),
                            ),
                            dmc.Text("Storage", size="xs", fw=600, c="#A3AED0"),
                        ],
                    ),
                    dmc.Stack(
                        gap=6,
                        justify="center",
                        children=[
                            dmc.Group(
                                gap="xs",
                                children=[
                                    DashIconify(icon="solar:server-bold-duotone", width=14, color="#A3AED0"),
                                    dmc.Text(f"{intel.get('hosts', 0) + power.get('hosts', 0):,} Hosts", size="sm", c="#2B3674", fw=600),
                                ],
                            ),
                            dmc.Group(
                                gap="xs",
                                children=[
                                    DashIconify(icon="solar:laptop-bold-duotone", width=14, color="#A3AED0"),
                                    dmc.Text(f"{intel.get('vms', 0) + power.get('lpar_count', 0):,} VMs", size="sm", c="#2B3674", fw=600),
                                ],
                            ),
                            dmc.Group(
                                gap="xs",
                                children=[
                                    DashIconify(icon="material-symbols:bolt-outline", width=14, color="#A3AED0"),
                                    dmc.Text(f"{energy.get('total_kw', 0):.1f} kW", size="sm", c="#2B3674", fw=600),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            dmc.Divider(my="md", color="rgba(67, 24, 255, 0.08)"),
            dmc.Group(
                gap="xs",
                children=[
                    DashIconify(icon="solar:layers-minimalistic-bold-duotone", width=16, color="#4318FF"),
                    dmc.Text("Architecture:", size="sm", fw=600, c="#2B3674"),
                    dmc.Text(arch_text, size="sm", c="#A3AED0"),
                ],
            ),
        ],
    )
```

### 3.4 Bilgi Kartı Gösterim Detayları

| Bileşen | İçerik | Kaynak |
|---------|--------|--------|
| **Başlık** | DC adı + Lokasyon | `data["meta"]["name"]`, `data["meta"]["location"]` |
| **CPU Ring** | CPU kullanım yüzdesi | `data["intel"]["cpu_used"] / data["intel"]["cpu_cap"]` |
| **RAM Ring** | RAM kullanım yüzdesi | `data["intel"]["ram_used"] / data["intel"]["ram_cap"]` |
| **Storage Ring** | Storage kullanım yüzdesi | `data["intel"]["storage_used"] / data["intel"]["storage_cap"]` |
| **Host/VM/Energy** | Sayısal metrikler | intel + power verilerinin toplamı |
| **Architecture** | Platform detayı | `data["platforms"]` (VMware, Nutanix, IBM) |
| **Details Butonu** | DC detay sayfasına link | `/datacenter/{dc_id}` |

### 3.5 Renk Kodlama Kuralları

| Kullanım (%) | Renk | Mantine Color |
|-------------|------|---------------|
| 0–49 | Yeşil | `teal` |
| 50–79 | Turuncu | `orange` |
| 80–100 | Kırmızı | `red` |

### 3.6 Çıktı Kriterleri

- [x] Haritada bir DC noktasına tıklanınca alt tarafta bilgi kartı açılır
- [x] Bilgi kartında CPU, RAM, Storage ring chart'ları vardır
- [x] "Open Details" butonu ile `/datacenter/{dc_id}` sayfasına yönlendirme yapılır
- [x] Kart glassmorphism efektiyle stillendirilir

---

## ADIM 4 — Routing & Navigation

### 4.1 Amaç

Yeni oluşturulan Global View sayfasının ana uygulama yapısına entegre edilmesi.

### 4.2 Sidebar Güncellemesi — `src/components/sidebar.py`

`create_sidebar_nav` fonksiyonundaki `links` listesine, **"Data Centers"** ve **"Customer View"** arasına aşağıdaki NavLink eklenir:

```python
dmc.NavLink(
    label="Global View",
    leftSection=DashIconify(icon="solar:globe-bold-duotone", width=20),
    href="/global-view",
    className="sidebar-link",
    active=active_path == "/global-view",
    variant="subtle",
    color="indigo",
    style={"borderRadius": "8px", "fontWeight": "500", "marginBottom": "5px"},
),
```

**Tam konum:** `links` listesinde index `2` pozisyonuna (Data Centers'dan sonra, Customer View'den önce) eklenecektir.

### 4.3 App.py Import Güncellemesi

`app.py` dosyasının üst kısmındaki import bloğuna ekleme:

**Satır 38** civarındaki mevcut import:
```python
from src.pages import home, datacenters, dc_view, customer_view, query_explorer
```

Şu şekilde güncellenecek:
```python
from src.pages import home, datacenters, dc_view, customer_view, query_explorer, global_view
```

### 4.4 App.py Router Güncellemesi

`render_main_content` callback fonksiyonundaki pathname dispatch'e yeni route eklenir.

**Mevcut** `query_explorer` kontrolünden **hemen önce** şu blok eklenir:

```python
if pathname == "/global-view":
    return global_view.build_global_view(tr)
```

Yani `render_main_content` fonksiyonunun ilgili kısmı şöyle olacak:

```python
def render_main_content(pathname, time_range, selected_customer):
    pathname = pathname or "/"
    tr = time_range or default_time_range()
    if pathname in ("/", ""):
        return home.build_overview(tr)
    if pathname == "/datacenters":
        return datacenters.build_datacenters(tr)
    if pathname and pathname.startswith("/datacenter/"):
        dc_id = pathname.replace("/datacenter/", "").strip("/")
        return dc_view.build_dc_view(dc_id, tr)
    if pathname == "/global-view":
        return global_view.build_global_view(tr)
    if pathname == "/customer-view":
        return customer_view.build_customer_layout(tr, selected_customer)
    if pathname == "/query-explorer":
        return query_explorer.layout()
    return home.build_overview(tr)
```

### 4.5 App.py Callback Eklenmesi

ADIM 3.2'deki `update_global_info_card` callback fonksiyonu `app.py` dosyasının callback bölümüne (mevcut callback'lerin sonuna, `if __name__` bloğundan hemen önce) eklenir:

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

### 4.6 Çıktı Kriterleri

- [x] Sidebar'da "🌍 Global View" menü elemanı görünür
- [x] `/global-view` URL'si harita sayfasını render eder
- [x] Harita noktasına tıklandığında bilgi kartı callback'i çalışır
- [x] Mevcut sayfalar ve route'lar etkilenmez

---

## UYGULAMA SIRALAMASI (Executer Checklist)

| Sıra | İşlem | Dosya | Durum |
|------|-------|-------|-------|
| 1 | `src/pages/global_view.py` dosyasını oluştur (DC_COORDINATES + _build_map_dataframe + _create_map_figure + build_global_view + build_dc_info_card) | `src/pages/global_view.py` | ⬜ |
| 2 | `src/components/sidebar.py` dosyasına Global View NavLink ekle | `src/components/sidebar.py` | ⬜ |
| 3 | `app.py` dosyasına `global_view` import'unu ekle | `app.py` | ⬜ |
| 4 | `app.py` → `render_main_content` callback'ine `/global-view` route'unu ekle | `app.py` | ⬜ |
| 5 | `app.py` → `update_global_info_card` callback'ini ekle | `app.py` | ⬜ |
| 6 | Uygulamayı çalıştır ve `/global-view` sayfasını test et | Terminal | ⬜ |

---

## CTO'NUN İHLAL EDİLEMEZ YASALARI

### YASA 1 — Sıfır Yorum Satırı
Executer, Python dosyalarında **TEK BİR** yorum satırı (`#`) veya docstring (`"""..."""`) **BIRAKMAYACAKTIR**. Tüm `.py` dosyaları saf kod içerecektir — açıklama satırları yasaktır.

### YASA 2 — Backend Koruması
`backend/`, `services/` (kök dizindeki), veya `k8s/` dizinlerine **DOKUNMAK YASAKTIR**. Tüm operasyon `src/` (Frontend) dizininde ve `app.py` dosyasında gerçekleşecektir.

### YASA 3 — Mevcut API Convention'a Uyum
Yeni sayfa, mevcut `api_client.py` fonksiyonlarını (`get_all_datacenters_summary`, `get_dc_details`) kullanacaktır. Yeni API endpoint'i **EKLENMEYECEK**, yeni backend çağrısı **YAPILMAYACAKTIR**.

### YASA 4 — UI Tutarlılığı
Harita sayfasının header bölümü, mevcut sayfaların (home.py, datacenters.py) header pattern'ini birebir takip edecektir: glassmorphism Paper → gradient H2 → date badge → count badge.

### YASA 5 — Bağımlılık Koruması
`requirements.txt` dosyasına yeni paket **EKLENMEYECEK**. Tüm kullanılan kütüphaneler (`plotly`, `pandas`, `dash`, `dash-mantine-components`, `dash-iconify`) zaten projede mevcuttur.

---

> **SON:** Bu plan, Executer ajanın satır satır uygulayacağı eksiksiz bir anayasadır.
> Tüm dosya yolları, fonksiyon isimleri, callback ID'leri ve import satırları kesindir.
> Herhangi bir belirsizlik durumunda CTO'ya danışın.
