# DC Görselleştirme Yükseltmesi — Premium Yarı Donat (Gauge) Entegrasyonu

## Amaç

Power Mimari sekmesinde kullanılan **yarı donat (gauge/half-donut) premium görünümü**, şu anda basit tam donat (full donut) kullanan **tüm diğer DC bölümlerine** entegre edilecek.

**Referans Görünüm:** `create_gauge_chart()` fonksiyonu — `src/components/charts.py:401-427`
- Yarım daire göstergesi (semi-circle gauge indicator)
- Renk zonları: 0-50 açık gri, 50-80 yarı şeffaf mor, 80-100 yarı şeffaf kırmızı
- Threshold çizgisi (90% seviyesinde)
- `%` suffix ile büyük merkezde rakam

**Mevcut Basit Donut:** `create_usage_donut_chart()` — `src/components/charts.py:86-131`
- Tam daire (360°) pie chart
- Sadece `Used` / `Free` iki dilim
- Ortalama estetik

---

## Etkilenen Bölümler & Dosyalar

### 1. `src/components/charts.py` — Yeni Fonksiyon Oluşturma

#### Görev 1.1: `create_premium_gauge_chart()` fonksiyonu oluştur

Mevcut `create_gauge_chart()` fonksiyonunu temel alarak, **yüzde (percentage) bazlı** yeni bir premium gauge fonksiyonu oluştur. Bu fonksiyon doğrudan yüzde değeri alacak (value/max hesabı gerektirmeyecek).

```python
def create_premium_gauge_chart(pct_value, title, color="#4318FF", height=220, show_threshold=True):
```

**Parametreler:**
- `pct_value`: float — 0-100 arası yüzde değeri
- `title`: str — Grafik başlığı (örn: "CPU Usage", "RAM Usage")
- `color`: str — Ana bar rengi (her bölüm için farklı renk)
- `height`: int — Grafik yüksekliği
- `show_threshold`: bool — 90% threshold çizgisi gösterilsin mi

**Görsel Detaylar (Power Mimari referans):**
- `go.Indicator` kullanılacak (`mode="gauge+number"`)
- `number={"suffix": "%", "font": {"size": 36, "color": "#2B3674", "family": "DM Sans", "weight": 900}}`
- Gauge axis range: `[0, 100]`
- Gauge steps (renk bölgeleri):
  - `[0, 50]` → `"#E9EDF7"` (açık gri)
  - `[50, 80]` → `rgba(color, 0.3)` (yarı şeffaf ana renk)
  - `[80, 100]` → `"rgba(238, 93, 80, 0.3)"` (yarı şeffaf kırmızı)
- Gauge bar color: Ana `color` parametresi
- Threshold: `{"line": {"color": "#2B3674", "width": 4}, "value": 90}`
- Title: `{"text": title, "font": {"size": 13, "color": "#A3AED0", "family": "DM Sans"}}`
- Layout:
  - `paper_bgcolor="rgba(0,0,0,0)"`
  - `margin=dict(l=20, r=20, t=44, b=20)`
  - `font=dict(family="DM Sans", color="#A3AED0")`

#### Görev 1.2: `create_premium_gauge_with_avg()` fonksiyonu oluştur

`create_avg_max_donut_chart()` yerine kullanılacak. Peak ve avg değerleri gauge şeklinde gösterecek.

```python
def create_premium_gauge_with_avg(avg_pct, max_pct, title, color="#4318FF", height=220):
```

**Parametreler:**
- `avg_pct`: float — Ortalama kullanım yüzdesi
- `max_pct`: float — Peak kullanım yüzdesi (gauge'da gösterilen ana değer)
- `title`: str — Grafik başlığı (örn: "CPU Usage (peak)")
- `color`: str — Ana bar rengi

**Görsel Detaylar:**
- `go.Indicator` kullanılacak (`mode="gauge+number"`)
- Ana değer olarak `max_pct` gösterilecek
- `number={"suffix": "%", "font": {"size": 32, "color": "#2B3674", "family": "DM Sans", "weight": 900}}`
- Gauge bar color: Ana `color` parametresi
- Aynı step renkleri
- **Ek annotation:** gauge altına `f"avg {int(avg_pct)}%"` yazısı
  - `font={"size": 12, "color": "#A3AED0", "family": "DM Sans"}`
  - `x=0.5, y=0.15`

---

### 2. `src/pages/dc_view.py` — Summary Sekmesi

**Dosya:** `src/pages/dc_view.py`  
**Fonksiyon:** `_build_summary_tab()` (satır 1162-1305)  
**Bölüm:** "Resource Utilization" (satır 1206-1229)

#### Görev 2.1: Summary — Resource Utilization donatlarını gauge'a çevir

**Mevcut kod (satır 1212-1228):**
```python
dmc.SimpleGrid(cols=3, spacing="lg", style={"marginTop": "12px"}, children=[
    _chart_card(dcc.Graph(
        figure=create_usage_donut_chart(cpu_pct, "CPU Usage"),
        ...
    )),
    _chart_card(dcc.Graph(
        figure=create_usage_donut_chart(mem_pct, "RAM Usage"),
        ...
    )),
    _chart_card(dcc.Graph(
        figure=create_usage_donut_chart(stor_pct, "Storage Usage"),
        ...
    )),
]),
```

**Yeni kod:**
```python
dmc.SimpleGrid(cols=3, spacing="lg", style={"marginTop": "12px"}, children=[
    _chart_card(dcc.Graph(
        figure=create_premium_gauge_chart(cpu_pct, "CPU Usage", color="#4318FF"),
        config={"displayModeBar": False},
        style={"height": "100%", "width": "100%"},
    )),
    _chart_card(dcc.Graph(
        figure=create_premium_gauge_chart(mem_pct, "RAM Usage", color="#05CD99"),
        config={"displayModeBar": False},
        style={"height": "100%", "width": "100%"},
    )),
    _chart_card(dcc.Graph(
        figure=create_premium_gauge_chart(stor_pct, "Storage Usage", color="#FFB547"),
        config={"displayModeBar": False},
        style={"height": "100%", "width": "100%"},
    )),
]),
```

**Renk Atamaları:**
| Metrik | Renk |
|--------|------|
| CPU Usage | `#4318FF` (mor) |
| RAM Usage | `#05CD99` (turkuaz yeşil) |
| Storage Usage | `#FFB547` (turuncu amber) |

---

### 3. `src/pages/dc_view.py` — Virtualization > Klasik Mimari

**Fonksiyon:** `_build_compute_tab()` (satır 561-631)  
**Bölüm:** Donut charts (satır 592-616)

#### Görev 3.1: Klasik Mimari donatlarını gauge'a çevir

**Mevcut kod (satır 592-616):**
```python
dmc.SimpleGrid(cols=3, spacing="lg", children=[
    _chart_card(dcc.Graph(
        figure=(
            create_avg_max_donut_chart(cpu_pct, cpu_pct_max, "CPU Usage (peak)")
            if cpu_pct_max > 0
            else create_usage_donut_chart(cpu_pct, "CPU Usage")
        ),
        ...
    )),
    _chart_card(dcc.Graph(
        figure=(
            create_avg_max_donut_chart(mem_pct, mem_pct_max, "RAM Usage (peak)")
            if mem_pct_max > 0
            else create_usage_donut_chart(mem_pct, "RAM Usage")
        ),
        ...
    )),
    _chart_card(dcc.Graph(
        figure=create_usage_donut_chart(stor_pct, "Storage Usage"),
        ...
    )),
]),
```

**Yeni kod:**
```python
dmc.SimpleGrid(cols=3, spacing="lg", children=[
    _chart_card(dcc.Graph(
        figure=(
            create_premium_gauge_with_avg(cpu_pct, cpu_pct_max, "CPU Usage (peak)", color="#4318FF")
            if cpu_pct_max > 0
            else create_premium_gauge_chart(cpu_pct, "CPU Usage", color="#4318FF")
        ),
        config={"displayModeBar": False},
        style={"height": "100%", "width": "100%"},
    )),
    _chart_card(dcc.Graph(
        figure=(
            create_premium_gauge_with_avg(mem_pct, mem_pct_max, "RAM Usage (peak)", color="#05CD99")
            if mem_pct_max > 0
            else create_premium_gauge_chart(mem_pct, "RAM Usage", color="#05CD99")
        ),
        config={"displayModeBar": False},
        style={"height": "100%", "width": "100%"},
    )),
    _chart_card(dcc.Graph(
        figure=create_premium_gauge_chart(stor_pct, "Storage Usage", color="#FFB547"),
        config={"displayModeBar": False},
        style={"height": "100%", "width": "100%"},
    )),
]),
```

> **Not:** `_build_compute_tab()` hem Klasik hem Hyperconverged için ortak kullanıldığından, bu değişiklik **her iki mimari sekmesini** de otomatik olarak etkileyecek.

---

### 4. `src/pages/dc_view.py` — Virtualization > Hyperconverged Mimari

Hyperconverged Mimari de `_build_compute_tab()` fonksiyonunu kullandığı için **Görev 3.1'deki değişiklik Hyperconverged'ı da kapsar.** Ek bir değişiklik gerekmez.

---

### 5. `src/pages/dc_view.py` — Network > Dashboard

**Fonksiyon:** `_build_network_dashboard_subtab()` (satır 1437-1660)  
**Bölüm:** Donut charts (satır 1491-1494 ve satır 1597-1626)

#### Görev 5.1: Network donat grafiklerini gauge'a çevir

**Mevcut donut oluşturma (satır 1492-1494):**
```python
donut_active = create_usage_donut_chart(port_availability_pct, "Port Availability", color="#FFB547")
donut_util = create_usage_donut_chart(overall_util_pct, "Port Utilization", color="#05CD99")
donut_icmp = create_usage_donut_chart(icmp_availability_pct, "ICMP Availability", color="#4318FF")
```

**Yeni kod:**
```python
donut_active = create_premium_gauge_chart(port_availability_pct, "Port Availability", color="#FFB547")
donut_util = create_premium_gauge_chart(overall_util_pct, "Port Utilization", color="#05CD99")
donut_icmp = create_premium_gauge_chart(icmp_availability_pct, "ICMP Availability", color="#4318FF")
```

**Renk Atamaları:**
| Metrik | Renk |
|--------|------|
| Port Availability | `#FFB547` (amber) |
| Port Utilization | `#05CD99` (turkuaz yeşil) |
| ICMP Availability | `#4318FF` (mor) |

#### Görev 5.2: Network donat chart height'ını güncelle

`_chart_card` wrapper'ının height'ını ve graph style'ını gauge'a uygun hale getir.

**Mevcut (satır 1600-1625):**
```python
style={"height": "180px"},
```

**Yeni:**
```python
style={"height": "100%", "width": "100%"},
```

#### Görev 5.3: Network callback'teki donut güncelleme fonksiyonlarını da gauge'a çevir

`app.py` içindeki network filter callback'i donat çizimleri güncelliyor. Bu callback'lerde de `create_usage_donut_chart` → `create_premium_gauge_chart` olarak güncellenecek.

**Dosya:** `app.py`  
**Aranacak pattern:** `create_usage_donut_chart` çağrıları (Network callback bölümü)

---

### 6. `src/pages/dc_view.py` — Network > SAN

**Fonksiyon:** `_build_san_subtab()` (satır 914-1137)  
**Bölüm:** Port license donuts (satır 1052-1106)

#### Görev 6.1: SAN donatlarını gauge'a çevir

**Mevcut kod (satır 1060-1104):**
```python
_chart_card(
    dcc.Graph(
        figure=create_usage_donut_chart(licensed_pct, "Pod License ROI", color="#4318FF"),
        ...
    )
),
...
_chart_card(
    dcc.Graph(
        figure=create_usage_donut_chart(active_pct, "Active vs Licensed", color="#05CD99"),
        ...
    )
),
...
_chart_card(
    dcc.Graph(
        figure=create_usage_donut_chart(available_pct, "Port Availability", color="#FFB547"),
        ...
    )
),
```

**Yeni kod:**
```python
_chart_card(
    dcc.Graph(
        figure=create_premium_gauge_chart(licensed_pct, "Pod License ROI", color="#4318FF"),
        config={"displayModeBar": False},
        style={"height": "100%", "width": "100%"},
    )
),
...
_chart_card(
    dcc.Graph(
        figure=create_premium_gauge_chart(active_pct, "Active vs Licensed", color="#05CD99"),
        config={"displayModeBar": False},
        style={"height": "100%", "width": "100%"},
    )
),
...
_chart_card(
    dcc.Graph(
        figure=create_premium_gauge_chart(available_pct, "Port Availability", color="#FFB547"),
        config={"displayModeBar": False},
        style={"height": "100%", "width": "100%"},
    )
),
```

---

### 7. `src/pages/dc_view.py` — Storage > Intel Storage

**Fonksiyon:** `_build_intel_storage_subtab()` (satır 1663-1770)  
**Bölüm:** Donuts (satır 1707-1709 ve satır 1744-1752)

#### Görev 7.1: Intel Storage donatlarını gauge'a çevir

**Mevcut kod (satır 1707-1709):**
```python
donut_total = create_usage_donut_chart(100.0, f"Total {smart_storage(total_gb)}", color="#FFB547")
donut_used = create_usage_donut_chart(used_pct, "Used Capacity", color="#4318FF")
donut_free = create_usage_donut_chart(free_pct, "Free Capacity", color="#05CD99")
```

**Yeni kod:**
```python
donut_total = create_premium_gauge_chart(100.0, f"Total {smart_storage(total_gb)}", color="#FFB547")
donut_used = create_premium_gauge_chart(used_pct, "Used Capacity", color="#4318FF")
donut_free = create_premium_gauge_chart(free_pct, "Free Capacity", color="#05CD99")
```

#### Görev 7.2: Intel Storage callback'teki donat güncelleme fonksiyonlarını da gauge'a çevir

`app.py` içindeki `intel-storage-device-selector` callback'indeki donat oluşturmalarını da `create_premium_gauge_chart` ile değiştir.

---

### 8. `src/components/charts.py` — Import Güncellemesi

#### Görev 8.1: Yeni fonksiyonları export listesine ekle

`charts.py` dosyasına eklenen `create_premium_gauge_chart` ve `create_premium_gauge_with_avg` fonksiyonları otomatik olarak import edilebilir hale gelecek.

---

### 9. `src/pages/dc_view.py` — Import Güncellemesi

#### Görev 9.1: dc_view.py import'larını güncelle

**Mevcut import (satır 22-27):**
```python
from src.components.charts import (
    create_usage_donut_chart,
    create_avg_max_donut_chart,
    create_gauge_chart,
    create_dual_line_chart,
    create_sparkline_chart,
)
```

**Yeni import:**
```python
from src.components.charts import (
    create_usage_donut_chart,
    create_avg_max_donut_chart,
    create_gauge_chart,
    create_premium_gauge_chart,
    create_premium_gauge_with_avg,
    create_dual_line_chart,
    create_sparkline_chart,
)
```

---

### 10. `app.py` — Callback Import ve Güncelleme

#### Görev 10.1: app.py'deki callback'lerde donut → gauge dönüşümü

`app.py` dosyasında Network ve Storage callback'leri `create_usage_donut_chart` kullanıyor. Bu callback'ler dinamik olarak güncellenen grafikler oluşturuyor. Bunların hepsini `create_premium_gauge_chart` ile değiştir.

**Aranacak pattern:** `create_usage_donut_chart` (app.py içinde)
**Yapılacak:** Her kullanımı `create_premium_gauge_chart` ile değiştir

**app.py import bölümüne ekle:**
```python
from src.components.charts import create_premium_gauge_chart, create_premium_gauge_with_avg
```

---

## `_chart_card` Height Uyumu

Gauge chart'lar donut'lara göre biraz daha yüksek alan gerektirir. `_chart_card` fonksiyonu şu anda 250px height kullanıyor (satır 522-528).

#### Görev 11: _chart_card height'ını gauge için ayarla

Gauge chart'lar default 220px height ile oluşturuluyor, `_chart_card` 250px height sağlıyor. Bu uyumlu.

Ancak Network bölümündeki donut'lar 180px height ile render ediliyor. Bunları gauge ile uyumlu olması için `style={"height": "100%", "width": "100%"}` olarak güncellemek yeterli (Görev 5.2'de yapılıyor).

---

## Değiştirilmeyecek Bölümler

> [!IMPORTANT]
> Aşağıdaki gauge kullanımları **zaten premium gauge kullanıyor**, dokunulmayacak:
> - Power Mimari — Memory Assigned gauge (satır 682-686)
> - Power Mimari — CPU Used gauge (satır 687-691)
> - Power Mimari — Storage Capacity gauge (satır 717-721)
> - IBM Storage subtab — Storage Capacity gauge (satır 1899-1905)

---

## Özet Değişiklik Tablosu

| # | Bölüm | Dosya | Satır | Mevcut | Yeni |
|---|--------|-------|-------|--------|------|
| 1 | Charts — Yeni Fonksiyon | `charts.py` | Yeni | — | `create_premium_gauge_chart()` |
| 2 | Charts — Yeni Fonksiyon | `charts.py` | Yeni | — | `create_premium_gauge_with_avg()` |
| 3 | Summary — Resource Util | `dc_view.py` | 1213-1227 | `create_usage_donut_chart` ×3 | `create_premium_gauge_chart` ×3 |
| 4 | Klasik Mimari | `dc_view.py` | 593-615 | `create_avg_max_donut_chart` + `create_usage_donut_chart` | `create_premium_gauge_with_avg` + `create_premium_gauge_chart` |
| 5 | Hyperconverged | `dc_view.py` | — | (otomatik, ortak fonksiyon) | (otomatik) |
| 6 | Network Dashboard | `dc_view.py` | 1492-1494 | `create_usage_donut_chart` ×3 | `create_premium_gauge_chart` ×3 |
| 7 | Network SAN | `dc_view.py` | 1060-1104 | `create_usage_donut_chart` ×3 | `create_premium_gauge_chart` ×3 |
| 8 | Intel Storage | `dc_view.py` | 1707-1709 | `create_usage_donut_chart` ×3 | `create_premium_gauge_chart` ×3 |
| 9 | dc_view import | `dc_view.py` | 22-27 | — | +2 import |
| 10 | app.py callbacks | `app.py` | Çoklu | `create_usage_donut_chart` | `create_premium_gauge_chart` |
| 11 | app.py import | `app.py` | import | — | +2 import |

---

## Checklist

- [ ] `charts.py` → `create_premium_gauge_chart()` fonksiyonu oluştur
- [ ] `charts.py` → `create_premium_gauge_with_avg()` fonksiyonu oluştur
- [ ] `dc_view.py` → Import'ları güncelle
- [ ] `dc_view.py` → `_build_summary_tab()` — 3× donut → gauge
- [ ] `dc_view.py` → `_build_compute_tab()` — 3× donut → gauge (Klasik + Hyperconverged)
- [ ] `dc_view.py` → `_build_network_dashboard_subtab()` — 3× donut → gauge
- [ ] `dc_view.py` → `_build_san_subtab()` — 3× donut → gauge
- [ ] `dc_view.py` → `_build_intel_storage_subtab()` — 3× donut → gauge
- [ ] `app.py` → Import'ları güncelle
- [ ] `app.py` → Network callback donut → gauge
- [ ] `app.py` → Intel Storage callback donut → gauge
- [ ] Test: Uygulamayı çalıştır ve tüm bölümleri kontrol et
