# DC Sayfaları Premium Görsel Yükseltme Planı

> **Kural:** Hiçbir veri, API, backend, servis veya callback mantığı değişmez. Yalnızca UI/CSS/görselleştirme katmanı yükseltilir.

---

## 🎯 Felsefe

Mevcut DC detail sayfaları fonksiyonel ama **"sade MVP"** görünüyor. Hedefimiz:
- **Glassmorphism** derinliği
- **Gradient** zenginliği
- **Micro-animation** canlılığı
- **Premium tipografi** & ikon kullanımı
- **Executive dashboard** hissi (Tesla / Apple dashboard estetiği)

---

## A. GLOBAL CSS YÜKSELTMELERİ

**Dosya:** `assets/style.css`

### A1. KPI Kartları — Premium Gradient Şerit

Mevcut `_kpi()` fonksiyonundaki kartlar düz beyaz nexus-card. Sol kenarına ince bir gradient accent border ekleyeceğiz.

```css
.dc-kpi-card {
    position: relative;
    overflow: hidden;
    transition: all 0.35s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.dc-kpi-card::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 4px;
    border-radius: 20px 0 0 20px;
    background: linear-gradient(180deg, #4318FF 0%, #05CD99 100%);
    opacity: 0;
    transition: opacity 0.3s ease;
}

.dc-kpi-card:hover::before {
    opacity: 1;
}

.dc-kpi-card:hover {
    transform: translateY(-4px);
    box-shadow:
        0px 20px 50px rgba(67, 24, 255, 0.10),
        0px 8px 20px rgba(112, 144, 176, 0.06) !important;
}
```

### A2. Section Title — Gradient Underline

Section başlıkları (`_section_title()`) düz metin. Altına ince gradient bir çizgi eklenecek.

```css
.dc-section-title {
    position: relative;
    padding-bottom: 10px;
}

.dc-section-title::after {
    content: '';
    position: absolute;
    left: 0;
    bottom: 0;
    width: 48px;
    height: 3px;
    border-radius: 3px;
    background: linear-gradient(90deg, #4318FF 0%, #7551FF 50%, #05CD99 100%);
}
```

### A3. Chart Card — Subtle Glow Hover

Grafik kartlarına hover'da hafif parlama efekti.

```css
.dc-chart-card {
    transition: all 0.35s cubic-bezier(0.25, 0.8, 0.25, 1);
    border: 1px solid transparent;
}

.dc-chart-card:hover {
    border-color: rgba(67, 24, 255, 0.08);
    box-shadow:
        0px 20px 50px rgba(67, 24, 255, 0.08),
        0px 8px 20px rgba(112, 144, 176, 0.05),
        inset 0 0 0 1px rgba(67, 24, 255, 0.05) !important;
    transform: translateY(-3px);
}
```

### A4. Tab Geçişleri — Smooth Content Transition

Tab panel içeriklerinin yüklenmesinde yumuşak animasyon.

```css
.dc-tab-content {
    animation: dcTabFade 0.4s ease-out;
}

@keyframes dcTabFade {
    from { opacity: 0; transform: translateY(12px); }
    to   { opacity: 1; transform: translateY(0); }
}
```

### A5. Capacity Metric Row — Premium Hover

Kapasite satırlarına hover efekti.

```css
.dc-capacity-row {
    transition: all 0.2s ease;
    border-radius: 8px;
    padding: 10px 12px !important;
    margin: 2px 0;
}

.dc-capacity-row:hover {
    background-color: rgba(67, 24, 255, 0.03);
    transform: translateX(4px);
}
```

### A6. Premium Tablo Stili — Executive

Mevcut tablolar çok sade. Tüm DC tablolarına uygulanacak executive tablo stili.

```css
.dc-premium-table thead th {
    color: #A3AED0 !important;
    font-weight: 600 !important;
    font-size: 0.72rem !important;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    border-bottom: 2px solid #E9EDF7 !important;
    padding: 12px 16px !important;
    white-space: nowrap;
}

.dc-premium-table tbody td {
    color: #2B3674 !important;
    font-weight: 500 !important;
    font-size: 0.82rem !important;
    padding: 14px 16px !important;
    border-bottom: 1px solid #F4F7FE !important;
    transition: all 0.15s ease;
}

.dc-premium-table tbody tr {
    transition: all 0.2s ease;
}

.dc-premium-table tbody tr:hover {
    background-color: rgba(67, 24, 255, 0.03) !important;
    transform: scale(1.002);
}

.dc-premium-table tbody tr:hover td {
    color: #4318FF !important;
}
```

### A7. Stagger Animation — Kartların Sıralı Belirmesi

KPI ve chart kartlarının sayfa yüklendiğinde sırayla belirmesi.

```css
.dc-stagger-1 { animation: dcTabFade 0.4s ease-out 0.05s both; }
.dc-stagger-2 { animation: dcTabFade 0.4s ease-out 0.10s both; }
.dc-stagger-3 { animation: dcTabFade 0.4s ease-out 0.15s both; }
.dc-stagger-4 { animation: dcTabFade 0.4s ease-out 0.20s both; }
```

### A8. Badge Status Glow

Connected/Online badge'larına glow efekti.

```css
.dc-status-connected {
    box-shadow: 0 0 8px rgba(5, 205, 153, 0.4);
}

.dc-status-disconnected {
    box-shadow: 0 0 8px rgba(238, 93, 80, 0.4);
}
```

---

## B. KPI KARTLARI YÜKSELTMESİ

**Dosya:** `src/pages/dc_view.py` — `_kpi()` fonksiyonu (satır 496-518)

### B1. KPI Card → Premium Gradient Card

**Mevcut:** Düz beyaz kart, basit ikon.

**Yeni:**
- `className="nexus-card dc-kpi-card dc-stagger-N"` eklenir
- İkon arka planına soft gradient eklenir
- Büyük değer yazısına gradient text uygulanır (opsiyonel, sadece numerik)
- Her KPI kartına stagger class eklenir (1-4 arası)

```python
def _kpi(title, value, icon, color="indigo", is_text=False, stagger=1):
    return html.Div(
        className=f"nexus-card dc-kpi-card dc-stagger-{stagger}",
        style={
            "padding": "20px",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "space-between",
        },
        children=[
            html.Div([
                html.Span(
                    title,
                    style={
                        "color": "#A3AED0",
                        "fontSize": "0.82rem",
                        "fontWeight": 500,
                        "letterSpacing": "0.02em",
                        "textTransform": "uppercase",
                    },
                ),
                html.H3(
                    str(value),
                    style={
                        "color": "#2B3674",
                        "fontSize": "1.1rem" if is_text else "1.6rem",
                        "fontWeight": 900,
                        "margin": "6px 0 0 0",
                        "letterSpacing": "-0.02em",
                    },
                ),
            ]),
            dmc.ThemeIcon(
                size=48,
                radius="xl",
                variant="light",
                color=color,
                style={
                    "background": f"linear-gradient(135deg, rgba(67, 24, 255, 0.08) 0%, rgba(5, 205, 153, 0.08) 100%)",
                },
                children=DashIconify(icon=icon, width=26),
            ),
        ],
    )
```

**Değişiklik Özeti:**
- Font boyutları büyütüldü (1.5rem → 1.6rem)
- Font weight arttırıldı (bold → 900)
- Letter-spacing eklendi
- Label uppercase yapıldı
- İkon boyutu 24→26, ThemeIcon 'xl'→48px, gradient background
- Stagger animasyon desteği

---

## C. SECTION TITLE YÜKSELTMESİ

**Dosya:** `src/pages/dc_view.py` — `_section_title()` fonksiyonu (satır 531-538)

### C1. Section Title → Gradient Altçizgi

```python
def _section_title(title, subtitle=None):
    return html.Div(
        className="dc-section-title",
        style={"marginBottom": "4px"},
        children=[
            html.H3(
                title,
                style={
                    "margin": 0,
                    "color": "#2B3674",
                    "fontSize": "1.05rem",
                    "fontWeight": 800,
                    "letterSpacing": "-0.01em",
                },
            ),
            html.P(
                subtitle,
                style={
                    "margin": "4px 0 0 0",
                    "color": "#A3AED0",
                    "fontSize": "0.8rem",
                    "fontWeight": 500,
                },
            ) if subtitle else None,
        ],
    )
```

---

## D. CHART CARD YÜKSELTMESİ

**Dosya:** `src/pages/dc_view.py` — `_chart_card()` fonksiyonu (satır 521-528)

### D1. Chart Card → Hover Glow Card

```python
def _chart_card(graph_component):
    return html.Div(
        className="nexus-card dc-chart-card",
        style={
            "padding": "16px",
            "height": "250px",
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "justifyContent": "center",
            "overflow": "hidden",
        },
        children=graph_component,
    )
```

---

## E. CAPACITY METRIC ROW YÜKSELTMESİ

**Dosya:** `src/pages/dc_view.py` — `_capacity_metric_row()` (satır 541-554)

### E1. Capacity Row → Premium Hover Row

```python
def _capacity_metric_row(label, cap_val, used_val, pct, unit_fn=None):
    cap_str  = unit_fn(cap_val) if unit_fn else str(cap_val)
    used_str = unit_fn(used_val) if unit_fn else str(used_val)

    pct_color = "#05CD99" if pct < 60 else "#FFB547" if pct < 80 else "#EE5D50"

    return html.Div(
        className="dc-capacity-row",
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "borderBottom": "1px solid #F4F7FE",
        },
        children=[
            html.Span(
                label,
                style={
                    "color": "#2B3674",
                    "fontWeight": 700,
                    "fontSize": "0.85rem",
                    "minWidth": "120px",
                },
            ),
            html.Span(
                f"Capacity: {cap_str}",
                style={"color": "#A3AED0", "fontSize": "0.8rem"},
            ),
            html.Span(
                f"Allocated: {used_str}",
                style={
                    "color": "#4318FF",
                    "fontSize": "0.8rem",
                    "fontWeight": 600,
                },
            ),
            dmc.Badge(
                f"{pct:.1f}%",
                color="indigo" if pct < 60 else "yellow" if pct < 80 else "red",
                variant="light",
                size="sm",
                style={"minWidth": "60px", "textAlign": "center"},
            ),
            html.Div(
                style={
                    "width": "80px",
                    "height": "6px",
                    "borderRadius": "3px",
                    "background": "#EEF2FF",
                    "overflow": "hidden",
                    "marginLeft": "8px",
                },
                children=html.Div(
                    style={
                        "width": f"{min(pct, 100):.1f}%",
                        "height": "100%",
                        "borderRadius": "3px",
                        "background": f"linear-gradient(90deg, #4318FF 0%, {pct_color} 100%)",
                        "transition": "width 0.6s cubic-bezier(0.25, 0.8, 0.25, 1)",
                    },
                ),
            ),
        ],
    )
```

**Yenilik:** Her capacity satırının sonuna küçük bir **progress bar** ekleniyor. Bu, yüzde değerini görsel olarak hemen anlamayı sağlar.

---

## F. BACKUP PANELLERİ YÜKSELTMESİ

**Dosya:** `src/components/backup_panel.py`

### F1. `_kpi_card()` → Premium KPI

Backup panelindeki compact KPI kartlarını daha premium hale getir.

**Mevcut (satır 11-61):** Düz sade kart.  
**Yeni:**
- İkon arka planı gradient
- Metin boyutları büyütme
- Hover efekti ekleme
- `className="dc-kpi-card"` ekleme

```python
def _kpi_card(title, value, icon, color="indigo"):
    return dmc.Paper(
        className="nexus-card dc-kpi-card",
        shadow="sm",
        radius="md",
        withBorder=False,
        style={
            "padding": "14px 16px",
            "minHeight": 0,
            "display": "flex",
            "alignItems": "center",
        },
        children=[
            dmc.Group(
                gap="sm",
                align="center",
                children=[
                    dmc.ThemeIcon(
                        size="lg",
                        radius="xl",
                        variant="light",
                        color=color,
                        children=DashIconify(icon=icon, width=20),
                    ),
                    html.Div(
                        children=[
                            html.Div(
                                title,
                                style={
                                    "fontSize": "0.72rem",
                                    "color": "#A3AED0",
                                    "marginBottom": "2px",
                                    "lineHeight": 1.2,
                                    "textTransform": "uppercase",
                                    "letterSpacing": "0.03em",
                                    "fontWeight": 600,
                                },
                            ),
                            html.Div(
                                value,
                                style={
                                    "fontSize": "1.1rem",
                                    "color": "#2B3674",
                                    "fontWeight": 800,
                                    "lineHeight": 1.2,
                                    "letterSpacing": "-0.01em",
                                },
                            ),
                        ]
                    ),
                ],
            ),
        ],
    )
```

### F2. `_usage_pie()` Donut → Premium Donut

Backup panellerindeki donut chart'ı daha premium yapacağız.

**Mevcut (satır 102-144):** Basit bir pie chart, düz renkler.  
**Yeni:**
- `hole=0.78` (daha ince halka)
- Merkeze yüzde değeri annotation (donut'un içine büyük yazı)
- Renk geçişleri daha yumuşak
- Hovertemplate gelişmiş

```python
def _usage_pie(used, total, title):
    used_val = max(float(used or 0), 0.0)
    total_val = max(float(total or 0), 0.0)
    free_val = max(total_val - used_val, 0.0) if total_val > 0 else 0.0
    if total_val <= 0:
        values = [0, 1]
    else:
        values = [used_val, free_val]

    utilisation_pct = pct_float(used_val, total_val) if total_val > 0 else 0.0
    if utilisation_pct < 60:
        used_color = "#4318FF"
    elif utilisation_pct < 80:
        used_color = "#FFB547"
    else:
        used_color = "#EE5D50"
    free_color = "#EEF2FF"

    fig = go.Figure(
        data=[
            go.Pie(
                labels=["Used", "Free"],
                values=values,
                hole=0.78,
                marker=dict(
                    colors=[used_color, free_color],
                    line=dict(color="rgba(0,0,0,0)", width=0),
                ),
                textinfo="none",
                hovertemplate="<b>%{label}</b><br>%{percent:.1%}<extra></extra>",
                sort=False,
                direction="clockwise",
            )
        ]
    )
    fig.update_layout(
        annotations=[dict(
            text=f"<b>{int(utilisation_pct)}%</b>",
            x=0.5,
            y=0.5,
            xanchor="center",
            yanchor="middle",
            font=dict(size=28, color="#2B3674", family="DM Sans"),
            showarrow=False,
        )],
        title=dict(
            text=f"<b>{title}</b>",
            x=0.5,
            xanchor="center",
            font=dict(size=11, color="#A3AED0", family="DM Sans"),
        ),
        margin=dict(l=8, r=8, t=28, b=8),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.06,
            xanchor="center",
            x=0.5,
            font=dict(size=11, family="DM Sans", color="#A3AED0"),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        height=260,
    )
    return fig
```

### F3. Backup Tabloları → Premium Tablo

Zerto, Veeam, NetBackup tablolarındaki `dmc.Table`'lara `className="dc-premium-table"` ekle.

**Zerto tablosu (satır 552-559):**
```python
table = dmc.Table(
    striped=True,
    highlightOnHover=True,
    withTableBorder=False,
    withColumnBorders=False,
    className="nexus-table dc-premium-table",
    children=[table_head, html.Tbody(body_rows)],
)
```

**Aynısı Veeam (satır 752-759) ve NetBackup (satır 333-340) için de.**

### F4. Zerto Tablo Satır Renkleri — Premium Badge

**Mevcut (satır 516-549):** Connected/disconnected satırları düz pastel arka plan rengi kullanıyor (`#E6F9E6` / `#FFE6E6`).

**Yeni versiyonda:**
- Düz arka plan rengi kaldırılır
- Connected durumu bir badge ile gösterilir
- Badge'a glow class eklenir

```python
connected_cell = html.Td(
    dmc.Badge(
        "Connected" if is_conn else "Disconnected",
        color="teal" if is_conn else "red",
        variant="light",
        size="sm",
        className="dc-status-connected" if is_conn else "dc-status-disconnected",
    )
)
```

### F5. `_pie_card()` boyut ve padding güncellemesi

**Mevcut (satır 147-167):** 280×280px sabit kutu.  
**Yeni:** Biraz daha geniş, padding arttırılmış, chart card class'ı eklenmiş.

```python
def _pie_card(fig):
    return html.Div(
        className="nexus-card dc-chart-card",
        style={
            "padding": "16px",
            "width": "320px",
            "height": "300px",
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

---

## G. PHYSICAL INVENTORY YÜKSELTMESİ

**Dosya:** `src/pages/dc_view.py` — `_build_physical_inventory_dc_tab()` (satır 1308-1413)

### G1. Bar Chart Görseli — Rounded, Gradient, Hover

**Mevcut:** Düz `#4318FF` renk, köşeler yuvarlak değil.

**Yeni — Devices by Role chart:**
- Bar color → gradient (koş renge göre renk atama)
- Rounded corners (marker_cornerradius=6)
- Hover template güncelleme
- Daha büyük text font

```python
fig_role = go.Figure(
    data=[go.Bar(
        x=role_counts or [0],
        y=role_labels or ["No data"],
        orientation="h",
        marker=dict(
            color=role_counts,
            colorscale=[
                [0.0, "#7551FF"],
                [0.5, "#4318FF"],
                [1.0, "#05CD99"],
            ],
            showscale=False,
            line=dict(color="rgba(0,0,0,0)", width=0),
        ),
        text=role_counts,
        textposition="outside",
        textfont=dict(size=12, color="#2B3674", family="DM Sans", weight=700),
        hovertemplate="<b>%{y}</b><br>Count: %{x:,}<extra></extra>",
    )]
)
```

- `fig_role.update_traces(marker_cornerradius=6)` eklenecek
- Layout → `height=320` (280'den arttırma), daha iyi padding
- `font=dict(family="DM Sans, sans-serif", color="#2B3674", size=12)` — label rengi daha koyu

### G2. Grouped Bar Chart — Rounded Bars

**Manufacturer by Role chart:** Her role'un bar'ına rounded corner ekle.
- `fig_rm.update_traces(marker_cornerradius=5)` ekle
- Renk paletini daha premium hale getir: `["#4318FF", "#05CD99", "#FFB547", "#7551FF", "#00DBE3", "#FF6B6B", "#A78BFA", "#0FBA81"]`
- Layout → `height=360` (320'den arttır)

### G3. Total Devices KPI — Full Width Premium Card

**Mevcut (satır 1391-1393):** `SimpleGrid(cols=1)` ile tek satır, sade.  
**Yeni:** 4 sütunluk premium KPI grid (toplam cihaz + ek metrikler).

Total Devices KPI'ı tek başına tam genişlik kart yerine bir row'a dönüştürülecek. Sağına ikona ile device count yazısı ve bir mini grafik/ilerleme göstergesi eklenecek.

```python
# Toplam KPI → 4 sütun grid ile premium görünüm
dmc.SimpleGrid(cols=4, spacing="lg", style={"marginTop": "12px"}, children=[
    _kpi("Total Devices", f"{total:,}", "solar:server-bold-duotone", color="indigo", stagger=1),
    _kpi("Device Roles", f"{len(by_role):,}", "solar:widget-4-bold-duotone", color="violet", stagger=2),
    _kpi("Top Role", title_case(by_role[0]["role"]) if by_role else "—", "solar:crown-bold-duotone", color="grape", is_text=True, stagger=3),
    _kpi("Manufacturers", f"{len(set(r['manufacturer'] for r in by_rm)) if by_rm else 0}", "solar:buildings-bold-duotone", color="teal", stagger=4),
]),
```

---

## H. NETWORK TAB YÜKSELTMELERİ

**Dosya:** `src/pages/dc_view.py`

### H1. Network Dashboard KPI Kartları — Stagger Animation

`_build_network_dashboard_subtab()` (satır 1437) içindeki KPI grid'ine stagger class eklenir.

**Mevcut (satır 1480-1489):** Normal `_kpi()` çağrıları.  
**Yeni:** Her `_kpi()` çağrısına `stagger=N` parametresi ekle.

### H2. Network Interface Table — Premium Tablo Stili

`DataTable` (satır 1529-1552) stil güncellemesi:

```python
style_cell={
    "padding": "10px 14px",
    "color": "#2B3674",
    "fontFamily": "DM Sans, sans-serif",
    "fontSize": "0.82rem",
    "borderColor": "#F4F7FE",
    "fontWeight": 500,
},
style_header={
    "backgroundColor": "#F8F9FC",
    "color": "#A3AED0",
    "fontWeight": 700,
    "fontFamily": "DM Sans, sans-serif",
    "fontSize": "0.72rem",
    "textTransform": "uppercase",
    "letterSpacing": "0.05em",
    "borderBottom": "2px solid #E9EDF7",
},
style_data_conditional=[
    {
        "if": {"state": "active"},
        "backgroundColor": "rgba(67, 24, 255, 0.04)",
        "border": "1px solid rgba(67, 24, 255, 0.1)",
    },
],
```

### H3. SAN Subtab — Tablo Header Premium

SAN Health tabloları (satır 914-1137) zaten kısmen premium ama header fontları küçük. Tüm SAN tablolarındaki `th` stillerini aynı premium formata çek.

---

## I. STORAGE TAB YÜKSELTMELERİ

**Dosya:** `src/pages/dc_view.py`

### I1. Intel Storage — Device Selector Premium

`_build_intel_storage_subtab()` (satır 1663)

Device Filter bölümündeki `dmc.Select`'e premium stil:
- Label font büyütme
- Placeholder stil güncellemesi

### I2. IBM Storage — Grouped Bar Chart Premium

`_build_ibm_storage_subtab()` (satır 1773)

Storage Systems Used vs Free chart'ına:
- Rounded corners
- Gradient hover
- Daha büyük labels

---

## J. PLOTLY CHART GLOBAL THEME

**Dosya:** `src/components/charts.py`

### J1. Chart Font Tutarlılığı

Tüm chart fonksiyonlarında font tutarlılığını sağlamak için global bir theme dict oluştur.

```python
_PREMIUM_FONT = dict(
    family="DM Sans, sans-serif",
    color="#2B3674",
    size=12,
)

_PREMIUM_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=_PREMIUM_FONT,
    hoverlabel=dict(
        bgcolor="rgba(255,255,255,0.97)",
        bordercolor="rgba(67, 24, 255, 0.12)",
        font=dict(family="DM Sans", size=12, color="#2B3674"),
    ),
)
```

Bu dict tüm chart fonksiyonlarına `fig.update_layout(**_PREMIUM_LAYOUT, ...)` ile uygulanacak.

### J2. Donut Chart (`create_usage_donut_chart`) — Premium Center Text

**Mevcut (satır 86-131):** 28px center text.  
**Yeni:**
- Center text boyutu: 32px
- Tek rakam ise (< 10%) `"<b>8.5%</b>"` formatında gösterilecek (ondalık)
- Renk: `#1a1b41` (daha koyu lacivert)

### J3. Gauge Chart (`create_gauge_chart`) — Premium Tipografi

**Mevcut (satır 401-427):** Default plotly font.  
**Yeni:**
- Number font: 36px, weight 900, color "#2B3674"
- Title font: 13px, color "#A3AED0", uppercase
- Steps renkleri daha yumuşak

---

## K. SUMMARY TAB YÜKSELTMELERİ

**Dosya:** `src/pages/dc_view.py` — `_build_summary_tab()` (satır 1162-1305)

### K1. Energy Breakdown — İkon Zenginleştirme

Energy KPI kartlarına ⚡ emoji yerine daha premium ikonlar:
- IBM Power → `material-symbols:power-rounded` (filled)
- vCenter → `material-symbols:cloud` (filled)
- Total → `material-symbols:flash-on` (filled)

### K2. Power Compute Summary Card — Gradient Header

IBM Power bölümündeki section'a hafif gradient arka plan:

```python
html.Div(
    className="nexus-card",
    style={
        "padding": "20px",
        "background": "linear-gradient(135deg, rgba(139, 92, 246, 0.03) 0%, rgba(67, 24, 255, 0.03) 100%)",
    },
    children=[...]
)
```

---

## L. VIRT TAB — CLUSTER SELECTOR YÜKSELTMESİ

**Dosya:** `src/pages/dc_view.py` — `_cluster_header()` (satır 2176-2190)

### L1. Cluster MultiSelect — Premium Pill Style

`dmc.MultiSelect` → Pill variant'ına sahip daha premium görünüm:
- `variant="filled"` (opsiyonel)
- Arka plan: `#F8F9FC`
- Radius: `xl`
- Daha büyük size: `md`

---

## M. STORAGE TAB — CAPACITY UTILIZATION TREND CHART YÜKSELTMESİ

**Dosya:** `src/components/charts.py` — `create_capacity_area_chart()` (satır 352-398)

> **Fotoğraf 1'deki sorun:** Chart'ta düz tek renkli fill var, y-ekseni gizli, eşik çizgisi yok. Kart boyutu küçük ama chart tüm alanı sığık dolduruyor. "Premium dashboard" hissi eksik.

### M1. Spline + Gradient Fill

**Mevcut:** `mode="lines"`, `fill="tozeroy"`, tek düz `rgba(67,24,255,0.12)` fill.

**Yeni:**
- `shape="spline"` → yumuşak eğri
- `smoothing=1.3` → daha akıcı geçiş
- Gradient fill: `fillgradient=dict(type="vertical", colorscale=[[0, "rgba(67,24,255,0.18)"], [1, "rgba(67,24,255,0.01)"]])` (Plotly 5.18+)
- Geri uyumluluk için fallback olarak `fillcolor="rgba(67,24,255,0.10)"` bırakılır

```python
fig.add_trace(
    go.Scatter(
        x=x,
        y=y_pct,
        mode="lines",
        fill="tozeroy",
        line=dict(
            width=2.5,
            color="#4318FF",
            shape="spline",
            smoothing=1.3,
        ),
        fillgradient=dict(
            type="vertical",
            colorscale=[
                [0.0, "rgba(67, 24, 255, 0.18)"],
                [1.0, "rgba(67, 24, 255, 0.01)"],
            ],
        ),
        fillcolor="rgba(67, 24, 255, 0.10)",  # fallback
        hovertemplate="<b>%{x|%b %d, %Y}</b><br>Utilization: <b>%{y:.1f}%</b><extra></extra>",
        name="Utilization %",
    )
)
```

### M2. %80 Eşik Referans Çizgisi

Kritik kapasite eşiğini görsel olarak belirtmek için dashed referans çizgisi:

```python
fig.add_hline(
    y=80,
    line_dash="dot",
    line_color="#FFB547",
    line_width=1.5,
    opacity=0.7,
    annotation_text="80% threshold",
    annotation_position="right",
    annotation=dict(
        font=dict(size=10, color="#FFB547", family="DM Sans"),
        bgcolor="rgba(255,255,255,0.85)",
        bordercolor="rgba(255,181,71,0.3)",
        borderwidth=1,
        borderpad=4,
    ),
)
```

### M3. Eksen & Layout Premium Güncelleme

**Mevcut:** Y-axis gizli (`showticklabels=False`), X-axis grid yok, height=260.

**Yeni:**

```python
layout_updates = dict(
    title=dict(
        text=f"<b>{title}</b>",
        font=dict(size=13, color="#2B3674", family="DM Sans", weight=700),
        x=0,
        xanchor="left",
        pad=dict(b=8),
    ),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    showlegend=show,
    margin=dict(l=40, r=60, t=44, b=36),
    height=height,
    hovermode="x unified",
    hoverlabel=dict(
        bgcolor="rgba(255,255,255,0.97)",
        bordercolor="rgba(67, 24, 255, 0.15)",
        font=dict(family="DM Sans", size=12, color="#2B3674"),
    ),
    xaxis=dict(
        showgrid=False,
        zeroline=False,
        showticklabels=True,
        tickfont=dict(size=11, color="#A3AED0", family="DM Sans"),
        tickformat="%b %d",
        tickangle=0,
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="rgba(227, 234, 252, 0.5)",
        gridwidth=1,
        zeroline=False,
        showticklabels=True,
        ticksuffix="%",
        tickfont=dict(size=11, color="#A3AED0", family="DM Sans"),
        range=[0, 105],
        side="right",
    ),
    font=dict(family="DM Sans", color="#A3AED0"),
)
```

**Değişiklik Özeti:**
- Spline eğri + gradient alan dolgusu
- %80 dashed threshold çizgisi (orange)
- Y-ekseni sağda, % suffix ile görünür
- Grid: yalnızca yatay, çok hafif
- Hover: tarih formatı + bold değer
- Margin genişletme → chart soluk nefes alır

---

## N. BACKUP & REPLICATION — ZERTO PANEL LAYOUT YÜKSELTMESİ

**Dosya:** `src/components/backup_panel.py` — `build_zerto_panel()` (satır 562-580)

> **Fotoğraf 2'deki sorun:** KPI kartları (sol) + donut chart (orta) sonrasında sağda büyük bir boş alan var. Bu boşluk eksiksiz bir executive dashboard hissi vermiyor.

### N1. Zerto Status Summary Panel — Boş Alanı Doldur

Donut chart'ın sağına "Site Status Overview" özet kartı eklenerek boş alan premium bir bileşenle doldurulur.

```python
# build_zerto_panel() içinde, agg dict'ten hesaplanır:
connected_count    = sum(1 for r in agg["rows"] if r.get("is_connected") is True)
disconnected_count = sum(1 for r in agg["rows"] if r.get("is_connected") is False)
total_sites        = len(agg["rows"])
util_pct           = pct_float(agg["total_used_mb"], agg["total_provisioned_mb"])

status_panel = html.Div(
    className="nexus-card dc-kpi-card",
    style={
        "padding": "20px 24px",
        "minWidth": "220px",
        "flex": "1",
        "display": "flex",
        "flexDirection": "column",
        "gap": "16px",
        "justifyContent": "center",
    },
    children=[
        html.Div(
            style={"borderBottom": "1px solid #F4F7FE", "paddingBottom": "12px"},
            children=[
                html.Span(
                    "SITE STATUS",
                    style={
                        "fontSize": "0.7rem",
                        "fontWeight": 700,
                        "color": "#A3AED0",
                        "letterSpacing": "0.08em",
                        "textTransform": "uppercase",
                    },
                ),
            ],
        ),
        dmc.Group(
            gap="xs",
            align="center",
            children=[
                DashIconify(icon="solar:check-circle-bold-duotone", width=20, style={"color": "#05CD99"}),
                html.Span(
                    f"{connected_count}",
                    style={"fontSize": "1.8rem", "fontWeight": 900, "color": "#2B3674", "letterSpacing": "-0.02em"},
                ),
                html.Span(
                    "connected",
                    style={"fontSize": "0.8rem", "color": "#A3AED0", "fontWeight": 500, "marginLeft": "4px"},
                ),
            ],
        ),
        dmc.Group(
            gap="xs",
            align="center",
            children=[
                DashIconify(icon="solar:close-circle-bold-duotone", width=20, style={"color": "#EE5D50"}),
                html.Span(
                    f"{disconnected_count}",
                    style={"fontSize": "1.8rem", "fontWeight": 900, "color": "#2B3674", "letterSpacing": "-0.02em"},
                ),
                html.Span(
                    "disconnected",
                    style={"fontSize": "0.8rem", "color": "#A3AED0", "fontWeight": 500, "marginLeft": "4px"},
                ),
            ],
        ),
        html.Div(
            style={"borderTop": "1px solid #F4F7FE", "paddingTop": "12px"},
            children=[
                html.Div(
                    style={"display": "flex", "justifyContent": "space-between", "marginBottom": "6px"},
                    children=[
                        html.Span("Utilization", style={"fontSize": "0.78rem", "color": "#A3AED0"}),
                        html.Span(
                            f"{util_pct:.1f}%",
                            style={
                                "fontSize": "0.78rem",
                                "fontWeight": 700,
                                "color": "#05CD99" if util_pct < 60 else "#FFB547" if util_pct < 80 else "#EE5D50",
                            },
                        ),
                    ],
                ),
                html.Div(
                    style={
                        "width": "100%", "height": "6px",
                        "borderRadius": "3px", "background": "#EEF2FF", "overflow": "hidden",
                    },
                    children=html.Div(
                        style={
                            "width": f"{min(util_pct, 100):.1f}%",
                            "height": "100%",
                            "borderRadius": "3px",
                            "background": (
                                "linear-gradient(90deg, #4318FF 0%, #05CD99 100%)" if util_pct < 60
                                else "linear-gradient(90deg, #4318FF 0%, #FFB547 100%)" if util_pct < 80
                                else "linear-gradient(90deg, #4318FF 0%, #EE5D50 100%)"
                            ),
                            "transition": "width 0.6s cubic-bezier(0.25, 0.8, 0.25, 1)",
                        },
                    ),
                ),
            ],
        ),
    ],
)
```

### N2. Zerto Grup Layout — 3 Sütun Düzeni

Mevcut `dmc.Group`'u 3 elemanlı `flex` row'a dönüştür:

```python
# Mevcut (2 eleman):
dmc.Group(
    align="flex-start",
    gap="lg",
    children=[
        html.Div(style={"minWidth": "200px"}, children=kpis),
        _pie_card(fig),
    ],
),

# Yeni (3 eleman — boş alan doldu):
html.Div(
    style={
        "display": "flex",
        "gap": "20px",
        "alignItems": "flex-start",
        "flexWrap": "wrap",
    },
    children=[
        html.Div(style={"minWidth": "190px", "flexShrink": 0}, children=kpis),
        _pie_card(fig),
        status_panel,
    ],
),
```

**Değişiklik Özeti:**
- Sağdaki boş alan `status_panel` ile dolduruldu
- `status_panel`: Connected/Disconnected site sayıları (büyük rakam), utilization progress bar
- Düz `dmc.Group` yerine `flexWrap` destekli `html.Div` → küçük ekranlarda kırılma
- Veri değişimi yok: tüm sayılar zaten `agg` dict'inden geliyor

---

## UYGULAMA SIRASI (Checklist)

- [ ] **1. CSS Ekleme** — `assets/style.css`'e A1-A8 arası tüm class'ları ekle
- [ ] **2. `_kpi()` güncelle** — `dc_view.py` B1
- [ ] **3. `_section_title()` güncelle** — `dc_view.py` C1
- [ ] **4. `_chart_card()` güncelle** — `dc_view.py` D1
- [ ] **5. `_capacity_metric_row()` güncelle** — `dc_view.py` E1
- [ ] **6. Backup `_kpi_card()` güncelle** — `backup_panel.py` F1
- [ ] **7. Backup `_usage_pie()` güncelle** — `backup_panel.py` F2
- [ ] **8. Backup tablo className güncelle** — `backup_panel.py` F3
- [ ] **9. Zerto satır renkleri → Badge** — `backup_panel.py` F4
- [ ] **10. `_pie_card()` güncelle** — `backup_panel.py` F5
- [ ] **11. Physical Inventory chart'ları** — `dc_view.py` G1-G3
- [ ] **12. Network tablo stilleri** — `dc_view.py` H1-H3
- [ ] **13. Storage premium** — `dc_view.py` I1-I2
- [ ] **14. Chart global theme** — `charts.py` J1-J3
- [ ] **15. Summary Tab ikon & gradient** — `dc_view.py` K1-K2
- [ ] **16. Cluster selector premium** — `dc_view.py` L1
- [ ] **17. Capacity Trend chart premium** — `charts.py` M1-M3
- [ ] **18. Zerto panel boş alan → Status panel** — `backup_panel.py` N1-N2
- [ ] **19. Test** — Tüm tab'ları kontrol et

---

## DEĞİŞTİRİLECEK DOSYALAR ÖZET

| Dosya | Değişiklik Türü | Bölüm Sayısı |
|-------|:---:|:---:|
| `assets/style.css` | CSS class ekleme | 8 |
| `src/pages/dc_view.py` | Fonksiyon güncelleme | 12 |
| `src/components/backup_panel.py` | Fonksiyon güncelleme | 5 |
| `src/components/charts.py` | Global theme + tip güncelleme | 3 |
| `src/components/s3_panel.py` | KPI card güncelleme | 1 |

**Fotoğraflardan eklenen bölümler:**

| Fotoğraf | Bölge | Bölüm | Kapsandı mı? |
|---|---|---|---|
| 1 | Storage → Capacity Utilization Trend | M1–M3 | ✅ Eklendi |
| 2 | Backup → Zerto boş alan (sağ) | N1–N2 | ✅ Eklendi |
| 3 | Backup → Zerto tablosu | F3, F4 | ✅ Zaten vardı |
| 4 | Physical → Devices by Role | G1 | ✅ Zaten vardı |
| 5 | Physical → Manufacturer by Role | G2 | ✅ Zaten vardı |

**Toplam etkilenen fonksiyon:** ~32  
**Veri / API değişikliği:** ❌ Yok  
**Yeni dosya:** ❌ Yok
