# DC Sayfaları — Sprint 3: Kritik Görsel Fix Planı

> **Kural:** Hiçbir veri, API, backend değişmez. Yalnızca UI/chart/layout katmanı.

---

## SORUNLAR VE FOTOĞRAF–KOD EŞLEŞMESİ

| Fotoğraf | Sayfa | Sorun | Bölüm |
|---|---|---|---|
| 1 | Storage → Capacity Planning | Chart düz, premium his vermiyor | A |
| 2 | Physical Inventory → Devices by Role | Bar çok ince, label taşıyor, sıkışık | B |
| 3 | Physical Inventory → Manufacturer by Role | Çok fazla sütun, küçük barlar, okunaksız | C |
| 4 | Network → Bandwidth (95th Percentile) | Tek renk, flat, label yok | D |
| 5 | Backup → Tüm 3 tab | Orantısız layout, tam donut → yarım ay olmalı, Veeam/NetBackup'ta status panel yok | E |

---

## A. STORAGE — CAPACITY UTILIZATION TREND CHART

**Dosya:** `src/components/charts.py` — `create_capacity_area_chart()` (satır 371–398)

### Sorun Analizi

Mevcut chart'ta kullanım ~%100 olduğunda alan dolgusu tüm chart'ı kaplar → düz mavi dikdörtgen görünümü. Y-ekseni `showticklabels=False` olduğu için değer okumak imkânsız. Eşik çizgisi eklenmiş (dc_2.md M2) ama sayfa yenilenmeden görünmüyor.

### A1. Dinamik Y-Ekseni — Değer Etrafında Zoom

Eğer tüm y değerleri yüksekse (~90-100%), grafiğin tüm alanı dolu görünür. Y-eksenini veriye göre otomatik zoom yap:

```python
if y_pct:
    y_min = max(0.0, min(y_pct) - 8.0)
    y_max = min(105.0, max(y_pct) + 5.0)
else:
    y_min, y_max = 0.0, 105.0
```

`yaxis=dict(..., range=[y_min, y_max])` ile layout'a ekle.

### A2. Son Nokta Marker — "Şu Anki Değer" Vurgusu

Son veri noktasını büyük renkli bir nokta ile vurgula:

```python
if x and y_pct:
    fig.add_trace(
        go.Scatter(
            x=[x[-1]],
            y=[y_pct[-1]],
            mode="markers",
            marker=dict(
                size=10,
                color="#4318FF",
                line=dict(color="white", width=2),
                symbol="circle",
            ),
            hovertemplate=f"<b>Current:</b> {y_pct[-1]:.1f}%<extra></extra>",
            showlegend=False,
        )
    )
```

### A3. Günlük Dikey Ayraç Çizgileri

Her günün başlangıcına hafif dashed dikey çizgi ekle (timestamp gün sınırları):

```python
import datetime

if x:
    seen_days = set()
    for ts in x:
        try:
            day = ts[:10] if isinstance(ts, str) else ts.strftime("%Y-%m-%d")
            if day not in seen_days:
                seen_days.add(day)
                fig.add_vline(
                    x=ts,
                    line_dash="dot",
                    line_color="rgba(163, 174, 208, 0.25)",
                    line_width=1,
                )
        except Exception:
            pass
```

### A4. Y-Ekseni: Sağda Görünür, % Suffix

```python
yaxis=dict(
    showgrid=True,
    gridcolor="rgba(227, 234, 252, 0.4)",
    gridwidth=1,
    zeroline=False,
    showticklabels=True,
    ticksuffix="%",
    tickfont=dict(size=11, color="#A3AED0", family="DM Sans"),
    range=[y_min, y_max],
    side="right",
    nticks=5,
),
```

### A5. Annotation — Mevcut Kullanım Değeri (Sol Üst)

```python
if y_pct:
    current_val = y_pct[-1]
    color_val = "#05CD99" if current_val < 60 else "#FFB547" if current_val < 80 else "#EE5D50"
    fig.add_annotation(
        text=f"<b>{current_val:.1f}%</b> current",
        x=0.01, y=0.97,
        xref="paper", yref="paper",
        showarrow=False,
        font=dict(size=13, color=color_val, family="DM Sans"),
        bgcolor="rgba(255,255,255,0.85)",
        bordercolor=color_val,
        borderwidth=1,
        borderpad=6,
        align="left",
    )
```

### A6. Chart Card Yüksekliği

`_build_intel_storage_subtab()` içinde chart card height 260 → **300** yapılır:

```python
# satır 1761 civarı — style={"height": "260px"} → {"height": "300px"}
# ve create_capacity_area_chart çağrısında height=260 → height=300
```

---

## B. PHYSICAL INVENTORY — DEVICES BY ROLE CHART

**Dosya:** `src/pages/dc_view.py` — `_build_physical_inventory_dc_tab()` (satır 1408–1442)

### Sorun Analizi

- `height=320` sabit ama 18+ rol olduğunda her bar ~17px kalıyor → çok ince
- `textposition="outside"` ile büyük bar değerleri (örn. 214) chart sınırını aşıp kesilebiliyor
- Sol margin 20px → uzun rol isimleri ("Customer Management Switch") kesiliyor
- `bargap` ayarlanmamış → barlar çok sıkışık

### B1. Dinamik Chart Yüksekliği

```python
# Satır ~1435 — height=320 yerine:
dynamic_height = max(340, len(role_labels) * 36)
```

### B2. Sol Margin Dinamik Genişletme

```python
# En uzun label kaç karakter?
max_label_len = max((len(l) for l in role_labels), default=10)
left_margin = min(max_label_len * 7 + 10, 220)  # max 220px
```

### B3. Text Labels — Koşullu Pozisyon

Büyük barlar için "inside" (beyaz metin), küçük barlar için "outside" (koyu metin):

```python
max_count = max(role_counts) if role_counts else 1
text_positions = [
    "inside" if c > max_count * 0.35 else "outside"
    for c in role_counts
]
text_colors = [
    "white" if c > max_count * 0.35 else "#2B3674"
    for c in role_counts
]

fig_role = go.Figure(
    data=[go.Bar(
        x=role_counts or [0],
        y=role_labels or ["No data"],
        orientation="h",
        marker=dict(
            color=role_counts,
            colorscale=[
                [0.0, "#C4B5FD"],   # açık mor (küçük değer)
                [0.4, "#7551FF"],   # orta mor
                [0.7, "#4318FF"],   # indigo
                [1.0, "#05CD99"],   # yeşil (en büyük değer)
            ],
            showscale=False,
            line=dict(color="rgba(0,0,0,0)", width=0),
        ),
        text=role_counts,
        textposition=text_positions,
        textfont=dict(size=11, family="DM Sans", weight=700, color=text_colors),
        hovertemplate="<b>%{y}</b><br>%{x:,} devices<extra></extra>",
        width=0.65,  # bar kalınlığı
    )]
)
fig_role.update_traces(marker_cornerradius=8)
fig_role.update_layout(
    margin=dict(l=left_margin, r=70, t=10, b=10),
    height=dynamic_height,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    showlegend=False,
    bargap=0.28,
    xaxis=dict(
        showgrid=False,
        zeroline=False,
        showticklabels=False,
        range=[0, max(role_counts or [1]) * 1.22],
    ),
    yaxis=dict(
        showgrid=False,
        zeroline=False,
        categoryorder="total ascending",
        tickfont=dict(family="DM Sans", size=12, color="#2B3674"),
    ),
    font=dict(family="DM Sans, sans-serif", color="#2B3674", size=12),
)
```

### B4. Chart Container — Scroll Destekli

Chart kart içinde overflow scroll ekle (çok fazla item varsa kaydırılabilir):

```python
# Satır 1505–1511 civarı
html.Div(
    className="nexus-card",
    style={"padding": "20px"},
    children=[
        _section_title("Devices by Role", "Device role distribution"),
        html.Div(
            style={"overflowY": "auto", "maxHeight": "480px"},
            children=dcc.Graph(
                figure=fig_role,
                config={"displayModeBar": False},
                style={"height": f"{dynamic_height}px"},
            ),
        ),
    ],
),
```

---

## C. PHYSICAL INVENTORY — MANUFACTURER BY ROLE CHART

**Dosya:** `src/pages/dc_view.py` — `_build_physical_inventory_dc_tab()` (satır 1444–1487)

### Sorun Analizi

- X-ekseni = manufacturers → çok fazla manufacturer varsa barlar küçülüyor
- Her role için ayrı trace → 8 trace × 15 manufacturer = 120 ince bar
- Değer etiketleri yok → kaç cihaz olduğu anlaşılmıyor
- Legend üste binmiş

### C1. Pivot Değişikliği: X = Role, Trace = Manufacturer (Top N)

Daha okunabilir bir pivot: X ekseninde roller (az sayıda), her trace bir manufacturer. Yalnızca top 8 manufacturer gösterilir.

```python
# Top 8 manufacturer'ı bul (total count'a göre)
manu_totals: dict[str, int] = {}
for r in rm_filtered:
    m = title_case(r.get("manufacturer") or "Unknown")
    manu_totals[m] = manu_totals.get(m, 0) + r["count"]

top_manufacturers = [m for m, _ in sorted(manu_totals.items(), key=lambda x: -x[1])[:8]]

# X = roller, trace = manufacturer
all_roles_rm = list(dict.fromkeys(
    title_case(r["role"]) for r in rm_filtered
))

colors = ["#4318FF", "#05CD99", "#FFB547", "#7551FF", "#00DBE3",
          "#FF6B6B", "#A78BFA", "#0FBA81"]

fig_rm = go.Figure()
for i, manu in enumerate(top_manufacturers):
    y_vals = []
    for role in all_roles_rm:
        count = next(
            (r["count"] for r in rm_filtered
             if title_case(r["role"]) == role and title_case(r.get("manufacturer") or "") == manu),
            0
        )
        y_vals.append(count)

    fig_rm.add_trace(go.Bar(
        name=manu,
        x=all_roles_rm,
        y=y_vals,
        marker_color=colors[i % len(colors)],
        text=[str(v) if v > 0 else "" for v in y_vals],
        textposition="outside",
        textfont=dict(size=10, color="#2B3674", family="DM Sans"),
        hovertemplate="<b>%{x}</b><br>" + manu + ": <b>%{y:,}</b><extra></extra>",
    ))

fig_rm.update_traces(marker_cornerradius=5)
```

### C2. Layout — Daha Geniş, Legend Altında

```python
fig_rm.update_layout(
    barmode="group",
    bargap=0.22,
    bargroupgap=0.08,
    margin=dict(l=20, r=20, t=20, b=120),
    height=400,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    showlegend=True,
    legend=dict(
        orientation="h",
        yanchor="top",
        y=-0.22,
        xanchor="center",
        x=0.5,
        font=dict(size=11, family="DM Sans", color="#2B3674"),
        bgcolor="rgba(0,0,0,0)",
        itemsizing="constant",
    ),
    xaxis=dict(
        showgrid=False,
        zeroline=False,
        tickangle=-30,
        tickfont=dict(family="DM Sans", size=11, color="#2B3674"),
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="rgba(227, 234, 252, 0.5)",
        gridwidth=1,
        zeroline=False,
        tickfont=dict(family="DM Sans", size=11, color="#A3AED0"),
    ),
    font=dict(family="DM Sans, sans-serif", color="#A3AED0", size=11),
)
```

### C3. Chart Card Yüksekliği

```python
# Satır 1513–1519 civarı
dcc.Graph(figure=fig_rm, config={"displayModeBar": False}, style={"height": "400px"}),
```

---

## D. NETWORK — BANDWIDTH (95TH PERCENTILE) CHART

**Dosya:** `src/components/charts.py` — `create_horizontal_bar_chart()` (satır 316–368)
**Çağrı yeri:** `src/pages/dc_view.py` satır 1608–1614

### Sorun Analizi

- Tek düz `#4318FF` renk → tüm barlar aynı görünüyor
- `showticklabels=False` x-ekseni → değer okumak imkânsız
- Bar text yok → Gbps değerleri gizli
- `bargap=0.18` → barlar ince
- `marker_cornerradius=6` var ama tek renk bozuyor etkiyi

### D1. Yeni Fonksiyon: `create_premium_horizontal_bar_chart()`

Mevcut `create_horizontal_bar_chart()` kırılmasın diye ayrı premium versiyon. Çağrı yerinde kullanılacak.

```python
def create_premium_horizontal_bar_chart(
    labels, values, title, unit_suffix="Gbps", height=340, show_legend=True
):
    """
    Premium horizontal bar chart.
    - Renk değere göre gradient (küçük = açık mor, büyük = koyu indigo → yeşil)
    - Bar'ların sağına değer etiketi (Gbps)
    - Rounded corners
    - Hover: interface + değer
    """
    labels = labels or []
    values = values or []
    x_data = [float(v or 0) for v in values]

    if not x_data:
        max_val = 1.0
    else:
        max_val = max(x_data) or 1.0

    # Normalize 0-1 for colorscale
    norm = [v / max_val for v in x_data]

    # Bar renkleri: düşük değer = #C4B5FD (lavender), yüksek = #4318FF (indigo)
    def lerp_hex(t):
        # #C4B5FD → #4318FF
        r = int(0xC4 + (0x43 - 0xC4) * t)
        g = int(0xB5 + (0x18 - 0xB5) * t)
        b = int(0xFD + (0xFF - 0xFD) * t)
        return f"#{r:02X}{g:02X}{b:02X}"

    bar_colors = [lerp_hex(n) for n in norm]

    text_labels = [f"{v:.2f} {unit_suffix}" if v > 0 else "" for v in x_data]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=labels,
            x=x_data,
            orientation="h",
            marker=dict(
                color=bar_colors,
                opacity=1.0,
                line=dict(color="rgba(0,0,0,0)", width=0),
            ),
            text=text_labels,
            textposition="outside",
            textfont=dict(size=11, color="#2B3674", family="DM Sans", weight=600),
            hovertemplate="<b>%{y}</b><br>P95: <b>%{x:.3f} " + unit_suffix + "</b><extra></extra>",
            name="",
        )
    )

    try:
        fig.update_traces(marker_cornerradius=8)
    except Exception:
        pass

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        margin=dict(l=10, r=90, t=10, b=10),
        height=height,
        bargap=0.30,
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            range=[0, max_val * 1.30],
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            tickfont=dict(family="DM Sans", size=12, color="#2B3674", weight=600),
            categoryorder="total ascending",
        ),
        font=dict(family="DM Sans", color="#A3AED0"),
        hoverlabel=dict(
            bgcolor="rgba(255,255,255,0.97)",
            bordercolor="rgba(67, 24, 255, 0.15)",
            font=dict(family="DM Sans", size=12, color="#2B3674"),
        ),
    )
    return fig
```

### D2. Çağrı Yerini Güncelle

`dc_view.py` satır 1608–1614:

```python
# Mevcut:
bar_fig = create_horizontal_bar_chart(
    labels=bar_labels,
    values=bar_values,
    title="Top 95th Percentile Interfaces (Gbps)",
    color="#4318FF",
    height=320,
)

# Yeni:
bar_fig = create_premium_horizontal_bar_chart(
    labels=bar_labels,
    values=bar_values,
    title="Top 95th Percentile Interfaces (Gbps)",
    unit_suffix="Gbps",
    height=360,
)
```

### D3. Import Güncelleme

`dc_view.py` başındaki import satırına `create_premium_horizontal_bar_chart` ekle.

---

## E. BACKUP & REPLICATION — TÜM 3 TAB PREMIUM LAYOUT

**Dosya:** `src/components/backup_panel.py`

### Sorun Analizi

1. **Donut tam daire** → `_usage_pie()` full donut kullanıyor; diğer sayfalarda `create_premium_gauge_chart()` (yarım ay) kullanılıyor
2. **Veeam & NetBackup'ta status panel yok** → Zerto'daki N1 status_panel Veeam/NetBackup'ta eksik
3. **KPI grid `cols=1`** → KPI'lar tek sütun halinde uzun bir liste oluşturuyor; 2×2 grid daha kompakt
4. **`_pie_card()` boyutları** → Tam daire için 320×300px tasarlandı; yarım ay gauge için bu ölçüler yanlış

---

### E1. `_usage_pie()` → `_usage_gauge_fig()` — Yarım Ay Gauge

`_usage_pie()` fonksiyonu yerine yeni `_usage_gauge_fig()`:

```python
from src.components.charts import create_premium_gauge_chart

def _usage_gauge_fig(used: float, total: float, title: str) -> go.Figure:
    """Yarım ay premium gauge — tam donut yerine."""
    used_val = max(float(used or 0), 0.0)
    total_val = max(float(total or 0), 0.0)
    pct = pct_float(used_val, total_val) if total_val > 0 else 0.0

    color = "#4318FF" if pct < 60 else "#FFB547" if pct < 80 else "#EE5D50"
    return create_premium_gauge_chart(pct, title, color=color, height=220)
```

**Tüm `_usage_pie()` çağrılarını `_usage_gauge_fig()` ile değiştir:**
- `build_netbackup_panel()` satır 238–242
- `build_zerto_panel()` satır 408–412
- `build_veeam_panel()` satır 760–764

### E2. `_pie_card()` → `_gauge_card()` — Yarım Ay İçin Yeni Boyutlar

```python
def _gauge_card(fig: go.Figure) -> html.Div:
    """Gauge (yarım ay) chart container."""
    return html.Div(
        className="nexus-card dc-chart-card",
        style={
            "padding": "12px 16px",
            "flex": "1",
            "minWidth": "220px",
            "maxWidth": "280px",
            "height": "240px",
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "justifyContent": "center",
            "boxSizing": "border-box",
        },
        children=dcc.Graph(
            figure=fig,
            config={"displayModeBar": False},
            style={"height": "100%", "width": "100%"},
        ),
    )
```

**Tüm `_pie_card(fig)` çağrılarını `_gauge_card(fig)` ile değiştir.**

### E3. KPI Grid — `cols=1` → `cols=2`

Tüm 3 paneldeki kpis `SimpleGrid`:

```python
# Mevcut:
kpis = dmc.SimpleGrid(cols=1, spacing="xs", children=[...])

# Yeni: 2×2 grid
kpis = dmc.SimpleGrid(
    cols=2,
    spacing="xs",
    style={"minWidth": "240px", "maxWidth": "320px"},
    children=[...]
)
```

Bu değişiklik 3 fonksiyonda da yapılır: `build_zerto_panel`, `build_veeam_panel`, `build_netbackup_panel`.

### E4. Veeam — Status Panel Ekleme

`build_veeam_panel()` içinde, `return` bloğundan önce Zerto'daki status_panel benzeri bileşen:

```python
online_count    = sum(1 for r in agg["rows"] if r.get("is_online") is True)
offline_count   = sum(1 for r in agg["rows"] if r.get("is_online") is False)
util_pct_v      = agg["utilisation_pct"]

veeam_status_panel = html.Div(
    className="nexus-card dc-kpi-card",
    style={
        "padding": "20px 24px",
        "flex": "1",
        "minWidth": "200px",
        "display": "flex",
        "flexDirection": "column",
        "gap": "16px",
        "justifyContent": "center",
    },
    children=[
        html.Div(
            style={"borderBottom": "1px solid #F4F7FE", "paddingBottom": "12px"},
            children=[html.Span("REPO STATUS", style={
                "fontSize": "0.7rem", "fontWeight": 700,
                "color": "#A3AED0", "letterSpacing": "0.08em", "textTransform": "uppercase",
            })],
        ),
        dmc.Group(gap="xs", align="center", children=[
            DashIconify(icon="solar:check-circle-bold-duotone", width=20, style={"color": "#05CD99"}),
            html.Span(f"{online_count}", style={
                "fontSize": "1.8rem", "fontWeight": 900, "color": "#2B3674", "letterSpacing": "-0.02em"
            }),
            html.Span("online", style={
                "fontSize": "0.8rem", "color": "#A3AED0", "fontWeight": 500, "marginLeft": "4px"
            }),
        ]),
        dmc.Group(gap="xs", align="center", children=[
            DashIconify(icon="solar:close-circle-bold-duotone", width=20, style={"color": "#EE5D50"}),
            html.Span(f"{offline_count}", style={
                "fontSize": "1.8rem", "fontWeight": 900, "color": "#2B3674", "letterSpacing": "-0.02em"
            }),
            html.Span("offline", style={
                "fontSize": "0.8rem", "color": "#A3AED0", "fontWeight": 500, "marginLeft": "4px"
            }),
        ]),
        html.Div(
            style={"borderTop": "1px solid #F4F7FE", "paddingTop": "12px"},
            children=[
                html.Div(
                    style={"display": "flex", "justifyContent": "space-between", "marginBottom": "6px"},
                    children=[
                        html.Span("Utilization", style={"fontSize": "0.78rem", "color": "#A3AED0"}),
                        html.Span(f"{util_pct_v:.1f}%", style={
                            "fontSize": "0.78rem", "fontWeight": 700,
                            "color": "#05CD99" if util_pct_v < 60 else "#FFB547" if util_pct_v < 80 else "#EE5D50",
                        }),
                    ],
                ),
                html.Div(
                    style={"width": "100%", "height": "6px", "borderRadius": "3px",
                           "background": "#EEF2FF", "overflow": "hidden"},
                    children=html.Div(style={
                        "width": f"{min(util_pct_v, 100):.1f}%", "height": "100%",
                        "borderRadius": "3px",
                        "background": (
                            "linear-gradient(90deg, #4318FF 0%, #05CD99 100%)" if util_pct_v < 60
                            else "linear-gradient(90deg, #4318FF 0%, #FFB547 100%)" if util_pct_v < 80
                            else "linear-gradient(90deg, #4318FF 0%, #EE5D50 100%)"
                        ),
                        "transition": "width 0.6s cubic-bezier(0.25, 0.8, 0.25, 1)",
                    }),
                ),
            ],
        ),
    ],
)
```

**Veeam `return` bloğundaki `dmc.Group`:**

```python
# Mevcut:
dmc.Group(
    align="flex-start", gap="lg",
    children=[
        html.Div(style={"minWidth": "200px"}, children=kpis),
        _pie_card(fig),
    ],
),

# Yeni:
html.Div(
    style={"display": "flex", "gap": "20px", "alignItems": "flex-start", "flexWrap": "wrap"},
    children=[
        html.Div(style={"flexShrink": 0}, children=kpis),
        _gauge_card(fig),
        veeam_status_panel,
    ],
),
```

### E5. NetBackup — Status Panel Ekleme

`build_netbackup_panel()` içinde `return` bloğundan önce:

```python
# agg zaten "utilisation_pct" içeriyor
util_pct_nb = agg["utilisation_pct"]
total_pools  = len(agg["rows"])
active_pools = len([r for r in agg["rows"] if (r.get("usablesizebytes") or 0) > 0])
inactive_pools = total_pools - active_pools

nb_status_panel = html.Div(
    className="nexus-card dc-kpi-card",
    style={
        "padding": "20px 24px",
        "flex": "1",
        "minWidth": "200px",
        "display": "flex",
        "flexDirection": "column",
        "gap": "16px",
        "justifyContent": "center",
    },
    children=[
        html.Div(
            style={"borderBottom": "1px solid #F4F7FE", "paddingBottom": "12px"},
            children=[html.Span("POOL STATUS", style={
                "fontSize": "0.7rem", "fontWeight": 700,
                "color": "#A3AED0", "letterSpacing": "0.08em", "textTransform": "uppercase",
            })],
        ),
        dmc.Group(gap="xs", align="center", children=[
            DashIconify(icon="solar:check-circle-bold-duotone", width=20, style={"color": "#05CD99"}),
            html.Span(f"{active_pools}", style={
                "fontSize": "1.8rem", "fontWeight": 900, "color": "#2B3674", "letterSpacing": "-0.02em"
            }),
            html.Span("active", style={
                "fontSize": "0.8rem", "color": "#A3AED0", "fontWeight": 500, "marginLeft": "4px"
            }),
        ]),
        dmc.Group(gap="xs", align="center", children=[
            DashIconify(icon="solar:close-circle-bold-duotone", width=20, style={"color": "#EE5D50"}),
            html.Span(f"{inactive_pools}", style={
                "fontSize": "1.8rem", "fontWeight": 900, "color": "#2B3674", "letterSpacing": "-0.02em"
            }),
            html.Span("inactive", style={
                "fontSize": "0.8rem", "color": "#A3AED0", "fontWeight": 500, "marginLeft": "4px"
            }),
        ]),
        html.Div(
            style={"borderTop": "1px solid #F4F7FE", "paddingTop": "12px"},
            children=[
                html.Div(
                    style={"display": "flex", "justifyContent": "space-between", "marginBottom": "6px"},
                    children=[
                        html.Span("Utilization", style={"fontSize": "0.78rem", "color": "#A3AED0"}),
                        html.Span(f"{util_pct_nb:.1f}%", style={
                            "fontSize": "0.78rem", "fontWeight": 700,
                            "color": "#05CD99" if util_pct_nb < 60 else "#FFB547" if util_pct_nb < 80 else "#EE5D50",
                        }),
                    ],
                ),
                html.Div(
                    style={"width": "100%", "height": "6px", "borderRadius": "3px",
                           "background": "#EEF2FF", "overflow": "hidden"},
                    children=html.Div(style={
                        "width": f"{min(util_pct_nb, 100):.1f}%", "height": "100%",
                        "borderRadius": "3px",
                        "background": (
                            "linear-gradient(90deg, #4318FF 0%, #05CD99 100%)" if util_pct_nb < 60
                            else "linear-gradient(90deg, #4318FF 0%, #FFB547 100%)" if util_pct_nb < 80
                            else "linear-gradient(90deg, #4318FF 0%, #EE5D50 100%)"
                        ),
                        "transition": "width 0.6s cubic-bezier(0.25, 0.8, 0.25, 1)",
                    }),
                ),
            ],
        ),
    ],
)
```

**NetBackup `return` bloğu:**

```python
# Mevcut (satır 369–387):
return html.Div(
    children=[
        header,
        dmc.Group(
            align="flex-start", gap="lg",
            children=[
                html.Div(style={"minWidth": "200px"}, children=kpis),
                _pie_card(fig),
            ],
        ),
        ...
    ]
)

# Yeni:
return html.Div(
    children=[
        header,
        html.Div(
            style={"display": "flex", "gap": "20px", "alignItems": "flex-start", "flexWrap": "wrap"},
            children=[
                html.Div(style={"flexShrink": 0}, children=kpis),
                _gauge_card(fig),
                nb_status_panel,
            ],
        ),
        html.Div(style={"height": "16px"}),
        html.Div(
            className="nexus-card",
            style={"padding": "16px", "marginTop": "8px"},
            children=table,
        ),
    ]
)
```

---

## UYGULAMA SIRASI (Checklist)

- [ ] **1. `create_capacity_area_chart()` — A1-A6** (`charts.py`)
  - Dinamik y-range, son nokta marker, günlük vline, y-ekseni sağda görünür, current annotation
- [ ] **2. Devices by Role — B1-B4** (`dc_view.py`)
  - Dinamik yükseklik, sol margin, koşullu text pozisyon, scroll container
- [ ] **3. Manufacturer by Role — C1-C3** (`dc_view.py`)
  - X=role pivot, top-8 manufacturer trace, legend altına, height=400
- [ ] **4. `create_premium_horizontal_bar_chart()` — D1** (`charts.py`)
  - Yeni fonksiyon: gradient renkler, text label, cornerradius
- [ ] **5. Bandwidth çağrısını güncelle — D2-D3** (`dc_view.py`)
  - Import + çağrı değişikliği
- [ ] **6. `_usage_gauge_fig()` ekle — E1** (`backup_panel.py`)
  - `_usage_pie()` yerine gauge fonksiyonu
- [ ] **7. `_gauge_card()` ekle — E2** (`backup_panel.py`)
  - `_pie_card()` yerine gauge boyutları
- [ ] **8. KPI grid `cols=2` — E3** (`backup_panel.py`)
  - 3 fonksiyonda SimpleGrid cols=1 → cols=2
- [ ] **9. Veeam status panel — E4** (`backup_panel.py`)
  - Status panel + layout güncellemesi
- [ ] **10. NetBackup status panel — E5** (`backup_panel.py`)
  - Status panel + layout güncellemesi
- [ ] **11. Zerto donut → gauge — E1+E2** (`backup_panel.py`)
  - `_usage_pie` → `_usage_gauge_fig`, `_pie_card` → `_gauge_card`

---

## DEĞİŞTİRİLEN DOSYALAR

| Dosya | Değişiklik | Bölüm |
|---|---|---|
| `src/components/charts.py` | `create_capacity_area_chart` güncellemesi + yeni `create_premium_horizontal_bar_chart` | A, D1 |
| `src/pages/dc_view.py` | Devices by Role, Manufacturer by Role, Bandwidth çağrısı | B, C, D2-D3 |
| `src/components/backup_panel.py` | `_usage_gauge_fig`, `_gauge_card`, KPI cols=2, Veeam+NetBackup status panel | E1-E5 |

**Veri / API değişikliği:** ❌ Sıfır  
**Yeni dosya:** ❌ Yok
