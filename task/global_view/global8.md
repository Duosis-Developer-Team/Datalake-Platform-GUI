# ✨ GLOBAL MAP VIEW V8.0 — DC Detail Sayfası & discovery_loki_rack Entegrasyonu

> **Versiyon:** 8.0  
> **Tarih:** 2026-04-02  
> **Hazırlayan:** Baş Planlayıcı & Sistem Mimarı  
> **Hedef:** Global View'deki DC kartlarındaki "Rack Details" butonunu "Detail" olarak yeniden adlandırmak ve `discovery_loki_rack` tablosundan DC'ye özel kabinet verilerini gösteren premium bir DC Detail sayfası oluşturmak.

---

## ARKA PLAN

### Neden Bu Değişiklik Gerekiyor?

1. **`loki_racks` tablosu append-only:** Her ETL çalışmasında aynı rack için yeni satır ekler. `collection_time` bazlı filtreleme yapılmadan sorgulama yapılırsa aynı kabinetler tekrar tekrar görünür. Zaman dilimi belirsiz.

2. **`discovery_loki_rack` tablosu current-state:** Her rack için tek satır, `first_observed` ve `last_observed` ile güncellik takibi yapılabilir. `component_moid` UNIQUE constraint ile duplicate imkansız.

3. **ETL durumu:** Arkadaş ETL collector'ı güncelledi → `discovery_loki_rack` tablosu artık NetBox API'den besleniyor ve dolu.

### Mevcut Akış (V7.0)

```
Global View → Region/Pin seç → DC kartı görünür
                                    ↓
                          [Rack Details] butonu
                                    ↓
                         /datacenter/{dc_id}
                         (DC Summary sayfası — rack yok)
```

### Hedef Akış (V8.0)

```
Global View → Region/Pin seç → DC kartı görünür
                                    ↓
                            [Detail] butonu
                                    ↓
                         /dc-detail/{dc_id}
                         (DC'ye özel kabinet listesi)
```

---

## DOKUNULACAK DOSYALAR

| # | Dosya | İşlem | Etki |
|---|-------|-------|------|
| 1 | `services/datacenter-api/app/db/queries/discovery_rack.py` | **YENİ** | Backend — discovery_loki_rack SQL sorguları |
| 2 | `services/datacenter-api/app/services/dc_service.py` | **GÜNCELLE** | Backend — `get_dc_racks()` metotu eklenir |
| 3 | `services/datacenter-api/app/routers/datacenters.py` | **GÜNCELLE** | Backend — `/datacenters/{dc_code}/racks` endpoint eklenir |
| 4 | `src/services/api_client.py` | **GÜNCELLE** | Frontend — `get_dc_racks()` HTTP wrapper eklenir |
| 5 | `src/pages/dc_detail.py` | **YENİ** | Frontend — Premium DC Detail sayfası (kabinet kartları) |
| 6 | `app.py` | **GÜNCELLE** | Frontend — `/dc-detail/{dc_id}` route + import eklenir |
| 7 | `src/pages/global_view.py` | **GÜNCELLE** | Frontend — "Rack Details" → "Detail", href → `/dc-detail/{dc_id}` (2 yerde) |
| 8 | `assets/style.css` | **GÜNCELLE** | Frontend — DC Detail sayfası için CSS (rack kartları, hover, animasyonlar) |

---

## KRİTİK KARAR — DC → RACK EŞLEŞMESİ

### Mevcut DC → Site Mapping Zinciri

```
loki_locations tablosu
  ├── DC_LIST_WITH_SITE sorgusu → dc_name + site_name çeker
  ├── db_service._dc_site_map → { "DC11": "Istanbul", "DC13": "Istanbul", ... }
  └── Global View'de site_name ile gruplama yapılır
```

### discovery_loki_rack Tablosundaki İlgili Kolonlar

```sql
site_id      varchar(255)   -- NetBox site ID (sayısal, varchar olarak)
location_id  varchar(255)   -- NetBox location ID (sayısal, varchar olarak)
```

### Eşleme Stratejisi

`discovery_loki_rack.location_id` → `discovery_loki_location.id` ile JOIN yapılır.
`discovery_loki_location` tablosunda `name` kolonu DC ismine karşılık gelir (DC11, DC13 gibi).

**SQL sorgusu:**

```sql
SELECT r.*
FROM discovery_loki_rack r
JOIN discovery_loki_location l ON r.location_id = l.id::varchar
WHERE l.name = %s OR l.parent_name = %s
ORDER BY r.name
```

**Alternatif (JOIN'siz):** Eğer `location_id` doğrudan `loki_locations.id` ile eşleşiyorsa, önce DC'ye ait location ID'leri çekilir, sonra `WHERE location_id IN (...)` kullanılır.

> **🔮 MİMAR NOTU:** İlk implementasyonda JOIN yaklaşımı kullanılacak. Eğer performans sorunu çıkarsa (ki çıkmamalı — discovery tabloları küçük), ikinci yaklaşıma geçilebilir.

---

## ADIM 1 — SQL Sorgu Dosyası

### 1.1 Yeni Dosya: `src/queries/discovery_rack.py`

Bu dosya `discovery_loki_rack` tablosuna yapılacak tüm sorguları barındırır.

```python
RACKS_BY_DC = """
SELECT
    r.id,
    r.name,
    r.display_name,
    r.status,
    r.status_description,
    r.u_height,
    r.kabin_enerji,
    r.pdu_a_ip,
    r.pdu_b_ip,
    r.rack_type,
    r.serial,
    r.asset_tag,
    r.tenant_name,
    r.facility_id,
    r.weight,
    r.max_weight,
    r.weight_unit,
    r.description,
    r.comments,
    r.first_observed,
    r.last_observed,
    r.location_id,
    r.site_id
FROM public.discovery_loki_rack r
JOIN public.discovery_loki_location l
    ON r.location_id = l.id::varchar
WHERE (l.name = %s OR l.parent_name = %s)
ORDER BY r.name
"""

RACK_SUMMARY_BY_DC = """
SELECT
    COUNT(*) AS total_racks,
    COUNT(*) FILTER (WHERE r.status = 'active') AS active_racks,
    COALESCE(SUM(r.u_height), 0) AS total_u_height,
    COUNT(*) FILTER (WHERE r.kabin_enerji IS NOT NULL AND r.kabin_enerji != '') AS racks_with_energy,
    COUNT(*) FILTER (WHERE r.pdu_a_ip IS NOT NULL AND r.pdu_a_ip != '') AS racks_with_pdu
FROM public.discovery_loki_rack r
JOIN public.discovery_loki_location l
    ON r.location_id = l.id::varchar
WHERE (l.name = %s OR l.parent_name = %s)
"""
```

### 1.2 Neden 2 Parametre (%s, %s)?

`loki_locations` hiyerarşisi:
- `parent_id IS NULL` → row kendisi DC → `name = 'DC11'`
- `parent_id IS NOT NULL` → sub-location → `parent_name = 'DC11'`

Rack'ın `location_id`'si DC seviyesindeki location'a veya alt location'a bağlı olabilir. Her iki durumu da kapsamak için `WHERE (l.name = %s OR l.parent_name = %s)` kullanılır. Her iki parametre de aynı `dc_code` değerini alır.

---

## ADIM 2 — Backend Service Layer

### 2.1 Yeni Query Dosyası (Backend)

**Dosya:** `services/datacenter-api/app/db/queries/discovery_rack.py`

Mevcut backend query dosyaları ile aynı pattern'de oluşturulur. Import'u `dc_service.py`'nin üstüne eklenir.

### 2.2 Backend db_service.py (dc_service.py)

**Dosya:** `services/datacenter-api/app/services/dc_service.py`

ÖNEMLİ: Backend'deki dosya `dc_service.py` olarak adlandırılmış. Frontend'deki `src/services/db_service.py` ile karıştırma.

Import eklenir:
```python
from app.db.queries import discovery_rack as drq
```

`DatabaseService` sınıfına `get_dc_racks()` metotu eklenir (Physical Inventory bölümünün yanına):

```python
def get_dc_racks(self, dc_code: str) -> dict:
    empty = {"racks": [], "summary": {"total_racks": 0, "active_racks": 0, "total_u_height": 0, "racks_with_energy": 0, "racks_with_pdu": 0}}
    if not dc_code or not dc_code.strip():
        return empty
    cache_key = f"dc_racks:{dc_code.strip()}"
    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return cached_val
    try:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                rows = self._run_rows(cur, drq.RACKS_BY_DC, (dc_code, dc_code))
                summary_row = self._run_row(cur, drq.RACK_SUMMARY_BY_DC, (dc_code, dc_code))
    except OperationalError as exc:
        logger.error("DB unavailable for get_dc_racks(%s): %s", dc_code, exc)
        return empty

    columns = [
        "id", "name", "display_name", "status", "status_description",
        "u_height", "kabin_enerji", "pdu_a_ip", "pdu_b_ip", "rack_type",
        "serial", "asset_tag", "tenant_name", "facility_id",
        "weight", "max_weight", "weight_unit",
        "description", "comments",
        "first_observed", "last_observed", "location_id", "site_id",
    ]
    racks = []
    for r in (rows or []):
        rack = {}
        for i, col in enumerate(columns):
            rack[col] = r[i] if i < len(r) else None
        if rack.get("first_observed"):
            rack["first_observed"] = str(rack["first_observed"])
        if rack.get("last_observed"):
            rack["last_observed"] = str(rack["last_observed"])
        racks.append(rack)

    s = summary_row or (0, 0, 0, 0, 0)
    summary = {
        "total_racks": int(s[0] or 0),
        "active_racks": int(s[1] or 0),
        "total_u_height": int(s[2] or 0),
        "racks_with_energy": int(s[3] or 0),
        "racks_with_pdu": int(s[4] or 0),
    }

    result = {"racks": racks, "summary": summary}
    cache.set(cache_key, result)
    return result
```

### 2.3 Backend Router Endpoint

**Dosya:** `services/datacenter-api/app/routers/datacenters.py`

Mevcut endpoint pattern'ini takip ederek:

```python
@router.get("/datacenters/{dc_code}/racks", response_model=dict[str, Any])
def dc_racks(dc_code: str, db: DatabaseService = Depends(get_db)):
    return db.get_dc_racks(dc_code)
```

---

## ADIM 3 — Frontend API Client Layer

### 3.1 Mimari Gerçek

Mevcut mimari:
```
Sayfalar (src/pages/*.py)
  ↓ import
api_client.py
  ↓ HTTP (httpx)
services/datacenter-api (FastAPI)
  ↓ method call
dc_service.py (DatabaseService)
  ↓ SQL
PostgreSQL
```

Tüm sayfalar `from src.services import api_client as api` yapıyor, asla direkt DB erişimi yok.

### 3.2 API Client Değişikliği

**Dosya:** `src/services/api_client.py`

Mevcut fonksiyon pattern'ini takip ederek:

```python
def get_dc_racks(dc_code: str) -> dict:
    try:
        enc = quote(dc_code, safe="")
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/racks")
        return data if isinstance(data, dict) else {"racks": [], "summary": {}}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {"racks": [], "summary": {}}
```

### 3.3 Frontend Sayfasında Kullanım

`dc_detail.py` sayfasında:

```python
from src.services import api_client as api
racks_data = api.get_dc_racks(dc_id)
```

---

## ADIM 4 — DC Detail Sayfası

### 4.1 Yeni Dosya: `src/pages/dc_detail.py`

Premium DC Detail sayfası. İçerik yapısı:

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back to Global View    DC11 — Istanbul    12 Cabinets   │
│─────────────────────────────────────────────────────────────│
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │Total Rack│ │Active    │ │Total U   │ │Energy    │      │
│  │   12     │ │   10     │ │  504 U   │ │   8 PDU  │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│─────────────────────────────────────────────────────────────│
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ KAB-A01      │ │ KAB-A02      │ │ KAB-B01      │       │
│  │ ● Active     │ │ ● Active     │ │ ○ Planned    │       │
│  │ 42U          │ │ 42U          │ │ 48U          │       │
│  │ ⚡ A+B PDU   │ │ ⚡ A PDU     │ │ ⚡ —         │       │
│  │ 🏷 Müşteri X │ │ 🏷 —         │ │ 🏷 Müşteri Y │       │
│  │ 📅 2h ago    │ │ 📅 2h ago    │ │ 📅 5d ago    │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│  ... (daha fazla rack kartı)                               │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Fonksiyon İmzası

```python
def build_dc_detail(dc_id, time_range=None):
```

### 4.3 Header Bölümü

```python
dmc.Paper(
    p="xl",
    radius="lg",
    style={
        "background": "rgba(255,255,255,0.90)",
        "backdropFilter": "blur(14px)",
        "boxShadow": "0 8px 32px rgba(67,24,255,0.10)",
        "border": "1px solid rgba(67,24,255,0.08)",
        "marginBottom": "24px",
    },
    children=[
        dmc.Group(
            justify="space-between",
            align="center",
            children=[
                dmc.Group(gap="md", align="center", children=[
                    dcc.Link(
                        dmc.ActionIcon(
                            DashIconify(icon="solar:arrow-left-bold-duotone", width=20),
                            variant="light",
                            color="indigo",
                            radius="md",
                            size="lg",
                        ),
                        href="/global-view",
                        style={"textDecoration": "none"},
                    ),
                    dmc.ThemeIcon(
                        size="xl",
                        radius="md",
                        variant="light",
                        color="indigo",
                        children=DashIconify(icon="solar:server-square-bold-duotone", width=24),
                    ),
                    dmc.Stack(gap=0, children=[
                        dmc.Text(dc_name, fw=800, size="xl", c="#2B3674"),
                        dmc.Text(dc_location, size="sm", c="#A3AED0", fw=500),
                    ]),
                ]),
                dmc.Badge(
                    f"{summary['total_racks']} Cabinets",
                    variant="light",
                    color="indigo",
                    size="lg",
                ),
            ],
        ),
    ],
)
```

### 4.4 KPI Row

```python
dmc.SimpleGrid(
    cols=4,
    spacing="lg",
    children=[
        _kpi_card("Total Racks", str(summary["total_racks"]), "solar:server-square-bold-duotone", "indigo"),
        _kpi_card("Active Racks", str(summary["active_racks"]), "solar:check-circle-bold-duotone", "teal"),
        _kpi_card("Total U Height", f"{summary['total_u_height']}U", "solar:ruler-bold-duotone", "orange"),
        _kpi_card("PDU Connected", str(summary["racks_with_pdu"]), "solar:bolt-circle-bold-duotone", "grape"),
    ],
)
```

### 4.5 KPI Card Yardımcı Fonksiyonu

```python
def _kpi_card(title, value, icon, color):
    return dmc.Paper(
        p="lg",
        radius="md",
        style={
            "background": "rgba(255,255,255,0.95)",
            "border": "1px solid rgba(67,24,255,0.06)",
            "boxShadow": "0 2px 8px rgba(67,24,255,0.04)",
        },
        children=[
            dmc.Group(justify="space-between", align="center", children=[
                dmc.Stack(gap=4, children=[
                    dmc.Text(title, size="xs", fw=600, c="#A3AED0"),
                    dmc.Text(value, size="xl", fw=800, c="#2B3674"),
                ]),
                dmc.ThemeIcon(
                    size="lg",
                    radius="md",
                    variant="light",
                    color=color,
                    children=DashIconify(icon=icon, width=20),
                ),
            ]),
        ],
    )
```

### 4.6 Rack Card Bileşeni

Her kabinet için bir kart. Status'a göre renk kodlaması:

| Status | Renk | Badge |
|--------|------|-------|
| `active` | `teal` | ● Active |
| `planned` | `blue` | ○ Planned |
| `reserved` | `orange` | ◐ Reserved |
| `retired` / diğer | `gray` | ✕ Retired |

```python
def _rack_card(rack):
    name = rack.get("name") or "Unknown"
    status = (rack.get("status") or "").lower()
    u_height = rack.get("u_height") or 0
    kabin_enerji = rack.get("kabin_enerji") or ""
    pdu_a = rack.get("pdu_a_ip") or ""
    pdu_b = rack.get("pdu_b_ip") or ""
    tenant = rack.get("tenant_name") or ""
    last_obs = rack.get("last_observed") or ""

    status_map = {
        "active": ("teal", "● Active"),
        "planned": ("blue", "○ Planned"),
        "reserved": ("orange", "◐ Reserved"),
    }
    s_color, s_label = status_map.get(status, ("gray", "— " + status.title() if status else "Unknown"))

    pdu_text = ""
    if pdu_a and pdu_b:
        pdu_text = f"A: {pdu_a} · B: {pdu_b}"
    elif pdu_a:
        pdu_text = f"A: {pdu_a}"
    elif pdu_b:
        pdu_text = f"B: {pdu_b}"
    else:
        pdu_text = "—"

    return dmc.Paper(
        p="lg",
        radius="md",
        className="rack-card",
        style={
            "background": "rgba(255,255,255,0.95)",
            "border": "1px solid rgba(67,24,255,0.08)",
            "boxShadow": "0 2px 12px rgba(67,24,255,0.06)",
        },
        children=[
            dmc.Group(justify="space-between", mb="sm", children=[
                dmc.Text(name, fw=700, size="md", c="#2B3674"),
                dmc.Badge(s_label, color=s_color, variant="light", size="sm"),
            ]),

            dmc.Group(gap="lg", mb="sm", children=[
                dmc.Group(gap="xs", children=[
                    DashIconify(icon="solar:ruler-bold-duotone", width=14, color="#A3AED0"),
                    dmc.Text(f"{u_height}U", size="sm", fw=600, c="#2B3674"),
                ]),
                dmc.Group(gap="xs", children=[
                    DashIconify(icon="solar:bolt-circle-bold-duotone", width=14, color="#A3AED0"),
                    dmc.Text(kabin_enerji or "—", size="sm", fw=500, c="#2B3674"),
                ]),
            ]),

            dmc.Divider(my="xs", color="rgba(67,24,255,0.06)"),

            dmc.Stack(gap=4, children=[
                dmc.Group(gap="xs", children=[
                    DashIconify(icon="solar:plug-circle-bold-duotone", width=12, color="#A3AED0"),
                    dmc.Text(f"PDU: {pdu_text}", size="xs", c="#A3AED0", truncate=True),
                ]),
                dmc.Group(gap="xs", children=[
                    DashIconify(icon="solar:user-bold-duotone", width=12, color="#A3AED0"),
                    dmc.Text(f"Tenant: {tenant or '—'}", size="xs", c="#A3AED0"),
                ]),
                dmc.Group(gap="xs", children=[
                    DashIconify(icon="solar:clock-circle-bold-duotone", width=12, color="#A3AED0"),
                    dmc.Text(f"Last seen: {_format_last_observed(last_obs)}", size="xs", c="#A3AED0"),
                ]),
            ]),
        ],
    )
```

### 4.7 Last Observed Formatlama

```python
def _format_last_observed(ts_str):
    if not ts_str:
        return "—"
    try:
        from datetime import datetime, timezone
        ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - ts
        if diff.days > 30:
            return f"{diff.days // 30}mo ago"
        if diff.days > 0:
            return f"{diff.days}d ago"
        hours = diff.seconds // 3600
        if hours > 0:
            return f"{hours}h ago"
        return "Just now"
    except Exception:
        return str(ts_str)[:16]
```

### 4.8 Empty State

Rack bulunamadığında güzel bir placeholder:

```python
dmc.Paper(
    p="xl",
    radius="lg",
    style={"textAlign": "center", "marginTop": "32px", ...},
    children=[
        DashIconify(icon="solar:server-square-bold-duotone", width=64, color="#A3AED0"),
        html.H3("No Cabinets Found", style={"color": "#2B3674", "marginTop": "16px"}),
        dmc.Text(
            f"No rack data available for {dc_id}. The discovery collector may not have synced yet.",
            c="#A3AED0",
            size="sm",
        ),
        dcc.Link(
            dmc.Button("Back to Global View", variant="light", color="indigo", radius="md", mt="lg"),
            href="/global-view",
            style={"textDecoration": "none"},
        ),
    ],
)
```

### 4.9 Rack Grid

Rack kartları responsive grid ile gösterilir:

```python
dmc.SimpleGrid(
    cols={"base": 1, "sm": 2, "lg": 3},
    spacing="lg",
    children=[_rack_card(r) for r in racks],
)
```

---

## ADIM 5 — Routing (app.py)

### 5.1 Import Ekleme (satır ~73)

Mevcut satır:
```python
from src.pages import home, datacenters, dc_view, customer_view, query_explorer, global_view, region_drilldown
```

Yeni:
```python
from src.pages import home, datacenters, dc_view, customer_view, query_explorer, global_view, region_drilldown, dc_detail
```

### 5.2 Route Ekleme (satır ~312-317 arası)

Mevcut `region-drilldown` bloğundan önce:

```python
    if pathname and pathname.startswith("/dc-detail/"):
        dc_id = pathname.replace("/dc-detail/", "").strip("/")
        return dc_detail.build_dc_detail(dc_id, tr)
```

### 5.3 Tam Routing Sırası (render_main_content)

```python
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
if pathname and pathname.startswith("/dc-detail/"):           # <-- YENİ
    dc_id = pathname.replace("/dc-detail/", "").strip("/")     # <-- YENİ
    return dc_detail.build_dc_detail(dc_id, tr)                # <-- YENİ
if pathname == "/region-drilldown":
    from urllib.parse import parse_qs
    params = parse_qs((search or "").lstrip("?"))
    region = params.get("region", [""])[0]
    return region_drilldown.build_region_drilldown(region, tr)
return home.build_overview(tr)
```

---

## ADIM 6 — Buton Güncellemesi (global_view.py)

### 6.1 Region Detail Panel — DC Kartları (satır ~510-522)

**Mevcut:**
```python
dcc.Link(
    dmc.Button(
        "Rack Details",
        variant="light",
        color="indigo",
        radius="md",
        size="xs",
        rightSection=DashIconify(icon="solar:arrow-right-bold-duotone", width=14),
    ),
    href=f"/datacenter/{dc_id}",
    style={"textDecoration": "none"},
),
```

**Yeni:**
```python
dcc.Link(
    dmc.Button(
        "Detail",
        variant="light",
        color="indigo",
        radius="md",
        size="xs",
        rightSection=DashIconify(icon="solar:arrow-right-bold-duotone", width=14),
    ),
    href=f"/dc-detail/{dc_id}",
    style={"textDecoration": "none"},
),
```

### 6.2 Pin-Click Info Card — build_dc_info_card (satır ~947-959)

**Mevcut:**
```python
dcc.Link(
    dmc.Button(
        "Rack Details",
        variant="light",
        color="indigo",
        radius="md",
        size="sm",
        rightSection=DashIconify(icon="solar:arrow-right-bold-duotone", width=16),
    ),
    href=f"/datacenter/{dc_id}",
    style={"textDecoration": "none"},
),
```

**Yeni:**
```python
dcc.Link(
    dmc.Button(
        "Detail",
        variant="light",
        color="indigo",
        radius="md",
        size="sm",
        rightSection=DashIconify(icon="solar:arrow-right-bold-duotone", width=16),
    ),
    href=f"/dc-detail/{dc_id}",
    style={"textDecoration": "none"},
),
```

---

## ADIM 7 — CSS Stilleri (assets/style.css)

### 7.1 Rack Card Hover Efekti

```css
.rack-card {
    transition: transform 0.25s cubic-bezier(0.25, 0.8, 0.25, 1),
                box-shadow 0.25s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.rack-card:hover {
    transform: translateY(-4px);
    box-shadow:
        0px 16px 40px rgba(67, 24, 255, 0.12),
        0px 6px 16px rgba(67, 24, 255, 0.06) !important;
}
```

### 7.2 DC Detail Animasyonu

```css
@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(16px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.dc-detail-animate {
    animation: fadeInUp 0.4s ease-out;
}
```

---

## DOSYA BAZINDA DEĞİŞİKLİK ÖZETİ

### `services/datacenter-api/app/db/queries/discovery_rack.py` — YENİ

| İçerik |
|--------|
| `RACKS_BY_DC` — DC'ye ait rack'leri çeken SQL |
| `RACK_SUMMARY_BY_DC` — DC'ye ait rack özet istatistikleri |

### `services/datacenter-api/app/services/dc_service.py` — GÜNCELLE

| İşlem |
|-------|
| `import discovery_rack as drq` eklenir |
| `get_dc_racks(dc_code)` metotu eklenir |

### `services/datacenter-api/app/routers/datacenters.py` — GÜNCELLE

| İşlem |
|-------|
| `/datacenters/{dc_code}/racks` GET endpoint eklenir |

### `src/services/api_client.py` — GÜNCELLE

| İşlem |
|-------|
| `get_dc_racks(dc_code)` HTTP wrapper fonksiyonu eklenir |

### `src/pages/dc_detail.py` — YENİ

| İçerik |
|--------|
| `build_dc_detail(dc_id, time_range)` — Ana sayfa fonksiyonu |
| `_kpi_card(title, value, icon, color)` — KPI kartı helper |
| `_rack_card(rack)` — Tek rack kartı builder |
| `_format_last_observed(ts_str)` — Zaman damgası formatlama |

### `app.py` — GÜNCELLE

| İşlem |
|-------|
| `dc_detail` import eklenir |
| `/dc-detail/{dc_id}` route eklenir |

### `src/pages/global_view.py` — GÜNCELLE

| İşlem |
|-------|
| "Rack Details" → "Detail" (2 yerde) |
| href `/datacenter/{dc_id}` → `/dc-detail/{dc_id}` (2 yerde) |

### `assets/style.css` — GÜNCELLE

| İşlem |
|-------|
| `.rack-card` hover efekti |
| `.dc-detail-animate` animasyonu |

---

## UYGULAMA SIRALAMASI (Executer Checklist)

| Sıra | İşlem | Dosya | Durum |
|------|-------|-------|-------|
| 1 | Backend query dosyası oluştur (RACKS_BY_DC + RACK_SUMMARY_BY_DC) | `services/datacenter-api/app/db/queries/discovery_rack.py` | ⬜ |
| 2 | Backend `dc_service.py`'ye `import discovery_rack as drq` ekle | `services/datacenter-api/app/services/dc_service.py` | ⬜ |
| 3 | Backend `dc_service.py`'ye `get_dc_racks()` metotu ekle | `services/datacenter-api/app/services/dc_service.py` | ⬜ |
| 4 | Backend router'a `/datacenters/{dc_code}/racks` endpoint ekle | `services/datacenter-api/app/routers/datacenters.py` | ⬜ |
| 5 | Frontend `api_client.py`'ye `get_dc_racks()` wrapper ekle | `src/services/api_client.py` | ⬜ |
| 6 | Frontend `dc_detail.py` oluştur — tüm bileşenlerle | `src/pages/dc_detail.py` | ⬜ |
| 7 | `app.py`'ye `dc_detail` import ekle | `app.py` | ⬜ |
| 8 | `app.py`'ye `/dc-detail/{dc_id}` route ekle | `app.py` | ⬜ |
| 9 | `global_view.py` — region detail panel: "Rack Details" → "Detail" + href güncelle | `src/pages/global_view.py` | ⬜ |
| 10 | `global_view.py` — pin-click info card: "Rack Details" → "Detail" + href güncelle | `src/pages/global_view.py` | ⬜ |
| 11 | `assets/style.css` — `.rack-card` hover + `.dc-detail-animate` animasyonu | `assets/style.css` | ⬜ |
| 12 | Test: Platform çalıştır → Global View → İstanbul seç → DC11 "Detail" tıkla | Tarayıcı | ⬜ |
| 13 | Test: Rack kartları doğru DC'ye ait mi? (site/location eşleme kontrolü) | Tarayıcı | ⬜ |
| 14 | Test: Empty state — rack'i olmayan bir DC'de "No Cabinets Found" mesajı | Tarayıcı | ⬜ |
| 15 | Test: Rack kart hover efekti (yukarı kayma + gölge) | Tarayıcı | ⬜ |
| 16 | Test: Back to Global View butonu çalışıyor mu? | Tarayıcı | ⬜ |

---

## ⚠️ CTO'NUN İHLAL EDİLEMEZ YASALARI

### YASA 1 — SIFIR YORUM SATIRI
Executer'ın yazacağı kodlarda **TEK BİR** açıklama satırı (`#`) veya docstring (`"""..."""`) **BULUNMAYACAKTIR**.

### YASA 2 — MEVCUT VERİ AKIŞINI KORUMA
`site_name` akışı, `api.get_all_datacenters_summary()` → `api.get_dc_details()` zinciri ve `_dc_site_map` mapping'i **değişmeyecek**.

### YASA 3 — region_drilldown.py'YE DOKUNMA
`region_drilldown.py` dosyası "Reserved" olarak kalacak. Yeni sayfa `dc_detail.py` olarak oluşturulacak.

### YASA 4 — BACKEND CUSTOMER-API'YE DOKUNMA
`services/customer-api/` dizinindeki kodlar **değişmeyecek**. Rack verisi yalnızca `services/datacenter-api/` üzerinden servis edilecek.

---

## BAĞIMLILIKLAR VE ÖN KOŞULLAR

| # | Ön Koşul | Durum |
|---|----------|-------|
| 1 | `discovery_loki_rack` tablosu dolu (ETL aktif) | ✅ Arkadaş halletti |
| 2 | `discovery_loki_location` tablosu dolu | ✅ Zaten dolu (128K) |
| 3 | `discovery_loki_rack.location_id` → `discovery_loki_location.id` eşleşmesi | ⚠️ Test edilmeli |
| 4 | Docker containerlar çalışıyor | ✅ Tümü Up |

---

> **SON:** Bu plan 2 yeni dosya (backend query + frontend sayfa), backend'de 2 dosya güncellemesi (dc_service + router), frontend'de 3 dosya güncellemesi (api_client + app.py + global_view.py) ve CSS ekleme gerektirir. `region_drilldown.py` reserved kalır.
