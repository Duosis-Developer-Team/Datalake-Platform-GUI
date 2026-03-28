# 🔗 GLOBAL MAP VIEW V5 — Drilldown Routing & site_name Entegrasyon Planı (global4.md)

> **Versiyon:** 5.0
> **Tarih:** 2026-03-26
> **Hazırlayan:** Baş Planlayıcı & Sistem Mimarı
> **Hedef:** Info Card'daki "Open Details" butonuna `site_name` (Loki Region) bilgisini ekleyerek Drilldown sayfasına dinamik yönlendirme. Monolith DB katmanına `site_name` eklenmesi.

---

## MİMARİ ÖZET

```
┌─────────────────────────────────────────────────────────────────────┐
│                    VERİ AKIŞI (Mevcut Durum → Hedef)                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  loki_locations tablosu                                             │
│  ├── site_name kolonu ZATENVar (varchar 255)                        │
│  └── DC_LIST SQL sorgusu site_name DÖNMÜyor ← SORUN               │
│                                                                     │
│  ┌─ src/queries/loki.py ─────────────────────────────────────────┐  │
│  │  DC_LIST        → sadece dc_name  (MEVCUT)                    │  │
│  │  DC_LIST_WITH_SITE → dc_name + site_name (EKLENecek, mikro-   │  │
│  │                     servis'te zaten var)                       │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                         ↓                                           │
│  ┌─ src/services/db_service.py ──────────────────────────────────┐  │
│  │  _load_dc_list() → site_map dict'i de üretecek               │  │
│  │  _rebuild_summary() → summary dict'e "site_name" eklenecek   │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                         ↓                                           │
│  ┌─ API Layer (api_client.py) ───────────────────────────────────┐  │
│  │  get_all_datacenters_summary() → JSON transparently passes    │  │
│  │  (DEĞİŞİKLİK YOK)                                            │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                         ↓                                           │
│  ┌─ src/pages/global_view.py ────────────────────────────────────┐  │
│  │  _build_map_dataframe() → customdata'ya site_name eklenir     │  │
│  │  build_dc_info_card() → site_name alıp "Open Details" href    │  │
│  │    href=f"/datacenter/{dc_id}?region={site_name}"             │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Dokunulacak Dosyalar

| # | Dosya | İşlem | Katman |
|---|-------|-------|--------|
| 1 | `src/queries/loki.py` | **GÜNCELLE** — `DC_LIST_WITH_SITE` + `DC_LIST_WITH_SITE_NO_STATUS` SQL ekle | DB/SQL |
| 2 | `src/services/db_service.py` | **GÜNCELLE** — `_load_dc_list` → site_map üret, `_rebuild_summary` → `site_name` ekle | Service |
| 3 | `src/pages/global_view.py` | **GÜNCELLE** — `_build_map_dataframe` ve `_create_map_figure` customdata'ya `site_name` ekle, `build_dc_info_card` href güncelle | Frontend |
| 4 | `app.py` | **GÜNCELLE** — `update_global_info_card` callback'ini `site_name`'i customdata'dan al | Callback |

---

## ADIM 1 — SQL Sorgusu Güncellemesi (src/queries/loki.py)

### 1.1 Mevcut Durum Analizi

**Monolith** `src/queries/loki.py` dosyasında yalnızca 3 SQL sorgusu var:
- `DC_LIST` → sadece `dc_name` döndürür
- `DC_LIST_NO_STATUS` → sadece `dc_name`, status filtresi olmadan
- `LOCATION_DC_MAP` → `location_name → dc_name` eşlemesi

**Mikroservis** `services/datacenter-api/app/db/queries/loki.py` dosyasında ise zaten `DC_LIST_WITH_SITE` ve `DC_LIST_WITH_SITE_NO_STATUS` sorguları mevcuttur. Bu sorgular `dc_name` VE `site_name` döndürür.

### 1.2 Yapılacak İşlem

Mikroservis'teki `DC_LIST_WITH_SITE` ve `DC_LIST_WITH_SITE_NO_STATUS` sorgularını monolith `src/queries/loki.py` dosyasına ekle:

```python
DC_LIST_WITH_SITE = """
SELECT DISTINCT
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name,
    site_name
FROM public.loki_locations
WHERE
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
    AND status_value = 'active'
ORDER BY 1
"""

DC_LIST_WITH_SITE_NO_STATUS = """
SELECT DISTINCT
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name,
    site_name
FROM public.loki_locations
WHERE
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
ORDER BY 1
"""
```

### 1.3 loki_locations Tablo Yapısı (Referans)

```sql
site_name varchar(255) NULL    -- Zaten tabloda mevcut (satır 10)
```

> **ÖNEMLİ:** Tabloya kolon eklenmesi veya değişiklik yapılması gerekmiyor. `site_name` kolonu loki_locations tablosunda zaten mevcuttur.

### 1.4 Çıktı Kriterleri

- [ ] `DC_LIST_WITH_SITE` SQL sabitesi `src/queries/loki.py` dosyasına eklendi
- [ ] `DC_LIST_WITH_SITE_NO_STATUS` SQL sabitesi eklendi
- [ ] Mevcut `DC_LIST`, `DC_LIST_NO_STATUS` ve `LOCATION_DC_MAP` sorgularına dokunulmadı
- [ ] SQL sorguları mikroservis versiyonuyla birebir aynı

---

## ADIM 2 — DB Service Güncellemesi (src/services/db_service.py)

### 2.1 `_load_dc_list()` Fonksiyonunun Güncellenmesi

Mevcut fonksiyon (satır 401-425) yalnızca `dc_name` listesi döndürür. Yeni versiyonda:
1. `DC_LIST_WITH_SITE` sorgusu kullanılacak
2. `self._dc_site_map: dict[str, str]` instance variable'ı oluşturulacak
3. DC listesi (`list[str]`) döndürülmeye devam edecek (geriye uyumluluk)

**MEVCUT KOD (satır 401-425):**
```python
def _load_dc_list(self) -> list[str]:
    try:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                rows = self._run_rows(cur, lq.DC_LIST)
                dc_names = [row[0] for row in rows if row[0]]
                if not dc_names:
                    rows = self._run_rows(cur, lq.DC_LIST_NO_STATUS)
                    dc_names = [row[0] for row in rows if row[0]]
    except OperationalError as exc:
        logger.warning("Could not load DC list from DB: %s — using fallback.", exc)
        return _FALLBACK_DC_LIST.copy()
    if dc_names:
        logger.info("Loaded %d datacenters from loki_locations: %s", len(dc_names), dc_names)
        return dc_names
    logger.warning("loki_locations returned empty DC list — using fallback.")
    return _FALLBACK_DC_LIST.copy()
```

**YENİ KOD:**
```python
def _load_dc_list(self) -> list[str]:
    self._dc_site_map = {}
    try:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                rows = self._run_rows(cur, lq.DC_LIST_WITH_SITE)
                dc_names = [row[0] for row in rows if row[0]]
                for row in rows:
                    if row[0] and len(row) > 1 and row[1]:
                        self._dc_site_map[row[0]] = row[1]
                if not dc_names:
                    rows = self._run_rows(cur, lq.DC_LIST_WITH_SITE_NO_STATUS)
                    dc_names = [row[0] for row in rows if row[0]]
                    for row in rows:
                        if row[0] and len(row) > 1 and row[1]:
                            self._dc_site_map[row[0]] = row[1]
    except OperationalError as exc:
        logger.warning("Could not load DC list from DB: %s — using fallback.", exc)
        return _FALLBACK_DC_LIST.copy()
    if dc_names:
        logger.info("Loaded %d datacenters from loki_locations: %s", len(dc_names), dc_names)
        return dc_names
    logger.warning("loki_locations returned empty DC list — using fallback.")
    return _FALLBACK_DC_LIST.copy()
```

**Değişiklikler:**
1. `self._dc_site_map = {}` — her yüklemede temizle
2. `lq.DC_LIST` → `lq.DC_LIST_WITH_SITE` — artık 2 kolonlu SQL
3. `lq.DC_LIST_NO_STATUS` → `lq.DC_LIST_WITH_SITE_NO_STATUS`
4. Her satırdan `row[1]` (site_name) alınarak `_dc_site_map[dc_name] = site_name` eşlemesi oluşturulur
5. `dc_names` listesi hâlâ `[row[0] for row in rows]` — geriye uyumlu

### 2.2 `_rebuild_summary()` Fonksiyonundaki `summary_list.append` Güncellenmesi

`_rebuild_summary` fonksiyonundaki `summary_list.append` dict'ine `site_name` alanı eklenecek.

**MEVCUT (satır 1270-1274):**
```python
summary_list.append({
    "id": dc,
    "name": dc,
    "location": d["meta"]["location"],
    "status": "Healthy",
```

**YENİ:**
```python
summary_list.append({
    "id": dc,
    "name": dc,
    "location": d["meta"]["location"],
    "site_name": self._dc_site_map.get(dc),
    "status": "Healthy",
```

> **NOT:** Bu satır, mikroservis `dc_service.py` satır 1270 ile birebir aynıdır. Paralel tutarlılık sağlanır.

### 2.3 `_dc_site_map` Kullanım Diyagramı

```
_load_dc_list()
   │
   ├─ SQL: DC_LIST_WITH_SITE
   │    row[0] = dc_name  (örn: "DC11")
   │    row[1] = site_name (örn: "ISTANBUL")
   │
   ├─ self._dc_site_map["DC11"] = "ISTANBUL"
   │   self._dc_site_map["AZ11"] = "AZERBAYCAN"
   │   self._dc_site_map["ICT11"] = "ALMANYA"
   │   ...
   │
   └─ return ["DC11", "AZ11", "ICT11", ...]  ← dc_names listesi
              (geriye uyumlu, aynı format)

_rebuild_summary()
   │
   ├─ self._dc_list = self._load_dc_list()  ← site_map da doluyor
   │
   └─ summary_list.append({
          "site_name": self._dc_site_map.get("DC11"),  → "ISTANBUL"
          ...
      })
```

### 2.4 Çıktı Kriterleri

- [ ] `_load_dc_list()` artık `DC_LIST_WITH_SITE` sorgusunu kullanıyor
- [ ] `self._dc_site_map` dict'i `_load_dc_list` içinde dolduruluyor
- [ ] `_rebuild_summary` → summary dict'e `"site_name"` alanı eklendi
- [ ] `dc_names` listesi formatı değişmedi (geriye uyumluluk)
- [ ] Fallback path (`_FALLBACK_DC_LIST`) korundu ve `_dc_site_map` boş dict olarak kalıyor

---

## ADIM 3 — Frontend: customdata'ya site_name Eklenmesi ve Drilldown Routing

### 3.1 `_build_map_dataframe` → site_name Alanı

`_build_map_dataframe` fonksiyonu zaten `dc.get("site_name")` kullanıyor (satır 34). Ancak `rows.append` dict'ine `site_name` ekli **DEĞİL**. Eklenecek:

**MEVCUT (satır 46-61):**
```python
rows.append({
    "id": dc_id,
    "name": dc.get("name", dc_id),
    "location": dc.get("location", site_name.title()),
    ...
})
```

**YENİ (satır 46-62, +1 satır):**
```python
rows.append({
    "id": dc_id,
    "name": dc.get("name", dc_id),
    "site_name": dc.get("site_name", ""),
    "location": dc.get("location", site_name.title()),
    ...
})
```

### 3.2 `_create_map_figure` → customdata'ya site_name Eklenmesi

Pin Body trace'inin `customdata` dizisine 8. alan olarak `site_name` eklenecek.

**MEVCUT customdata yapısı:**
```
[0] = id          (dc_id)
[1] = name        (dc_name)
[2] = location    (şehir adı)
[3] = vm_count
[4] = host_count
[5] = health
[6] = ping
```

**YENİ customdata yapısı (index 7 = site_name):**
```
[0] = id          (dc_id)
[1] = name        (dc_name)
[2] = location    (şehir adı)
[3] = vm_count
[4] = host_count
[5] = health
[6] = ping
[7] = site_name   ← YENİ
```

**customdata_vals oluşturma kısmı:**

MEVCUT:
```python
customdata_vals.append([
    row["id"], row["name"], row["location"],
    row["vm_count"], row["host_count"], row["health"],
    ping_values[i],
])
```

YENİ:
```python
customdata_vals.append([
    row["id"], row["name"], row["location"],
    row["vm_count"], row["host_count"], row["health"],
    ping_values[i], row.get("site_name", ""),
])
```

### 3.3 `build_dc_info_card` → Drilldown href Güncellemesi

**MEVCUT (satır 476-486):**
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

**YENİ:**
```python
dcc.Link(
    dmc.Button(
        "Open Details",
        variant="light",
        color="indigo",
        radius="md",
        rightSection=DashIconify(icon="solar:arrow-right-linear", width=16),
    ),
    href=f"/datacenter/{dc_id}?region={site_name}",
    style={"textDecoration": "none"},
),
```

### 3.4 `build_dc_info_card` → Fonksiyon İmzasına site_name Eklenmesi

Fonksiyon `dc_id, tr` yerine `dc_id, tr, site_name=""` alacak:

**MEVCUT (satır 387):**
```python
def build_dc_info_card(dc_id, tr):
```

**YENİ:**
```python
def build_dc_info_card(dc_id, tr, site_name=""):
```

> **ÖNEMLİ:** `site_name` parametresi varsayılan değeri olan opsiyonel bir parametre. Mevcut çağrıları bozmaz.

### 3.5 Çıktı Kriterleri

- [ ] `_build_map_dataframe` → rows dict'ine `"site_name"` alanı eklendi
- [ ] `_create_map_figure` → customdata[7] = site_name
- [ ] `build_dc_info_card` → imzaya `site_name=""` parametresi eklendi
- [ ] "Open Details" butonu → `href=f"/datacenter/{dc_id}?region={site_name}"`
- [ ] Mevcut harita, tooltip, gauge, pin marker hiçbir şekilde bozulmadı

---

## ADIM 4 — Callback Güncellemesi (app.py)

### 4.1 `update_global_info_card` Callback'inde site_name Akışı

Tıklanan marker'ın `customdata[7]` verisinden `site_name` alınarak `build_dc_info_card`'a geçirilecek.

**MEVCUT (callback body):**
```python
dc_id = custom[0]
tr = time_range or default_time_range()
from src.pages.global_view import build_dc_info_card
return build_dc_info_card(dc_id, tr), patched_fig
```

**YENİ:**
```python
dc_id = custom[0]
site_name = custom[7] if len(custom) > 7 else ""
tr = time_range or default_time_range()
from src.pages.global_view import build_dc_info_card
return build_dc_info_card(dc_id, tr, site_name=site_name), patched_fig
```

### 4.2 Veri Akışı Diyagramı

```
Kullanıcı pin'e tıklar
        ↓
clickData.points[0].customdata
  [0]=dc_id  [1]=name  [2]=location  [3]=vm  [4]=host  [5]=health  [6]=ping  [7]=site_name
        ↓
app.py → update_global_info_card
  dc_id = custom[0]
  site_name = custom[7]
        ↓
build_dc_info_card(dc_id, tr, site_name="ISTANBUL")
        ↓
"Open Details" butonunun href'i:
  /datacenter/DC11?region=ISTANBUL
```

### 4.3 Çıktı Kriterleri

- [ ] `customdata`'dan `site_name` (index 7) güvenli şekilde çekiliyor (`len(custom) > 7` kontrolü)
- [ ] `build_dc_info_card` çağrısına `site_name` keyword argument olarak geçiriliyor
- [ ] Mevcut callback output'ları ve `dash.Patch()` rotasyon mantığı korundu

---

## KORUMA LİSTESİ

> **DOKUNULMAYACAK BİLEŞENLER:**

| # | Bileşen | Neden |
|---|---------|-------|
| 1 | 3D Küre (orthographic projection) | global3.md ile kuruldu, bozulmamalı |
| 2 | 3 katmanlı pin marker (shadow+halo+gradient) | Estetik korunmalı |
| 3 | Siber ızgara (graticules) | Görsel bütünlük |
| 4 | Küre rotasyonu (dash.Patch rotation/scale) | UX akışı |
| 5 | Reset Map View butonu ve callback'i | Fonksiyonellik |
| 6 | Glassmorphism tooltip (hovertemplate) | Premium tooltip |
| 7 | RingProgress gauge'lar | Info Card içeriği |
| 8 | Architecture satırı (VMware/Nutanix/IBM) | Info Card içeriği |
| 9 | `backend/`, `services/`, `k8s/` dizinleri | CTO yasası |
| 10 | `requirements.txt` | CTO yasası |

---

## UYGULAMA SIRALAMASI (Executer Checklist)

| Sıra | İşlem | Dosya | Durum |
|------|-------|-------|-------|
| 1 | `DC_LIST_WITH_SITE` + `DC_LIST_WITH_SITE_NO_STATUS` SQL ekle | `src/queries/loki.py` | ⬜ |
| 2 | `_load_dc_list()` → `DC_LIST_WITH_SITE` kullan + `_dc_site_map` oluştur | `src/services/db_service.py` satır 401-425 | ⬜ |
| 3 | `_rebuild_summary()` → `summary_list.append` dict'ine `"site_name"` ekle | `src/services/db_service.py` satır 1270-1274 | ⬜ |
| 4 | `_build_map_dataframe` → rows dict'ine `"site_name"` ekle | `src/pages/global_view.py` satır 46 | ⬜ |
| 5 | `_create_map_figure` → customdata'ya `row.get("site_name", "")` ekle | `src/pages/global_view.py` customdata_vals | ⬜ |
| 6 | `build_dc_info_card(dc_id, tr)` → `build_dc_info_card(dc_id, tr, site_name="")` | `src/pages/global_view.py` satır 387 | ⬜ |
| 7 | "Open Details" href → `/datacenter/{dc_id}?region={site_name}` | `src/pages/global_view.py` satır 484 | ⬜ |
| 8 | `update_global_info_card` → `custom[7]` site_name'i al ve geçir | `app.py` callback | ⬜ |
| 9 | Test: Uygulamayı çalıştır, pin'e tıkla, "Open Details" URL'ini kontrol et | Terminal + Tarayıcı | ⬜ |

---

## ⚠️ CTO'NUN İHLAL EDİLEMEZ YASALARI

### **YASA 1 — SIFIR YORUM SATIRI**

**Executer'ın yazacağı kodlarda TEK BİR açıklama satırı (`#`) veya docstring (`"""..."""`) BULUNMAYACAKTIR.** Tüm `.py` dosyaları saf, yorum-sız kod içerecektir. Bu yasanın ihlali halinde kod reddedilir.

### **YASA 2 — Backend Koruması**

Yalnızca aşağıdaki dosyalar değiştirilecektir:
- `src/queries/loki.py` (SQL sabitesi ekleme)
- `src/services/db_service.py` (site_map entegrasyonu)
- `src/pages/global_view.py` (frontend güncelleme)
- `app.py` (callback güncelleme)

`backend/`, `k8s/`, `services/` (kök seviye) dizinlerine **DOKUNMAK YASAKTIR.**

### **YASA 3 — Bağımlılık Koruması**

`requirements.txt`'e yeni paket **EKLENMEYECEK.** Tüm kullanılan modüller mevcut bağımlılıklardadır.

---

## DOĞRULAMA PLANI

### Otomatik Test

Mevcut test dosyası: `tests/test_db_service.py`

```bash
cd /Users/namlisarac/Desktop/Work/Datalake-Platform-GUI && python -m pytest tests/test_db_service.py -v
```

### Manuel Doğrulama (Tarayıcı)

1. Uygulamayı başlat: `python app.py`
2. Tarayıcıda `/global-view` sayfasına git
3. Küre üzerinde bir DC pin'ine tıkla
4. Info Card'ın altındaki "Open Details" butonunu incele
5. Butonun `href` değerinin `/datacenter/DC11?region=ISTANBUL` formatında olduğunu doğrula
6. Butona tıkla ve URL bar'dan query string'i kontrol et
7. 3D kürenin dönmesini, pin marker'ların ve tooltip'in bozulmadığını gözlemle
8. "Reset Map View" butonunun hâlâ çalıştığını teyit et

> **SON:** Bu plan, `site_name` verisini DB katmanından URL'e kadar uçtan uca taşıyacak cerrahi bir müdahaledir.
> 4 dosya güncellenir, 0 yeni dosya oluşturulur, 0 paket eklenir.
