# 🔗 GLOBAL MAP VIEW V5.2 — Routing Revizyonu & Adaptif Yakınlaştırma (global5.md)

> **Versiyon:** 5.2
> **Tarih:** 2026-03-26
> **Hazırlayan:** Baş Planlayıcı & Sistem Mimarı
> **Hedef:** (1) "Open Details" butonunu "Region Drilldown" butonuna dönüştürmek. (2) Türkiye içindeki yoğun DC bölgeleri için daha yüksek zoom, yurt dışı DC'ler için standart zoom uygulayan Bölge Bazlı Adaptif Yakınlaştırma sistemi.

---

## DOKUNULACAK DOSYALAR

| # | Dosya | İşlem |
|---|-------|-------|
| 1 | `src/pages/global_view.py` | **GÜNCELLE** — buton metni/ikonu/href + `_CITY_OFFSETS` genişletme |
| 2 | `app.py` | **GÜNCELLE** — clientside callback'te adaptif tScale mantığı |

---

## ADIM 1 — Buton Metni ve İkon Revizyonu

### 1.1 Konum

`src/pages/global_view.py` → `build_dc_info_card` fonksiyonu → Info Card header'ındaki sağ taraftaki `dmc.Group` içindeki `dcc.Link` bileşeni.

### 1.2 Değişiklikler

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
        "Region Drilldown",
        variant="light",
        color="indigo",
        radius="md",
        rightSection=DashIconify(icon="solar:map-point-wave-bold-duotone", width=18),
    ),
    href=f"/region-drilldown?region={site_name}",
    style={"textDecoration": "none"},
),
```

### 1.3 Değişiklik Detayları

| Öğe | Eski | Yeni | Neden |
|-----|------|------|-------|
| **Buton metni** | `"Open Details"` | `"Region Drilldown"` | UX: Bölge analizi konseptini yansıtır |
| **İkon** | `solar:arrow-right-linear` (16px) | `solar:map-point-wave-bold-duotone` (18px) | Bölge/konum semantiği |
| **href** | `/datacenter/{dc_id}` | `/region-drilldown?region={site_name}` | Rota tamamen değişiyor |
| **dc_id** | URL path'te kullanılıyordu | **ARTIK KULLANILMIYOR** | Bölge rotası DC-bağımsız |

---

## ADIM 2 — Href / Routing Revizyonu

### 2.1 Rota Karşılaştırması

```
ESKİ:  /datacenter/DC11                    ← DC-specific detay sayfası
       /datacenter/DC11?region=ISTANBUL    ← (global4 ara formatı)

YENİ:  /region-drilldown?region=ISTANBUL   ← Bölge analizi sayfası
```

> **NOT:** URL'de `{dc_id}` parametresi **ARTIK BULUNMUYOR**.

### 2.2 site_name Akışı

```
Pin tıklanır → clickData.customdata[7] = "ISTANBUL"
    → app.py callback → build_dc_info_card(dc_id, tr, site_name="ISTANBUL")
        → href=f"/region-drilldown?region=ISTANBUL"
```

---

## ADIM 3 — Kalıntı Temizliği ve Koruma

### 3.1 Temizlenecekler

- [ ] `href=f"/datacenter/{dc_id}"` referansı tamamen kaldırıldı
- [ ] `href=f"/datacenter/{dc_id}?region={site_name}"` (global4 ara formatı) yok
- [ ] `dc_id` SADECE `api.get_dc_details` ve UI gösterimi için kullanılıyor — `href`'te yok

### 3.2 Korunacaklar (DOKUNMA!)

| Bileşen | Durum |
|---------|-------|
| 3D Küre, Pin markers, Tooltip, Gauge'lar | ❌ DOKUNMA |
| Reset Map View butonu + reset callback | ❌ DOKUNMA |
| `_build_map_dataframe`, `_create_map_figure` | ❌ DOKUNMA |

---

## ADIM 4 — Bölge Bazlı Adaptif Yakınlaştırma (Adaptive Zoom)

### 4.1 Problem

Türkiye'de 3 şehirde toplam **7+ DC** bulunur:
- **İstanbul:** DC11, DC13, DC15, DC17 (4 DC, aynı koordinat bölgesi)
- **Ankara:** DC14, DC16 (2 DC)
- **İzmir:** DC12 (1 DC)

Mevcut sabit `tScale = 6.0` ile Türkiye'deki pin'ler birbirine çok yakın görünür ve ayırt edilemez. Yurt dışı DC'ler ise (her şehirde genelde 1 DC) `6.0` ile gayet iyi görünür.

### 4.2 Çözüm: Conditional Scale in Clientside Callback

`app.py` → Clientside callback (satır 484-519) içinde `customdata[7]` (site_name) değerine bakılarak **Türkiye bölgeleri** için `10.0`, **yurt dışı** için `6.0` uygulanacak.

### 4.3 Mevcut Clientside Callback (satır 499)

```javascript
var tLon = point.lon, tLat = point.lat, tScale = 6.0;  // ← SABİT
```

### 4.4 Güncellenmiş Satır (4 satıra genişler)

```javascript
var siteName = (point.customdata && point.customdata[7]) ? point.customdata[7].toUpperCase() : '';
var trSites = ['ISTANBUL', 'ANKARA', 'IZMIR'];
var tLon = point.lon, tLat = point.lat;
var tScale = trSites.indexOf(siteName) >= 0 ? 10.0 : 6.0;
```

### 4.5 Tam Güncellenmiş Callback

```javascript
function(clickData) {
    if (!clickData || !clickData.points || !clickData.points.length)
        return window.dash_clientside.no_update;
    var point = clickData.points[0];
    if (!point.customdata || !point.customdata[0])
        return window.dash_clientside.no_update;
    var outer = document.getElementById('global-map-graph');
    if (!outer) return window.dash_clientside.no_update;
    var gd = outer.querySelector('.js-plotly-plot') || outer;
    if (!gd._fullLayout || !gd._fullLayout.geo) return window.dash_clientside.no_update;
    var rot = gd._fullLayout.geo.projection.rotation;
    var startLon = rot.lon, startLat = rot.lat;
    var startScale = gd._fullLayout.geo.projection.scale || 1.0;
    var siteName = (point.customdata && point.customdata[7]) ? point.customdata[7].toUpperCase() : '';
    var trSites = ['ISTANBUL', 'ANKARA', 'IZMIR'];
    var tLon = point.lon, tLat = point.lat;
    var tScale = trSites.indexOf(siteName) >= 0 ? 10.0 : 6.0;
    var dur = 1100, t0 = null;
    function ease(t) { return t<.5 ? 4*t*t*t : 1-Math.pow(-2*t+2,3)/2; }
    function step(ts) {
        if (!t0) t0 = ts;
        var p = Math.min((ts-t0)/dur, 1), e = ease(p);
        window.Plotly.relayout(gd, {
            'geo.projection.rotation.lon': startLon+(tLon-startLon)*e,
            'geo.projection.rotation.lat': startLat+(tLat-startLat)*e,
            'geo.projection.scale':        startScale+(tScale-startScale)*e
        });
        if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
    return window.dash_clientside.no_update;
}
```

### 4.6 Scale Değerleri

| Bölge | site_name Örnekleri | scale | Neden |
|-------|---------------------|-------|-------|
| **Türkiye** | `ISTANBUL`, `ANKARA`, `IZMIR` | **10.0** | Yoğun DC kümesi — yüksek yakınlaştırma |
| **Yurt Dışı** | `AZERBAYCAN`, `ALMANYA`, `INGILTERE`, vb. | **6.0** | Tek DC — standart yakınlaştırma |
| **Reset** | — | **1.0** | Tam küre (değişmiyor) |

### 4.7 Pin Offset Genişletme (Opsiyonel Optimizasyon)

Pin'lerin birbirinden fiziksel uzaklığını 2x artırmak için `_CITY_OFFSETS` genişletilir:

**MEVCUT (satır 23-27):**
```python
_CITY_OFFSETS = [
    (0.00, 0.00), (0.06, 0.00), (-0.06, 0.00),
    (0.00, 0.09), (0.00, -0.09), (0.06, 0.09),
    (-0.06, 0.09), (0.06, -0.09),
]
```

**ÖNERİLEN (2x genişletilmiş):**
```python
_CITY_OFFSETS = [
    (0.00, 0.00), (0.12, 0.00), (-0.12, 0.00),
    (0.00, 0.18), (0.00, -0.18), (0.12, 0.18),
    (-0.12, 0.18), (0.12, -0.18),
]
```

### 4.8 Görsel Karşılaştırma

```
ÖNCE (scale=6.0, küçük offset):            SONRA (scale=10.0, büyük offset):

     ┌────────────────────┐                 ┌────────────────────┐
     │      ●●            │ pin'ler         │    ●     ●         │ pin'ler
     │       ●●           │ üst üste        │                    │ net ayrık
     └────────────────────┘                 │    ●     ●         │
                                            └────────────────────┘
```

### 4.9 Çıktı Kriterleri

- [ ] `customdata[7]` (site_name) okunarak Türkiye/yurt dışı ayrımı yapılıyor
- [ ] Türkiye DC'leri → `tScale = 10.0`, yurt dışı → `tScale = 6.0`
- [ ] Reset callback'teki `tScale = 1.0` **DEĞİŞMİYOR**
- [ ] `_CITY_OFFSETS` değerleri 2x genişletilmiş

---

## UYGULAMA SIRALAMASI (Executer Checklist)

| Sıra | İşlem | Dosya | Durum |
|------|-------|-------|-------|
| 1 | `"Open Details"` → `"Region Drilldown"` | `global_view.py` satır 478 | ⬜ |
| 2 | İkon: `solar:arrow-right-linear` → `solar:map-point-wave-bold-duotone` (18px) | `global_view.py` satır 482 | ⬜ |
| 3 | href: `/datacenter/{dc_id}` → `/region-drilldown?region={site_name}` | `global_view.py` satır 484 | ⬜ |
| 4 | `_CITY_OFFSETS` → 2x genişlet (0.06→0.12, 0.09→0.18) | `global_view.py` satır 23-27 | ⬜ |
| 5 | Clientside callback: `tScale = 6.0` → conditional (TR=10.0, yurt dışı=6.0) | `app.py` satır 499 | ⬜ |
| 6 | Test: İstanbul DC tıkla → yüksek zoom, Azerbaycan tıkla → standart zoom | Tarayıcı | ⬜ |

---

## ⚠️ CTO'NUN İHLAL EDİLEMEZ YASASI — SIFIR YORUM SATIRI

**Executer'ın yazacağı kodlarda TEK BİR açıklama satırı (`#`) veya docstring (`"""..."""`) BULUNMAYACAKTIR.** Sadece saf Python kodu yazılacaktır. Bu yasanın ihlali halinde kod reddedilir.

---

> **SON:** Bu plan 2 dosyada toplam ~10 satırlık cerrahi değişiklik gerektirir.
> `src/pages/global_view.py` → buton + offset, `app.py` → clientside callback scale.
> Reset callback'i ve 3D küre yapısı korunur.
