# 🎯 Detail Pages Header Upgrade — Task Plan

**Yayın Tarihi:** 2 Mart 2026, 04:12
**Hazırlayan:** Senior Developer Organizer
**Kapsam:** `dc_view.py`, `cluster_view.py`, `customer_view.py`
**Yeni Bileşen:** `src/components/header.py` → `create_detail_header()`
**Durum:** ⏳ Executor uygulaması bekleniyor

---

## Mevcut Durum Analizi — 3 Sayfanın Header'ı

### `dc_view.py` (Satır 68-81)
```python
html.Div(
    className="nexus-glass",          # sticky, z-index sorunlu
    children=[
        dcc.Link(back_arrow, href="/datacenters"),
        html.H1(dc_name, color="#2B3674", fontSize="1.8rem"),  # düz, gradient yok
        html.Span(f"Region: {dc_loc}  |  Report: {start}–{end}"),  # düz metin
    ],
    style={"padding": "20px 30px", "marginBottom": "20px", "display": "flex"}
)
# Sekmeler: dmc.Tabs → Header'dan AYRI, aşağıda kaydırılıyor
```

### `cluster_view.py` (Satır 16-30)
```python
html.Div(
    className="nexus-glass",          # aynı sorunlar
    children=[
        dcc.Link(back_arrow, href="/datacenters"),
        html.H1(f"Cluster: {cluster_id}", color="#2B3674", fontSize="1.5rem"),
        # Lokasyon bilgisi YOK
        # Tarih bilgisi YOK
    ]
)
# Sekme YOK (placeholder sayfası)
```

### `customer_view.py` (Satır 42-49)
```python
html.Div(
    className="nexus-glass",
    children=[
        html.H1("Customer View", fontSize="1.5rem"),  # Back butonu YOK
        html.P(f"Report period: {start}–{end}"),       # düz metin
    ]
)
# Sekmeler: dmc.Tabs → Header'dan AYRI (94-500. satır arasında)
```

### 3 Sayfanın Ortak Sorunları
| Sorun | dc_view | cluster_view | customer_view |
|-------|---------|--------------|---------------|
| `nexus-glass` sticky z-index çakışması | ✗ | ✗ | ✗ |
| `html.H1` — gradyan tipografi yok | ✗ | ✗ | ✗ |
| Tarih pill badge yok | ✗ | ✗ | ✗ |
| Region/Lokasyon badge yok | ✗ | ✗ | — |
| Sekmeler header içinde sticky değil | ✗ | — | ✗ |
| Kod tekrarı (3x benzer yapı) | ✗ | ✗ | ✗ |

---

## Task 1: Contextual Command Center (Executive Detail Header)

### Mimari Karar: Nereye koyulacak?

`create_detail_header()` → **`src/components/header.py`** (yeni dosya)

**Neden `components/header.py` ve `app.py` değil?**
- `app.py` callback ve Dash uygulama başlatma için — UI bileşenleri oraya **gitmez**.
- `src/components/` zaten `charts.py`, `sidebar.py` barındırıyor — header oraya aittir.
- Her sayfa `from src.components.header import create_detail_header` ile çağırır — tek import, sıfır tekrar.

---

### DEĞİŞİKLİK 1 — Yeni Dosya: `src/components/header.py`

```python
"""
Shared detail page header component.

Kullanım:
    from src.components.header import create_detail_header

    header = create_detail_header(
        title="DC11",
        back_href="/datacenters",
        back_label="Data Centers",
        subtitle_badge="📍 Istanbul",
        subtitle_color="indigo",
        time_range=tr,
        tabs=dmc.Tabs(...),          # opsiyonel — None bırakılabilir
    )
"""
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify


def create_detail_header(
    title: str,
    back_href: str,
    back_label: str = "Back",
    subtitle_badge: str | None = None,
    subtitle_color: str = "indigo",
    time_range: dict | None = None,
    icon: str = "solar:server-square-bold-duotone",
    tabs=None,
) -> dmc.Paper:
    """
    Evrensel Executive Detail Header — glassmorphism + sticky + sekmeler.

    Args:
        title:          Sayfa başlığı (örn: "DC11", "Cluster: C01", "Customer View")
        back_href:      Back butonu linki (örn: "/datacenters")
        back_label:     Tooltip / Back butonu yanındaki metin (görünmez, erişilebilirlik için)
        subtitle_badge: Region/lokasyon/bağlam badge metni (örn: "📍 Istanbul")
                        None ise badge gösterilmez.
        subtitle_color: Badge rengi (Mantine renk adı veya hex — varsayılan "indigo")
        time_range:     {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"} veya None
        icon:           Başlık solundaki ikon (DashIconify icon adı)
        tabs:           dmc.Tabs bileşeni — varsa header içine entegre edilir (sticky sekme).
                        None ise sekme alanı gösterilmez.

    Returns:
        dmc.Paper: Glassmorphism + sticky konteynır
    """
    tr = time_range or {}
    start = tr.get("start", "")
    end   = tr.get("end", "")

    # ── Back Butonu ─────────────────────────────────────────────────────
    back_button = dcc.Link(
        dmc.ActionIcon(
            DashIconify(icon="solar:arrow-left-linear", width=20),
            variant="light",
            color="indigo",
            size="lg",
            radius="md",
            title=f"Back to {back_label}",
        ),
        href=back_href,
        style={"textDecoration": "none"},
    )

    # ── Başlık Satırı (İkon + Gradyan H2 + Region Badge) ────────────────
    title_children = [
        DashIconify(icon=icon, width=22, color="#4318FF"),
        html.H2(
            title,
            style={
                "margin": 0,
                "fontWeight": 900,
                "letterSpacing": "-0.02em",
                "lineHeight": 1.2,
                "fontSize": "1.6rem",
                "background": "linear-gradient(90deg, #1a1b41 0%, #4318FF 100%)",
                "WebkitBackgroundClip": "text",
                "WebkitTextFillColor": "transparent",
                "backgroundClip": "text",
            },
        ),
    ]

    # Region/Bağlam Badge (opsiyonel)
    if subtitle_badge:
        title_children.append(
            dmc.Badge(
                subtitle_badge,
                variant="light",
                color=subtitle_color,
                radius="xl",
                size="sm",
                style={
                    "textTransform": "none",
                    "fontWeight": 500,
                    "letterSpacing": 0,
                    "alignSelf": "center",
                },
            )
        )

    # ── Tarih Rozeti (sağ taraf) ─────────────────────────────────────────
    date_badge_children: list = []
    if start and end:
        date_badge_children = [
            dmc.Badge(
                children=dmc.Group(
                    gap=6,
                    align="center",
                    children=[
                        DashIconify(icon="solar:calendar-mark-bold-duotone", width=13),
                        f"{start} – {end}",
                    ],
                ),
                variant="light",
                color="indigo",
                radius="xl",
                size="md",
                style={"textTransform": "none", "fontWeight": 500, "letterSpacing": 0},
            )
        ]

    # ── Üst Katman: Back | İkon+Başlık+Badge | Tarih ────────────────────
    top_layer = dmc.Group(
        justify="space-between",
        align="center",
        mb=tabs is not None and "md" or 0,   # sekme varsa alt boşluk
        children=[
            # SOL: Back butonu + Başlık grubu
            dmc.Group(
                gap="md",
                align="center",
                children=[
                    back_button,
                    dmc.Group(
                        gap="sm",
                        align="center",
                        children=title_children,
                    ),
                ],
            ),
            # SAĞ: Tarih rozeti
            dmc.Group(gap="sm", children=date_badge_children),
        ],
    )

    # ── Ortak dmc.Paper kapsayıcı (Sticky) ──────────────────────────────
    paper_children = [top_layer]
    if tabs is not None:
        paper_children.append(tabs)

    return dmc.Paper(
        px="xl",
        py="md",
        radius=0,                           # kenar: tam genişlik sticky → radius=0
        style={
            "background": "rgba(255, 255, 255, 0.88)",
            "backdropFilter": "blur(14px)",
            "WebkitBackdropFilter": "blur(14px)",
            "boxShadow": "0 4px 24px rgba(67, 24, 255, 0.08), 0 1px 6px rgba(0, 0, 0, 0.05)",
            "borderBottom": "1px solid rgba(67, 24, 255, 0.08)",
            "position": "sticky",           # ← STICKY: CEO talebi
            "top": 0,
            "zIndex": 1000,                 # sidebar zIndex aşıyor → sidebar=1100 ise 999 yap
            "marginBottom": "24px",
        },
        children=paper_children,
    )
```

> ⚠️ **`zIndex: 1000` notu:** Sidebar'ın `zIndex` değerini kontrol et.
> Eğer sidebar `zIndex: 1100` ise bu değeri `999` yap.
> Eğer sidebar `zIndex: 999` veya `1000` ise `1001` yap.

---

### DEĞİŞİKLİK 2 — `dc_view.py` — Header Entegrasyonu (Satır 68-81)

**Import ekle (Satır 7'nin altına):**
```python
from src.components.header import create_detail_header
```

**Header bloğunu değiştir (Satır 68-81):**

```python
# MEVCUT (Satır 68-81) — SİL ve YENİYLE DEĞİŞTİR:
html.Div(
    className="nexus-glass",
    children=[
        dcc.Link(DashIconify(...), href="/datacenters"),
        html.Div([html.H1(dc_name, ...), html.Span(f"Region: {dc_loc}...")]),
    ],
    style={...}
),

# YENİ — tek satır çağrı:
create_detail_header(
    title=dc_name,
    back_href="/datacenters",
    back_label="Data Centers",
    subtitle_badge=f"📍 {dc_loc}" if dc_loc else None,
    subtitle_color="indigo",
    time_range=tr,
    icon="solar:server-square-bold-duotone",
    tabs=dmc.Tabs(           # ← SEKME dc_view.py Satır 84-315 buraya TAŞINACAK
        color="indigo",
        variant="pills",
        radius="md",
        value="intel",
        children=[
            dmc.TabsList(
                children=[
                    dmc.TabsTab("Intel Virtualization", value="intel"),
                    dmc.TabsTab("Power Virtualization", value="power"),
                    dmc.TabsTab("Summary", value="summary"),
                ],
                style={"paddingTop": "12px"},    # ← üst boşluk (paper içinde)
            ),
            # TabsPaneller AYNI KALIR — sadece TabsList header'a girdi
        ],
    ),
),
```

> **Sekme stratejisi dc_view için:** `dmc.TabsList` header'a taşınır, `dmc.TabsPanel`'lar sayfada aşağıda kalır.
> Alternatif: Tüm `dmc.Tabs` header'a alınabilir ama o zaman içerik panelleri çok uzar.
> **Önerilen:** Sadece `dmc.TabsList` başlıkla sticky olsun, paneller aşağıda kalsın.
> Bunun için `tabs` argümanına **sadece** `dmc.TabsList` sarılmış bir `dmc.Tabs` geçilebilir.

---

### DEĞİŞİKLİK 3 — `cluster_view.py` — Header Entegrasyonu (Satır 16-30)

**Import ekle:**
```python
from src.components.header import create_detail_header
```

**Header bloğunu değiştir (Satır 16-30):**

```python
# MEVCUT (Satır 16-30) — SİL ve YENİYLE DEĞİŞTİR:
html.Div(className="nexus-glass", children=[
    dcc.Link(back_arrow, href="/datacenters"),
    html.Div([html.H1(f"Cluster: {cluster_id}", ...), html.P("under construction")]),
])

# YENİ:
create_detail_header(
    title=f"Cluster: {cluster_id or '—'}",
    back_href="/datacenters",
    back_label="Data Centers",
    subtitle_badge="🚧 Under Construction",
    subtitle_color="yellow",
    time_range=None,           # cluster_view'da time_range yok — tarih rozeti gizlenir
    icon="solar:box-bold-duotone",
    tabs=None,                 # cluster_view'da sekme yok
),
```

---

### DEĞİŞİKLİK 4 — `customer_view.py` — Header Entegrasyonu (Satır 42-49)

**Import ekle:**
```python
from src.components.header import create_detail_header
```

**Header bloğunu değiştir (Satır 42-49):**

```python
# MEVCUT (Satır 42-49) — SİL ve YENİYLE DEĞİŞTİR:
html.Div(className="nexus-glass", children=[
    html.H1("Customer View", ...),
    html.P(f"Report period: {start}–{end}"),
])

# YENİ:
create_detail_header(
    title="Customer View",
    back_href="/",             # Ana sayfaya — back butonu Overview'a döner
    back_label="Overview",
    subtitle_badge="👤 Boyner",
    subtitle_color="teal",
    time_range=tr,
    icon="solar:users-group-two-rounded-bold-duotone",
    tabs=None,                 # customer_view sekmeler header'a alınmaz (callback bağımlı)
),
```

> **`customer_view` sekme notu:** Bu sayfadaki `dmc.Tabs` `html.Div(id="customer-view-content")` altında callback ile güncelleniyor. Sekmeleri header'a almak callback mimarisini bozar — bu yüzden `tabs=None` bırakılıyor. Callback yapısı **değişmez**.

---

### `create_detail_header` Parametre Tablosu — 3 Sayfa Karşılaştırması

| Parametre | `dc_view.py` | `cluster_view.py` | `customer_view.py` |
|-----------|-------------|-------------------|-------------------|
| `title` | `dc_name` (dinamik) | `f"Cluster: {cluster_id}"` | `"Customer View"` |
| `back_href` | `"/datacenters"` | `"/datacenters"` | `"/"` |
| `back_label` | `"Data Centers"` | `"Data Centers"` | `"Overview"` |
| `subtitle_badge` | `f"📍 {dc_loc}"` | `"🚧 Under Construction"` | `"👤 Boyner"` |
| `subtitle_color` | `"indigo"` | `"yellow"` | `"teal"` |
| `time_range` | `tr` | `None` | `tr` |
| `icon` | `solar:server-square-bold-duotone` | `solar:box-bold-duotone` | `solar:users-group-two-rounded-bold-duotone` |
| `tabs` | `dmc.TabsList(...)` veya `None` | `None` | `None` |

---

### Sekme Stratejisi — dc_view için Detay

CEO'nun talebi: **Sekmeler başlıkla birlikte üstte sticky kalsın**.

**Seçenek A — Sadece TabsList sticky (ÖNERİLEN):**
```
dmc.Paper(sticky) içinde:
  top_layer: Back | DC11 📍 Istanbul | 📅 tarih
  dmc.Tabs(value="intel"):
    dmc.TabsList:  [Intel Virtualization] [Power Virtualization] [Summary]

Sayfada aşağıda (Header dışında):
  dmc.TabsPanel(value="intel", ...) ← içerik scroll'lanabilir
  dmc.TabsPanel(value="power", ...)
  dmc.TabsPanel(value="summary", ...)
```

**Neden TabsPanel header'a giremez?**
- TabsPanel içerikleri yüzlerce satır kod + grafik = sticky header'da taşınamaz.
- Sadece TabsList (3 buton) sticky olunca yeterince faydalı.
- dc_view.py'de **tüm dmc.Tabs değil, sadece dmc.TabsList** oluşturulup `tabs=` argümanına geçilecek.

**Spesifik `tabs=` argümanı dc_view için:**
```python
tabs=dmc.TabsList(
    style={"paddingTop": "8px"},
    children=[
        dmc.TabsTab("Intel Virtualization", value="intel"),
        dmc.TabsTab("Power Virtualization", value="power"),
        dmc.TabsTab("Summary", value="summary"),
    ],
),
```

> ⚠️ `create_detail_header` fonksiyonu içindeki `if tabs is not None` bloğu
> hem `dmc.TabsList` hem `dmc.Tabs` kabul ediyor — herhangi bir Dash bileşeni geçilebilir.
> `dmc.Tabs(color="indigo", variant="pills", value="intel")` wrapper'ı dc_view.py'de
> Header'ın **dışında** kalmaya devam eder.

---

### Sidebar `zIndex` Kontrolü

```python
# Bu komutu çalıştır ya da style.css'i kontrol et:
# src/components/sidebar.py içinde zIndex değeri nedir?
```

Plana göre:
- `create_detail_header` → `zIndex: 1000`
- Sidebar `zIndex` > 1000 ise → header `zIndex: 999` yap
- Sidebar `zIndex` ≤ 999 ise → header `zIndex: 1000` uygundur

---

### ✅ Task 1 Kabul Kriterleri

**Yapısal:**
- [ ] `src/components/header.py` oluşturuldu.
- [ ] `create_detail_header()` fonksiyonu tüm parametrelerle doğru çalışıyor.
- [ ] `python app.py` — 3 sayfa da hatasız başlangıç.
- [ ] `/datacenters` → herhangi bir DC kartına tıkla → `dc_view` sayfası açılıyor.

**dc_view Header:**
- [ ] Back butonu (`dmc.ActionIcon`, indigo, light variant) görünüyor.
- [ ] Başlık `dc_name` gradyanla (lacivert→mor) görünüyor.
- [ ] `📍 Istanbul` (veya ilgili lokasyon) indigo badge görünüyor.
- [ ] 📅 Tarih rozeti sağ tarafa hizalı.
- [ ] Sekmeler (Intel / Power / Summary) header içinde görünüyor.
- [ ] Header **sticky** — sayfa aşağı kaydırınca sekmeler üstte kalıyor.
- [ ] Header arka planı `rgba(255,255,255,0.88)` — blur efekti var.

**cluster_view Header:**
- [ ] Back butonu Data Centers'a gidiyor.
- [ ] Başlık `Cluster: {ID}` gradyanla görünüyor.
- [ ] `🚧 Under Construction` sarı badge görünüyor.
- [ ] Tarih rozeti gösterilmiyor (`time_range=None`).
- [ ] Sekme yok.

**customer_view Header:**
- [ ] Back butonu Overview `/` adresine gidiyor.
- [ ] Başlık "Customer View" gradyanla görünüyor.
- [ ] `👤 Boyner` teal badge görünüyor.
- [ ] 📅 Tarih rozeti sağ tarafa hizalı.
- [ ] Mevcut callback yapısı bozulmadı (sekme yok).

**Görsel Tutarlılık:**
- [ ] dc_view, cluster_view, customer_view — 3'ü de Overview ve Data Centers sayfasıyla aynı glassmorphism standardında.
- [ ] Tüm sayfalar arasındaki Back butonu, tarih rozeti ve gradyan H2 stilistik olarak aynı.

---

### 📝 Task 1 Değişiklik Özeti

```
YENİ DOSYA — src/components/header.py:
  create_detail_header(
      title, back_href, back_label,
      subtitle_badge, subtitle_color,
      time_range, icon, tabs
  ) → dmc.Paper

  dmc.Paper style:
    background: rgba(255,255,255,0.88)
    backdropFilter: blur(14px)
    boxShadow: 0 4px 24px rgba(67,24,255,0.08)
    borderBottom: 1px solid rgba(67,24,255,0.08)
    position: sticky | top: 0 | zIndex: 1000
    radius: 0 (tam genişlik)

  İç yapı:
    dmc.Group(justify="space-between")
      ├── SOL: dcc.Link(ActionIcon back) + dmc.Group([icon, H2, subtitle_badge])
      └── SAĞ: dmc.Badge(takvim ikonu + tarih)
    tabs (opsiyonel — None ise gösterilmez)

GÜNCELLEME — src/pages/dc_view.py:
  Import: + from src.components.header import create_detail_header
  Satır 68-81: html.Div(nexus-glass) → create_detail_header(
      title=dc_name,
      subtitle_badge=f"📍 {dc_loc}",
      time_range=tr,
      tabs=dmc.TabsList([Intel, Power, Summary])
  )
  dmc.Tabs kalır — sadece TabsList header'a çıkar

GÜNCELLEME — src/pages/cluster_view.py:
  Import: + from src.components.header import create_detail_header
  Satır 16-30: html.Div(nexus-glass) → create_detail_header(
      title=f"Cluster: {cluster_id}",
      subtitle_badge="🚧 Under Construction",
      time_range=None,
      tabs=None
  )

GÜNCELLEME — src/pages/customer_view.py:
  Import: + from src.components.header import create_detail_header
  Satır 42-49: html.Div(nexus-glass) → create_detail_header(
      title="Customer View",
      subtitle_badge="👤 Boyner",
      time_range=tr,
      tabs=None   ← callback bağımlı sekmeler korunuyor
  )

DEĞİŞMEYEN:
  - TabsPanel içerikleri
  - customer_view callback'leri
  - db_service.py
  - style.css (nexus-glass silinmez)
  - sidebar.py
```

**Toplam:** 1 yeni dosya + 3 sayfa güncelleme.
`create_detail_header` → 1 kez yazılıyor, 3 sayfada kullanılıyor. Sıfır kod tekrarı.
