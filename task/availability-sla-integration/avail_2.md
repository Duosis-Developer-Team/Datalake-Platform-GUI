# Availability Annual — Layout Restructure Plan

> **Kural:** Sadece `src/pages/availability_annual.py` dosyasına dokunulacak.
> Backend, API, CSS, diğer sayfalar değişmez.
> **Bu dosya plan içindir — execute edilmeyecek.**

---

## HEDEF LAYOUT

Mevcut layout:
```
┌─────────────────────────────────────────────────────┐
│  Annual Availability (düz yazı)                     │
├──────────────────────────┬──────────────────────────┤
│                          │  Year: [2026 ▼]           │
│  DC Kartları (3 sütun)   │                           │
│  [AZ11] [DC11] [DC12]   │  Data center: [AZ11 ▼]    │
│  [DC13] [DC14] [DC15]   │                           │
│  [DC16] [DC17] [DC18]   │                           │
└──────────────────────────┴──────────────────────────┘
│  Detay Panel (seçilen DC)                           │
└─────────────────────────────────────────────────────┘
```

**İstenen yeni layout:**
```
┌─────────────────────────────────────────────────────┐
│  ← 🗓 Annual Availability          2026-01-01–today  │  ← create_detail_header() gibi sticky header
│  "All data centers — overall availability"          │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  [AZ11][DC11][DC12][DC13][DC14][DC15]               │  ← Tam genişlik, 4 sütun
│  [DC16][DC17][DC18][...]                            │
└─────────────────────────────────────────────────────┘

┌───────────────────┬─────────────────────────────────┐
│  Year: [2026 ▼]   │  Data center: [AZ11 – AzinT ▼]  │  ← Filtreler, alt satırda yan yana
└───────────────────┴─────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  DC: AZ11 – AzinTelecom DC                         │
│  [OVERALL AVAIL.] [Period (min)] [Total downtime]   │
│  Service availability (product catalog)             │
└─────────────────────────────────────────────────────┘
```

---

## DEĞİŞTİRİLECEK DOSYA

**`src/pages/availability_annual.py`**

Tüm `build_availability_annual_layout()` fonksiyonu (satır 68–184) yeniden yazılacak.
Callback (`_render_availability_annual`, satır 187–302) değişmeyecek — sadece layout bölümü.

---

## A. HEADER BLOĞU — `create_detail_header()` Pattern ile

**Mevcut (satır 108–181):** Düz `html.Div` içinde `dmc.Text("Annual Availability")` + sağda Year/DC dropdown.

**Yeni:** `create_detail_header()` fonksiyonu kullanılacak.

### A1. Import Ekleme

`availability_annual.py` dosyasının import bölümüne (satır 1–14 civarı) ekle:

```python
from src.components.header import create_detail_header
from src.utils.time_range import default_time_range
```

> **Not:** `default_time_range` zaten import edilmiş — tekrar ekleme.
> `create_detail_header` yeni eklenmesi gereken import.

### A2. Header Çağrısı

`build_availability_annual_layout()` içinde header'ı şöyle oluştur:

```python
tr_list = default_time_range()

page_header = create_detail_header(
    title="Annual Availability",
    back_href="/",
    back_label="Overview",
    icon="solar:calendar-bold-duotone",
    time_range=tr_list,
    tabs=None,
)
```

> `create_detail_header()` parametreleri:
> - `title` → Sayfa başlığı
> - `back_href` → Geri butonu linki (Overview'e veya `/` anasayfaya)
> - `back_label` → Tooltip metni
> - `icon` → Başlık solundaki ikon (solar ikonlarından biri)
> - `time_range` → `{"start": "...", "end": "..."}` — sağda tarih badge'i göstermek için
> - `tabs=None` → Tab yok, header sade kalacak

---

## B. OVERVIEW GRID — Tam Genişlik, 4 Sütun

**Mevcut (satır 140–148):** `html.Div(id="availability-annual-overview")` bir `flex: 1 1 280px` kutusunun içinde, sağında Year/DC dropdown var.

**Yeni:** Overview grid ayrı bir blok olarak, tam genişlikte (padding sadece sol-sağ).

```python
overview_section = html.Div(
    style={
        "padding": "0 32px",
        "marginBottom": "16px",
    },
    children=[
        dmc.Text(
            "All data centers — overall availability",
            size="sm",
            fw=600,
            c="#344054",
            mb=4,
        ),
        dmc.Text(
            "Compared for the selected report year (AuraNotify match).",
            size="xs",
            c="dimmed",
            mb="sm",
        ),
        html.Div(id="availability-annual-overview"),   # ← callback bu id'yi dolduruyor
    ],
)
```

> Callback içinde `overview_content`'i dolduran `SimpleGrid`'in `cols` değeri
> **3'ten 4'e** çıkarılacak (B1 bölümüne bak).

---

## C. FİLTRELER — Alt Satır, Yan Yana

**Mevcut (satır 150–178):** Year + DC dropdown'ları sağda dikey `Stack` içinde.

**Yeni:** Overview grid'inin altında, yatay `dmc.Group` içinde.

```python
filter_row = html.Div(
    style={
        "padding": "0 32px",
        "marginBottom": "24px",
    },
    children=[
        dmc.Group(
            gap="md",
            align="flex-end",
            wrap="nowrap",
            children=[
                dmc.Select(
                    label="Year",
                    id="availability-annual-year",
                    data=year_options,
                    value=str(current_year),
                    w=140,
                    searchable=False,
                    clearable=False,
                ),
                dmc.Select(
                    label="Data center",
                    id="availability-annual-dc",
                    data=dc_options,
                    value=default_dc_id,
                    searchable=True,
                    clearable=False,
                    nothingFoundMessage="No DCs",
                    style={"flex": 1},      # ← kalan genişliği doldur
                ),
            ],
        ),
    ],
)
```

---

## D. CALLBACK İÇİ — SimpleGrid Cols Güncellemesi

**Dosya:** `src/pages/availability_annual.py`
**Satır:** 253 (callback içindeki `SimpleGrid`)

```python
# MEVCUT:
dmc.SimpleGrid(cols=3, spacing="sm", verticalSpacing="sm", children=overview_cards)

# YENİ:
dmc.SimpleGrid(
    cols={"base": 2, "md": 3, "lg": 4},
    spacing="sm",
    verticalSpacing="sm",
    children=overview_cards,
)
```

> Bu değişiklik callback içinde — geri kalan callback mantığı değişmez.

---

## E. TAM SAYFA LAYOUT — YENİ RETURN BLOĞU

`build_availability_annual_layout()` fonksiyonunun `return` satırı (mevcut satır 184) şöyle değişecek:

```python
return html.Div([
    page_header,        # A2: Sticky header (create_detail_header)
    overview_section,   # B:  Tam genişlik DC grid (callback ile doldurulur)
    filter_row,         # C:  Year + DC seçici (yatay, altta)
    html.Div(id="availability-annual-body"),  # Detay paneli (callback ile doldurulur)
])
```

---

## F. `build_availability_annual_layout()` TAM YENİ HALİ (Referans)

Mevcut fonksiyon (satır 68–184) tamamen şununla değiştirilecek:

```python
def build_availability_annual_layout(visible_sections: set[str] | None = None) -> html.Div:
    """Annual Availability sayfası: sticky header + tam genişlik DC grid + alt filtreler + detay."""

    def _sec(code: str) -> bool:
        if visible_sections is None:
            return True
        return code in visible_sections

    if not _sec("sec:availability_annual:report"):
        return html.Div(
            dmc.Alert(
                "You do not have permission to view this report.",
                color="red",
                variant="light",
            ),
            style={"padding": "24px"},
        )

    tr_list = default_time_range()
    datacenters = api.get_all_datacenters_summary(tr_list)
    current_year = datetime.now(timezone.utc).year
    year_options = [
        {"value": str(y), "label": str(y)}
        for y in range(MIN_REPORT_YEAR, current_year + 1)
    ]
    dc_options: list[dict] = []
    default_dc_id: str | None = None
    for dc in datacenters:
        cid = dc.get("id")
        if cid is None:
            continue
        sid = str(cid)
        label = (
            format_dc_display_name(dc.get("name"), dc.get("description"))
            or str(dc.get("name") or sid)
        )
        dc_options.append({"value": sid, "label": label})
        if default_dc_id is None:
            default_dc_id = sid

    if not dc_options:
        return html.Div(
            dmc.Alert("No data centers available for this environment.", color="gray", variant="light"),
            style={"padding": "24px 32px"},
        )

    # ── A2: Sticky Header ────────────────────────────────────────────────
    page_header = create_detail_header(
        title="Annual Availability",
        back_href="/",
        back_label="Overview",
        icon="solar:calendar-bold-duotone",
        time_range=tr_list,
        tabs=None,
    )

    # ── B: Overview Grid (tam genişlik, callback doldurur) ───────────────
    overview_section = html.Div(
        style={
            "padding": "0 32px",
            "marginBottom": "16px",
        },
        children=[
            dmc.Text(
                "All data centers — overall availability",
                size="sm",
                fw=600,
                c="#344054",
                mb=4,
            ),
            dmc.Text(
                "Compared for the selected report year (AuraNotify match).",
                size="xs",
                c="dimmed",
                mb="sm",
            ),
            html.Div(id="availability-annual-overview"),
        ],
    )

    # ── C: Filtreler (yatay, altta) ──────────────────────────────────────
    filter_row = html.Div(
        style={
            "padding": "0 32px",
            "marginBottom": "24px",
        },
        children=[
            dmc.Group(
                gap="md",
                align="flex-end",
                wrap="nowrap",
                children=[
                    dmc.Select(
                        label="Year",
                        id="availability-annual-year",
                        data=year_options,
                        value=str(current_year),
                        w=140,
                        searchable=False,
                        clearable=False,
                    ),
                    dmc.Select(
                        label="Data center",
                        id="availability-annual-dc",
                        data=dc_options,
                        value=default_dc_id,
                        searchable=True,
                        clearable=False,
                        nothingFoundMessage="No DCs",
                        style={"flex": 1},
                    ),
                ],
            ),
        ],
    )

    return html.Div([
        page_header,
        overview_section,
        filter_row,
        html.Div(id="availability-annual-body"),
    ])
```

---

## G. CALLBACK DEĞİŞİKLİĞİ (Sadece SimpleGrid)

`_render_availability_annual` callback'i içinde **sadece şu satır değişir** (satır 253):

```python
# MEVCUT:
dmc.SimpleGrid(cols=3, spacing="sm", verticalSpacing="sm", children=overview_cards)

# YENİ:
dmc.SimpleGrid(
    cols={"base": 2, "md": 3, "lg": 4},
    spacing="sm",
    verticalSpacing="sm",
    children=overview_cards,
)
```

Callback'in geri kalanı (`_render_availability_annual`, satır 187–302) **hiç değişmez.**

---

## DEĞİŞİKLİK ÖZETİ

| Bölüm | Mevcut Satırlar | Değişiklik |
|-------|----------------|------------|
| Import | Satır 1–14 | `create_detail_header` import eklenir |
| `build_availability_annual_layout()` | Satır 68–184 | **Tamamen yeniden yazılır** (F bölümü) |
| Callback `SimpleGrid` | Satır 253 | `cols=3` → `cols={"base":2,"md":3,"lg":4}` |
| Callback geri kalan | Satır 187–302 | **Değişmez** |

---

## UYGULAMA SIRASI

1. `create_detail_header` import'unu satır 14'e ekle
2. `build_availability_annual_layout()` fonksiyonunu F bölümündeki yeni halle değiştir
3. Callback içindeki `SimpleGrid` satırını G bölümüyle güncelle
4. Container rebuild: `docker compose up -d --build app`
5. `http://localhost:8050/availability` sayfasını test et
