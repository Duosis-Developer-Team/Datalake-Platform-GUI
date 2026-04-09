# 🏛️ Overview Content Modernization — Master Plan

**Yayın Tarihi:** 2 Mart 2026, 00:44
**Hazırlayan:** Senior Developer Organizer
**Hedef Dosyalar:** `src/pages/home.py` + `src/components/charts.py`
**Durum:** ⏳ Executor uygulaması bekleniyor

**DC Summary güncellemesi (2 Nis 2026):** Overview tablosunda Data Center metni Data Centers sayfasıyla aynı şekilde `format_dc_display_name` (name - description). Classic/Hyperconverged CPU ve RAM için `cpu_pct_max` / `ram_pct_max` (yoksa ortalama) tek rozet; Disk ve IBM snapshot aynı rozet stili; rozet içinde silik `max` etiketi. Yardımcı: `effective_max_pct` — test: `tests/test_home_arch_usage_display.py`.

---

## Genel Mimari Kuralı

Tüm ana kart kapsayıcıları:
- `className="nexus-card"` **korunur** — çerçeve sistemi değişmez
- `padding: "20px"` → `padding: "24px"` (nefes payı)
- Kart başlıkları `html.H3` → `dmc.Text(fw=700, size="lg", c="#2B3674")` (Mantine entegrasyonu)
- Alt başlıklar `html.P` → `dmc.Text(size="xs", c="dimmed")` (semantik token)

---

## Mevcut Dosya Haritası

```
src/pages/home.py
  Satır 019-053: metric_card() yardımcı fonksiyonu
  Satır 056-067: platform_card() yardımcı fonksiyonu
  Satır 070-121: build_overview() — veri toplama
  Satır 122-182: Header (dmc.Paper) — TAMAMLANDI ✅
  Satır 183:     KPI strip (SimpleGrid cols=5) — DOKUNULMAZ
  Satır 184-233: Faz 1 — Platform Breakdown + Resource Usage
  Satır 234-268: Faz 2 — Energy by Source + DC Comparison
  Satır 269-311: Faz 3 — DC Summary Tablosu

src/components/charts.py
  Satır 047-078: create_usage_donut_chart()   → FAZ 1 kapsamında
  Satır 164-183: create_energy_breakdown_chart() → FAZ 2 kapsamında
  Satır 108-132: create_grouped_bar_chart()   → FAZ 2 kapsamında
```

---
---

## FAZ 1: Üst Blok — Platform Breakdown & Resource Usage

**Hedef Satırlar:** `home.py` Satır 184-233
**Etkilenen Fonksiyon:** `charts.py` `create_usage_donut_chart()` (Satır 47-78)

---

### FAZ 1-A: Platform Breakdown (`home.py` Satır 189-196)

#### Mevcut Sorun
`platform_card()` fonksiyonu `className="nexus-card"` kullanıyor. Bu, `.nexus-card` CSS'inin `box-shadow: 0px 18px 40px rgba(112,144,176,0.12)` gölgesini ve `transform: translateY(-5px)` hover'ını uyguluyor. Ana `nexus-card` içinde başka bir `nexus-card` → **iç içe gölge çakışması, kaba görünüm**.

#### Hedef
Alt kartlar (Nutanix, VMware, IBM) için daha **hafif, hiyerarşik** bir görünüm.
Ana kartla aralarındaki zeminsel fark belirgin olsun.

#### DEĞİŞİKLİK 1-A-i — `platform_card()` fonksiyonu (`home.py` Satır 56-67)

```python
# MEVCUT (Satır 56-67):
def platform_card(title, hosts, vms, clusters=None, color="#4318FF"):
    children = [
        dmc.Text(title, fw=700, size="sm", c="#2B3674", style={"marginBottom": "8px"}),
        dmc.Group(gap="lg", children=[dmc.Text(f"Hosts: {hosts}", size="sm", c="#A3AED0"), dmc.Text(f"VMs: {vms}", size="sm", c="#A3AED0")]),
    ]
    if clusters is not None:
        children.insert(1, dmc.Text(f"Clusters: {clusters}", size="sm", c="#A3AED0"))
    return html.Div(
        className="nexus-card",
        style={"padding": "16px", "borderLeft": f"4px solid {color}"},
        children=children,
    )
```

```python
# YENİ (Satır 56-67 — TAMAMEN DEĞİŞTİR):
def platform_card(title, hosts, vms, clusters=None, color="#4318FF"):
    children = [
        dmc.Group(
            gap="xs",
            align="center",
            style={"marginBottom": "10px"},
            children=[
                html.Div(style={
                    "width": "10px", "height": "10px",
                    "borderRadius": "50%",
                    "backgroundColor": color,
                    "flexShrink": 0,
                }),
                dmc.Text(title, fw=700, size="sm", c="#2B3674"),
            ],
        ),
        dmc.Stack(
            gap=4,
            children=[
                dmc.Group(gap="xs", children=[
                    dmc.Text("Hosts", size="xs", c="dimmed", style={"width": "52px"}),
                    dmc.Text(str(hosts), size="sm", fw=600, c="#2B3674"),
                ]),
                dmc.Group(gap="xs", children=[
                    dmc.Text("VMs", size="xs", c="dimmed", style={"width": "52px"}),
                    dmc.Text(str(vms), size="sm", fw=600, c="#2B3674"),
                ]),
            ],
        ),
    ]
    if clusters is not None:
        children[1].children.insert(1, dmc.Group(gap="xs", children=[
            dmc.Text("Clusters", size="xs", c="dimmed", style={"width": "52px"}),
            dmc.Text(str(clusters), size="sm", fw=600, c="#2B3674"),
        ]))
    return html.Div(
        style={
            "padding": "14px 16px",
            "borderRadius": "12px",
            "backgroundColor": "#f8f9fa",
            "borderLeft": f"3px solid {color}",
            "border": f"1px solid #e9ecef",
            "borderLeftWidth": "3px",
            "borderLeftColor": color,
        },
        children=children,
    )
```

| Değişen | Eski | Yeni | Gerekçe |
|---------|------|------|---------|
| Kapsayıcı | `className="nexus-card"` (gölge + hover) | Inline `style` ile hafif kart | İç içe büyük gölge çakışması engellendi |
| Başlık | Düz `dmc.Text(title)` | `dmc.Group` + `●` renk noktası + metin | Platform renk kodu görsel referans verir |
| Metrikler | `dmc.Group(gap="lg")` yatay sıra | `dmc.Stack(gap=4)` + label-value çiftleri | Daha okunabilir key-value hiyerarşi |
| Arka plan | `#FFFFFF` (nexus-card) | `#f8f9fa` | Ana karttan (`#FFFFFF`) hafifçe ayrışır |
| Kenar | `borderLeft: 4px solid {color}` | `border: 1px solid #e9ecef` + `borderLeft: 3px solid {color}` | Tüm kenar ince gri çerçeve + sol renk aksanı |

#### DEĞİŞİKLİK 1-A-ii — Ana Platform kartı wrapper (`home.py` Satır 189-196)

```python
# MEVCUT (Satır 189-196):
html.Div(
    [
        html.H3("Platform breakdown", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
        dmc.SimpleGrid(cols=3, spacing="md", children=platform_cards),
    ],
    className="nexus-card",
    style={"padding": "20px"},
),
```

```python
# YENİ:
html.Div(
    [
        dmc.Text("Platform Breakdown", fw=700, size="lg", c="#2B3674", style={"marginBottom": "4px"}),
        dmc.Text("Nutanix · VMware · IBM Power", size="xs", c="dimmed", style={"marginBottom": "16px"}),
        dmc.SimpleGrid(cols=3, spacing="md", children=platform_cards),
    ],
    className="nexus-card",
    style={"padding": "24px"},
),
```

---

### FAZ 1-B: Resource Usage — Ring Charts (`charts.py` Satır 47-78 + `home.py` Satır 197-231)

#### Mevcut Sorun
`create_usage_donut_chart()`: `go.Pie` kullanıyor, `hole=0.7`. Ortadaki annotation `size=24` küçük. `linecap` (uç yuvarlama) mevcut API'de mümkün değil — `go.Pie`'da bu özellik yok.

#### Çözüm
Plotly `go.Indicator` **değil** — `go.Pie` ile devam edip görsel değerleri artırıyoruz:
- Annotation font boyutu `24` → `32`, `weight="bold"` ekle
- Tracin geçiş gradyanı için `marker.colors` array'i iki renkli → sade kalacak, ama daha kaim stroke'lu görünüm için `go.Pie` → `go.Pie(pull=[0,0])` + `hole=0.72`
- Başlık (label) daha belirgin konuma alınacak

> **Teknik Not:** Plotly `go.Pie`'da `linecap` yoktur. Uç yuvarlama için `dmc.RingProgress` kullanılabilir — bu tamamen Python/Dash bileşeni, `dcc.Graph` gerektirmiyor. **Resource Usage bölümü `dcc.Graph` → `dmc.RingProgress`'e migrate edilecek.**

#### DEĞİŞİKLİK 1-B-i — `charts.py`: `create_usage_donut_chart()` GÜNCELLENİYOR (Satır 47-78)

```python
# MEVCUT (Satır 47-78):
def create_usage_donut_chart(value, label, color="#4318FF"):
    try:
        val = float(value)
    except:
        val = 0
    remaining = 100 - val
    fig = go.Figure(data=[go.Pie(
        values=[val, remaining],
        labels=["Used", "Free"],
        hole=0.7,
        marker=dict(colors=[color, "#E9EDF7"]),
        sort=False,
        textinfo='none',
        hoverinfo='label+value'
    )])
    fig.update_layout(
        annotations=[dict(
            text=f"{int(val)}%",
            x=0.5, y=0.5,
            font=dict(size=24, color="#2B3674", family="DM Sans", weight="bold"),
            showarrow=False
        )],
        title=dict(text=label, x=0.5, xanchor='center', font=dict(size=14, color="#A3AED0", family="DM Sans")),
        showlegend=False,
        margin=dict(l=20, r=20, t=40, b=20),
        height=200,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    return fig
```

```python
# YENİ — daha büyük orta rakam, daha kaim halka, daha temiz layout:
def create_usage_donut_chart(value, label, color="#4318FF"):
    try:
        val = float(value)
    except (TypeError, ValueError):
        val = 0
    val = max(0.0, min(100.0, val))
    remaining = 100.0 - val

    fig = go.Figure(data=[go.Pie(
        values=[val, remaining],
        labels=["Used", "Free"],
        hole=0.72,
        marker=dict(
            colors=[color, "#EEF2FF"],
            line=dict(color="rgba(0,0,0,0)", width=0),
        ),
        sort=False,
        textinfo="none",
        hoverinfo="skip",
        direction="clockwise",
    )])

    fig.update_layout(
        annotations=[dict(
            text=f"<b>{int(val)}%</b>",
            x=0.5, y=0.45,
            font=dict(size=30, color="#2B3674", family="DM Sans"),
            showarrow=False,
            xanchor="center",
        )],
        title=dict(
            text=f"<b>{label}</b>",
            x=0.5,
            xanchor="center",
            font=dict(size=13, color="#A3AED0", family="DM Sans"),
        ),
        showlegend=False,
        margin=dict(l=10, r=10, t=44, b=10),
        height=180,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig
```

| Değişen | Eski | Yeni | Gerekçe |
|---------|------|------|---------|
| `hole` | `0.7` | `0.72` | Halka biraz daha kaim |
| Annotation `size` | `24` | `30` | Orta rakam daha büyük ve dominant |
| Annotation `text` | `f"{int(val)}%"` | `f"<b>{int(val)}%</b>"` | HTML bold |
| `hoverinfo` | `"label+value"` | `"skip"` | Hover kaldırıldı — küçük grafiklerde karışıklık |
| İç renk | `"#E9EDF7"` | `"#EEF2FF"` | Hafif indigoTint — marka paletine uyumlu |
| `line.width` | *(varsayılan)* | `0` | Dilimler arası çizgi kaldırıldı |
| `margin` | `l=20, r=20, t=40, b=20` | `l=10, r=10, t=44, b=10` | Grafik alanı daha verimli |
| `height` | `200` | `180` | Kompakt — kart içine daha iyi oturur |

#### DEĞİŞİKLİK 1-B-ii — Resource Usage kart wrapper (`home.py` Satır 197-231)

```python
# MEVCUT (Satır 197-231):
html.Div(
    [
        html.H3("Resource usage", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
        html.P("Daily average over report period", style={"margin": "0 0 12px 0", "color": "#A3AED0", "fontSize": "0.8rem"}),
        dmc.SimpleGrid(
            cols=3,
            spacing="md",
            children=[
                html.Div(dcc.Graph(figure=create_usage_donut_chart(cpu_pct, "CPU", "#4318FF"), config={"displayModeBar": False}, style={"height": "160px"})),
                html.Div(dcc.Graph(figure=create_usage_donut_chart(ram_pct, "RAM", "#05CD99"), config={"displayModeBar": False}, style={"height": "160px"})),
                html.Div(dcc.Graph(figure=create_usage_donut_chart(stor_pct, "Storage", "#FFB547"), config={"displayModeBar": False}, style={"height": "160px"})),
            ],
        ),
    ],
    className="nexus-card",
    style={"padding": "20px"},
),
```

```python
# YENİ:
html.Div(
    [
        dmc.Text("Resource Usage", fw=700, size="lg", c="#2B3674", style={"marginBottom": "4px"}),
        dmc.Text("Daily average over report period", size="xs", c="dimmed", style={"marginBottom": "16px"}),
        dmc.SimpleGrid(
            cols=3,
            spacing="md",
            children=[
                html.Div(dcc.Graph(
                    figure=create_usage_donut_chart(cpu_pct, "CPU", "#4318FF"),
                    config={"displayModeBar": False},
                    style={"height": "180px"},
                )),
                html.Div(dcc.Graph(
                    figure=create_usage_donut_chart(ram_pct, "RAM", "#05CD99"),
                    config={"displayModeBar": False},
                    style={"height": "180px"},
                )),
                html.Div(dcc.Graph(
                    figure=create_usage_donut_chart(stor_pct, "Storage", "#FFB547"),
                    config={"displayModeBar": False},
                    style={"height": "180px"},
                )),
            ],
        ),
    ],
    className="nexus-card",
    style={"padding": "24px"},
),
```

---

### FAZ 1 Kabul Kriterleri

- [ ] `python app.py` — hatasız başlangıç.
- [ ] Platform Breakdown: 3 alt kart (Nutanix, VMware, IBM) açık gri zeminli, ince kenarlıklı, solunda renk aksanı.
- [ ] Alt kartlarda kaba `nexus-card` gölgesi yok — hafif, hiyerarşik görünüm.
- [ ] Her platform alt kartında renk noktası (●) + platform adı yan yana.
- [ ] Resource Usage: Orta yüzde rakamları **daha büyük** (`size=30`, bold).
- [ ] Halka dilimleri arası çizgi yok — tek parça döngü görünümü.
- [ ] CPU `#4318FF`, RAM `#05CD99`, Storage `#FFB547` renkleri korunuyor.

---
---

## FAZ 2: Grafik Bloğu — Energy by Source & DC Comparison

**Hedef Satırlar:** `home.py` Satır 234-268
**Etkilenen Fonksiyonlar:** `charts.py` `create_energy_breakdown_chart()` (164-183) + `create_grouped_bar_chart()` (108-132)

---

### FAZ 2-A: Energy by Source — Premium Ring Chart

#### Mevcut Sorun
`create_energy_breakdown_chart()`: `go.Pie` + `hole=0.5` + `textinfo="label+percent"`. Etiketler pasta içine sıkıştırılmış — kalabalık, okunamaz. `showlegend=False` — açıklamalar tamamen yok.

#### DEĞİŞİKLİK 2-A-i — `charts.py` `create_energy_breakdown_chart()` (Satır 164-183) YENİDEN YAZ

```python
# MEVCUT (Satır 164-183):
def create_energy_breakdown_chart(labels, values, title="Energy by source", height=250):
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.5,
        marker=dict(colors=["#4318FF", "#05CD99", "#FFB547"]),
        textinfo="label+percent",
        hoverinfo="label+value+percent",
    )])
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color="#2B3674", family="DM Sans")),
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=40, b=20),
        height=height,
        font=dict(family="DM Sans", color="#A3AED0"),
    )
    return fig
```

```python
# YENİ — Ring chart: etiketler içinde değil, legend'da. Ortada toplam kW:
def create_energy_breakdown_chart(labels, values, title="Energy by source", height=260):
    total = sum(v for v in values if v)
    total_text = f"<b>{total:,.0f}</b><br><span style='font-size:11px'>kW Total</span>"

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.65,
        marker=dict(
            colors=["#4318FF", "#05CD99", "#FFB547"],
            line=dict(color="rgba(0,0,0,0)", width=0),
        ),
        textinfo="none",
        hovertemplate="<b>%{label}</b><br>%{value:,.0f} kW (%{percent})<extra></extra>",
        direction="clockwise",
        sort=False,
    )])

    fig.update_layout(
        annotations=[dict(
            text=total_text,
            x=0.38, y=0.5,
            font=dict(size=20, color="#2B3674", family="DM Sans"),
            showarrow=False,
            xanchor="center",
        )],
        showlegend=True,
        legend=dict(
            orientation="v",
            x=0.78,
            y=0.5,
            xanchor="left",
            yanchor="middle",
            font=dict(family="DM Sans", size=12, color="#2B3674"),
            bgcolor="rgba(0,0,0,0)",
            itemsizing="constant",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=20, b=10),
        height=height,
        font=dict(family="DM Sans", color="#A3AED0"),
    )
    return fig
```

| Değişen | Eski | Yeni | Gerekçe |
|---------|------|------|---------|
| `hole` | `0.5` | `0.65` | Daha geniş merkez — toplam kW için alan |
| `textinfo` | `"label+percent"` | `"none"` | Etiketler pasta içinde değil |
| `showlegend` | `False` | `True` | Legend sağ tarafa dikey olarak |
| `legend` | *(yok)* | `orientation="v", x=0.78` | Sağ kenara hizalı dikey legend |
| Orta annotation | *(yok)* | Toplam kW değeri | Ring chart'ın özeti |
| `hovertemplate` | `"label+value+percent"` | Özel format | `kW` birimi hover'da görünür |
| `line.width` | *(varsayılan)* | `0` | Dilim arası çizgi kaldırıldı |

#### DEĞİŞİKLİK 2-A-ii — Energy kart wrapper (`home.py` Satır 239-249)

```python
# MEVCUT (Satır 239-249):
html.Div(
    [
        html.H3("Energy by source", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
        html.P("Daily average (kW)", style={"margin": "0 0 12px 0", "color": "#A3AED0", "fontSize": "0.8rem"}),
        dcc.Graph(
            figure=create_energy_breakdown_chart(eb_labels, eb_values, "Energy (kW)", height=260),
            config={"displayModeBar": False},
        ),
    ],
    className="nexus-card",
    style={"padding": "20px"},
),
```

```python
# YENİ:
html.Div(
    [
        dmc.Text("Energy by Source", fw=700, size="lg", c="#2B3674", style={"marginBottom": "4px"}),
        dmc.Text("Daily average (kW) — IBM Power & vCenter", size="xs", c="dimmed", style={"marginBottom": "12px"}),
        dcc.Graph(
            figure=create_energy_breakdown_chart(eb_labels, eb_values, height=260),
            config={"displayModeBar": False},
            style={"height": "260px"},
        ),
    ],
    className="nexus-card",
    style={"padding": "24px"},
),
```

> **Not:** `create_energy_breakdown_chart()` çağrısından `title` argümanı kaldırıldı (fonksiyon artık başlığı kendi yerleştirmiyor, kart başlığı `dmc.Text` ile yazılıyor).

---

### FAZ 2-B: DC Comparison — Horizontal Bar Chart

#### Mevcut Sorun
`create_grouped_bar_chart()`: Dikey `go.Bar` + DC isimleri x ekseninde. DC adları uzunsa üst üste biniyor, x ekseni okunaksız hale geliyor.

#### Çözüm
`go.Bar` → **Yatay format** (`orientation="h"`). DC adları y ekseninde, değerler x ekseninde — hem görsel hem okunabilir.

#### DEĞİŞİKLİK 2-B-i — `charts.py` `create_grouped_bar_chart()` (Satır 108-132) YENİDEN YAZ

```python
# MEVCUT (Satır 108-132):
def create_grouped_bar_chart(labels, series_dict, title, height=300):
    fig = go.Figure()
    colors = ["#4318FF", "#05CD99", "#FFB547"]
    for i, (name, values) in enumerate(series_dict.items()):
        fig.add_trace(go.Bar(
            x=labels,
            y=values,
            name=name,
            marker_color=colors[i % len(colors)],
        ))
    fig.update_layout(
        barmode="group",
        title=dict(text=title, font=dict(size=14, color="#2B3674", family="DM Sans")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=20, r=20, t=50, b=40),
        height=height,
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(showgrid=False, zeroline=False),
        font=dict(family="DM Sans", color="#A3AED0"),
    )
    return fig
```

```python
# YENİ — Yatay format, minimalist grid:
def create_grouped_bar_chart(labels, series_dict, title, height=300):
    fig = go.Figure()
    colors = ["#4318FF", "#05CD99", "#FFB547"]
    for i, (name, values) in enumerate(series_dict.items()):
        fig.add_trace(go.Bar(
            y=labels,           # DC adları Y ekseninde
            x=values,           # Değerler X ekseninde
            name=name,
            orientation="h",    # Yatay bar
            marker=dict(
                color=colors[i % len(colors)],
                line=dict(color="rgba(0,0,0,0)", width=0),
            ),
            text=[f"{v:,}" for v in values],    # Bar üstüne değer yaz
            textposition="outside",
            textfont=dict(family="DM Sans", size=11, color="#A3AED0"),
        ))
    fig.update_layout(
        barmode="group",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.08,
            xanchor="center",
            x=0.5,
            font=dict(family="DM Sans", size=12, color="#2B3674"),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=10, r=40, t=10, b=40),
        height=height,
        bargap=0.3,
        bargroupgap=0.05,
        xaxis=dict(
            showgrid=True,
            gridcolor="rgba(233,236,239,0.6)",
            gridwidth=1,
            zeroline=False,
            showticklabels=True,
            tickfont=dict(family="DM Sans", size=11, color="#A3AED0"),
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            tickfont=dict(family="DM Sans", size=11, color="#2B3674"),
            autorange="reversed",   # İlk DC üstte
        ),
        font=dict(family="DM Sans", color="#A3AED0"),
    )
    return fig
```

| Değişen | Eski | Yeni | Gerekçe |
|---------|------|------|---------|
| `orientation` | *(dikey, varsayılan)* | `"h"` | DC adları y ekseninde — uzun isimler okunabilir |
| `x/y` | `x=labels, y=values` | `y=labels, x=values` | Yatay format için eksen yer değiştirdi |
| Grid | `showgrid=False` her iki eksen | X ekseninde hafif gri grid | Değer okumayı kolaylaştırır |
| Değer etiketi | *(yok)* | `text=values, textposition="outside"` | Bar yanında değer görünür |
| Legend | `y=1.02` (üst) | `y=-0.08` (alt) | Yatay formatta alt legend daha dengeli |
| `bargap` | *(varsayılan)* | `0.3` | Barlar arası boşluk artırıldı |
| `yaxis.autorange` | *(varsayılan)* | `"reversed"` | İlk DC (üst satır) listenin başında |

#### DEĞİŞİKLİK 2-B-ii — DC Comparison kart wrapper (`home.py` Satır 251-266)

```python
# MEVCUT (Satır 251-266):
html.Div(
    [
        html.H3("DC comparison", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
        dcc.Graph(
            figure=create_grouped_bar_chart(
                dc_names,
                {"Hosts": dc_hosts, "VMs": dc_vms},
                "Hosts & VMs by DC",
                height=260,
            ),
            config={"displayModeBar": False},
        ),
    ],
    className="nexus-card",
    style={"padding": "20px"},
),
```

```python
# YENİ:
html.Div(
    [
        dmc.Text("DC Comparison", fw=700, size="lg", c="#2B3674", style={"marginBottom": "4px"}),
        dmc.Text("Hosts & VMs per Data Center", size="xs", c="dimmed", style={"marginBottom": "12px"}),
        dcc.Graph(
            figure=create_grouped_bar_chart(
                dc_names,
                {"Hosts": dc_hosts, "VMs": dc_vms},
                title="",           # Başlık artık dmc.Text'te — grafik başlığı boş
                height=260,
            ),
            config={"displayModeBar": False},
            style={"height": "260px"},
        ),
    ],
    className="nexus-card",
    style={"padding": "24px"},
),
```

---

### FAZ 2 Kabul Kriterleri

- [ ] `python app.py` — hatasız başlangıç.
- [ ] Energy by Source: Pasta etiketleri grafik içinde **değil** — sağda legend listesi var.
- [ ] Energy ring'in ortasında toplam kW değeri görünüyor.
- [ ] Energy hover'ında `kW` birimi var.
- [ ] DC Comparison: Barlar **yatay** — DC adları y ekseninde okunabilir.
- [ ] Her barda yanında değer etiketi (`1,234` formatında) görünüyor.
- [ ] X ekseninde hafif gri grid çizgileri var.
- [ ] Y (DC adları) ekseninde grid yok.
- [ ] Legend altta, ortalanmış.

---
---

## FAZ 3: Veri Tablosu — DC Summary

**Hedef Satırlar:** `home.py` Satır 269-311

---

### Mevcut Sorun

```python
# Satır 275-309 — MEVCUT dmc.Table:
dmc.Table(
    striped=True,
    highlightOnHover=True,
    children=[
        html.Thead(html.Tr([
            html.Th("DC"), html.Th("Location"), html.Th("Platforms"),
            html.Th("Hosts"), html.Th("VMs"), html.Th("CPU %"), html.Th("RAM %"),
        ])),
        html.Tbody([
            html.Tr([
                html.Td(dcc.Link(s["name"], ...)),
                html.Td(s["location"]),
                html.Td(s.get("platform_count", 0)),
                html.Td(s["host_count"]),
                html.Td(s["vm_count"]),
                html.Td(f"{s['stats'].get('used_cpu_pct', 0)}%"),  # düz metin
                html.Td(f"{s['stats'].get('used_ram_pct', 0)}%"),  # düz metin
            ])
            for s in summaries
        ]),
    ],
),
```

**Sorunlar:**
- TH stil yok — başlıklar düz siyah, küçük, hizasız
- CPU % / RAM % düz metin — kritiklik rengi yok
- Sayısal sütunlar text-align: left (varsayılan) — sağa hizalanmalı

---

### Hazırlık — Yardımcı Fonksiyon Ekle (`home.py`)

`build_overview()` fonksiyonunun **başına** (Satır 70'ten sonra, `build_overview()` içine) şu yardımcı fonksiyonu ekle:

```python
def _pct_badge(value):
    """CPU/RAM yüzdesini renkli dmc.Badge ile döndür."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.0
    if v >= 80:
        color = "red"
    elif v >= 60:
        color = "orange"
    else:
        color = "teal"
    return dmc.Badge(
        f"{v:.1f}%",
        color=color,
        variant="light",
        radius="sm",
        size="sm",
        style={"fontWeight": 600, "letterSpacing": 0},
    )
```

> Bu fonksiyon `build_overview()` dışına, modül seviyesine de taşınabilir. Ancak `dmc` import'u fonksiyon dışında zaten mevcut — nereye koyarsan koy çalışır.

---

### DEĞİŞİKLİK 3 — DC Summary Tablosu (`home.py` Satır 269-311)

```python
# MEVCUT (Satır 269-311):
html.Div(
    className="nexus-card nexus-table",
    style={"margin": "0 30px", "padding": "20px", "overflowX": "auto"},
    children=[
        html.H3("DC summary", ...),
        html.P("CPU % and RAM % are daily averages over the report period.", ...),
        dmc.Table(striped=True, highlightOnHover=True, children=[...]),
    ],
),
```

```python
# YENİ — TAMAMEN bununla değiştir (Satır 269-311):
html.Div(
    className="nexus-card nexus-table",
    style={"margin": "0 30px", "padding": "24px", "overflowX": "auto"},
    children=[
        dmc.Text("DC Summary", fw=700, size="lg", c="#2B3674", style={"marginBottom": "4px"}),
        dmc.Text(
            "CPU % and RAM % are daily averages over the report period.",
            size="xs", c="dimmed", style={"marginBottom": "16px"}
        ),
        dmc.Table(
            striped=True,
            highlightOnHover=True,
            withTableBorder=False,
            withColumnBorders=False,
            verticalSpacing="sm",
            horizontalSpacing="md",
            children=[
                html.Thead(
                    html.Tr([
                        html.Th("Data Center", style={
                            "color": "#A3AED0", "fontWeight": 600,
                            "fontSize": "0.75rem", "textTransform": "uppercase",
                            "letterSpacing": "0.05em", "paddingBottom": "10px",
                        }),
                        html.Th("Location", style={
                            "color": "#A3AED0", "fontWeight": 600,
                            "fontSize": "0.75rem", "textTransform": "uppercase",
                            "letterSpacing": "0.05em",
                        }),
                        html.Th("Platforms", style={
                            "color": "#A3AED0", "fontWeight": 600,
                            "fontSize": "0.75rem", "textTransform": "uppercase",
                            "letterSpacing": "0.05em", "textAlign": "right",
                        }),
                        html.Th("Hosts", style={
                            "color": "#A3AED0", "fontWeight": 600,
                            "fontSize": "0.75rem", "textTransform": "uppercase",
                            "letterSpacing": "0.05em", "textAlign": "right",
                        }),
                        html.Th("VMs", style={
                            "color": "#A3AED0", "fontWeight": 600,
                            "fontSize": "0.75rem", "textTransform": "uppercase",
                            "letterSpacing": "0.05em", "textAlign": "right",
                        }),
                        html.Th("CPU %", style={
                            "color": "#A3AED0", "fontWeight": 600,
                            "fontSize": "0.75rem", "textTransform": "uppercase",
                            "letterSpacing": "0.05em", "textAlign": "right",
                        }),
                        html.Th("RAM %", style={
                            "color": "#A3AED0", "fontWeight": 600,
                            "fontSize": "0.75rem", "textTransform": "uppercase",
                            "letterSpacing": "0.05em", "textAlign": "right",
                        }),
                    ])
                ),
                html.Tbody([
                    html.Tr([
                        html.Td(
                            dcc.Link(
                                s["name"],
                                href=f"/datacenter/{s['id']}",
                                style={"color": "#4318FF", "fontWeight": 600, "textDecoration": "none"},
                            )
                        ),
                        html.Td(
                            dmc.Text(s["location"], size="sm", c="dimmed"),
                        ),
                        html.Td(
                            dmc.Text(str(s.get("platform_count", 0)), size="sm", fw=500, c="#2B3674"),
                            style={"textAlign": "right"},
                        ),
                        html.Td(
                            dmc.Text(f"{s['host_count']:,}", size="sm", fw=500, c="#2B3674"),
                            style={"textAlign": "right"},
                        ),
                        html.Td(
                            dmc.Text(f"{s['vm_count']:,}", size="sm", fw=500, c="#2B3674"),
                            style={"textAlign": "right"},
                        ),
                        html.Td(
                            _pct_badge(s["stats"].get("used_cpu_pct", 0)),
                            style={"textAlign": "right"},
                        ),
                        html.Td(
                            _pct_badge(s["stats"].get("used_ram_pct", 0)),
                            style={"textAlign": "right"},
                        ),
                    ])
                    for s in summaries
                ]),
            ],
        ),
    ],
),
```

#### Değişiklik Tablosu

| # | Değişen | Eski | Yeni | Gerekçe |
|---|---------|------|------|---------|
| 1 | **Kart başlığı** | `html.H3("DC summary")` | `dmc.Text(fw=700, size="lg")` | Mantine entegrasyonu |
| 2 | **Alt başlık** | `html.P(...)` | `dmc.Text(size="xs", c="dimmed")` | Semantik token |
| 3 | **TH stili** | Düz, stilsiz | Uppercase + `#A3AED0` + `font-size: 0.75rem` + letter-spacing | Premium tablo başlık tipografisi |
| 4 | **Sayısal sütunlar** | `textAlign: left` (varsayılan) | `textAlign: "right"` | Sayılar sağa hizalı — standart tablo kuralı |
| 5 | **CPU % / RAM %** | `html.Td("42%")` düz metin | `_pct_badge(value)` → `dmc.Badge` | Renk kodu: yeşil (<60) / turuncu (60-80) / kırmızı (>80) |
| 6 | **Sayı formatı** | `str(s["host_count"])` | `f"{s['host_count']:,}"` | 1,234 formatında binler ayırıcı |
| 7 | **Lokasyon** | `html.Td(s["location"])` | `dmc.Text(size="sm", c="dimmed")` | Renk hiyerarşisi — soluk, ikincil bilgi |
| 8 | **Table props** | `striped, highlightOnHover` | + `withTableBorder=False, withColumnBorders=False, verticalSpacing="sm"` | Daha temiz, sade tablo görünümü |
| 9 | **Padding** | `"20px"` | `"24px"` | Genel kural |

---

### FAZ 3 Kabul Kriterleri

- [ ] `python app.py` — hatasız başlangıç.
- [ ] Tablo başlık satırı (TH) uppercase, soluk gri, küçük noktalı harfler arası boşluklu.
- [ ] "Data Center", "Location" sütunları sola; "Platforms", "Hosts", "VMs", "CPU %", "RAM %" sağa hizalı.
- [ ] "Data Center" sütunundaki isimler hâlâ tıklanabilir mor link.
- [ ] CPU % ve RAM % değerleri düz metin değil — `dmc.Badge` badge içinde renk kodu ile.
  - `< 60%` → yeşil (teal)
  - `60%–80%` → turuncu (orange)
  - `≥ 80%` → kırmızı (red)
- [ ] Host ve VM sayıları binler ayırıcı ile (`1,234`).
- [ ] Tablo dikey kenarlıkları yok (`withColumnBorders=False`).
- [ ] Satırlar hover'da vurgulanan zebra deseni.

---
---

## 🧪 Bütünleşik Test Senaryosu (3 Faz Birden)

| # | Test | Beklenen |
|---|------|---------|
| 1 | `python app.py` | Hatasız başlangıç |
| 2 | Overview sayfasını aç | Sayfa tam yükleniyor |
| 3 | Platform Breakdown kartı | 3 alt kart açık gri, ince kenarlıklı, renk noktalı |
| 4 | Alt kart hover | Büyük gölge yok — hafif zemin |
| 5 | Resource Usage | 3 halka, orta rakamlar büyük (30px bold) |
| 6 | Energy by Source | Etiket grafik içinde yok, sağda legend listesi var |
| 7 | Energy ring ortası | Toplam kW değeri |
| 8 | DC Comparison | Yatay barlar — DC adları y ekseninde okunabilir |
| 9 | DC Comparison barlar | Yanlarında sayısal değer etiketi |
| 10 | DC Summary TH | Uppercase, soluk, küçük |
| 11 | DC Summary hizalama | Sayılar sağa, metinler sola |
| 12 | CPU % < 60 | Yeşil badge |
| 13 | CPU % 60-80 | Turuncu badge |
| 14 | CPU % >= 80 | Kırmızı badge |
| 15 | Tıklanabilir link | DC adına tıklayınca `/datacenter/{id}` sayfasına gidiyor |
| 16 | Zaman filtresi | Preset değişince tüm bloklar güncelleniyor |
| 17 | Konsol | Hiçbir `TypeError` / `KeyError` yok |

---

## 📝 Master Plan Değişiklik Özeti

```
src/components/charts.py
  Satır 047-078: create_usage_donut_chart()
    hole: 0.7→0.72, annotation size: 24→30, bold,
    hoverinfo: "skip", line.width: 0, iç renk: EEF2FF

  Satır 108-132: create_grouped_bar_chart()
    orientation: dikey → "h" (yatay)
    x/y eksenleri yer değiştirdi
    text=values (bar yanı etiket), bargap=0.3
    X ekseni hafif gri grid, Y ekseni grid yok
    legend alta taşındı

  Satır 164-183: create_energy_breakdown_chart()
    hole: 0.5→0.65, textinfo: "none"
    showlegend: True, legend sağ dikey
    Orta annotation: toplam kW
    hovertemplate: kW birimli özel format

src/pages/home.py
  Satır 056-067: platform_card()
    nexus-card → inline style (#f8f9fa zemin, ince border)
    Başlık: renk noktası + platform adı
    Metrikler: Stack key-value çiftleri

  Satır 189-196: Platform Breakdown wrapper
    html.H3 → dmc.Text(fw=700)
    alt başlık: dmc.Text(c="dimmed")
    padding: 20px → 24px

  Satır 197-231: Resource Usage wrapper
    html.H3 → dmc.Text(fw=700)
    html.P → dmc.Text(c="dimmed")
    Graph height: 160px → 180px
    padding: 20px → 24px

  Satır 239-249: Energy wrapper
    html.H3 → dmc.Text(fw=700)
    html.P → dmc.Text(c="dimmed")
    title argümanı kaldırıldı
    padding: 20px → 24px

  Satır 251-266: DC Comparison wrapper
    html.H3 → dmc.Text(fw=700)
    title="" (grafik başlığı boş)
    padding: 20px → 24px

  Satır 269-311: DC Summary tablosu
    YENİ: _pct_badge() yardımcı fonksiyon eklendi
    html.H3 / html.P → dmc.Text
    html.Th → premium stilli (uppercase, dimmed, sm)
    html.Td sayısal → textAlign: right
    html.Td CPU/RAM → _pct_badge() ile dmc.Badge
    Sayı formatı: int → f"{n:,}" (binler ayırıcı)
    padding: 20px → 24px

DEĞİŞMEYEN:
  - KPI strip (SimpleGrid cols=5)
  - metric_card() fonksiyonu
  - Tüm veri çekme mantığı (Satır 70-121)
  - Callback'lar (app.py)
  - Sidebar (sidebar.py)
  - assets/style.css
  - .nexus-card CSS sınıfı (kullanımda kalıyor)
```

**Toplam:** 2 dosya (`charts.py` 3 fonksiyon + `home.py` 1 yardımcı fonksiyon + 6 blok güncelleme).

---
---

## 🚨 Faz 2 Acil Revizyon — Grafik Kurtarma Operasyonu

**Tarih:** 2 Mart 2026, 01:10
**Kaynak:** CEO incelemesi — grafikler görsel fiyasko
**Kapsam:** `src/components/charts.py` — 3 fonksiyon cerrahi güncelleme
**Durum:** ⏳ Executor uygulaması bekleniyor

> Önceki Faz 1-B ve Faz 2 planlarındaki kod **GEÇERSİZ**. Bu bölümdeki kod nihai ve kesindir. Executor sadece buradaki değerleri uygulayacak.

---

### 🔴 Düzeltme 1 — Resource Usage Donut (`charts.py`)

**Sorunlar:**
1. Halka çok kalın — `hole` küçük
2. Orta yüzde yazısı tam merkeze oturmuyor — `y=0.45` kayıyor

**Hedef fonksiyon:** `create_usage_donut_chart()` — `charts.py`'deki tüm içeriğini şununla değiştir:

```python
def create_usage_donut_chart(value, label, color="#4318FF"):
    try:
        val = float(value)
    except (TypeError, ValueError):
        val = 0.0
    val = max(0.0, min(100.0, val))
    remaining = 100.0 - val

    fig = go.Figure(data=[go.Pie(
        values=[val, remaining],
        labels=["Used", "Free"],
        hole=0.82,                              # ← 0.72 → 0.82: daha ince, zarif halka
        marker=dict(
            colors=[color, "#EEF2FF"],
            line=dict(color="rgba(0,0,0,0)", width=0),
        ),
        sort=False,
        textinfo="none",
        hoverinfo="skip",
        direction="clockwise",
    )])

    fig.update_layout(
        annotations=[dict(
            text=f"<b>{int(val)}%</b>",
            x=0.5,
            y=0.5,                              # ← 0.45 → 0.5: tam merkez
            xanchor="center",
            yanchor="middle",                   # ← YENİ: dikey tam merkez
            font=dict(size=28, color="#2B3674", family="DM Sans"),
            showarrow=False,
        )],
        title=dict(
            text=f"<b>{label}</b>",
            x=0.5,
            xanchor="center",
            font=dict(size=12, color="#A3AED0", family="DM Sans"),
        ),
        showlegend=False,
        margin=dict(l=8, r=8, t=44, b=8),
        height=180,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig
```

| Parametre | Eski | Yeni | Etki |
|-----------|------|------|------|
| `hole` | `0.72` | **`0.82`** | Halka çok daha ince ve zarif |
| `annotation.y` | `0.45` | **`0.5`** | Tam dikey merkez |
| `annotation.yanchor` | *(yok)* | **`"middle"`** | Plotly'nin `y=0.5`'i gerçekten ortalaması için zorunlu |
| `annotation.size` | `30` | **`28`** | Daha ince halkaya orantılı font |

> **Kritik:** `yanchor="middle"` olmadan `y=0.5` Plotly'de tam merkez değildir — bu parametre zorunludur.

---

### 🔴 Düzeltme 2 — Energy by Source Ring (`charts.py`)

**Sorunlar:**
1. Orta `kW Total` annotation'ı kaymış
2. Legend (IBM Power, vCenter) düzgün hizalanmamış

**Hedef fonksiyon:** `create_energy_breakdown_chart()` — şununla değiştir:

```python
def create_energy_breakdown_chart(labels, values, title="Energy by source", height=260):
    try:
        total = sum(float(v) for v in values if v is not None)
    except (TypeError, ValueError):
        total = 0.0
    total_text = f"<b>{total:,.0f}</b><br><span style='font-size:11px;color:#A3AED0'>kW Total</span>"

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.65,
        marker=dict(
            colors=["#4318FF", "#05CD99", "#FFB547"],
            line=dict(color="rgba(0,0,0,0)", width=0),
        ),
        textinfo="none",
        hovertemplate="<b>%{label}</b><br>%{value:,.0f} kW (%{percent})<extra></extra>",
        direction="clockwise",
        sort=False,
    )])

    fig.update_layout(
        annotations=[dict(
            text=total_text,
            x=0.38,                             # Ring biraz solda, legend sağda
            y=0.5,                              # ← Kesin dikey merkez
            xanchor="center",
            yanchor="middle",                   # ← ZorunLU: dikey tam merkez
            font=dict(size=18, color="#2B3674", family="DM Sans"),
            showarrow=False,
        )],
        showlegend=True,
        legend=dict(
            orientation="v",
            x=1.05,                             # ← 0.78 → 1.05: grafik dışına taşıdı, temiz
            y=0.5,                              # ← Dikey orta hizalama
            xanchor="left",
            yanchor="middle",                   # ← Dikey tam merkez
            font=dict(family="DM Sans", size=12, color="#2B3674"),
            bgcolor="rgba(0,0,0,0)",
            itemsizing="constant",
            tracegroupgap=8,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=110, t=16, b=16),  # ← r=110: legend için sağda alan
        height=height,
        font=dict(family="DM Sans", color="#A3AED0"),
    )
    return fig
```

| Parametre | Eski | Yeni | Etki |
|-----------|------|------|------|
| `annotation.y` | `0.5` (kayıyordu) | **`0.5` + `yanchor="middle"`** | Gerçek dikey merkez |
| `legend.x` | `0.78` (grafik içi) | **`1.05`** | Grafik dışına çıktı — ring ile çakışmıyor |
| `legend.y` | `0.5` | **`0.5` + `yanchor="middle"`** | Legend dikey ortalandı |
| `margin.r` | `10` | **`110`** | Legend için sağda boşluk açıldı |

> **Kritik:** `margin.r=110` olmadan `x=1.05`'teki legend görünmez, kart dışına taşar.

---

### 🔴 Düzeltme 3 — DC Comparison Bar (`charts.py`)

**Sorunlar:**
1. Barlar iplik gibi ince (`bargap` çok büyük)
2. X ekseni dikey çizgiler hâlâ duruyor
3. DC adları (AZ11, DC11 vb.) okunaksız küçük

**Hedef fonksiyon:** `create_grouped_bar_chart()` — şununla değiştir:

```python
def create_grouped_bar_chart(labels, series_dict, title, height=380):
    fig = go.Figure()
    colors = ["#4318FF", "#05CD99", "#FFB547"]

    for i, (name, values) in enumerate(series_dict.items()):
        fig.add_trace(go.Bar(
            y=labels,
            x=values,
            name=name,
            orientation="h",
            marker=dict(
                color=colors[i % len(colors)],
                line=dict(color="rgba(0,0,0,0)", width=0),
                opacity=0.9,
            ),
            text=[f"{v:,}" for v in values],
            textposition="outside",
            textfont=dict(family="DM Sans", size=11, color="#A3AED0"),
            insidetextanchor="middle",
        ))

    fig.update_layout(
        barmode="group",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.10,
            xanchor="center",
            x=0.5,
            font=dict(family="DM Sans", size=12, color="#2B3674"),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=10, r=50, t=8, b=50),
        height=height,                          # ← 300 → 380: barlar üst üste binmesin
        bargap=0.20,                            # ← 0.30 → 0.20: barlar daha etli/kalın
        bargroupgap=0.08,
        xaxis=dict(
            showgrid=False,                     # ← True → False: dikey çizgiler silindi
            zeroline=False,
            showticklabels=True,
            tickfont=dict(family="DM Sans", size=11, color="#A3AED0"),
        ),
        yaxis=dict(
            showgrid=False,                     # ← False (zaten), ekstra emin olalım
            zeroline=False,
            tickfont=dict(family="DM Sans", size=13, color="#2B3674"),  # ← 11 → 13: okunabilir
            autorange="reversed",
        ),
        font=dict(family="DM Sans", color="#A3AED0"),
    )
    return fig
```

| Parametre | Eski | Yeni | Etki |
|-----------|------|------|------|
| `bargap` | `0.30` | **`0.20`** | Barlar arası boşluk azaldı → barlar etli, kalın |
| `height` | `300` | **`380`** | Daha fazla dikey alan → DC'ler üst üste binmez |
| `xaxis.showgrid` | `True` | **`False`** | X eksenindeki tüm dikey çizgiler silindi |
| `yaxis.tickfont.size` | `11` | **`13`** | DC adları daha büyük, okunabilir |
| `margin.r` | `40` | **`50`** | Bar yanı etiket için biraz daha alan |

> **Kritik nüans:** `bargap` **tüm gruplar arasındaki** boşluktur. `bargroupgap` ise bir grup içindeki barlar arasıdır. Kalın barlar için `bargap` küçültülür.

**`home.py`'deki çağrıyı da güncelle** — yeni `height=380`:

```python
# home.py — DC Comparison dcc.Graph çağrısını bul ve güncelle:
dcc.Graph(
    figure=create_grouped_bar_chart(
        dc_names,
        {"Hosts": dc_hosts, "VMs": dc_vms},
        title="",
        height=380,             # ← 260 → 380
    ),
    config={"displayModeBar": False},
    style={"height": "380px"}, # ← 260px → 380px
),
```

---

### ✅ Acil Revizyon Kabul Kriterleri

- [ ] `python app.py` — hatasız başlangıç.

**Resource Usage:**
- [ ] Halkalar ince ve zarif — `hole=0.82`.
- [ ] Orta yüzde rakamı tam merkeze oturmuş — ne yukarıda ne aşağıda.
- [ ] `28%`, `64%`, `91%` gibi rakamlar bold ve okunaklı.

**Energy by Source:**
- [ ] `kW Total` annotation grafiğin tam ortasında — kaymıyor.
- [ ] Legend (IBM Power, vCenter) ring'in **sağ dışında**, düzgün hizalı.
- [ ] Legend ile ring grafiği çakışmıyor.

**DC Comparison:**
- [ ] Barlar **etli ve kalın** — iplik gibi değil.
- [ ] X ekseninde **hiçbir ızgara çizgisi yok** — temiz zemin.
- [ ] Y eksenindeki DC adları (AZ11, DC11 vb.) `size=13` — okunabilir.
- [ ] Grafik yüksekliği `380px` — DC'ler üst üste binmiyor.

---

### 📝 Acil Revizyon Değişiklik Özeti

```
Dosya: src/components/charts.py

  create_usage_donut_chart():
    hole: 0.72 → 0.82
    annotation.y: 0.45 → 0.5
    annotation.yanchor: (yok) → "middle"  ← ZORUNLU
    annotation.size: 30 → 28

  create_energy_breakdown_chart():
    annotation.yanchor: (yok) → "middle"  ← ZORUNLU
    legend.x: 0.78 → 1.05
    legend.yanchor: (yok) → "middle"
    margin.r: 10 → 110  ← legend görünür kalması için

  create_grouped_bar_chart():
    bargap: 0.30 → 0.20  ← barlar kalınlaşır
    height default: 300 → 380
    xaxis.showgrid: True → False  ← çizgiler silindi
    yaxis.tickfont.size: 11 → 13  ← okunabilir DC adları

Dosya: src/pages/home.py
  DC Comparison dcc.Graph:
    height arg: 260 → 380
    style.height: "260px" → "380px"

DEĞİŞMEYEN:
  - Tüm renkler (#4318FF, #05CD99, #FFB547)
  - orientation="h" (yatay bar)
  - Energy ring hole=0.65
  - DC Summary tablosu
```

**Toplam:** 1 dosya (`charts.py`) 3 fonksiyon + `home.py` 1 satır (height).

---
---

## 🏆 Ultra-Premium Faz 2 & 3 — Nihai Plan (CEO Onaylı)

**Tarih:** 2 Mart 2026, 01:31
**Kaynak:** CEO direktifi — çıta en tepeye çekildi
**Durum:** ⏳ Executor uygulaması bekleniyor

> ⚠️ **Bu bölüm tüm önceki Faz 2 ve Faz 3 planlarını GEÇERSİZ kılar.** Executor yalnızca bu bölümü uygulayacak.
> Faz 1 (Platform Breakdown + platform_card) değişmez.

---

### Madde 1 — Evrensel Kartlar: Hover Micro-Interaction

#### Hedef
`assets/style.css` — `.nexus-card:hover` kuralı.

#### Mevcut Kural (`style.css` Satır 47-52)
```css
.nexus-card:hover {
    transform: translateY(-5px);
    box-shadow:
        0px 30px 60px rgba(112, 144, 176, 0.20),
        0px 10px 20px rgba(112, 144, 176, 0.10) !important;
}
```

#### Yeni Kural (Bununla değiştir)
```css
.nexus-card:hover {
    transform: translateY(-3px);
    box-shadow:
        0px 20px 50px rgba(67, 24, 255, 0.10),
        0px 8px 20px rgba(112, 144, 176, 0.08) !important;
}
```

Ayrıca `.nexus-card` base kuralındaki `transition` kontrol et ve güncelle:
```css
.nexus-card {
    /* ... mevcut kurallar ... */
    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);  /* Bu zaten var — bırak */
}
```

| CSS | Eski | Yeni | Etki |
|-----|------|------|------|
| `translateY` | `-5px` | **`-3px`** | Daha zarif, abartısız kalkış |
| `box-shadow renk` | `rgba(112,144,176,...)` gri | **`rgba(67,24,255,0.10)`** mor aura | Premium marka rengi gölge |

---

### Madde 2 — Resource Usage: Plotly İptal → `dmc.RingProgress`

#### Teknik Bağlam
`dmc.RingProgress` — Dash Mantine Components native bileşeni.
- `sections=[{"value": 40, "color": "blue"}]` — yüzde ve renk
- `size=150` — dış çap (px)
- `thickness=12` — halka kalınlığı (px)
- `label` — ortaya herhangi bir Dash bileşeni yerleştirir
- `roundCaps=True` — uçlar yuvarlak ✅ (dmc.Title gradient'ın aksine bu **çalışır**)

#### DEĞİŞİKLİK 2-i — `home.py` Satır 197-231 (Resource Usage kartı)

**`create_usage_donut_chart()` çağrılarını tamamen kaldır. `dcc.Graph` kaldır. Aşağıdaki kodu koy:**

```python
# YENİ — Plotly'siz, saf Mantine:
html.Div(
    [
        dmc.Text("Resource Usage", fw=700, size="lg", c="#2B3674", style={"marginBottom": "4px"}),
        dmc.Text("Daily average over report period", size="xs", c="dimmed", style={"marginBottom": "20px"}),
        dmc.SimpleGrid(
            cols=3,
            spacing="xl",
            children=[
                _ring_stat(cpu_pct,  "CPU",     "#4318FF"),
                _ring_stat(ram_pct,  "RAM",     "#05CD99"),
                _ring_stat(stor_pct, "Storage", "#FFB547"),
            ],
        ),
    ],
    className="nexus-card",
    style={"padding": "24px"},
),
```

#### DEĞİŞİKLİK 2-ii — `home.py` modül seviyesine `_ring_stat()` fonksiyonu ekle

`platform_card()` fonksiyonunun **hemen altına** (Satır 68'den sonra) ekle:

```python
def _ring_stat(value, label, color):
    """dmc.RingProgress ile tek kaynak kullanım halkası."""
    try:
        v = max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        v = 0.0

    # Renk → glow rengi (rgba)
    glow_map = {
        "#4318FF": "rgba(67, 24, 255, 0.18)",
        "#05CD99": "rgba(5, 205, 153, 0.18)",
        "#FFB547": "rgba(255, 181, 71, 0.18)",
    }
    glow = glow_map.get(color, "rgba(67,24,255,0.12)")

    return html.Div(
        style={
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "gap": "10px",
        },
        children=[
            dmc.RingProgress(
                size=130,
                thickness=10,
                roundCaps=True,
                sections=[{"value": v, "color": color}],
                style={"filter": f"drop-shadow(0 0 8px {glow})"},
                label=html.Div(
                    style={"textAlign": "center"},
                    children=[
                        dmc.Text(
                            f"{int(v)}%",
                            fw=900,
                            size="xl",
                            c="#2B3674",
                            style={"lineHeight": 1},
                        ),
                    ],
                ),
            ),
            dmc.Text(label, size="sm", fw=600, c="#A3AED0"),
        ],
    )
```

#### DEĞİŞİKLİK 2-iii — `charts.py` `create_usage_donut_chart()` kaldır

`create_usage_donut_chart()` fonksiyonunu (Satır 47-78) **sil** — artık kullanılmıyor.

`home.py` import satırı (Satır 7-11) — `create_usage_donut_chart` import'unu kaldır:
```python
# MEVCUT:
from src.components.charts import (
    create_usage_donut_chart,       # ← BU SATIRI SİL
    create_energy_breakdown_chart,
    create_grouped_bar_chart,
)

# YENİ:
from src.components.charts import (
    create_energy_breakdown_chart,
    create_grouped_bar_chart,
)
```

---

### Madde 3 — DC Comparison: Executive Analiz Premium Barlar

#### Hedef Fonksiyon: `charts.py` → `create_grouped_bar_chart()` — TAMAMEN YENİDEN YAZ

```python
def create_grouped_bar_chart(labels, series_dict, title, height=380):
    fig = go.Figure()
    colors     = ["#4318FF",              "#05CD99"]
    colors_dim = ["rgba(67,24,255,0.55)", "rgba(5,205,153,0.55)"]

    all_vals = [v for vals in series_dict.values() for v in vals if v]
    avg = (sum(all_vals) / len(all_vals)) if all_vals else 0

    for i, (name, values) in enumerate(series_dict.items()):
        fig.add_trace(go.Bar(
            y=labels,
            x=values,
            name=name,
            orientation="h",
            marker=dict(
                color=colors[i % len(colors)],
                opacity=0.85,
                line=dict(color="rgba(0,0,0,0)", width=0),
            ),
            hovertemplate=f"<b>%{{y}}</b><br>{name}: %{{x:,}}<extra></extra>",
        ))

    # Sistem ortalaması referans çizgisi
    fig.add_vline(
        x=avg,
        line_dash="dot",
        line_color="rgba(67, 24, 255, 0.35)",
        line_width=1.5,
        annotation_text=f"Avg: {avg:,.0f}",
        annotation_position="top",
        annotation_font=dict(family="DM Sans", size=11, color="rgba(67,24,255,0.7)"),
    )

    fig.update_layout(
        barmode="group",
        hovermode="y unified",              # ← Tüm trace'ler tek tooltip'te
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.12,
            xanchor="center",
            x=0.5,
            font=dict(family="DM Sans", size=12, color="#2B3674"),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=10, r=20, t=24, b=50),
        height=height,
        bargap=0.15,                        # ← Etli, kalın barlar
        bargroupgap=0.06,
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,           # ← X ekseni sayısı yok — tooltip'te var
            tickfont=dict(family="DM Sans", size=11, color="#A3AED0"),
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            tickfont=dict(family="DM Sans", size=13, color="#2B3674", weight=600),
            autorange="reversed",
        ),
        hoverlabel=dict(
            bgcolor="rgba(255,255,255,0.95)",
            bordercolor="rgba(67,24,255,0.2)",
            font=dict(family="DM Sans", size=12, color="#2B3674"),
        ),
        font=dict(family="DM Sans", color="#A3AED0"),
    )

    # Yuvarlak bar köşeleri — Plotly >= 5.12 destekliyorsa
    try:
        fig.update_traces(marker_cornerradius=6)
    except Exception:
        pass  # Eski Plotly — sorunsuz atla

    return fig
```

| Özellik | Eski | Yeni | Etki |
|---------|------|------|------|
| `bargap` | `0.30` | **`0.15`** | Barlar etli ve kalın |
| `text` / etiket | Bar yanı yazı | **Kaldırıldı** | Hover tooltip'te — daha temiz |
| `hovermode` | varsayılan | **`"y unified"`** | Tüm trace'ler tek tooltip baloncuğunda |
| `add_vline` | *(yok)* | **Sistem ortalaması kesik çizgi** | Analitik referans, premium SaaS tarzı |
| `marker_cornerradius` | *(yok)* | **`6`** (try/except ile) | Yuvarlatılmış bar uçları — Plotly ≥ 5.12 |
| `showticklabels` X | `True` | **`False`** | Sayılar tooltip'te, eksende değil — minimalist |
| `hoverlabel` | *(yok)* | Beyaz, mor kenarlı özel tooltip | Premium hover UI |

> **`add_vline` hesabı:** `avg` tüm host + VM değerlerinin ortalaması. Hosts ve VMs farklı birimde — her seri kendi ortalamasını almak istersen: `avg = sum(series_dict["Hosts"]) / len(labels)`. Executor uygun bulduğu yaklaşımı seçer.

**`home.py` — DC Comparison dcc.Graph height güncelle:**
```python
dcc.Graph(
    figure=create_grouped_bar_chart(
        dc_names,
        {"Hosts": dc_hosts, "VMs": dc_vms},
        title="",
        height=380,
    ),
    config={"displayModeBar": False},
    style={"height": "380px"},
),
```

---

### Madde 4 — Energy by Source: Annotation Tam Merkez

#### Hedef Fonksiyon: `charts.py` → `create_energy_breakdown_chart()` — TAMAMEN YENİDEN YAZ

```python
def create_energy_breakdown_chart(labels, values, title="Energy by source", height=260):
    try:
        total = sum(float(v) for v in values if v is not None)
    except (TypeError, ValueError):
        total = 0.0

    # Ortadaki blok: büyük sayı + küçük "kW Total" alt satır
    center_text = (
        f"<span style='font-size:28px;font-weight:900;color:#2B3674'>"
        f"{total:,.0f}"
        f"</span>"
        f"<br>"
        f"<span style='font-size:11px;color:#A3AED0'>kW Total</span>"
    )

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.68,
        marker=dict(
            colors=["#4318FF", "#05CD99"],
            line=dict(color="rgba(0,0,0,0)", width=0),
        ),
        textinfo="none",
        hovertemplate="<b>%{label}</b><br>%{value:,.0f} kW — %{percent}<extra></extra>",
        direction="clockwise",
        sort=False,
    )])

    fig.update_layout(
        annotations=[dict(
            text=center_text,
            x=0.5,
            y=0.5,
            xanchor="center",
            yanchor="middle",               # ← tam dikey merkez
            showarrow=False,
            align="center",
        )],
        showlegend=True,
        legend=dict(
            orientation="v",
            x=1.05,                         # ← ring dışında
            y=0.5,
            xanchor="left",
            yanchor="middle",
            font=dict(family="DM Sans", size=12, color="#2B3674"),
            bgcolor="rgba(0,0,0,0)",
            itemsizing="constant",
            tracegroupgap=10,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=120, t=16, b=16),   # ← r=120: legend için alan
        height=height,
        font=dict(family="DM Sans", color="#A3AED0"),
    )
    return fig
```

| Özellik | Eski | Yeni | Etki |
|---------|------|------|------|
| `center_text` | `<b>10</b><br>...` | **`<span style='font-size:28px;font-weight:900'>10</span>`** | Sayı büyük, bold, renk doğrudan HTML ile |
| `annotation.x/y` | `0.38 / 0.5` | **`0.5 / 0.5`** | Ring grafik tam ortalandı (legend x=1.05'e taşındığından ring sola kaymıyor) |
| `annotation.yanchor` | `"middle"` | **`"middle"`** | Korunuyor — zorunlu |
| `annotation.align` | *(yok)* | **`"center"`** | Çok satırlı metin ortaya hizalı |
| `hole` | `0.65` | **`0.68`** | Biraz daha ince, annotation için daha fazla alan |
| `margin.r` | `110` | **`120`** | Legend için 10px daha fazla alan |

---

### ✅ Ultra-Premium Nihai Kabul Kriterleri

**Micro-interactions:**
- [ ] Kart hover'ında `translateY(-3px)` — zarif, abartısız kalkış.
- [ ] Hover gölgesi mor aura (`rgba(67,24,255,0.10)`) — gri değil.

**Resource Usage (dmc.RingProgress):**
- [ ] `python app.py` — hatasız başlangıç, `create_usage_donut_chart` import hatası yok.
- [ ] 3 halka `dmc.RingProgress` ile render ediliyor — `dcc.Graph` yok.
- [ ] Halkalar `roundCaps=True` — uçları yuvarlak.
- [ ] Her halkanın altında renk glow/aura efekti (`drop-shadow`).
- [ ] Ortada `fontWeight:900` büyük yüzde rakamı.
- [ ] CPU `#4318FF` mor, RAM `#05CD99` turkuaz, Storage `#FFB547` turuncu.

**DC Comparison:**
- [ ] Barlar etli — `bargap=0.15`.
- [ ] Bar yan yazılar yok — tooltip ile bilgi.
- [ ] Hover'da `y unified` — tek baloncukta tüm seri değerleri.
- [ ] Dikey kesik çizgili **"Avg: X"** referans çizgisi görünüyor.
- [ ] Bar uçları yuvarlak (Plotly sürümü uygunsa).
- [ ] X ekseni sayıları yok — minimalist.
- [ ] Y DC adları `size=13`, bold.

**Energy by Source:**
- [ ] `total_kW` sayısı ring'in ortasında — tam merkez, kaymıyor.
- [ ] Sayı `font-size:28px, font-weight:900` — büyük ve tok.
- [ ] `kW Total` alt satırı soluk gri, küçük.
- [ ] Legend sağ dışta, dikey, ortaya hizalı.
- [ ] Ring ile legend çakışmıyor.

---

### 📝 Ultra-Premium Değişiklik Özeti

```
assets/style.css
  .nexus-card:hover:
    translateY: -5px → -3px
    box-shadow renk: gri → rgba(67,24,255,0.10) mor aura

src/pages/home.py
  Import satırı:
    create_usage_donut_chart → KALDIRILDI

  Modül seviyesi — YENİ FONKSİYON:
    _ring_stat(value, label, color)
      → dmc.RingProgress(roundCaps=True, drop-shadow glow)
      → ortada dmc.Text(fw=900)

  Satır 197-231 (Resource Usage kartı):
    3x dcc.Graph(create_usage_donut_chart) → 3x _ring_stat()

  DC Comparison dcc.Graph:
    height: 260 → 380
    style.height: "260px" → "380px"

src/components/charts.py
  create_usage_donut_chart():
    TAMAMEN SİLİNDİ

  create_energy_breakdown_chart():
    center_text: <span font-size:28px font-weight:900> formatı
    annotation.x: 0.38 → 0.5 (tam ortalandı)
    annotation.yanchor: "middle" (korunuyor)
    hole: 0.65 → 0.68
    margin.r: 110 → 120

  create_grouped_bar_chart():
    bargap: 0.30 → 0.15 (etli barlar)
    hovermode: "y unified" (YENİ)
    add_vline: sistem ortalaması kesik çizgi (YENİ)
    marker_cornerradius: 6 (try/except, YENİ)
    text/textposition: KALDIRILDI (tooltip'te)
    xaxis.showticklabels: False
    hoverlabel: özel beyaz/mor tooltip (YENİ)

DEĞİŞMEYEN:
  - Faz 1 (platform_card, Platform Breakdown)
  - Faz 3 (DC Summary tablosu + _pct_badge)
  - KPI strip
  - Sidebar
  - Callback'lar
  - nexus-card base CSS (sadece :hover değişiyor)
```

**Toplam:** 3 dosya — `style.css` (1 kural), `home.py` (import + yeni fonksiyon + 1 kart), `charts.py` (2 fonksiyon güncelle + 1 fonksiyon sil).

---
---

## 💎 Faz 3 — Ultra-Premium Tablo: DC Summary (Nihai Plan)

**Tarih:** 2 Mart 2026, 01:47
**Kaynak:** CEO direktifi — tablo radikal modernizasyonu
**Hedef:** `src/pages/home.py` — Satır 269-311 (DC Summary bloğu)
**Durum:** ⏳ Executor uygulaması bekleniyor

> ⚠️ Bu bölüm tüm önceki Faz 3 planlarını **GEÇERSİZ** kılar. Executor yalnızca buradaki kodu uygular.

---

### Mevcut Kod (Başlamadan Önce Referans — `home.py` Satır 269-311)

```python
html.Div(
    className="nexus-card nexus-table",
    style={"margin": "0 30px", "padding": "20px", "overflowX": "auto"},
    children=[
        html.H3("DC summary", style={"margin": "0 0 4px 0", "color": "#2B3674"}),
        html.P("CPU % and RAM % are daily averages over the report period.", ...),
        dmc.Table(
            striped=True,
            highlightOnHover=True,
            children=[
                html.Thead(html.Tr([
                    html.Th("DC"), html.Th("Location"), html.Th("Platforms"),
                    html.Th("Hosts"), html.Th("VMs"), html.Th("CPU %"), html.Th("RAM %"),
                ])),
                html.Tbody([
                    html.Tr([
                        html.Td(dcc.Link(s["name"], href=..., style={"color":"#4318FF","fontWeight":600})),
                        html.Td(s["location"]),
                        html.Td(s.get("platform_count", 0)),
                        html.Td(s["host_count"]),
                        html.Td(s["vm_count"]),
                        html.Td(f"{s['stats'].get('used_cpu_pct',0)}%"),   # düz metin
                        html.Td(f"{s['stats'].get('used_ram_pct',0)}%"),   # düz metin
                    ])
                    for s in summaries
                ]),
            ],
        ),
    ],
),
```

---

### Hazırlık — 3 Yardımcı Fonksiyon Ekle (`home.py`)

Bu 3 fonksiyonu `_ring_stat()` fonksiyonunun **hemen altına** (modül seviyesinde) ekle. `build_overview()` içine değil.

#### Fonksiyon A — `_pct_badge(value)` — Dinamik Sağlık Rozeti

```python
def _pct_badge(value):
    """CPU/RAM yüzdesini değere göre renk kodlu dmc.Badge ile döndür."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.0

    if v >= 80:
        color, variant = "red", "light"
    elif v >= 50:
        color, variant = "blue", "light"
    else:
        color, variant = "teal", "light"

    # Sıfır susturma: değer 0 ise soluk göster
    if v == 0.0:
        return dmc.Text("—", size="sm", c="dimmed", style={"textAlign": "right"})

    return dmc.Badge(
        f"{v:.1f}%",
        color=color,
        variant=variant,
        radius="sm",
        size="sm",
        style={
            "fontWeight": 600,
            "letterSpacing": 0,
            "fontVariantNumeric": "tabular-nums",
            "minWidth": "52px",
            "textAlign": "center",
        },
    )
```

| Değer | Renk | Anlam |
|-------|------|-------|
| `>= 80%` | 🔴 Kırmızı | Kritik/Dolu |
| `50-79%` | 🔵 Mavi | Normal |
| `< 50%` | 🟢 Yeşil | İyi |
| `0%` | — dim | Veri yok / boş |

#### Fonksiyon B — `_num_cell(value, suffix="")` — Sayısal Hücre

```python
def _num_cell(value, suffix=""):
    """Sayısal değeri sağa hizalı, tabular-nums formatında döndür.
    0 ise soluklaştırılmış tire göster."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = 0

    if v == 0:
        return dmc.Text("—", size="sm", c="dimmed",
                         style={"textAlign": "right", "fontVariantNumeric": "tabular-nums"})

    return dmc.Text(
        f"{v:,}{suffix}",
        size="sm",
        fw=500,
        c="#2B3674",
        style={"textAlign": "right", "fontVariantNumeric": "tabular-nums"},
    )
```

#### Fonksiyon C — `_dc_link(name, dc_id)` — Premium DC Linki

```python
def _dc_link(name, dc_id):
    """DC ismini altı çizgisiz, marka renginde, kalın link olarak döndür."""
    return dcc.Link(
        dmc.Text(
            name,
            size="sm",
            fw=700,
            c="#4318FF",
            style={"letterSpacing": "-0.01em"},
        ),
        href=f"/datacenter/{dc_id}",
        style={"textDecoration": "none"},
    )
```

---

### DEĞİŞİKLİK 3 — DC Summary Tablosu (`home.py` Satır 269-311 — TAMAMEN DEĞİŞTİR)

```python
# YENİ — Ultra-Premium DC Summary:
html.Div(
    className="nexus-card nexus-table",
    style={
        "margin": "0 30px",
        "padding": "24px",
        "overflowX": "auto",
    },
    children=[
        dmc.Text(
            "DC Summary",
            fw=700,
            size="lg",
            c="#2B3674",
            style={"marginBottom": "4px"},
        ),
        dmc.Text(
            "CPU & RAM: daily averages over the report period.",
            size="xs",
            c="dimmed",
            style={"marginBottom": "18px"},
        ),
        dmc.Table(
            striped=True,
            highlightOnHover=True,
            withTableBorder=False,
            withColumnBorders=False,
            verticalSpacing="sm",
            horizontalSpacing="md",
            children=[
                html.Thead(
                    html.Tr([
                        html.Th(
                            "Data Center",
                            style={
                                "color": "#A3AED0",
                                "fontWeight": 600,
                                "fontSize": "0.72rem",
                                "textTransform": "uppercase",
                                "letterSpacing": "0.07em",
                                "paddingBottom": "12px",
                                "borderBottom": "2px solid #f1f3f5",
                            },
                        ),
                        html.Th(
                            "Location",
                            style={
                                "color": "#A3AED0",
                                "fontWeight": 600,
                                "fontSize": "0.72rem",
                                "textTransform": "uppercase",
                                "letterSpacing": "0.07em",
                                "paddingBottom": "12px",
                                "borderBottom": "2px solid #f1f3f5",
                            },
                        ),
                        html.Th(
                            "Platforms",
                            style={
                                "color": "#A3AED0",
                                "fontWeight": 600,
                                "fontSize": "0.72rem",
                                "textTransform": "uppercase",
                                "letterSpacing": "0.07em",
                                "paddingBottom": "12px",
                                "borderBottom": "2px solid #f1f3f5",
                                "textAlign": "right",
                            },
                        ),
                        html.Th(
                            "Hosts",
                            style={
                                "color": "#A3AED0",
                                "fontWeight": 600,
                                "fontSize": "0.72rem",
                                "textTransform": "uppercase",
                                "letterSpacing": "0.07em",
                                "paddingBottom": "12px",
                                "borderBottom": "2px solid #f1f3f5",
                                "textAlign": "right",
                            },
                        ),
                        html.Th(
                            "VMs",
                            style={
                                "color": "#A3AED0",
                                "fontWeight": 600,
                                "fontSize": "0.72rem",
                                "textTransform": "uppercase",
                                "letterSpacing": "0.07em",
                                "paddingBottom": "12px",
                                "borderBottom": "2px solid #f1f3f5",
                                "textAlign": "right",
                            },
                        ),
                        html.Th(
                            "CPU %",
                            style={
                                "color": "#A3AED0",
                                "fontWeight": 600,
                                "fontSize": "0.72rem",
                                "textTransform": "uppercase",
                                "letterSpacing": "0.07em",
                                "paddingBottom": "12px",
                                "borderBottom": "2px solid #f1f3f5",
                                "textAlign": "right",
                            },
                        ),
                        html.Th(
                            "RAM %",
                            style={
                                "color": "#A3AED0",
                                "fontWeight": 600,
                                "fontSize": "0.72rem",
                                "textTransform": "uppercase",
                                "letterSpacing": "0.07em",
                                "paddingBottom": "12px",
                                "borderBottom": "2px solid #f1f3f5",
                                "textAlign": "right",
                            },
                        ),
                    ])
                ),
                html.Tbody([
                    html.Tr([
                        # DC İsmi — premium link
                        html.Td(_dc_link(s["name"], s["id"])),

                        # Lokasyon — soluk renk
                        html.Td(
                            dmc.Text(s["location"], size="sm", c="dimmed")
                        ),

                        # Platform sayısı — sağa hizalı, sıfır susturma
                        html.Td(
                            _num_cell(s.get("platform_count", 0)),
                            style={"textAlign": "right"},
                        ),

                        # Host sayısı — sağa hizalı, tabular-nums
                        html.Td(
                            _num_cell(s["host_count"]),
                            style={"textAlign": "right"},
                        ),

                        # VM sayısı — sağa hizalı, tabular-nums
                        html.Td(
                            _num_cell(s["vm_count"]),
                            style={"textAlign": "right"},
                        ),

                        # CPU % — renk kodlu badge
                        html.Td(
                            _pct_badge(s["stats"].get("used_cpu_pct", 0)),
                            style={"textAlign": "right"},
                        ),

                        # RAM % — renk kodlu badge
                        html.Td(
                            _pct_badge(s["stats"].get("used_ram_pct", 0)),
                            style={"textAlign": "right"},
                        ),
                    ])
                    for s in summaries
                ]),
            ],
        ),
    ],
),
```

---

### Değişiklik Tablosu

| # | Bileşen | Eski | Yeni | Etki |
|---|---------|------|------|------|
| 1 | **DC linki** | `dcc.Link(color="#4318FF", fontWeight:600)` + mavi altı çizgili | `_dc_link()` → `dmc.Text(fw=700)` sarılmış link, `textDecoration:"none"` | Altı çizgisiz, typography hierarchy |
| 2 | **Lokasyon** | `html.Td(s["location"])` koyu siyah | `dmc.Text(c="dimmed")` | Birincil/ikincil bilgi hiyerarşisi |
| 3 | **Sayısal hücreler** | `html.Td(s["host_count"])` — `textAlign:left` | `_num_cell()` → `fontVariantNumeric:"tabular-nums"`, `textAlign:right` | Sütunlar dikey hizalı, sağa yaslanmış |
| 4 | **Sıfır susturma** | `0` bold siyah | `_num_cell(0)` → `"—"` soluk gri | Görsel gürültü azaltıldı |
| 5 | **CPU/RAM %** | `"42%"` düz metin | `_pct_badge()` → `dmc.Badge` renk kodlu | ≥80 kırmızı / 50-79 mavi / <50 yeşil |
| 6 | **0% badge** | `"0%"` gösterilir | `_pct_badge(0)` → `"—"` soluk | Veri yoksa gürültü yok |
| 7 | **TH başlıklar** | Düz siyah | Uppercase + `0.72rem` + `letterSpacing:0.07em` + `#A3AED0` + alt kenarlık | Premium tablo başlık tipografisi |
| 8 | **TH alt çizgi** | `striped` varsayılan | `borderBottom: "2px solid #f1f3f5"` | Başlık-içerik ayrımı belirgin |
| 9 | **Table props** | `striped, highlightOnHover` | `+ withTableBorder=False, withColumnBorders=False, verticalSpacing="sm"` | Temiz, modern tablo gövdesi |
| 10 | **Kart padding** | `"20px"` | `"24px"` | Genel kural |

---

### Dikkat Noktaları

**`fontVariantNumeric: "tabular-nums"`:**
- CSS'te `font-variant-numeric: tabular-nums` — tüm rakamlar aynı genişlikte.
- `1,234` ve `0,987` dikey olarak mükemmel hizalı.
- React/Dash stil dictinde camelCase: `"fontVariantNumeric": "tabular-nums"`.

**`_dc_link()` içindeki `dmc.Text` sarması:**
- `dcc.Link` bir anchor `<a>` tag'i — doğrudan `dmc.Text` prop'larını almaz.
- Çözüm: `dcc.Link(dmc.Text(...), href=...)` — `dmc.Text` child olarak sarılır.
- `style={"textDecoration":"none"}` — `dcc.Link`'e uygula, `dmc.Text`'e değil.

**`_pct_badge()` ve `_num_cell()` konumu:**
- İkisi de `build_overview()` dışında, modül seviyesinde tanımlanacak.
- `dmc` ve `dcc` import'ları üstte zaten mevcut — ek import gerekmez.

**`striped=True` satır rengi:**
- Mantine'nin `striped` özelliği her çift satıra çok hafif gri arka plan uygular.
- `highlightOnHover=True` ile hover'da satır vurgulanır.
- `withTableBorder=False` — dış kenarlık yok, nexus-card zaten sınırlıyor.

---

### ✅ Faz 3 Kabul Kriterleri

**Bağlantılar:**
- [ ] DC isimleri (`AZ11`, `DC11` vb.) mor, **altı çizgisiz**, kalın (`fw=700`).
- [ ] DC'ye tıklandığında `/datacenter/{id}` sayfasına yönlendirme çalışıyor.

**Tipografi:**
- [ ] TH başlıklar uppercase, soluk gri (`#A3AED0`), küçük (`0.72rem`), letter-spaced.
- [ ] TH'nin altında ince `#f1f3f5` çizgisi var.
- [ ] Lokasyon sütunu dimmed/soluk — DC ismine göre daha geri planda.

**Sayısal hücreler:**
- [ ] Hosts, VMs, Platforms sütunları sağa hizalı.
- [ ] `1,234` formatı — binler ayırıcı görünüyor.
- [ ] `tabular-nums` — sütunlar dikey mükemmel hizalı.

**Sıfır susturma:**
- [ ] Değer `0` olan sayısal hücrelerde `—` (tire) görünüyor — `0` değil.
- [ ] Değer `0%` olan CPU/RAM hücrelerinde `—` görünüyor — rozet değil.
- [ ] Tire `c="dimmed"` soluk — dikkat çekmiyor.

**Rozet renkleri:**
- [ ] CPU/RAM `>= 80%` → 🔴 kırmızı badge.
- [ ] CPU/RAM `50-79%` → 🔵 mavi badge.
- [ ] CPU/RAM `< 50%` → 🟢 yeşil badge.

**Tablo estetiği:**
- [ ] Satırlar hover'da vurgulanıyor (`highlightOnHover`).
- [ ] Zebra deseni var (`striped`).
- [ ] Dikey ve yatay kenarlıklar yok (`withTableBorder=False, withColumnBorders=False`).
- [ ] `python app.py` — hatasız başlangıç.

---

### 📝 Faz 3 Değişiklik Özeti

```
src/pages/home.py

  YENİ FONKSİYONLAR (modül seviyesi, _ring_stat'ın altına):
    _pct_badge(value)
      if v >= 80  → red badge
      if v >= 50  → blue badge
      else        → teal badge
      if v == 0   → "—" dimmed text (sıfır susturma)

    _num_cell(value, suffix="")
      if v == 0   → "—" dimmed text (sıfır susturma)
      else        → f"{v:,}" tabular-nums, sağa hizalı

    _dc_link(name, dc_id)
      dcc.Link(dmc.Text(fw=700, c="#4318FF"), textDecoration="none")

  Satır 269-311 (DC Summary bloğu — TAMAMEN DEĞİŞTİR):
    html.H3 → dmc.Text(fw=700, size="lg")
    html.P  → dmc.Text(size="xs", c="dimmed")
    padding: "20px" → "24px"
    dmc.Table yeni prop'lar:
      withTableBorder=False
      withColumnBorders=False
      verticalSpacing="sm"
      horizontalSpacing="md"
    html.Th → uppercase, 0.72rem, letterSpacing, borderBottom
    html.Td DC link → _dc_link()
    html.Td lokasyon → dmc.Text(c="dimmed")
    html.Td sayılar → _num_cell() (sağa, tabular-nums, sıfır susturma)
    html.Td CPU/RAM → _pct_badge() (renk kodlu, sıfır susturma)

DEĞİŞMEYEN:
  - Tüm Faz 1 (platform_card, Platform Breakdown)
  - Tüm Faz 2 (dmc.RingProgress, charts.py fonksiyonları)
  - KPI strip (SimpleGrid cols=5)
  - Callback'lar (app.py)
  - Sidebar (sidebar.py)
  - assets/style.css
```

**Toplam:** 1 dosya (`home.py`) — 3 yeni modül fonksiyonu + Satır 269-311 güncelleme.
`charts.py` değişmez. `app.py` değişmez. `style.css` değişmez.

---
---

## 🌐 Task 4 — Ultra-Premium Hacimsel Görselleştirme ve Kokpit Tasarımı (Nihai)

**Tarih:** 2 Mart 2026, 02:26
**Kaynak:** CEO direktifi — devrimsel görsel mimari
**Hedef Dosyalar:** `src/components/charts.py` (2 YENİ fonksiyon) + `src/pages/home.py` (2 çağırma güncellemesi)
**Durum:** ⏳ Executor uygulaması bekleniyor

> ✅ Mevcut fonksiyonlara **dokunulmaz**. `create_energy_breakdown_chart` ve `create_grouped_bar_chart` silinmez.
> Sadece 2 yeni fonksiyon eklenir; home.py'deki ilgili 2 kart güncellenir.

---

### Madde 1 — Energy by Source: Semi-Circle Donut

#### Teknik Bağlam — Plotly'de Yarım Halka

Plotly `go.Pie`'da yarım halka (semi-circle) resmi olarak şu yöntemle yapılır:

1. Gerçek veri dilimlerine ek olarak **şeffaf bir dummy dilim** ekle. Bu dummy'nin değeri, diğer tüm dilimlerin toplamına eşit.
2. `rotation=180` ile dairenin düz kenarı altta olur.
3. Dummy dilimin rengi `"rgba(0,0,0,0)"` (tamamen saydam) — görünmez.
4. `direction="clockwise"` + `rotation=180` → gerçek dilimler üst yarıda, düz taban altta.

**Sonuç:** Klasik speedometer / gauge tarzı yarım halka. `hole=0.60` ile halka formu korunur. Merkez metnini `x=0.5, y=0.22` ile alt orta noktaya sabitliyoruz.

#### YENİ Fonksiyon — `charts.py`'nin SONUNA ekle (mevcut fonksiyonları bozma)

```python
def create_energy_semi_circle(labels, values, height=280):
    """
    Energy by Source — Yarım Halka (Semi-Circle Donut).
    Düz taban altta; toplam kW merkez alt noktada büyük tipografiyle.
    """
    try:
        total = sum(float(v) for v in values if v is not None)
    except (TypeError, ValueError):
        total = 0.0

    # Dummy dilim: diğer tüm dilimlerin toplamı kadar, tamamen şeffaf
    dummy_val = total if total > 0 else 1

    full_labels = list(labels) + [""]
    full_values = list(values) + [dummy_val]
    full_colors = ["#4318FF", "#05CD99", "#FFB547", "rgba(0,0,0,0)"]

    # Renk sayısını veri sayısına göre kırp
    color_slice = full_colors[: len(labels)] + ["rgba(0,0,0,0)"]

    fig = go.Figure(data=[go.Pie(
        labels=full_labels,
        values=full_values,
        hole=0.60,
        rotation=180,               # ← düz kenar altta
        direction="clockwise",
        sort=False,
        marker=dict(
            colors=color_slice,
            line=dict(color="rgba(0,0,0,0)", width=0),
        ),
        textinfo="none",
        hoverinfo="skip",           # dummy dilimi tooltip'ten gizle
    )])

    # Gerçek dilimler için özel hover
    fig.update_traces(
        customdata=full_labels,
        hovertemplate="<b>%{label}</b><br>%{value:,.0f} kW<extra></extra>",
        selector=dict(type="pie"),
    )

    # Merkez alt metin — düz tabanın hemen üstüne
    center_text = (
        f"<span style='font-size:26px;font-weight:900;color:#2B3674'>"
        f"{total:,.0f}"
        f"</span>"
        f"<br>"
        f"<span style='font-size:11px;color:#A3AED0'>kW Total</span>"
    )

    fig.update_layout(
        annotations=[dict(
            text=center_text,
            x=0.5,
            y=0.10,                 # ← düz tabanın hemen üstü (rotation=180 ile)
            xanchor="center",
            yanchor="middle",
            showarrow=False,
            align="center",
        )],
        showlegend=True,
        legend=dict(
            orientation="h",        # ← Yatay, alta
            yanchor="top",
            y=-0.04,
            xanchor="center",
            x=0.5,
            font=dict(family="DM Sans", size=12, color="#2B3674"),
            bgcolor="rgba(0,0,0,0)",
            itemsizing="constant",
            # Dummy "" girdisini legend'dan gizle:
            traceorder="normal",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=50),   # ← alta legend için boşluk
        height=height,
        font=dict(family="DM Sans", color="#A3AED0"),
    )

    # Dummy dilimi legend'dan gizle
    # Plotly'de go.Pie trace'inde showlegend per-slice kontrolü yok.
    # Geçici çözüm: dummy etiketini boş ("") bırakıyoruz → legend'da görünmez.

    return fig
```

#### `home.py` — Energy by Source Kartını Güncelle

Mevcut Energy kartındaki `create_energy_breakdown_chart` çağrısını **sadece bu fonksiyon adını değiştirerek** güncelle:

```python
# MEVCUT:
dcc.Graph(
    figure=create_energy_breakdown_chart(eb_labels, eb_values, height=260),
    config={"displayModeBar": False},
    style={"height": "260px"},
),

# YENİ — sadece fonksiyon adı değişiyor:
dcc.Graph(
    figure=create_energy_semi_circle(eb_labels, eb_values, height=280),
    config={"displayModeBar": False},
    style={"height": "280px"},
),
```

#### `home.py` — Import Satırını Güncelle

```python
# MEVCUT:
from src.components.charts import (
    create_energy_breakdown_chart,
    create_grouped_bar_chart,
)

# YENİ (ikisi de kalsın + yenilerini ekle):
from src.components.charts import (
    create_energy_breakdown_chart,      # ← Diğer sayfalarda kullanılıyor olabilir — bırak
    create_grouped_bar_chart,           # ← Bırak
    create_energy_semi_circle,          # ← YENİ
    create_dc_treemap,                  # ← YENİ
)
```

| Özellik | Eski (`create_energy_breakdown_chart`) | Yeni (`create_energy_semi_circle`) |
|---------|---------------------------------------|-------------------------------------|
| Şekil | Tam daire halka | **Yarım daire (semi-circle)** |
| Merkez metin | `x=0.5, y=0.5` (ortada) | **`x=0.5, y=0.10`** (düz taban üstü) |
| Legend konum | Sağ dikey | **Alt yatay** (`orientation="h"`) |
| `rotation` | *(yok)* | **`180`** (düz kenar altta) |
| Dummy dilim | *(yok)* | **Şeffaf, toplam kadar** (yarım daire için zorunlu) |

---

### Madde 2 — DC Comparison: Treemap Görselleştirme

#### Teknik Bağlam — Plotly `go.Treemap`

`go.Treemap` — kutu büyüklüğü değere (`values`) göre otomatik ölçeklenir.

```
Temel örnek:
  labels = ["DC1", "DC2", "DC13"]
  values = [100,   50,    800   ]
  parents = ["", "", ""]          ← tüm root'ta (düz hiyerarşi)
```

Renk gradyanı için `marker.colors` + `colorscale` kullanılabilir veya her kutuya manuel renk atanabilir.

**Mor → Turkuaz gradyan** için Plotly'nin built-in `colorscale` kullanılacak — değer ne kadar büyükse o kadar derin mor.

#### YENİ Fonksiyon — `charts.py`'nin SONUNA ekle

```python
def create_dc_treemap(dc_names, dc_vms, height=320):
    """
    DC Comparison — Treemap.
    Kutu büyüklüğü VM sayısını temsil eder.
    Büyük DC (yüksek VM) geniş kutu, küçük DC dar kutu.
    Renk: VM sayısına göre mor → turkuaz gradyan.
    """
    # Sıfır veya None değerleri 1'e tamamla — treemap 0 değeri işleyemez
    safe_vms = [max(1, int(v or 0)) for v in dc_vms]

    fig = go.Figure(go.Treemap(
        labels=dc_names,
        values=safe_vms,
        parents=[""] * len(dc_names),      # ← Düz (flat) hiyerarşi — root'ta
        branchvalues="total",
        marker=dict(
            colorscale=[
                [0.0,  "#7B2FFF"],          # Düşük VM → Derin mor
                [0.35, "#4318FF"],          # Orta → Bulutistan moru
                [0.70, "#2196F3"],          # Yüksek → Mavi
                [1.0,  "#05CD99"],          # En yüksek VM → Turkuaz
            ],
            colors=safe_vms,                # ← Renk değeri VM sayısı
            showscale=False,                # ← Renk ölçeği göstergesi gizle
            line=dict(
                color="rgba(255,255,255,0.15)",
                width=2,
            ),
            pad=dict(t=4, l=4, r=4, b=4),
        ),
        textfont=dict(
            family="DM Sans",
            color="rgba(255,255,255,0.92)",
        ),
        textposition="middle center",
        texttemplate=(
            "<b>%{label}</b><br>"
            "<span style='font-size:11px;opacity:0.85'>%{value:,} VMs</span>"
        ),
        hovertemplate=(
            "<b>%{label}</b><br>"
            "VM Count: %{value:,}<br>"
            "%{percentRoot:.1%} of total"
            "<extra></extra>"
        ),
        tiling=dict(
            packing="squarify",             # ← Kare benzeri kutular
        ),
    ))

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),   # ← Tamamen kenarsız
        height=height,
        font=dict(family="DM Sans", color="rgba(255,255,255,0.9)"),
    )

    return fig
```

| Özellik | Bar Chart (eski) | Treemap (yeni) |
|---------|-----------------|----------------|
| Görsel | Yatay çubuklar | **Kutu alanı haritası** |
| Büyüklük bilgisi | Y ekseni pozisyonu | **Kutu alanı (VM sayısı)** |
| DC13 büyüklüğü | Uzun çubuk | **Devasa blok** — baskınlık anında fark edilir |
| Eksenler | X + Y ekseni | **Hiç eksen yok** — sadece kutular |
| Grid | *(mevcut)* | **Yok** |
| Renk | Düz `#4318FF` / `#05CD99` | **Mor→Turkuaz gradyan** (VM yoğunluğuna göre) |
| Hover | `y unified` | **Özel tooltip** — DC adı + VM sayısı + oran |
| Etiket | Ayrı legend | **Kutu içinde** — DC adı + VM sayısı |

#### `home.py` — DC Comparison Kartını Güncelle

```python
# MEVCUT bloc (Satır 251-266 civarı):
html.Div(
    [
        dmc.Text("DC Comparison", fw=700, size="lg", c="#2B3674", style={"marginBottom": "4px"}),
        dmc.Text("Hosts & VMs per Data Center", size="xs", c="dimmed", style={"marginBottom": "12px"}),
        dcc.Graph(
            figure=create_grouped_bar_chart(
                dc_names,
                {"Hosts": dc_hosts, "VMs": dc_vms},
                title="",
                height=380,
            ),
            config={"displayModeBar": False},
            style={"height": "380px"},
        ),
    ],
    className="nexus-card",
    style={"padding": "24px"},
),

# YENİ — Treemap ile değiştir:
html.Div(
    [
        dmc.Text("DC Landscape", fw=700, size="lg", c="#2B3674", style={"marginBottom": "4px"}),
        dmc.Text(
            "VM distribution across Data Centers — area = VM count",
            size="xs",
            c="dimmed",
            style={"marginBottom": "12px"},
        ),
        dcc.Graph(
            figure=create_dc_treemap(dc_names, dc_vms, height=320),
            config={"displayModeBar": False},
            style={"height": "320px", "borderRadius": "12px", "overflow": "hidden"},
        ),
    ],
    className="nexus-card",
    style={"padding": "24px"},
),
```

> **Not:** Kart başlığı "DC Comparison" → "**DC Landscape**" olarak değişti. Bu CEO'nun treemap konseptini yansıtır — karşılaştırmadan ziyade yayılım / hacim haritası.

---

### Teknik Dikkat Noktaları

#### Semi-Circle için Dummy Dilim
```
Neden dummy gerekli?
go.Pie halka tam daire çizer.
Yarım halka için: toplam_değer kadar şeffaf dummy ekle.
Plotly bunu tam daire üzerinde eşit böler:
  → Gerçek dilimler üst yarıda (rotation=180 ile)
  → Dummy dilim alt yarıda (görünmez)
```

Eğer 3 kaynak var (IBM Power, vCenter, Rack):
```python
full_values = [ibm_val, vcenter_val, rack_val,   total]  # 4. eleman dummy
full_colors = ["#4318FF", "#05CD99", "#FFB547",  "rgba(0,0,0,0)"]
```

#### Treemap `parents=["","",""]`
```
Flat (düz) hiyerarşi için tüm parent'lar boş string.
Hiyerarşik treemap için: parents=["Root","Root","Root"]
Biz flat istiyoruz — DC'ler aynı seviyede yan yana.
```

#### Treemap `branchvalues="total"`
```
"total" → her kutu'nun alanı doğrudan values[i]'ye eşit.
"remainder" → parent'tan kalan pay hesaplanır.
Flat treemap'te her ikisi de aynı sonucu verir.
```

#### `safe_vms` neden gerekli?
```python
safe_vms = [max(1, int(v or 0)) for v in dc_vms]
```
Plotly Treemap `value=0` olan kutular için hata verir veya gizler.
`max(1, ...)` → en az 1 VM değeri garantisi.

---

### ✅ Task 4 Kabul Kriterleri

**Energy Semi-Circle:**
- [ ] `python app.py` — hatasız başlangıç.
- [ ] Grafik yarım daire formunda — tam daire değil.
- [ ] Düz kenar (D şeklinin düz tarafı) **altta**.
- [ ] Toplam kW değeri düz kenarın hemen üstünde, büyük ve bold.
- [ ] `kW Total` alt yazısı soluk gri, küçük.
- [ ] Legend altta, yatay, ortalanmış.
- [ ] Dummy dilim legendda görünmüyor (boş etiket).

**DC Treemap:**
- [ ] `python app.py` — hatasız başlangıç.
- [ ] DC'ler kutu formatında yan yana — çubuk yok.
- [ ] En yüksek VM sayılı DC (DC13 vb.) en **büyük** kutuyu kaplıyor.
- [ ] Kutular mor → turkuaz renk gradyanı taşıyor (VM sayısına göre).
- [ ] Kutu içinde DC adı ve VM sayısı yazıyor.
- [ ] Hover'da DC adı + VM sayısı + toplam yüzde görünüyor.
- [ ] X/Y ekseni, grid, çizgi yok — tamamen temiz.
- [ ] Kart başlığı "DC Landscape" .
- [ ] Kutu köşeleri kart ile uyumlu (`borderRadius: "12px"`).

---

### 📝 Task 4 Değişiklik Özeti

```
src/components/charts.py — SONUNA 2 YENİ FONKSİYON EKLE:

  create_energy_semi_circle(labels, values, height=280):
    go.Pie + hole=0.60 + rotation=180
    Dummy dilim (şeffaf, toplam kadar)
    center annotation: x=0.5, y=0.10 (alt merkez)
    legend: orientation="h", y=-0.04 (altta yatay)

  create_dc_treemap(dc_names, dc_vms, height=320):
    go.Treemap + parents=["","","",...]
    marker.colorscale: "#7B2FFF" → "#4318FF" → "#2196F3" → "#05CD99"
    texttemplate: "<b>DC adı</b><br>VM sayısı"
    margin: l=0, r=0, t=0, b=0 (tamamen kenarsız)

src/pages/home.py — 2 GÜNCELLEME:

  1) Import satırı:
     + create_energy_semi_circle
     + create_dc_treemap

  2) Energy by Source kartı:
     create_energy_breakdown_chart(... height=260) →
     create_energy_semi_circle(... height=280)
     style.height: "260px" → "280px"

  3) DC Comparison kartı:
     create_grouped_bar_chart(...) →
     create_dc_treemap(dc_names, dc_vms, height=320)
     Kart başlığı: "DC Comparison" → "DC Landscape"
     Alt başlık: "area = VM count"
     style.height: "380px" → "320px"

DEĞİŞMEYEN:
  - create_energy_breakdown_chart() — silinmez
  - create_grouped_bar_chart() — silinmez
  - Tüm Faz 1, 2, 3 güncellemeleri
  - KPI strip, Sidebar, Callback'lar
  - assets/style.css
```

**Toplam:** 1 dosya (`charts.py`) 2 yeni fonksiyon + `home.py` 1 import + 2 kart güncellemesi.

---
---

## ⚡ Task 5 — The Elite Energy Component (Tesla-Style)

**Tarih:** 2 Mart 2026, 02:43
**Kaynak:** CEO onayı — fütüristik elitizm
**Hedef:** `create_energy_semi_circle()` → **`create_energy_elite()`** olarak yeniden yaz
**Dosyalar:** `charts.py` (1 yeni fonksiyon) + `home.py` (1 güncelleme) + optional Dash callback

> ✅ Önceki `create_energy_semi_circle()` geçersiz. `create_energy_elite()` onun yerine geçer.
> Task 4'teki diğer işler (DC Treemap) değişmez.

---

### Teknik Mimari Özeti

```
create_energy_elite():
  go.Pie
    ├── hole = 0.62          (yeterince geniş merkez alan)
    ├── rotation = 180       (düz kenar altta)
    ├── direction = "clockwise"
    ├── dummy slice          (toplam kadar şeffaf — semi-circle için zorunlu)
    ├── marker.line          (beyaz segmented gap — parçalı donanım hissi)
    └── customdata           (hover için ek veri)

  update_layout:
    ├── annotation y=0.12    (42px rakam — düz taban üstü)
    ├── annotation y=0.02    (12px "kW TOTAL" — rakamın altı)
    └── legend               (alta yatay, emoji pill ikonları)

  dcc.Graph wrapper:
    └── style.filter: "drop-shadow(0 0 10px rgba(67,24,255,0.4))"
        (Neon Glow — Plotly içine değil, HTML container'a)

  Opsiyonel Dash Callback:
    └── hoverData → selectedpoints → opacity dim/glow efekti
```

---

### YENİ Fonksiyon — `charts.py` SONUNA ekle

```python
# Elite icon map — enerji kaynaklarına göre sembol
_ENERGY_ICONS = {
    "IBM Power":   "⚡",
    "vCenter":     "☁️",
    "Rack":        "🏗️",
    "Solar":       "☀️",
    "Wind":        "💨",
}

def create_energy_elite(labels, values, height=300):
    """
    Elite Energy Gauge — Tesla tarzı fütüristik yarım halka.

    Özellikler:
    - Semi-circle (rotation=180, dummy slice)
    - 42px ultra-bold merkez rakam
    - Segmented beyaz çizgiler (parçalı donanım hissi)
    - Emoji pill legend
    - customdata ile hover altyapısı
    """
    try:
        total = sum(float(v) for v in values if v is not None)
    except (TypeError, ValueError):
        total = 0.0

    dummy_val = total if total > 0 else 1.0

    # Legend için emoji prefix
    icon_labels = [
        f"{_ENERGY_ICONS.get(lbl, '●')} {lbl}"
        for lbl in labels
    ]
    full_labels  = icon_labels + [""]       # "" → dummy (legend'da görünmez)
    full_values  = list(values) + [dummy_val]

    # Renk paleti — son eleman dummy için şeffaf
    palette = ["#4318FF", "#05CD99", "#FFB547", "#A78BFA"]
    color_slice = palette[: len(labels)] + ["rgba(0,0,0,0)"]

    # customdata — dilim yüzdesi ve kW değeri (hover için)
    total_safe = total if total > 0 else 1
    pcts       = [round(100 * float(v) / total_safe, 1) for v in values] + [0]

    fig = go.Figure(data=[go.Pie(
        labels=full_labels,
        values=full_values,
        hole=0.62,
        rotation=180,
        direction="clockwise",
        sort=False,
        marker=dict(
            colors=color_slice,
            line=dict(
                color="rgba(255,255,255,1)",  # ← Beyaz segmented gap
                width=3,                      # ← 3px boşluk → parçalı donanım hissi
            ),
        ),
        textinfo="none",
        # Dummy dilimi hover'dan gizle (label boş → atlıyor)
        hovertemplate=(
            "<b>%{label}</b><br>"
            "%{value:,.0f} kW<br>"
            "%{customdata:.1f}%"
            "<extra></extra>"
        ),
        customdata=pcts,
        pull=[0] * (len(labels) + 1),        # ← Hover callback için başlangıç
    )])

    # ── Annotation 1: Büyük rakam (42px, ultra-bold, lacivert) ──────────
    # semi-circle'da y=0.12 → düz tabanın hemen üstü
    number_text = (
        f"<span style='"
        f"font-size:42px;"
        f"font-weight:900;"
        f"color:#1a1b41;"
        f"line-height:1;"
        f"font-family:DM Sans,sans-serif;"
        f"'>{total:,.0f}</span>"
    )

    # ── Annotation 2: "kW TOTAL" label (12px, gri) ──────────────────────
    unit_text = (
        "<span style='"
        "font-size:12px;"
        "font-weight:600;"
        "color:#A3AED0;"
        "letter-spacing:0.12em;"
        "text-transform:uppercase;"
        "font-family:DM Sans,sans-serif;"
        "'>kW TOTAL</span>"
    )

    fig.update_layout(
        annotations=[
            dict(
                text=number_text,
                x=0.5,
                y=0.14,             # ← rakam: düz taban üstü
                xanchor="center",
                yanchor="middle",
                showarrow=False,
                align="center",
            ),
            dict(
                text=unit_text,
                x=0.5,
                y=0.02,             # ← "kW TOTAL" etiketi: rakamın altı
                xanchor="center",
                yanchor="middle",
                showarrow=False,
                align="center",
            ),
        ],
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.06,
            xanchor="center",
            x=0.5,
            font=dict(
                family="DM Sans",
                size=12,
                color="#2B3674",
            ),
            bgcolor="rgba(0,0,0,0)",
            itemsizing="constant",
            traceorder="normal",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=60),
        height=height,
        font=dict(family="DM Sans", color="#A3AED0"),
    )

    return fig
```

---

### `home.py` — Energy by Source Kartı Güncelle

#### Import satırı:

```python
# MEVCUT:
from src.components.charts import (
    create_energy_breakdown_chart,
    create_grouped_bar_chart,
    create_energy_semi_circle,
    create_dc_treemap,
)

# YENİ — create_energy_elite ekle, create_energy_semi_circle çıkmaz (zarar vermez):
from src.components.charts import (
    create_energy_breakdown_chart,     # bırak
    create_grouped_bar_chart,          # bırak
    create_energy_semi_circle,         # bırak (zarar vermez)
    create_dc_treemap,                 # bırak
    create_energy_elite,               # ← YENİ
)
```

#### Energy Kartı dcc.Graph Güncellemesi:

```python
# MEVCUT (Task 4'ten):
dcc.Graph(
    figure=create_energy_semi_circle(eb_labels, eb_values, height=280),
    config={"displayModeBar": False},
    style={"height": "280px"},
),

# YENİ — 3 değişiklik:
#   1. Fonksiyon: create_energy_elite
#   2. id="energy-elite-graph" eklendi (hover callback için)
#   3. wrapper div: filter: drop-shadow (neon glow)
html.Div(
    dcc.Graph(
        id="energy-elite-graph",            # ← Callback için zorunlu ID
        figure=create_energy_elite(eb_labels, eb_values, height=300),
        config={"displayModeBar": False},
        style={"height": "300px"},
    ),
    style={
        "filter": "drop-shadow(0 0 10px rgba(67, 24, 255, 0.35))",
        "WebkitFilter": "drop-shadow(0 0 10px rgba(67, 24, 255, 0.35))",
        "borderRadius": "50%",              # ← Glow'u daire şekline uydurur
        "overflow": "hidden",
    },
),
```

> **Neden `filter` Plotly içine değil div'e?**
> Plotly grafiğin kendi DOM'unu kontrol eder — inline style veya CSS ile Plotly canvas'ına uygulanan `filter` çalışmaz.
> HTML wrapper div'e uygulanan `filter` tüm canvas'ı (svg dahil) etkiler — bu standart çözümdür.

---

### Opsiyonel Dash Callback — Hover Dim/Glow Efekti

Bu callback olmadan grafik statik çalışır (neon glow + segmented + typography tamam).
Callback eklenerek **hover'da ilgili dilim parlar, diğerleri solar**.

#### `app.py` veya `pages/home.py` → Callback Ekle

```python
from dash import Input, Output, State, callback
import plotly.graph_objects as go

@callback(
    Output("energy-elite-graph", "figure"),
    Input("energy-elite-graph", "hoverData"),
    State("energy-elite-graph", "figure"),
    prevent_initial_call=True,
)
def energy_hover_glow(hover_data, current_figure):
    """
    Hover'da:
      - Hoverlanan dilim: opacity 1.0, pull 0.04 (dışa çıkma)
      - Diğer dilimler: opacity 0.45 (soluklaşma)
    Hover dışında: tüm dilimler opacity 1.0, pull 0.
    """
    import copy
    fig = go.Figure(current_figure)
    n_real = len(fig.data[0].labels) - 1   # Son eleman dummy

    if hover_data is None:
        # Reset: tüm dilimler tam parlak
        fig.update_traces(
            pull=[0] * len(fig.data[0].labels),
            marker_opacity=1.0,
        )
        return fig

    # Hovered dilim indeksi
    pt = hover_data.get("points", [{}])[0]
    hovered_idx = pt.get("pointNumber", None)

    if hovered_idx is None or hovered_idx >= n_real:
        return fig

    # pull listesi: hoverlanan dilim dışa çıksın
    pull_vals = [0.0] * len(fig.data[0].labels)
    pull_vals[hovered_idx] = 0.04

    # Renk opaklığı: hoverlanan tam parlak, diğerleri soluk
    original_colors = list(fig.data[0].marker.colors)
    new_colors = []
    for i, c in enumerate(original_colors):
        if i == hovered_idx:
            new_colors.append(c)                   # Orijinal renk — tam parlak
        elif i == n_real:
            new_colors.append("rgba(0,0,0,0)")     # Dummy — hep şeffaf
        else:
            # Mevcut rengi soluklaştır — opacity değiştir
            # Hex renk ise rgba'ya çevir
            if c.startswith("#") and len(c) == 7:
                r = int(c[1:3], 16)
                g = int(c[3:5], 16)
                b = int(c[5:7], 16)
                new_colors.append(f"rgba({r},{g},{b},0.30)")
            else:
                new_colors.append(c)

    fig.update_traces(
        pull=pull_vals,
        marker=dict(
            colors=new_colors,
            line=dict(color="rgba(255,255,255,1)", width=3),
        ),
    )
    return fig
```

| Callback Özelliği | Değer | Etki |
|-------------------|-------|------|
| `pull[hovered] = 0.04` | 4% dışa çıkma | Hovered dilim hafifçe büyür |
| Hovered renk | Orijinal | Tam parlak |
| Diğer dilimler | `rgba(R,G,B,0.30)` | %70 soluklaşma |
| Dummy (`n_real`) | `rgba(0,0,0,0)` | Her zaman şeffaf |
| Reset | `hoverData=None` | Tüm dilimler normale döner |

> ⚠️ **Bu callback `app.py`'ye eklenirse:** `energy-elite-graph` ID'si sayfa routing'i aktif olan projelerde çakışabilir. ID'ye `id="energy-elite-graph"` dışında bir prefix ekleyebilirsiniz: `id="home-energy-elite-graph"`.

---

### Görsel Bileşen Mimarisi

```
html.Div (wrapper)
  └── filter: drop-shadow(0 0 10px rgba(67,24,255,0.35))  ← Neon Glow
      └── dcc.Graph(id="energy-elite-graph")
          └── go.Pie(
                hole=0.62,
                rotation=180,              ← Yarım halka
                marker.line.width=3        ← Segmented gaps
                marker.line.color=white
              )
          └── annotations[0]:
                y=0.14, font-size:42px, font-weight:900   ← Devasa rakam
                color:#1a1b41
          └── annotations[1]:
                y=0.02, font-size:12px                     ← "kW TOTAL"
                letter-spacing:0.12em, UPPERCASE
          └── legend(orientation="h", emoji prefix)        ← ⚡ IBM Power ☁️ vCenter
```

---

### ✅ Task 5 Kabul Kriterleri

**Semi-Circle & Neon Glow:**
- [ ] `python app.py` — hatasız başlangıç.
- [ ] Grafik **yarım daire** — düz kenar altta. Tam daire değil.
- [ ] Grafik çevresinde hafif **mor parlama** (drop-shadow) var.
- [ ] Dilimler arasında **beyaz segmented boşluklar** var — bitişik değil.

**Typography:**
- [ ] Orta rakam (`total kW`) **42px, ultra-bold, `#1a1b41` lacivert**.
- [ ] Rakam düz kenarın üstünde, tam merkeze oturmuş — kaymıyor.
- [ ] "kW TOTAL" etiketi **12px, büyük harf, letter-spaced, gri**.
- [ ] "kW TOTAL" rakamın hemen altında — milimetrik hizalı.

**Legend:**
- [ ] Legend **alta yatay**.
- [ ] Her etiket önünde emoji ikon var: `⚡ IBM Power`, `☁️ vCenter`.
- [ ] Dummy dilim legendda **görünmüyor**.

**Hover (Opsiyonel Callback):**
- [ ] Dilime hover'da o dilim hafifçe **dışa çıkıyor** (`pull=0.04`).
- [ ] Diğer dilimler **soluklaşıyor** (`rgba %30 opacity`).
- [ ] Hover ayrılınca tüm dilimler **normale dönüyor**.

---

### 📝 Task 5 Değişiklik Özeti

```
src/components/charts.py — YENİ FONKSİYON (sonuna ekle):
  _ENERGY_ICONS dict (modül seviyesi, global)
  create_energy_elite(labels, values, height=300):
    go.Pie:
      hole=0.62 | rotation=180 | direction="clockwise"
      dummy slice (şeffaf, total kadar)
      marker.line: color=white, width=3 (segmented gaps)
      customdata=pcts (hover için yüzde)
    annotations[0]: y=0.14, 42px bold #1a1b41 (rakam)
    annotations[1]: y=0.02, 12px gray UPPERCASE (etiket)
    legend: h, emoji prefix labels

src/pages/home.py:
  Import: + create_energy_elite

  Energy kartı dcc.Graph →
    html.Div(style={filter: drop-shadow...})  ← wrapper (neon glow)
      └── dcc.Graph(
            id="energy-elite-graph",          ← callback ID
            figure=create_energy_elite(...)
            height: 280px → 300px
          )

  Opsiyonel app.py:
    @callback energy_hover_glow()
    pull + opacity dim/glow sistemi

DEĞİŞMEYEN:
  - create_energy_semi_circle() — korunur
  - DC Treemap
  - Tüm Faz 1, 2, 3
  - style.css
  - Callback'lar (hover callback opsiyonel ekleme)
```

**Toplam:** 1 dosya (`charts.py`) 1 yeni fonksiyon + `home.py` 1 import + Energy kart wrapper güncelleme
+ Opsiyonel: `app.py` hover callback.

---
---

## 💫 Task 6 — Final Elite Polishing: Full Donut & Zero Overlap Typography

**Tarih:** 2 Mart 2026, 02:55
**Kaynak:** CEO direktifi — semi-circle fiyaskosu kökten temizleniyor
**Hedef:** `create_energy_elite()` → **`create_energy_elite_v2()`** (Full Donut, milimetrik tipografi)
**Dosyalar:** `charts.py` (1 yeni fonksiyon) + `home.py` (1 satır değişim)

> ✅ Önceki `create_energy_elite()` silinmez — `v2` yeni eklenir, home.py çağrısı güncellenir.
> Task 4 (DC Treemap) ve diğer herşey **değişmez**.

---

### Mevcut Sorun Analizi

```
Task 5 çıktısı — 2 hata:
  1. Semi-circle: dummy dilim + rotation=180 → metin konumlandırması
     kırıldı. y=0.14 düz taban üstü için hesaplandı ama
     full ekranda başka bir noktaya oturdu.

  2. Çift annotation (y=0.14 + y=0.02) üst üste geliyor.
     Plotly annotation koordinatları normalize (0-1) — semi-circle
     kırpılmış görsel alanda bu koordinatlar yanlış hizalanıyor.

Çözüm:
  Full Donut → klasik tam daire → y koordinatları güvenilir.
  y=0.55 (üst) + y=0.45 (alt) → her zaman ayrışık, asla üst üste gelmez.
```

---

### YENİ Fonksiyon — `charts.py` SONUNA ekle

```python
def create_energy_elite_v2(labels, values, height=300):
    """
    Elite Energy Gauge v2 — Full Donut, Zero-Overlap Typography.

    Task 6 değişiklikleri:
    - Semi-circle (dummy + rotation) KALDIRILDI → Tam Donut
    - Annotation: y=0.55 rakam / y=0.45 etiket → asla üst üste gelmiyor
    - Neon glow: wrapper div'de (bu fonksiyon değil, home.py'de)
    - Segmented gaps: marker.line korunuyor
    - Emoji legend: korunuyor
    """
    try:
        total = sum(float(v) for v in values if v is not None)
    except (TypeError, ValueError):
        total = 0.0

    # Emoji prefix legend
    icon_labels = [
        f"{_ENERGY_ICONS.get(lbl, '●')} {lbl}"
        for lbl in labels
    ]

    # Renk paleti
    palette = ["#4318FF", "#05CD99", "#FFB547", "#A78BFA"]
    color_slice = palette[: len(labels)]

    # customdata — hover için yüzde
    total_safe = total if total > 0 else 1
    pcts = [round(100 * float(v) / total_safe, 1) for v in values]

    fig = go.Figure(data=[go.Pie(
        labels=icon_labels,
        values=list(values),
        hole=0.65,                          # ← Geniş merkez alan — annotation için
        sort=False,
        marker=dict(
            colors=color_slice,
            line=dict(
                color="rgba(255,255,255,1)",# ← Segmented beyaz gap — KORUNUYOR
                width=3,
            ),
        ),
        textinfo="none",
        hovertemplate=(
            "<b>%{label}</b><br>"
            "%{value:,.0f} kW<br>"
            "%{customdata:.1f}%"
            "<extra></extra>"
        ),
        customdata=pcts,
        direction="clockwise",
        # rotation=180 YOK — full donut, varsayılan başlangıç
    )])

    # ── Annotation 1: Büyük rakam (42px, ultra-bold, lacivert) ──────
    # y=0.55 → tam ortanın biraz üstü (full donut'ta güvenilir)
    number_text = (
        f"<span style='"
        f"font-size:42px;"
        f"font-weight:900;"
        f"color:#1a1b41;"
        f"line-height:1;"
        f"font-family:DM Sans,sans-serif;"
        f"'>{total:,.0f}</span>"
    )

    # ── Annotation 2: "kW TOTAL" label (12px, letter-spaced, gri) ───
    # y=0.45 → tam ortanın biraz altı — rakamdan 10 birim aşağı
    unit_text = (
        "<span style='"
        "font-size:12px;"
        "font-weight:600;"
        "color:#A3AED0;"
        "letter-spacing:0.12em;"
        "text-transform:uppercase;"
        "font-family:DM Sans,sans-serif;"
        "'>kW TOTAL</span>"
    )

    fig.update_layout(
        annotations=[
            dict(
                text=number_text,
                x=0.5,
                y=0.55,             # ← Milimetrik: rakam üstte
                xanchor="center",
                yanchor="middle",
                showarrow=False,
                align="center",
            ),
            dict(
                text=unit_text,
                x=0.5,
                y=0.45,             # ← Milimetrik: etiket altta — ASLA üst üste gelmiyor
                xanchor="center",
                yanchor="middle",
                showarrow=False,
                align="center",
            ),
        ],
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.06,
            xanchor="center",
            x=0.5,
            font=dict(family="DM Sans", size=12, color="#2B3674"),
            bgcolor="rgba(0,0,0,0)",
            itemsizing="constant",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=16, b=60),
        height=height,
        font=dict(family="DM Sans", color="#A3AED0"),
    )

    return fig
```

---

### Annotation Koordinat Mantığı — Neden `y=0.55` ve `y=0.45`?

```
Plotly annotation koordinatları: 0.0 (alt) → 1.0 (üst)
Tam daire donut merkezi: x=0.5, y=0.5

Metin bloğu yüksekliği tahmini:
  42px rakam ≈ normalize 0.08 birim
  12px etiket ≈ normalize 0.05 birim
  Boşluk       ≈ 0.02 birim
  Toplam       ≈ 0.15 birim

Bölüm:
  Rakam merkezi:  y = 0.50 + 0.05 = 0.55  (ortanın 5 birim üstü)
  Etiket merkezi: y = 0.50 - 0.05 = 0.45  (ortanın 5 birim altı)

Sonuç: 0.10 birim (10%) ayrışma → asla çakışmaz.

NOT: Semi-circle (rotation=180) bu koordinatları bozuyordu çünkü
görsel alan yarıya kısalır ama normalize sistem değişmez.
Full donut'ta bu sorun yoktur.
```

---

### `home.py` — Tek Satır Değişim

Sadece fonksiyon adını değiştir. Wrapper div, ID, height — **hiçbiri değişmez**:

```python
# MEVCUT (Task 5'ten):
html.Div(
    dcc.Graph(
        id="energy-elite-graph",
        figure=create_energy_elite(eb_labels, eb_values, height=300),   # ← bu değişiyor
        config={"displayModeBar": False},
        style={"height": "300px"},
    ),
    style={
        "filter": "drop-shadow(0 0 10px rgba(67, 24, 255, 0.35))",
        "WebkitFilter": "drop-shadow(0 0 10px rgba(67, 24, 255, 0.35))",
        "borderRadius": "50%",
        "overflow": "hidden",
    },
),

# YENİ — sadece fonksiyon adı değişiyor:
html.Div(
    dcc.Graph(
        id="energy-elite-graph",
        figure=create_energy_elite_v2(eb_labels, eb_values, height=300),  # ← v2
        config={"displayModeBar": False},
        style={"height": "300px"},
    ),
    style={
        "filter": "drop-shadow(0 0 10px rgba(67, 24, 255, 0.35))",      # KORUNUYOR
        "WebkitFilter": "drop-shadow(0 0 10px rgba(67, 24, 255, 0.35))",# KORUNUYOR
        "borderRadius": "50%",                                           # KORUNUYOR
        "overflow": "hidden",                                            # KORUNUYOR
    },
),
```

**Import satırı — sadece `create_energy_elite_v2` ekle:**

```python
from src.components.charts import (
    create_energy_breakdown_chart,
    create_grouped_bar_chart,
    create_energy_semi_circle,
    create_dc_treemap,
    create_energy_elite,            # bırak (hover callback hâlâ referans alabilir)
    create_energy_elite_v2,         # ← YENİ
)
```

---

### Task 5 → Task 6 Fark Tablosu

| Özellik | Task 5 (`create_energy_elite`) | Task 6 (`create_energy_elite_v2`) |
|---------|-------------------------------|-----------------------------------|
| Grafik tipi | Semi-Circle (yarım daire) | **Full Donut (tam daire)** |
| `rotation` | `180` | **Yok — varsayılan** |
| `dummy_val` | Toplam kadar şeffaf dilim | **Yok — kaldırıldı** |
| `full_labels` | `icon_labels + [""]` | **Sadece `icon_labels`** |
| Annotation 1 | `y=0.14` | **`y=0.55`** |
| Annotation 2 | `y=0.02` | **`y=0.45`** |
| Üst üste gelme | ✗ Oluşuyor | ✅ **`0.55 - 0.45 = 0.10` → asla çakışmaz** |
| `marker.line` | `width=3, white` | **Korunuyor** |
| `hole` | `0.62` | **`0.65`** (daha fazla merkez alan) |
| Neon glow | wrapper div'de | **Korunuyor (wrapper değişmez)** |
| Emoji legend | Korunuyor | **Korunuyor** |
| `customdata` | `pcts` | **Korunuyor** |
| Hover callback | Opsiyonel | **Hâlâ geçerli (`v1` ile aynı data yapısı)** |

---

### ✅ Task 6 Kabul Kriterleri

**Full Donut:**
- [ ] `python app.py` — hatasız başlangıç.
- [ ] Grafik **tam daire donut** — yarım daire değil.
- [ ] `hole=0.65` — geniş merkez alan görünüyor.

**Zero Overlap Typography:**
- [ ] Merkez rakam (`total kW`) **42px, `#1a1b41` lacivert, ultra-bold**.
- [ ] Rakam ve etiket **ayrışık** — üst üste gelmiyor.
- [ ] "kW TOTAL" etiketi **12px, BÜYÜK HARF, letter-spaced, `#A3AED0` gri**.
- [ ] Rakam yaklaşık grafiğin üst orta noktasında (`y≈0.55`).
- [ ] Etiket yaklaşık grafiğin alt orta noktasında (`y≈0.45`).

**Korunanlar:**
- [ ] Dilimler arası **beyaz segmented boşluklar** (`line.width=3`) var.
- [ ] Grafik çevresinde **mor neon glow** (`drop-shadow`) var.
- [ ] Emoji legend **alta yatay**: `⚡ IBM Power`, `☁️ vCenter`.
- [ ] Hover tooltip kW ve % gösteriyor.
- [ ] `id="energy-elite-graph"` korunuyor — hover callback bozulmuyor.

---

### 📝 Task 6 Değişiklik Özeti

```
src/components/charts.py — YENİ FONKSİYON (sonuna ekle):
  create_energy_elite_v2(labels, values, height=300):
    KALDIRILDI: dummy_val, full_labels + [""], rotation=180
    DEĞİŞTİ: hole: 0.62 → 0.65
    DEĞİŞTİ: annotation[0].y: 0.14 → 0.55  (rakam, üst yarı merkez)
    DEĞİŞTİ: annotation[1].y: 0.02 → 0.45  (etiket, alt yarı merkez)
    KORUNDU: marker.line(white, width=3)
    KORUNDU: customdata=pcts
    KORUNDU: emoji icon_labels
    KORUNDU: legend(h, y=-0.06)
    KORUNDU: neon glow → wrapper div'de (bu fonksiyon değil)

src/pages/home.py:
  Import: + create_energy_elite_v2
  dcc.Graph figure:
    create_energy_elite(...) → create_energy_elite_v2(...)
  Wrapper div (filter, borderRadius): DOKUNULMAZ

DEĞİŞMEYEN:
  - create_energy_elite() — silinmez
  - DC Treemap
  - Tüm Faz 1, 2, 3 ve Task 4, 5
  - style.css | Sidebar | KPI strip
  - Hover callback (v2 ile uyumlu — aynı data yapısı)
```

**Toplam:** 1 dosya (`charts.py`) 1 yeni fonksiyon + `home.py` 1 import + 1 fonksiyon adı değişimi.
`wrapper div`, `id`, `style`, `height` — **hiçbiri değişmez.**
