# Data Centers Sayfası — Apple / Google Seviyesi Premium Sprint

> **Kural:** Hiçbir veri, API, backend değişmez.  
> **Hedef:** Sayfayı açtığında "vay be" dedirtmek.

---

## MEVCUT SORUNLAR

| # | Sorun | Etki |
|---|---|---|
| 1 | Kartlar fade/slide animasyonsuz belirir | "Hazır sayfa" hissi yok |
| 2 | Tüm kartlar aynı görünür — kullanım seviyesi renklere yansımaz | Bilgi taşımayan görsellik |
| 3 | Power ring (RingProgress) ince ve düz | Premium his vermiyor |
| 4 | CPU/RAM verisi `stats`'ta var ama kartlarda hiç gösterilmiyor | Kritik metrik kayıp |
| 5 | Sayfa arka planı düz beyaz/açık gri | Derinlik yok |
| 6 | Header altında aggregate metrik yok | Sayfa açılışında oryantasyon eksik |
| 7 | Location sadece küçük gri yazı | Coğrafi bağlam zayıf |
| 8 | "Details →" badge hover animasyonu yok | Interactivity hissi eksik |
| 9 | Metric satırları hover'da hiç değişmiyor | Durağan his |
| 10 | Pulse dot rengi sabit yeşil — SLA durumuna göre değişmiyor | Anlamlı sinyal eksik |

---

## A. CSS — AURORA ARKA PLAN + GİRİŞ ANİMASYONLARI

**Dosya:** `assets/style.css`

### A1. Sayfa Aurora Arka Planı

Sayfanın arkasına yavaş hareket eden çok katmanlı radial gradient aurora efekti:

```css
/* ── Aurora Arka Plan ── */
@keyframes aurora-shift {
    0%   { transform: translate(0%, 0%)   scale(1); }
    33%  { transform: translate(3%, -4%)  scale(1.05); }
    66%  { transform: translate(-2%, 3%)  scale(0.97); }
    100% { transform: translate(0%, 0%)   scale(1); }
}

.dc-aurora-bg {
    position: fixed;
    inset: 0;
    z-index: -1;
    overflow: hidden;
    pointer-events: none;
}

.dc-aurora-bg::before {
    content: '';
    position: absolute;
    width: 120%;
    height: 120%;
    top: -10%;
    left: -10%;
    background:
        radial-gradient(ellipse 55% 45% at 15% 5%,  rgba(67, 24, 255, 0.07) 0%, transparent 55%),
        radial-gradient(ellipse 50% 40% at 85% 90%, rgba(5, 205, 153, 0.06)  0%, transparent 50%),
        radial-gradient(ellipse 40% 35% at 70% 10%, rgba(117, 81, 255, 0.05) 0%, transparent 45%),
        radial-gradient(ellipse 60% 50% at 30% 80%, rgba(0, 219, 227, 0.04)  0%, transparent 55%),
        #F4F7FE;
    animation: aurora-shift 18s ease-in-out infinite alternate;
}
```

### A2. Kart Giriş Animasyonu — Slide-Up + Scale-In

```css
@keyframes dc-card-enter {
    from {
        opacity: 0;
        transform: translateY(32px) scale(0.96);
        filter: blur(2px);
    }
    to {
        opacity: 1;
        transform: translateY(0) scale(1);
        filter: blur(0);
    }
}

.dc-card-enter {
    animation: dc-card-enter 0.60s cubic-bezier(0.22, 1, 0.36, 1) both;
}

/* 12 kart için stagger delay */
.dc-card-n1  { animation-delay: 0.04s; }
.dc-card-n2  { animation-delay: 0.10s; }
.dc-card-n3  { animation-delay: 0.16s; }
.dc-card-n4  { animation-delay: 0.22s; }
.dc-card-n5  { animation-delay: 0.28s; }
.dc-card-n6  { animation-delay: 0.34s; }
.dc-card-n7  { animation-delay: 0.40s; }
.dc-card-n8  { animation-delay: 0.46s; }
.dc-card-n9  { animation-delay: 0.52s; }
.dc-card-n10 { animation-delay: 0.58s; }
.dc-card-n11 { animation-delay: 0.64s; }
.dc-card-n12 { animation-delay: 0.70s; }
```

### A3. Kart Hover — Elit Lift + Glow

```css
/* Üst gradient çizgi hover animasyonu */
.dc-vault-card::after {
    content: '';
    position: absolute;
    top: 0;
    left: 5%;
    right: 5%;
    height: 2px;
    border-radius: 0 0 4px 4px;
    opacity: 0;
    transition: opacity 0.3s ease, left 0.3s ease, right 0.3s ease;
    /* Rengini Python'dan inline style ile override edeceğiz */
    background: linear-gradient(90deg, #4318FF 0%, #7551FF 50%, #05CD99 100%);
}

.dc-vault-card:hover::after {
    opacity: 1;
    left: 0%;
    right: 0%;
}

.dc-vault-card {
    position: relative;
    overflow: hidden;
    transition:
        transform 0.32s cubic-bezier(0.22, 1, 0.36, 1),
        box-shadow 0.32s cubic-bezier(0.22, 1, 0.36, 1),
        border-color 0.32s ease;
    cursor: pointer;
}

.dc-vault-card:hover {
    transform: translateY(-8px) scale(1.005);
    box-shadow:
        0px 32px 64px rgba(67, 24, 255, 0.16),
        0px 12px 24px rgba(67, 24, 255, 0.08),
        0px 4px 8px  rgba(0, 0, 0, 0.04) !important;
    border-color: rgba(67, 24, 255, 0.15) !important;
}
```

### A4. Kart İçi Shimmer Efekti (Hover'da süpürme ışık çizgisi)

```css
@keyframes dc-shimmer {
    0%   { left: -120%; }
    100% { left: 120%;  }
}

.dc-vault-card .dc-shimmer {
    position: absolute;
    top: 0;
    left: -120%;
    width: 80%;
    height: 100%;
    background: linear-gradient(
        105deg,
        transparent 40%,
        rgba(255, 255, 255, 0.18) 50%,
        transparent 60%
    );
    pointer-events: none;
    z-index: 1;
    transition: none;
}

.dc-vault-card:hover .dc-shimmer {
    animation: dc-shimmer 0.65s ease-in-out;
}
```

### A5. Metric Row Hover

```css
.dc-metric-row {
    border-radius: 8px;
    padding: 4px 6px;
    margin: 0 -6px;
    transition: background-color 0.18s ease, transform 0.18s ease;
}

.dc-metric-row:hover {
    background-color: rgba(67, 24, 255, 0.04);
    transform: translateX(3px);
}
```

### A6. "Details" Badge → Premium Arrow Animasyonu

```css
.dc-details-badge {
    transition: all 0.22s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.dc-details-badge:hover {
    background: rgba(67, 24, 255, 0.12) !important;
    transform: translateX(3px);
    box-shadow: 0 0 0 1px rgba(67, 24, 255, 0.2);
}
```

### A7. Pulse Dot — SLA Renk Varyantları

```css
/* Mevcut: sabit yeşil */
.dc-pulse-dot { background-color: #05CD99; }

/* Yeni: SLA'ya göre renkler */
.dc-pulse-dot-ok       { background-color: #05CD99; }  /* > 99.5% */
.dc-pulse-dot-warn     { background-color: #FFB547; }  /* 99 – 99.5% */
.dc-pulse-dot-critical { background-color: #EE5D50; }  /* < 99% */
```

### A8. Summary KPI Cards Entrance

```css
@keyframes kpi-slide-down {
    from { opacity: 0; transform: translateY(-16px); }
    to   { opacity: 1; transform: translateY(0); }
}

.dc-summary-kpi {
    animation: kpi-slide-down 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.dc-summary-kpi:nth-child(1) { animation-delay: 0.00s; }
.dc-summary-kpi:nth-child(2) { animation-delay: 0.06s; }
.dc-summary-kpi:nth-child(3) { animation-delay: 0.12s; }
.dc-summary-kpi:nth-child(4) { animation-delay: 0.18s; }
.dc-summary-kpi:nth-child(5) { animation-delay: 0.24s; }
```

### A9. Gradient Accent Top Border (Renk: Kullanım Durumuna Göre)

Her kart tipi için renk sınıfı:

```css
.dc-accent-healthy  { border-top: 3px solid #05CD99 !important; }
.dc-accent-moderate { border-top: 3px solid #FFB547 !important; }
.dc-accent-high     { border-top: 3px solid #EE5D50 !important; }
.dc-accent-idle     { border-top: 3px solid #A3AED0 !important; }
```

---

## B. SAYFA LAYOUT — AURORA ARKA PLAN + HEADER

**Dosya:** `src/pages/datacenters.py` — `build_datacenters()` (satır 230–408)

### B1. Aurora Arka Plan Div

`build_datacenters()` içindeki `return html.Div([...])` listesinin başına ekle:

```python
# Aurora arka plan (fixed, z-index: -1)
html.Div(className="dc-aurora-bg"),
```

### B2. Header Alt Gradient Çizgi

Mevcut header `dmc.Paper`'ına `borderBottom` yerine:

```python
# Mevcut:
"boxShadow": "0 4px 24px rgba(67, 24, 255, 0.07), 0 1px 4px rgba(0, 0, 0, 0.04)",

# Yeni — ek:
"borderBottom": "none",
"background": "rgba(255, 255, 255, 0.88)",
"backdropFilter": "blur(20px)",
"WebkitBackdropFilter": "blur(20px)",
"boxShadow": (
    "0 4px 24px rgba(67, 24, 255, 0.08), "
    "0 1px 4px rgba(0,0,0,0.03), "
    "0 1px 0 rgba(67, 24, 255, 0.10)"  # alt ince çizgi
),
```

---

## C. SUMMARY KPI STRIP — Header İle Grid Arasına

**Dosya:** `src/pages/datacenters.py`

Header `dmc.Paper` ile `SimpleGrid` arasına yeni bölüm eklenir.

### C1. Aggregate Hesaplamalar

`build_datacenters()` içinde datacenters listesi çekildikten sonra:

```python
total_hosts  = sum(dc.get("host_count",  0) for dc in datacenters)
total_vms    = sum(dc.get("vm_count",    0) for dc in datacenters)
total_clusters = sum(dc.get("cluster_count", 0) for dc in datacenters)
total_power  = sum(
    float(dc.get("stats", {}).get("total_energy_kw", 0) or 0)
    for dc in datacenters
)
avg_cpu      = (
    sum(float(dc.get("stats", {}).get("used_cpu_pct", 0) or 0) for dc in datacenters)
    / len(datacenters)
    if datacenters else 0.0
)
avg_ram      = (
    sum(float(dc.get("stats", {}).get("used_ram_pct", 0) or 0) for dc in datacenters)
    / len(datacenters)
    if datacenters else 0.0
)
```

### C2. Summary Strip Bileşeni

```python
def _summary_kpi(icon, label, value, color="indigo", idx=1):
    return html.Div(
        className="dc-summary-kpi nexus-card",
        style={
            "padding": "16px 20px",
            "display": "flex",
            "alignItems": "center",
            "gap": "14px",
            "borderRadius": "14px",
            "background": "rgba(255,255,255,0.90)",
            "backdropFilter": "blur(12px)",
            "WebkitBackdropFilter": "blur(12px)",
            "boxShadow": "0 2px 12px rgba(67,24,255,0.06)",
            "border": "1px solid rgba(255,255,255,0.7)",
            "flex": 1,
        },
        children=[
            dmc.ThemeIcon(
                size=44,
                radius="xl",
                variant="light",
                color=color,
                children=DashIconify(icon=icon, width=22),
            ),
            html.Div([
                html.Div(label, style={
                    "fontSize": "0.7rem",
                    "fontWeight": 700,
                    "color": "#A3AED0",
                    "textTransform": "uppercase",
                    "letterSpacing": "0.07em",
                }),
                html.Div(str(value), style={
                    "fontSize": "1.45rem",
                    "fontWeight": 900,
                    "color": "#2B3674",
                    "letterSpacing": "-0.02em",
                    "lineHeight": 1.1,
                    "fontVariantNumeric": "tabular-nums",
                }),
            ]),
        ],
    )

summary_strip = html.Div(
    style={
        "display": "flex",
        "gap": "12px",
        "padding": "0 32px",
        "marginBottom": "24px",
        "flexWrap": "wrap",
    },
    children=[
        _summary_kpi("solar:server-bold-duotone",      "Active DCs",  len(datacenters),        "indigo", 1),
        _summary_kpi("solar:server-minimalistic-bold-duotone", "Total Hosts", f"{total_hosts:,}", "orange", 2),
        _summary_kpi("solar:laptop-bold-duotone",      "Total VMs",   f"{total_vms:,}",         "teal",   3),
        _summary_kpi("solar:box-bold-duotone",         "Clusters",    f"{total_clusters:,}",    "grape",  4),
        _summary_kpi("solar:bolt-bold-duotone",        "Total Power", f"{total_power:.1f} kW",  "yellow", 5),
    ],
)
```

---

## D. `_dc_vault_card()` TAM YENİDEN TASARIMI

**Dosya:** `src/pages/datacenters.py` — `_dc_vault_card()` (satır 20–227)

### D1. Yeni Değişkenler

```python
def _dc_vault_card(dc, sla_entry=None):
    dc_title     = format_dc_display_name(dc.get("name"), dc.get("description"))
    stats        = dc.get("stats") or {}
    ibm_kw       = float(stats.get("ibm_kw", 0.0) or 0.0)
    total_kw     = float(stats.get("total_energy_kw", 0.0) or 0.0)
    cpu_pct      = float(stats.get("used_cpu_pct", 0.0) or 0.0)
    ram_pct      = float(stats.get("used_ram_pct", 0.0) or 0.0)
    power_ratio  = round((ibm_kw / total_kw * 100) if total_kw > 0 else 0.0, 1)
    remaining    = max(0.0, 100.0 - power_ratio)

    # SLA rengi: pulse dot için
    sla_pct = float((sla_entry or {}).get("availability_pct", 100.0) or 100.0)
    if sla_pct >= 99.5:
        pulse_class  = "dc-pulse-dot dc-pulse-dot-ok"
        accent_class = "dc-accent-healthy"
        ring_color   = "#05CD99"
    elif sla_pct >= 99.0:
        pulse_class  = "dc-pulse-dot dc-pulse-dot-warn"
        accent_class = "dc-accent-moderate"
        ring_color   = "#FFB547"
    else:
        pulse_class  = "dc-pulse-dot dc-pulse-dot-critical"
        accent_class = "dc-accent-high"
        ring_color   = "#EE5D50"

    # Boşta olan DC (total_kw == 0)
    if total_kw == 0:
        accent_class = "dc-accent-idle"
        ring_color   = "#A3AED0"
```

### D2. Location Badge — Colored Pill

Mevcut `dmc.Text(dc.get("location"), size="xs", c="#A3AED0")` yerine:

```python
location_badge = dmc.Badge(
    dmc.Group(
        gap=4,
        align="center",
        children=[
            DashIconify(icon="solar:map-point-bold-duotone", width=11),
            dc.get("location", "—"),
        ],
    ),
    variant="light",
    color="indigo",
    radius="xl",
    size="xs",
    style={
        "textTransform": "none",
        "fontWeight": 600,
        "padding": "2px 8px",
        "letterSpacing": 0,
    },
)
```

### D3. Metric Rows — Hover Sınıfı + Büyük Sayılar

```python
metric_rows = [
    html.Div(
        className="dc-metric-row",
        children=dmc.Group(
            justify="space-between",
            align="center",
            children=[
                dmc.Group(
                    gap="xs",
                    align="center",
                    children=[
                        dmc.ThemeIcon(
                            size="sm",
                            variant="light",
                            color=m["color"],
                            radius="md",
                            children=DashIconify(icon=m["icon"], width=14),
                        ),
                        dmc.Text(m["label"], size="sm", c="#A3AED0", fw=500),
                    ],
                ),
                dmc.Text(
                    str(m["value"]),
                    fw=800,
                    size="sm",
                    c="#2B3674",
                    style={
                        "fontVariantNumeric": "tabular-nums",
                        "letterSpacing": "-0.01em",
                    },
                ),
            ],
        ),
    )
    for m in metrics
]
```

### D4. Power Ring — Kalın + CPU/RAM Arklı Çift Halka

DMC `RingProgress` ile IBM power + CPU ikili halka. IBM power dışta (thick), CPU ince içte:

```python
# Power dial: Dışta IBM power, içte CPU
power_dial = dmc.Stack(
    gap=4,
    align="center",
    children=[
        html.Div(
            style={"position": "relative", "width": "116px", "height": "116px"},
            children=[
                # Dış halka: IBM Power oranı
                dmc.RingProgress(
                    size=116,
                    thickness=11,
                    roundCaps=True,
                    sections=[
                        {"value": power_ratio, "color": "#FFB547",
                         "tooltip": f"IBM Power: {power_ratio:.0f}%"},
                        {"value": remaining,   "color": "rgba(67,24,255,0.12)"},
                    ],
                    label=None,
                    style={"position": "absolute", "top": 0, "left": 0},
                ),
                # İç halka: CPU kullanımı (daha küçük, içte)
                dmc.RingProgress(
                    size=84,
                    thickness=9,
                    roundCaps=True,
                    sections=[
                        {"value": cpu_pct, "color": "#4318FF",
                         "tooltip": f"CPU: {cpu_pct:.0f}%"},
                        {"value": max(0, 100 - cpu_pct), "color": "rgba(67,24,255,0.08)"},
                    ],
                    label=html.Div(
                        style={"textAlign": "center"},
                        children=[
                            dmc.Text(
                                f"{power_ratio:.0f}%",
                                fw=900,
                                size="md",
                                c="#2B3674",
                                style={"lineHeight": 1, "letterSpacing": "-0.02em"},
                            ),
                            dmc.Text("IBM", size="xs", c="dimmed",
                                     style={"lineHeight": 1, "marginTop": "2px"}),
                        ],
                    ),
                    style={
                        "position": "absolute",
                        "top": "50%",
                        "left": "50%",
                        "transform": "translate(-50%, -50%)",
                    },
                ),
            ],
        ),
        dmc.Text("Power", size="xs", fw=700, c="#A3AED0"),
        dmc.Text(
            f"{total_kw:.1f} kW",
            size="xs",
            c="dimmed",
            style={"fontVariantNumeric": "tabular-nums", "marginTop": "-2px"},
        ),
    ],
)
```

### D5. CPU / RAM Footer Progress Bars

Kartın en altına, metrik satırlar ile power ring'in altına eklenir:

```python
def _mini_bar(label, pct, color):
    """Küçük inline progress bar."""
    bar_color = color if pct < 75 else "#FFB547" if pct < 90 else "#EE5D50"
    return html.Div(
        style={"flex": 1},
        children=[
            html.Div(
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "marginBottom": "4px",
                },
                children=[
                    html.Span(label, style={
                        "fontSize": "0.68rem",
                        "fontWeight": 700,
                        "color": "#A3AED0",
                        "textTransform": "uppercase",
                        "letterSpacing": "0.06em",
                    }),
                    html.Span(f"{pct:.0f}%", style={
                        "fontSize": "0.68rem",
                        "fontWeight": 800,
                        "color": bar_color,
                    }),
                ],
            ),
            html.Div(
                style={
                    "height": "5px",
                    "borderRadius": "3px",
                    "background": "#EEF2FF",
                    "overflow": "hidden",
                },
                children=html.Div(
                    style={
                        "width": f"{min(pct, 100):.1f}%",
                        "height": "100%",
                        "borderRadius": "3px",
                        "background": f"linear-gradient(90deg, {color} 0%, {bar_color} 100%)",
                        "transition": "width 0.8s cubic-bezier(0.22, 1, 0.36, 1)",
                    },
                ),
            ),
        ],
    )

resource_footer = html.Div(
    style={
        "display": "flex",
        "gap": "12px",
        "paddingTop": "12px",
        "borderTop": "1px solid rgba(227, 234, 252, 0.8)",
        "marginTop": "4px",
    },
    children=[
        _mini_bar("CPU", cpu_pct, "#4318FF"),
        _mini_bar("RAM", ram_pct, "#7551FF"),
    ],
)
```

### D6. Shimmer Div + Accent Class + Tam Kart

Mevcut `dmc.Paper` yerine yeni tam kart yapısı:

```python
return dmc.Paper(
    className=f"dc-vault-card {accent_class}",
    p="lg",
    radius="lg",
    style={
        "background": "rgba(255, 255, 255, 0.88)",
        "backdropFilter": "blur(16px)",
        "WebkitBackdropFilter": "blur(16px)",
        "boxShadow": (
            "0 2px 16px rgba(67, 24, 255, 0.07), "
            "0 1px 4px rgba(0,0,0,0.04)"
        ),
        "border": "1px solid rgba(255, 255, 255, 0.75)",
        "height": "100%",
        "display": "flex",
        "flexDirection": "column",
        "gap": "12px",
        "overflow": "hidden",
        "position": "relative",
    },
    children=[
        # Shimmer overlay (CSS hover ile aktive olur)
        html.Div(className="dc-shimmer"),

        # Header: DC adı + location + Details badge
        dmc.Group(
            justify="space-between",
            align="flex-start",
            children=[
                dmc.Group(
                    gap="xs",
                    align="flex-start",
                    children=[
                        dmc.Tooltip(
                            label=sla_service.format_availability_tooltip(sla_entry),
                            position="top",
                            withArrow=True,
                            children=html.Div(
                                className=pulse_class,
                                style={"marginTop": "5px"},
                            ),
                        ),
                        dmc.Stack(
                            gap=3,
                            children=[
                                dmc.Text(dc_title, fw=800, size="md", c="#2B3674",
                                         style={"letterSpacing": "-0.01em", "lineHeight": 1.2}),
                                location_badge,
                            ],
                        ),
                    ],
                ),
                dcc.Link(
                    dmc.Badge(
                        "Details →",
                        className="dc-details-badge",
                        variant="light",
                        color="indigo",
                        size="sm",
                        radius="xl",
                        style={"cursor": "pointer", "textDecoration": "none"},
                    ),
                    href=f"/datacenter/{dc['id']}",
                    style={"textDecoration": "none"},
                ),
            ],
        ),

        # İnce divider
        html.Div(style={"height": "1px", "background": "rgba(227, 234, 252, 0.8)"}),

        # Ana içerik: Metrik satırlar | Divider | Power ring
        html.Div(
            style={
                "display": "flex",
                "flexDirection": "row",
                "alignItems": "stretch",
                "gap": "14px",
                "flex": 1,
            },
            children=[
                dmc.Stack(gap=2, style={"flex": 1}, children=metric_rows),
                html.Div(
                    style={
                        "width": "1px",
                        "background": "linear-gradient(to bottom, transparent, rgba(67,24,255,0.10), transparent)",
                        "alignSelf": "stretch",
                        "flexShrink": 0,
                    }
                ),
                html.Div(
                    style={"display": "flex", "alignItems": "center", "justifyContent": "center"},
                    children=[power_dial],
                ),
            ],
        ),

        # CPU / RAM footer
        resource_footer,
    ],
)
```

---

## E. KART GRID — Wrapper + Stagger

**Dosya:** `src/pages/datacenters.py` — `build_datacenters()` (satır 391–407)

### E1. SimpleGrid → Her Karta Wrapper ile Stagger

```python
# Mevcut:
dmc.SimpleGrid(
    cols=3,
    spacing="lg",
    style={"padding": "0 32px"},
    children=[
        _dc_vault_card(dc, sla_by_dc.get(dc.get("id"))) for dc in datacenters
    ],
)

# Yeni:
dmc.SimpleGrid(
    cols=3,
    spacing="lg",
    style={"padding": "0 32px"},
    children=[
        html.Div(
            className=f"dc-card-enter dc-card-n{min(i+1, 12)}",
            style={"height": "100%"},
            children=_dc_vault_card(
                dc,
                sla_by_dc.get(dc.get("id")) or sla_by_dc.get(str(dc.get("id", "")).upper()),
            ),
        )
        for i, dc in enumerate(datacenters)
    ],
)
```

---

## F. TAM SAYFA LAYOUT SIRASI

`build_datacenters()` return içeriği şu sırayla olacak:

```python
return html.Div([
    dcc.Store(id="datacenters-export-store", ...),
    dcc.Download(id="datacenters-export-download"),

    # 1. Aurora arka plan
    html.Div(className="dc-aurora-bg"),

    # 2. Header
    dmc.Paper(...),   # mevcut, B2 güncellemeleri ile

    # 3. Summary KPI Strip
    summary_strip,    # C bölümü

    # 4. DC Kart Grid
    (
        dmc.SimpleGrid(...)  # E1 ile stagger wrapper'lı
        if ds("sec:datacenters:grid")
        else dmc.Alert(...)
    ),
])
```

---

## UYGULAMA SIRASI (Checklist)

- [ ] **1. CSS — Aurora arka plan** — `assets/style.css` A1
- [ ] **2. CSS — Kart giriş animasyonu + stagger delays** — `assets/style.css` A2
- [ ] **3. CSS — Hover lift + shimmer + border** — `assets/style.css` A3–A4
- [ ] **4. CSS — Metric row hover** — `assets/style.css` A5
- [ ] **5. CSS — Details badge hover** — `assets/style.css` A6
- [ ] **6. CSS — Pulse dot renk varyantları** — `assets/style.css` A7
- [ ] **7. CSS — Summary KPI strip animasyonu** — `assets/style.css` A8
- [ ] **8. CSS — Accent top border class'ları** — `assets/style.css` A9
- [ ] **9. Python — `build_datacenters()` aurora div + B2 header** — `datacenters.py` B
- [ ] **10. Python — Aggregate hesaplamalar** — `datacenters.py` C1
- [ ] **11. Python — `_summary_kpi()` + `summary_strip`** — `datacenters.py` C2
- [ ] **12. Python — `_dc_vault_card()` yeni değişkenler + SLA renk** — `datacenters.py` D1
- [ ] **13. Python — Location badge** — `datacenters.py` D2
- [ ] **14. Python — Metric rows hover class** — `datacenters.py` D3
- [ ] **15. Python — Çift halka power dial** — `datacenters.py` D4
- [ ] **16. Python — `_mini_bar()` + footer** — `datacenters.py` D5
- [ ] **17. Python — Shimmer div + accent class tam kart** — `datacenters.py` D6
- [ ] **18. Python — SimpleGrid stagger wrapper** — `datacenters.py` E1
- [ ] **19. Python — Layout sırası** — `datacenters.py` F
- [ ] **20. Test** — Tüm kartları incele, animasyon sıralamalarını kontrol et

---

## DEĞİŞTİRİLEN DOSYALAR

| Dosya | Değişiklik | Bölüm |
|---|---|---|
| `assets/style.css` | Aurora BG, giriş animasyonları, hover efektler, pulse dot varyantları | A1–A9 |
| `src/pages/datacenters.py` | Kart redesign, summary strip, stagger wrapper, aurora div | B–F |

**Veri / API değişikliği:** ❌ Sıfır  
**Yeni dosya:** ❌ Yok
