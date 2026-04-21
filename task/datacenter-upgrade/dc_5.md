# DC Kartları — Sprint 5: Asimetri Düzeltme + Gelişmiş Animasyonlar

> **Kural:** Veri / API değişmez. Yalnızca UI / CSS / layout.

---

## SORUN ANALİZİ

### 1. Asimetrik Kart Boyutlandırması

**Kök neden:** Kart header'ında `dmc.Group(justify="space-between")` içinde sol taraf (DC adı) sabit genişlik kısıtlaması olmadan büyüyor. "DC16 – Türksat Macunköy DC" gibi uzun isimler `flex-shrink` olmadığı için "Details →" badge'ini alta itiyor. Bu hem header yüksekliğini değiştiriyor hem de tüm kartın iç orantısını bozuyor.

**İkinci neden:** `SimpleGrid` col'ları `align-items: stretch` kullanıyor ama kart içindeki flex yapı yüksekliğe göre ölçeklenmediğinden kartlar arasında dikey hizasızlık oluşuyor.

### 2. Eksik Premium Animasyonlar

Mevcut animasyonlar (dc_4.md):
- Kart giriş: slide-up + fade ✓
- Hover: lift + shimmer ✓
- Metric row hover ✓

Eksik olanlar (bu sprint):
- Footer barların 0'dan dolması
- Ring'in dönerek / pulse'layarak belirmesi
- DC başlığı ve satırların kart içinde sırayla gelmesi
- Sürekli nefes alan hover öncesi idle animasyonu
- Hover'da ring glow pulse
- Gradient accent border sweep animasyonu

---

## BÖLÜM A — ASİMETRİ DÜZELTMESİ

**Dosya:** `src/pages/datacenters.py` — `_dc_vault_card()` header bölümü (satır ~314–360)

### A1. Temel Problem: Flex Header Truncation Fix

**Mevcut header yapısı:**
```python
dmc.Group(
    justify="space-between",
    align="flex-start",
    children=[
        dmc.Group(gap="xs", ...   # sol: dot + title + badge
            dc_title (sınırsız genişlik)  ← SORUN
        ),
        dcc.Link("Details →")   # sağa sıkışıyor
    ]
)
```

**Düzeltme:** `dmc.Group` yerine `html.Div` + `display: flex` + `minWidth: 0` pattern'i. Bu CSS'in temel flex truncation çözümüdür.

```python
# Yeni header yapısı:
html.Div(
    style={
        "display": "flex",
        "justifyContent": "space-between",
        "alignItems": "flex-start",
        "gap": "8px",
    },
    children=[
        # Sol: pulse + title + location — minWidth:0 ile truncation aktive
        html.Div(
            style={"display": "flex", "gap": "6px", "alignItems": "flex-start", "minWidth": 0, "flex": 1},
            children=[
                dmc.Tooltip(
                    label=sla_service.format_availability_tooltip(sla_entry),
                    position="top",
                    withArrow=True,
                    children=html.Div(className=pulse_class, style={"marginTop": "5px", "flexShrink": 0}),
                ),
                html.Div(
                    style={"minWidth": 0, "flex": 1},  # ← kritik: minWidth:0
                    children=[
                        dmc.Tooltip(
                            label=dc_title,             # tam isim tooltip'te görünür
                            position="top",
                            withArrow=True,
                            openDelay=400,
                            children=dmc.Text(
                                dc_title,
                                fw=800,
                                size="md",
                                c="#2B3674",
                                className="dc-card-title",
                                style={
                                    "letterSpacing": "-0.01em",
                                    "lineHeight": 1.2,
                                    "overflow": "hidden",
                                    "textOverflow": "ellipsis",
                                    "whiteSpace": "nowrap",   # ← tek satır, ellipsis
                                },
                            ),
                        ),
                        location_badge,
                    ],
                ),
            ],
        ),
        # Sağ: Details badge — flexShrink:0 ile her zaman sağ üstte
        html.Div(
            style={"flexShrink": 0},
            children=dcc.Link(
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
        ),
    ],
)
```

**Sonuç:** DC ismi ne kadar uzun olursa olsun "Details →" her zaman sağ üst köşede sabit kalır. Uzun isimler `…` ile kısalır; tooltip ile tam isim görünür.

### A2. Header Sabit Yükseklik (opsiyonel ek güvence)

Header bölümüne `minHeight: "52px"` vermek, tüm kartlarda header alanının eşit olmasını garantiler:

```python
html.Div(
    style={
        ...
        "minHeight": "52px",   # başlık alanı her zaman aynı yükseklikte
    },
    ...
)
```

### A3. SimpleGrid — Equal Height Satırlar

`dmc.SimpleGrid` içinde her wrapper div'in `height: "100%"` olduğundan emin ol (mevcut kodda zaten var). Ek olarak `verticalSpacing="lg"` parametresi eklenir:

```python
dmc.SimpleGrid(
    cols=3,
    spacing="lg",
    verticalSpacing="lg",      # ← satırlar arası boşluk da sabit
    style={"padding": "0 32px"},
    children=[...]
)
```

---

## BÖLÜM B — CSS ANİMASYONLARI

**Dosya:** `assets/style.css`

### B1. Footer Progress Bar — scaleX(0→1) Fill Animasyonu

Mevcut bar'lar inline `width: X%` ile set ediliyor; sayfa yüklendiğinde direkt değerinde görünüyor. `scaleX` transform ile GPU-hızlandırmalı fill animasyonu:

```css
@keyframes bar-fill-in {
    from { transform: scaleX(0); }
    to   { transform: scaleX(1); }
}

.dc-bar-fill {
    transform-origin: left center;
    animation: bar-fill-in 0.9s cubic-bezier(0.22, 1, 0.36, 1) both;
}

/* Kart giriş sırasına göre bar delay */
.dc-card-n1  .dc-bar-fill { animation-delay: 0.40s; }
.dc-card-n2  .dc-bar-fill { animation-delay: 0.46s; }
.dc-card-n3  .dc-bar-fill { animation-delay: 0.52s; }
.dc-card-n4  .dc-bar-fill { animation-delay: 0.58s; }
.dc-card-n5  .dc-bar-fill { animation-delay: 0.64s; }
.dc-card-n6  .dc-bar-fill { animation-delay: 0.70s; }
.dc-card-n7  .dc-bar-fill { animation-delay: 0.76s; }
.dc-card-n8  .dc-bar-fill { animation-delay: 0.82s; }
.dc-card-n9  .dc-bar-fill { animation-delay: 0.88s; }
.dc-card-n10 .dc-bar-fill { animation-delay: 0.94s; }
.dc-card-n11 .dc-bar-fill { animation-delay: 1.00s; }
.dc-card-n12 .dc-bar-fill { animation-delay: 1.06s; }
```

**Python tarafında** `_mini_bar()` içindeki dolgu div'ine `className="dc-bar-fill"` eklenecek.

### B2. Ring — Pop-in Bouncy Rotate Animasyonu

RingProgress wrapper'ına sarmalayan div'e pop-in animasyonu:

```css
@keyframes ring-pop-in {
    0%   { opacity: 0; transform: scale(0.55) rotate(-90deg); }
    60%  { transform: scale(1.06) rotate(4deg); }
    80%  { transform: scale(0.97) rotate(-1deg); }
    100% { opacity: 1; transform: scale(1) rotate(0deg); }
}

.dc-ring-wrapper {
    animation: ring-pop-in 0.75s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}

/* Kart sırasına göre delay */
.dc-card-n1  .dc-ring-wrapper { animation-delay: 0.30s; }
.dc-card-n2  .dc-ring-wrapper { animation-delay: 0.36s; }
.dc-card-n3  .dc-ring-wrapper { animation-delay: 0.42s; }
.dc-card-n4  .dc-ring-wrapper { animation-delay: 0.48s; }
.dc-card-n5  .dc-ring-wrapper { animation-delay: 0.54s; }
.dc-card-n6  .dc-ring-wrapper { animation-delay: 0.60s; }
.dc-card-n7  .dc-ring-wrapper { animation-delay: 0.66s; }
.dc-card-n8  .dc-ring-wrapper { animation-delay: 0.72s; }
.dc-card-n9  .dc-ring-wrapper { animation-delay: 0.78s; }
.dc-card-n10 .dc-ring-wrapper { animation-delay: 0.84s; }
.dc-card-n11 .dc-ring-wrapper { animation-delay: 0.90s; }
.dc-card-n12 .dc-ring-wrapper { animation-delay: 0.96s; }
```

**Python tarafında** çift halka container `html.Div`'ine `className="dc-ring-wrapper"` eklenecek.

### B3. Hover'da Ring Glow Pulse

Kart hover olduğunda ring etrafında yumuşak glow nabzı:

```css
@keyframes ring-glow-pulse {
    0%, 100% { filter: drop-shadow(0 0 0px transparent); }
    50%       { filter: drop-shadow(0 0 10px rgba(255, 181, 71, 0.45)); }
}

.dc-vault-card:hover .dc-ring-wrapper {
    animation: ring-glow-pulse 1.6s ease-in-out infinite;
}
```

### B4. DC Başlık Metni — Slide-In (kart giriş sırasıyla)

```css
@keyframes title-slide-in {
    from {
        opacity: 0;
        transform: translateX(-10px);
        filter: blur(1px);
    }
    to {
        opacity: 1;
        transform: translateX(0);
        filter: blur(0);
    }
}

.dc-card-title {
    animation: title-slide-in 0.45s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.dc-card-n1  .dc-card-title { animation-delay: 0.12s; }
.dc-card-n2  .dc-card-title { animation-delay: 0.18s; }
.dc-card-n3  .dc-card-title { animation-delay: 0.24s; }
.dc-card-n4  .dc-card-title { animation-delay: 0.30s; }
.dc-card-n5  .dc-card-title { animation-delay: 0.36s; }
.dc-card-n6  .dc-card-title { animation-delay: 0.42s; }
.dc-card-n7  .dc-card-title { animation-delay: 0.48s; }
.dc-card-n8  .dc-card-title { animation-delay: 0.54s; }
.dc-card-n9  .dc-card-title { animation-delay: 0.60s; }
.dc-card-n10 .dc-card-title { animation-delay: 0.66s; }
.dc-card-n11 .dc-card-title { animation-delay: 0.72s; }
.dc-card-n12 .dc-card-title { animation-delay: 0.78s; }
```

### B5. Metric Row — Kart İçi Sıralı Giriş

Her kart içindeki 4 satır sırayla aşağıdan yukarı belirir:

```css
@keyframes metric-row-enter {
    from { opacity: 0; transform: translateX(-8px); }
    to   { opacity: 1; transform: translateX(0); }
}

.dc-metric-row {
    animation: metric-row-enter 0.35s ease-out both;
}

/* Satır sırası — Python'dan dc-row-1/2/3/4 class'ı eklenecek */
.dc-row-1 { animation-delay: var(--row-base-delay, 0.20s); }
.dc-row-2 { animation-delay: calc(var(--row-base-delay, 0.20s) + 0.05s); }
.dc-row-3 { animation-delay: calc(var(--row-base-delay, 0.20s) + 0.10s); }
.dc-row-4 { animation-delay: calc(var(--row-base-delay, 0.20s) + 0.15s); }

/* Her kartın base delay: card-n ile kombinle */
.dc-card-n1  .dc-metric-row { --row-base-delay: 0.16s; }
.dc-card-n2  .dc-metric-row { --row-base-delay: 0.22s; }
.dc-card-n3  .dc-metric-row { --row-base-delay: 0.28s; }
.dc-card-n4  .dc-metric-row { --row-base-delay: 0.34s; }
.dc-card-n5  .dc-metric-row { --row-base-delay: 0.40s; }
.dc-card-n6  .dc-metric-row { --row-base-delay: 0.46s; }
.dc-card-n7  .dc-metric-row { --row-base-delay: 0.52s; }
.dc-card-n8  .dc-metric-row { --row-base-delay: 0.58s; }
.dc-card-n9  .dc-metric-row { --row-base-delay: 0.64s; }
.dc-card-n10 .dc-metric-row { --row-base-delay: 0.70s; }
.dc-card-n11 .dc-metric-row { --row-base-delay: 0.76s; }
.dc-card-n12 .dc-metric-row { --row-base-delay: 0.82s; }
```

**Python tarafında** her `metric_row` `html.Div`'ine sıra numarasına göre `dc-row-{i+1}` class'ı eklenecek:
```python
html.Div(
    className=f"dc-metric-row dc-row-{i + 1}",
    ...
)
```

### B6. Accent Top Border — Ortadan Kenarlara Açılma Animasyonu

Şu an accent border kart yüklendiğinde direkt görünüyor. Ortadan açılarak gelmesi:

```css
@keyframes accent-sweep {
    from { clip-path: inset(0 50% 0 50%); }
    to   { clip-path: inset(0 0% 0 0%);   }
}

.dc-accent-healthy,
.dc-accent-moderate,
.dc-accent-high,
.dc-accent-idle {
    /* Not: border-top'u ::before pseudo-element'e taşıyoruz */
}

.dc-vault-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    border-radius: 12px 12px 0 0;
    animation: accent-sweep 0.6s cubic-bezier(0.22, 1, 0.36, 1) both;
    animation-delay: var(--card-accent-delay, 0.05s);
}

.dc-accent-healthy::before  { background: #05CD99; }
.dc-accent-moderate::before { background: #FFB547; }
.dc-accent-high::before     { background: #EE5D50; }
.dc-accent-idle::before     { background: #A3AED0; }

/* Card sırasına göre accent delay */
.dc-card-n1  .dc-vault-card  { --card-accent-delay: 0.04s; }
.dc-card-n2  .dc-vault-card  { --card-accent-delay: 0.10s; }
.dc-card-n3  .dc-vault-card  { --card-accent-delay: 0.16s; }
.dc-card-n4  .dc-vault-card  { --card-accent-delay: 0.22s; }
.dc-card-n5  .dc-vault-card  { --card-accent-delay: 0.28s; }
.dc-card-n6  .dc-vault-card  { --card-accent-delay: 0.34s; }
.dc-card-n7  .dc-vault-card  { --card-accent-delay: 0.40s; }
.dc-card-n8  .dc-vault-card  { --card-accent-delay: 0.46s; }
.dc-card-n9  .dc-vault-card  { --card-accent-delay: 0.52s; }
.dc-card-n10 .dc-vault-card  { --card-accent-delay: 0.58s; }
.dc-card-n11 .dc-vault-card  { --card-accent-delay: 0.64s; }
.dc-card-n12 .dc-vault-card  { --card-accent-delay: 0.70s; }
```

**Önemli:** `dc-accent-*` class'larındaki mevcut `border-top` CSS kuralları kaldırılacak (artık `::before` ile yapılıyor).

### B7. Idle Floating Animasyonu (Nefes Alma)

Hover olmadığında kartlar çok hafif yukarı-aşağı sallanır:

```css
@keyframes dc-idle-float {
    0%, 100% { transform: translateY(0px); }
    50%       { transform: translateY(-3px); }
}

/* Hover transform ile çakışmaması için :not(:hover) */
.dc-card-enter:not(:hover) {
    animation:
        dc-card-enter 0.60s cubic-bezier(0.22, 1, 0.36, 1) both,
        dc-idle-float 5s ease-in-out 1.5s infinite;
    /* dc-card-enter bittikten 1.5s sonra float başlar */
}

/* Her kart farklı faz offset ile sallanır — dalgalı görünüm */
.dc-card-n1:not(:hover)  { animation-delay: 0.04s, 1.50s; }
.dc-card-n2:not(:hover)  { animation-delay: 0.10s, 1.80s; }
.dc-card-n3:not(:hover)  { animation-delay: 0.16s, 2.10s; }
.dc-card-n4:not(:hover)  { animation-delay: 0.22s, 1.60s; }
.dc-card-n5:not(:hover)  { animation-delay: 0.28s, 1.90s; }
.dc-card-n6:not(:hover)  { animation-delay: 0.34s, 2.20s; }
.dc-card-n7:not(:hover)  { animation-delay: 0.40s, 1.70s; }
.dc-card-n8:not(:hover)  { animation-delay: 0.46s, 2.00s; }
.dc-card-n9:not(:hover)  { animation-delay: 0.52s, 2.30s; }
.dc-card-n10:not(:hover) { animation-delay: 0.58s, 1.55s; }
.dc-card-n11:not(:hover) { animation-delay: 0.64s, 1.85s; }
.dc-card-n12:not(:hover) { animation-delay: 0.70s, 2.15s; }
```

---

## BÖLÜM C — PYTHON TARAFINDA GEREKLİ KÜÇÜK DEĞİŞİKLİKLER

**Dosya:** `src/pages/datacenters.py`

### C1. Metric Row Class'ı — Sıra Numarası

```python
# Mevcut:
metric_rows = [
    html.Div(className="dc-metric-row", ...)
    for m in metrics
]

# Yeni:
metric_rows = [
    html.Div(className=f"dc-metric-row dc-row-{i + 1}", ...)
    for i, m in enumerate(metrics)
]
```

### C2. Footer Bar — `dc-bar-fill` Class'ı

`_mini_bar()` içindeki dolgu div'ine class ekle:

```python
# Mevcut inner fill div:
html.Div(
    style={
        "width": f"{min(pct, 100):.1f}%",
        ...
    },
)

# Yeni — className eklendi:
html.Div(
    className="dc-bar-fill",
    style={
        "width": f"{min(pct, 100):.1f}%",
        ...
    },
)
```

### C3. Ring Wrapper — `dc-ring-wrapper` Class'ı

Çift halka container div'ine class ekle:

```python
# Mevcut:
html.Div(
    style={"position": "relative", "width": "116px", "height": "116px"},
    children=[...]
)

# Yeni:
html.Div(
    className="dc-ring-wrapper",
    style={"position": "relative", "width": "116px", "height": "116px"},
    children=[...]
)
```

### C4. DC Başlık — `dc-card-title` Class'ı

```python
# Mevcut dmc.Text:
dmc.Text(dc_title, fw=800, size="md", c="#2B3674", style={...})

# Yeni:
dmc.Text(dc_title, fw=800, size="md", c="#2B3674", className="dc-card-title", style={...})
```

---

## ANİMASYON ZAMANLAMASINın ÖZET GÖRSELİ

```
Zaman →  0ms   100ms  200ms  300ms  400ms  500ms  600ms  700ms  800ms  900ms
Kart-1   [░░░░card-enter░░░░░░░]
          [title-slide-in]
                    [row-1]
                         [row-2]
                              [row-3]
                                   [row-4]
                                         [ring-pop-in]
                                                    [bar-fill-in]
                                                              [idle-float starts after 1.5s]
```

---

## UYGULAMA SIRASI (Checklist)

- [ ] **1. CSS — B6: Accent border → `::before` pseudo migrasyonu** (önce yap, breakage riski)
- [ ] **2. CSS — B1: `dc-bar-fill` + kart n-delay'leri**
- [ ] **3. CSS — B2: `dc-ring-wrapper` pop-in animasyonu**
- [ ] **4. CSS — B3: Ring hover glow pulse**
- [ ] **5. CSS — B4: `dc-card-title` slide-in**
- [ ] **6. CSS — B5: Metric row stagger + CSS custom property**
- [ ] **7. CSS — B7: Idle float animasyonu**
- [ ] **8. Python — A1: Header flex truncation fix**
- [ ] **9. Python — A2: Header minHeight güvencesi**
- [ ] **10. Python — A3: SimpleGrid verticalSpacing**
- [ ] **11. Python — C1: Metric row `dc-row-N` class**
- [ ] **12. Python — C2: `dc-bar-fill` class**
- [ ] **13. Python — C3: `dc-ring-wrapper` class**
- [ ] **14. Python — C4: `dc-card-title` class**
- [ ] **15. Test** — 12+ kart görünümü, truncation, animasyon sıralaması

---

## DEĞİŞTİRİLEN DOSYALAR

| Dosya | Değişiklik | Bölüm |
|---|---|---|
| `assets/style.css` | 7 yeni animasyon, pseudo-element migration, CSS custom property | B1–B7 |
| `src/pages/datacenters.py` | Header truncation fix, class ekleme | A1–A3, C1–C4 |

**Veri / API değişikliği:** ❌ Sıfır  
**Yeni dosya:** ❌ Yok
