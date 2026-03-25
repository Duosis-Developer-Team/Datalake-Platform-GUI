# 🌍 GLOBAL MAP VIEW V2 — UX/UI İyileştirme Planı (global2.md)

> **Versiyon:** 2.0  
> **Tarih:** 2026-03-25  
> **Hazırlayan:** Baş Planlayıcı & Sistem Mimarı  
> **Hedef:** MVP'deki 3 kritik UI/UX sorununu çözmek — üst üste binen noktalar, eksik ülkeler ve çirkin tooltip.  
> **Kapsam:** Yalnızca `src/pages/global_view.py` dosyası güncellenir.

---

## SORUN ANALİZİ

| # | Sorun | Kök Neden | Etki |
|---|-------|-----------|------|
| 1 | İstanbul'daki DC'ler üst üste binip devasa leke oluşturuyor | DC11, DC12, DC13 arası koordinat farkı sadece ~0.004° (~400m), bu harita zoom=4 seviyesinde piksel bazında aynı nokta | Kullanıcı ayrı DC'leri ayırt edemiyor |
| 2 | UK, Baku, Ankara DC'leri görünmüyor/eksik | `DC_COORDINATES` sözlüğünde bu lokasyonlar tanımlı değil, fallback İstanbul'a düşüyor → İstanbul'u daha da şişiriyor | Coğrafi dağılım yanlış yansıyor |
| 3 | Hover tooltip Plotly varsayılan çirkin formatında | `hover_data` dict kullanıyor → `key=value` satır formatı, stil kontrolü yok | Profesyonel görünmüyor, UX zayıf |

---

## ADIM 1 — Koordinat Dağıtımı & Yeni Ülkeler

### 1.1 Amaç

`DC_COORDINATES` sözlüğünü yeniden yapılandırarak:
- Eksik ülkeleri (İngiltere, Azerbaycan) eklemek
- Ankara koordinatını sabitlemek
- Aynı şehirdeki DC'lere **jitter/offset** uygulayarak üst üste binmeyi engellemek
- Fallback koordinatını İstanbul'dan nötr bir noktaya taşımak

### 1.2 Jitter Stratejisi

Aynı şehirdeki DC'ler birbirinden **minimum 0.06° (~6.5km)** mesafede olmalıdır. Bu sayede zoom=4 seviyesinde bile noktalar ayrı adacıklar olarak görünür.

Dağılım deseni — merkez noktadan kuzey, güney, doğu, batı yönlerinde offset:

```
         DC12 (+0.06, 0)
           ⬆
DC13 (0, -0.06) ← MERKEZ → DC14 (0, +0.06)
           ⬇
         DC11 (-0.06, 0)
```

### 1.3 Yeni DC_COORDINATES Sözlüğü

Mevcut (satır 9–20) `DC_COORDINATES` sözlüğü **tamamen** aşağıdaki ile değiştirilecektir:

```python
DC_COORDINATES = {
    "DC11": {"lat": 40.95, "lon": 28.88, "city": "Istanbul"},
    "DC12": {"lat": 41.08, "lon": 28.98, "city": "Istanbul"},
    "DC13": {"lat": 41.00, "lon": 29.10, "city": "Istanbul"},
    "DC14": {"lat": 41.10, "lon": 29.20, "city": "Istanbul"},
    "DC15": {"lat": 40.92, "lon": 29.05, "city": "Istanbul"},
    "DC21": {"lat": 39.92, "lon": 32.85, "city": "Ankara"},
    "DC22": {"lat": 39.98, "lon": 32.78, "city": "Ankara"},
    "DC31": {"lat": 38.42, "lon": 27.13, "city": "Izmir"},
    "Equinix": {"lat": 50.12, "lon": 8.72, "city": "Frankfurt"},
    "Maincubes": {"lat": 50.05, "lon": 8.58, "city": "Frankfurt"},
    "E-Shelter": {"lat": 50.18, "lon": 8.65, "city": "Frankfurt"},
    "Interxion": {"lat": 52.30, "lon": 4.94, "city": "Amsterdam"},
    "UK1": {"lat": 51.51, "lon": -0.13, "city": "London"},
    "UK2": {"lat": 51.45, "lon": -0.05, "city": "London"},
    "AZ1": {"lat": 40.41, "lon": 49.87, "city": "Baku"},
    "AZ2": {"lat": 40.47, "lon": 49.93, "city": "Baku"},
}
```

### 1.4 Koordinat Değişiklik Detayları

#### İstanbul Cluster'ı (5 DC)

| DC | Eski Lat | Eski Lon | Yeni Lat | Yeni Lon | Offset Açıklama |
|----|----------|----------|----------|----------|-----------------|
| DC11 | 41.0082 | 28.9784 | 40.95 | 28.88 | Güneybatı, -0.058, -0.098 |
| DC12 | 41.0122 | 28.9760 | 41.08 | 28.98 | Kuzey, merkeze yakın |
| DC13 | 41.0055 | 28.9530 | 41.00 | 29.10 | Doğu, +0.15 lon |
| DC14 | 41.0190 | 29.0600 | 41.10 | 29.20 | Kuzeydoğu, en uzak |
| DC15 | — | — | 40.92 | 29.05 | Yeni DC, güneydoğu |

> DC'ler arası minimum mesafe artık **~0.07° ≈ 7.5km** → zoom=4'te net ayrım.

#### Yeni Ülkeler

| DC | Lat | Lon | Şehir | Ülke |
|----|-----|-----|-------|------|
| UK1 | 51.51 | -0.13 | London | İngiltere |
| UK2 | 51.45 | -0.05 | London | İngiltere |
| AZ1 | 40.41 | 49.87 | Baku | Azerbaycan |
| AZ2 | 40.47 | 49.93 | Baku | Azerbaycan |

#### Ankara Sabitleme

| DC | Eski Lat | Eski Lon | Yeni Lat | Yeni Lon | Not |
|----|----------|----------|----------|----------|-----|
| DC21 | 39.9208 | 32.8541 | 39.92 | 32.85 | Sabitlendi (değişiklik yok) |
| DC22 | — | — | 39.98 | 32.78 | Yeni DC, kuzeybatı offset |

### 1.5 Fallback Koordinatının Değiştirilmesi

Mevcut fallback (satır 24):
```python
_FALLBACK = {"lat": 41.0082, "lon": 28.9784, "city": "Unknown"}
```

Yeni fallback — **Karadeniz'in ortası** (deniz üzeri, hiçbir DC ile çakışmaz):
```python
_FALLBACK = {"lat": 43.50, "lon": 34.00, "city": "Unknown"}
```

> Bu koordinat Karadeniz'in açık deniz kısmıdır. Eşleşmeyen DC'ler burada görünecek ve İstanbul kümesini şişirmeyecektir. Kullanıcı deniz üzerinde bir nokta görürse, koordinat eşleştirmesinin eksik olduğunu hemen anlayacaktır.

### 1.6 Tam Kod Değişikliği — _build_map_dataframe İçinde

`_build_map_dataframe` fonksiyonunun sadece `_FALLBACK` satırı değişir. Fonksiyonun geri kalanı aynı kalır:

```python
def _build_map_dataframe(summaries):
    _FALLBACK = {"lat": 43.50, "lon": 34.00, "city": "Unknown"}
    rows = []
    for dc in summaries:
        dc_id = dc.get("id", "")
        coords = DC_COORDINATES.get(dc_id, _FALLBACK)
        stats = dc.get("stats", {})
        cpu_pct = stats.get("used_cpu_pct", 0.0)
        ram_pct = stats.get("used_ram_pct", 0.0)
        health = (cpu_pct + ram_pct) / 2.0 if (cpu_pct + ram_pct) > 0 else 0.0
        rows.append({
            "id": dc_id,
            "name": dc.get("name", dc_id),
            "location": dc.get("location", coords["city"]),
            "lat": coords["lat"],
            "lon": coords["lon"],
            "host_count": dc.get("host_count", 0),
            "vm_count": dc.get("vm_count", 0),
            "platform_count": dc.get("platform_count", 0),
            "cluster_count": dc.get("cluster_count", 0),
            "cpu_pct": round(cpu_pct, 1),
            "ram_pct": round(ram_pct, 1),
            "health": round(health, 1),
            "total_energy_kw": float(stats.get("total_energy_kw", 0.0) or 0.0),
        })
    return pd.DataFrame(rows)
```

### 1.7 Çıktı Kriterleri

- [x] İstanbul'daki DC noktaları artık ayrı adacıklar olarak görünür (min ~7km mesafe)
- [x] UK (London) ve Azerbaycan (Baku) DC'leri haritada doğru konumda görünür
- [x] Ankara DC'leri sabit ve doğru koordinatta
- [x] Bilinmeyen DC'ler Karadeniz üzerinde görünür (İstanbul'u şişirmez)
- [x] Frankfurt ve Amsterdam DC'leri etkilenmez

---

## ADIM 2 — Balon Boyutlandırma (Bubble Scaling)

### 2.1 Sorun Detayı

Mevcut durumda `size="vm_count"` doğrudan kullanılıyor ve `size_max=40` ayarlı (satır 70–71). 7000 VM'lik bir DC'nin balonu, 50 VM'lik bir DC'ye göre 140 kat büyük oluyor — bu da haritayı kaplayacak bir daireye dönüşüyor.

### 2.2 Çözüm: Logaritmik Ölçekleme

`math.log1p` (log(1+x)) kullanılarak VM sayısı logaritmik ölçeğe çekilecek ve `size_max` düşürülecektir.

| VM Sayısı | log1p(vm) | Görsel Etki |
|-----------|-----------|-------------|
| 10 | 2.40 | Küçük nokta |
| 100 | 4.62 | Orta nokta |
| 1,000 | 6.91 | Büyük nokta |
| 7,000 | 8.85 | En büyük nokta (ama kontrollü) |

Oran: 7000 VM / 10 VM = 700x (lineer) → 8.85 / 2.40 = **3.7x** (logaritmik). Çok daha dengeli.

### 2.3 Kod Değişikliği — _build_map_dataframe İçinde

`_build_map_dataframe` fonksiyonuna `import math` eklenmeli ve rows.append bloğuna yeni bir alan eklenmelidir:

**Dosyanın en üstüne** (satır 1 civarı) `import math` eklenir:

```python
import math
```

`_build_map_dataframe` fonksiyonundaki `rows.append` bloğuna yeni alan eklenir:

```python
"bubble_size": math.log1p(dc.get("vm_count", 0)),
```

Tüm `rows.append` bloğu güncellenmiş hali (mevcut alanlar + yeni `bubble_size`):

```python
rows.append({
    "id": dc_id,
    "name": dc.get("name", dc_id),
    "location": dc.get("location", coords["city"]),
    "lat": coords["lat"],
    "lon": coords["lon"],
    "host_count": dc.get("host_count", 0),
    "vm_count": dc.get("vm_count", 0),
    "platform_count": dc.get("platform_count", 0),
    "cluster_count": dc.get("cluster_count", 0),
    "cpu_pct": round(cpu_pct, 1),
    "ram_pct": round(ram_pct, 1),
    "health": round(health, 1),
    "total_energy_kw": float(stats.get("total_energy_kw", 0.0) or 0.0),
    "bubble_size": math.log1p(dc.get("vm_count", 0)),
})
```

### 2.4 Kod Değişikliği — _create_map_figure İçinde

`px.scatter_mapbox` çağrısındaki `size` ve `size_max` parametreleri değiştirilecektir.

**Mevcut** (satır 70–71):
```python
size="vm_count",
size_max=40,
```

**Yeni:**
```python
size="bubble_size",
size_max=25,
```

Ayrıca `update_traces` bloğundaki `sizemin` değeri ayarlanacaktır.

**Mevcut** (satır 112–117):
```python
fig.update_traces(
    marker=dict(
        opacity=0.85,
        sizemin=8,
    )
)
```

**Yeni:**
```python
fig.update_traces(
    marker=dict(
        opacity=0.85,
        sizemin=6,
    )
)
```

### 2.5 hover_data Güncelleme

`hover_data` dict'inden `bubble_size`'ın gizlenmesi gerekir (kullanıcıya log değeri göstermek anlamsız). ADIM 3'te `hover_data` tamamen kaldırılacağı için burada ek işlem gerekmez — ama eğer ADIM 3 uygulanmadan test yapılacaksa:

```python
hover_data={
    ...
    "bubble_size": False,
},
```

### 2.6 Çıktı Kriterleri

- [x] En büyük DC balonu artık haritayı kaplamaz (max ~25px çap)
- [x] Küçük DC'ler de görünür kalır (min 6px)
- [x] Büyük-küçük DC arasındaki boyut oranı ~3-4x ile sınırlıdır (lineer 140x yerine)

---

## ADIM 3 — Custom Hover Template (Estetik Tooltip)

### 3.1 Sorun Detayı

Mevcut durumda `hover_data` dict (satır 80–89) Plotly'nin varsayılan `key=value` formatını üretiyor:

```
DC13
location=Istanbul
host_count=143
vm_count=6996
cpu_pct=75.2
ram_pct=94.8
```

Bu format görsel olarak çirkin ve profesyonel bir dashboard'a yakışmıyor.

### 3.2 Çözüm: hovertemplate + hoverlabel

Plotly'nin `hovertemplate` özelliği ile tam kontrollü HTML benzeri tooltip ve `hoverlabel` ile stil özelleştirmesi yapılacaktır.

### 3.3 Hedef Tooltip Görünümü

```
┌──────────────────────────────┐
│  DC13                        │
│  📍 Istanbul                 │
│  💻 VMs: 6,996 | 🖥️ Hosts: 143│
│  ⚡ Health: %85.0             │
└──────────────────────────────┘
```

### 3.4 Kod Değişikliği — _create_map_figure İçinde

`px.scatter_mapbox` çağrısından `hover_name` ve `hover_data` parametreleri **tamamen kaldırılacak** ve `custom_data` genişletilecektir.

**Kaldırılacak satırlar** (satır 79–89):
```python
hover_name="name",
hover_data={
    "location": True,
    "host_count": True,
    "vm_count": True,
    "cpu_pct": ":.1f",
    "ram_pct": ":.1f",
    "lat": False,
    "lon": False,
    "health": False,
},
```

**Mevcut custom_data** (satır 90):
```python
custom_data=["id"],
```

**Yeni custom_data** (genişletilmiş):
```python
custom_data=["id", "name", "location", "vm_count", "host_count", "health"],
```

### 3.5 hovertemplate Tanımı

`fig.update_traces` bloğu **tamamen** aşağıdaki ile değiştirilecektir:

```python
fig.update_traces(
    marker=dict(
        opacity=0.85,
        sizemin=6,
    ),
    hovertemplate=(
        "<b style='font-size:14px;'>%{customdata[1]}</b><br>"
        "📍 %{customdata[2]}<br>"
        "💻 VMs: %{customdata[3]:,} | 🖥️ Hosts: %{customdata[4]:,}<br>"
        "⚡ Health: %%%{customdata[5]:.1f}"
        "<extra></extra>"
    ),
)
```

**Template Açıklamaları:**

| Placeholder | Kaynak | Açıklama |
|-------------|--------|----------|
| `%{customdata[0]}` | `id` | DC kodu (tooltip'te kullanılmıyor, callback için) |
| `%{customdata[1]}` | `name` | DC adı — kalın ve büyük font |
| `%{customdata[2]}` | `location` | Şehir/lokasyon — 📍 emojisi ile |
| `%{customdata[3]:,}` | `vm_count` | VM sayısı — binlik ayraçlı |
| `%{customdata[4]:,}` | `host_count` | Host sayısı — binlik ayraçlı |
| `%{customdata[5]:.1f}` | `health` | Sağlık yüzdesi — 1 ondalık |
| `<extra></extra>` | — | Plotly'nin varsayılan "trace 0" etiketini gizler |

> **DİKKAT:** `%%%{customdata[5]:.1f}` ifadesindeki ilk `%%` → literal `%` karakteri üretir, ardından `%{...}` Plotly placeholder'ı gelir. Sonuç: `%85.0` şeklinde görünür.

### 3.6 hoverlabel Stil Ayarı

`fig.update_layout` bloğuna (mevcut `coloraxis_colorbar` ayarının yanına) aşağıdaki `hoverlabel` eklenir:

```python
fig.update_layout(
    mapbox_style="carto-positron",
    margin=dict(l=0, r=0, t=0, b=0),
    height=600,
    paper_bgcolor="rgba(0,0,0,0)",
    hoverlabel=dict(
        bgcolor="rgba(255, 255, 255, 0.95)",
        bordercolor="rgba(67, 24, 255, 0.15)",
        font=dict(
            family="DM Sans, sans-serif",
            size=13,
            color="#2B3674",
        ),
        align="left",
    ),
    coloraxis_colorbar=dict(
        title="Utilization %",
        thickness=12,
        len=0.5,
        bgcolor="rgba(255,255,255,0.8)",
        bordercolor="rgba(67,24,255,0.1)",
        borderwidth=1,
        tickfont=dict(size=11, family="DM Sans, sans-serif"),
        title_font=dict(size=12, family="DM Sans, sans-serif"),
    ),
)
```

**hoverlabel Stil Detayları:**

| Özellik | Değer | Neden |
|---------|-------|-------|
| `bgcolor` | `rgba(255, 255, 255, 0.95)` | Yarı-saydam beyaz — glassmorphism uyumu |
| `bordercolor` | `rgba(67, 24, 255, 0.15)` | İnce indigo çerçeve — marka rengi |
| `font.family` | `DM Sans, sans-serif` | Projenin varsayılan fontu ile tutarlılık |
| `font.size` | `13` | Okunabilir ama haritayı kapatmayacak boyut |
| `font.color` | `#2B3674` | Koyu lacivert — projenin metin rengi |
| `align` | `left` | Soldan hizalı — daha düzenli görünüm |

### 3.7 Çıktı Kriterleri

- [x] Hover'da Plotly varsayılan `key=value` formatı görünmez
- [x] Tooltip'te DC adı kalın, lokasyon emojili, VM/Host binlik ayraçlı
- [x] Health yüzdesi `%85.0` formatında görünür
- [x] Tooltip arka planı beyaz, çerçeve indigo, font DM Sans
- [x] `<extra></extra>` ile "trace 0" etiketi gizlenir

---

## EXECUTER UYGULAMA SIRASI (Checklist)

| Sıra | İşlem | Satır Aralığı | Durum |
|------|-------|---------------|-------|
| 1 | Dosyanın en üstüne `import math` ekle (satır 1'den sonra) | Satır 1 | ⬜ |
| 2 | `DC_COORDINATES` sözlüğünü yeni versiyon ile değiştir | Satır 9–20 | ⬜ |
| 3 | `_build_map_dataframe` → `_FALLBACK` koordinatını Karadeniz'e çek | Satır 24 | ⬜ |
| 4 | `_build_map_dataframe` → `rows.append` bloğuna `bubble_size` ekle | Satır 33–47 | ⬜ |
| 5 | `_create_map_figure` → `size="bubble_size"`, `size_max=25` yap | Satır 70–71 | ⬜ |
| 6 | `_create_map_figure` → `hover_name` ve `hover_data` kaldır | Satır 79–89 | ⬜ |
| 7 | `_create_map_figure` → `custom_data` genişlet | Satır 90 | ⬜ |
| 8 | `_create_map_figure` → `fig.update_layout`'a `hoverlabel` ekle | Satır 95–110 | ⬜ |
| 9 | `_create_map_figure` → `fig.update_traces`'i yeni hovertemplate ile değiştir | Satır 112–117 | ⬜ |
| 10 | Uygulamayı çalıştır, `/global-view` sayfasını test et | Terminal | ⬜ |

---

## TAM DEĞİŞİKLİK ÖZETİ — `src/pages/global_view.py`

Aşağıda dosyanın **tamamıyla güncellenmiş** `_create_map_figure` fonksiyonu referans olarak verilmiştir:

```python
def _create_map_figure(df):
    if df.empty:
        fig = px.scatter_mapbox(
            lat=[41.0082],
            lon=[28.9784],
            zoom=4,
        )
        fig.update_layout(
            mapbox_style="carto-positron",
            margin=dict(l=0, r=0, t=0, b=0),
            height=600,
            paper_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    fig = px.scatter_mapbox(
        df,
        lat="lat",
        lon="lon",
        size="bubble_size",
        size_max=25,
        color="health",
        color_continuous_scale=[
            [0.0, "#05CD99"],
            [0.5, "#FFB547"],
            [1.0, "#E85347"],
        ],
        range_color=[0, 100],
        custom_data=["id", "name", "location", "vm_count", "host_count", "health"],
        zoom=4,
        center={"lat": 45.0, "lon": 20.0},
    )

    fig.update_layout(
        mapbox_style="carto-positron",
        margin=dict(l=0, r=0, t=0, b=0),
        height=600,
        paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(
            bgcolor="rgba(255, 255, 255, 0.95)",
            bordercolor="rgba(67, 24, 255, 0.15)",
            font=dict(
                family="DM Sans, sans-serif",
                size=13,
                color="#2B3674",
            ),
            align="left",
        ),
        coloraxis_colorbar=dict(
            title="Utilization %",
            thickness=12,
            len=0.5,
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="rgba(67,24,255,0.1)",
            borderwidth=1,
            tickfont=dict(size=11, family="DM Sans, sans-serif"),
            title_font=dict(size=12, family="DM Sans, sans-serif"),
        ),
    )

    fig.update_traces(
        marker=dict(
            opacity=0.85,
            sizemin=6,
        ),
        hovertemplate=(
            "<b style='font-size:14px;'>%{customdata[1]}</b><br>"
            "📍 %{customdata[2]}<br>"
            "💻 VMs: %{customdata[3]:,} | 🖥️ Hosts: %{customdata[4]:,}<br>"
            "⚡ Health: %%%{customdata[5]:.1f}"
            "<extra></extra>"
        ),
    )

    return fig
```

---

## CTO'NUN İHLAL EDİLEMEZ YASALARI

### YASA 1 — Sıfır Yorum Satırı
Executer, `src/pages/global_view.py` dosyasında **TEK BİR** yorum satırı (`#`) veya docstring (`"""..."""`) **BIRAKMAYACAKTIR**. Tüm açıklama satırları bu plan dokümanındadır — kod dosyası saf Python kodu içerecektir.

### YASA 2 — Tek Dosya Kuralı
Bu V2 güncellemesinde **YALNIZCA** `src/pages/global_view.py` dosyası değiştirilecektir. `app.py`, `sidebar.py`, `api_client.py` veya başka herhangi bir dosyaya **DOKUNULMAYACAKTIR**.

### YASA 3 — custom_data Index Koruması
`custom_data` listesinin **ilk elemanı (index 0) her zaman `"id"` olmalıdır**. `app.py`'deki `update_global_info_card` callback'i `customdata[0]` üzerinden DC ID'yi alır. Bu index değiştirilirse callback bozulur.

---

> **SON:** Bu plan, mevcut MVP kodunun (global_view.py 432 satır) sadece belirli bölümlerini hedefleyen cerrahi bir müdahaledir.
> `build_global_view` ve `build_dc_info_card` fonksiyonlarına **DOKUNULMAZ** — değişiklikler yalnızca `DC_COORDINATES`, `_build_map_dataframe` ve `_create_map_figure` kapsamındadır.
