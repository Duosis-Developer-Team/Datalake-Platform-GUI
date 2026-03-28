# ✨ GLOBAL MAP VIEW V7.0 — Komuta Merkezi Polish & UX İyileştirmeler

> **Versiyon:** 7.0  
> **Tarih:** 2026-03-28  
> **Hazırlayan:** Baş Planlayıcı & Sistem Mimarı  
> **Hedef:** V6.0'da inşa edilen Komuta Merkezi layout'unu son kullanıcı deneyimi seviyesinde cilalamak — eksik metrikler, kart zenginliği, menü UX, harita yükseklik tutarsızlığı, boş durum tasarımı ve görsel detayları kusursuzlaştırmak.

---

## DOKUNULACAK DOSYALAR

| # | Dosya | İşlem | Etki |
|---|-------|-------|------|
| 1 | `src/pages/global_view.py` | **GÜNCELLE** | Detay paneli zenginleştirme, menü UX, boş durum, harita yükseklik tutarlılığı |
| 2 | `app.py` | **GÜNCELLE** | NavLink active state callback, accordion varsayılan açık |
| 3 | `assets/style.css` | **GÜNCELLE** | DC kart hover efekti, detay paneli parlama, scroll alanı ince ayar |

---

## TESPİT EDİLEN POLISH KONULARI

### Kritik Eksiklikler (V6.0'da Uygulanmış Ama Eksik Kalan)

| # | Sorun | Dosya | Satır |
|---|-------|-------|-------|
| P1 | `_create_map_figure` height hâlâ 650 (non-empty branch) — empty branch 600 yapıldı ama data branch yapılmadı | `global_view.py` | 285 |
| P2 | Detay paneli DC kartlarında **RingProgress (CPU/RAM) YOK** — sadece Power kW ve Rack Details butonu var | `global_view.py` | 401-438 |
| P3 | Detay paneli DC kartlarında **Storage metrikleri YOK** | `global_view.py` | 362-479 |
| P4 | Detay paneli DC kartlarında **Host/VM sayıları YOK** | `global_view.py` | 401-438 |
| P5 | Detay paneli DC kartlarında **Architecture bilgisi YOK** (VMware/Nutanix/IBM) | `global_view.py` | 401-438 |
| P6 | `build_dc_info_card` (pin-click detay) **RingProgress Gauge'ları eksik** — eski V5 versiyonundaki zengin 4-sütunlu gauge grid kaldırılmış | `global_view.py` | 678-758 |
| P7 | Accordion `value=[]` — hiçbir kıta varsayılan açık değil, kullanıcı boş bir menü görüyor | `global_view.py` | 356 |
| P8 | Region Menu Panel'de scroll alanı yüksekliği (`h=520`) ile panel yüksekliği (`h=600`) tutarsız — header+divider ~40px, kalan ~560 olmalı | `global_view.py` | 635, 654 |

### UX İyileştirmeleri

| # | İyileştirme | Açıklama |
|---|-------------|----------|
| U1 | **Boş durumda placeholder** | Sayfa ilk açıldığında detay paneli tamamen boş — kullanıcıyı yönlendiren nazik bir mesaj gerekiyor |
| U2 | **DC kart hover efekti** | `build_region_detail_panel` DC kartlarında hover animasyonu yok — premium hissi düşürüyor |
| U3 | **Menü NavLink health renk göstergesi** | Her NavLink'in solunda veya sağında bölgenin ortalama health durumunu gösteren küçük bir renk noktası |
| U4 | **Region Menu Panel header'da toplam DC sayısı** | "Regions" başlığının yanında genel `{n} Active DCs` badge'i |
| U5 | **Pin-click detay kartına health badge** | Mevcut `build_dc_info_card`'da health yüzdesi badge'i var ama eski zengin format kaybedilmiş |

---

## ADIM 1 — Harita Yüksekliği Tutarlılığı

### 1.1 Sorun (P1)

`_create_map_figure` fonksiyonunda 2 branch var:
- **Empty branch (satır 159):** `height=600` ✅ (V6.0'da güncellendi)
- **Data branch (satır 285):** `height=650` ❌ (GÜNCELLENMEMİŞ)

Ayrıca `dcc.Graph` style'ında (satır 623) `height: 600px` yazıyor. Plotly figure height ile CSS height uyuşmuyor.

### 1.2 Çözüm

| Konum | Mevcut | Yeni |
|-------|--------|------|
| `_create_map_figure` data branch (satır 285) | `height=650` | `height=600` |

Bu tek satırlık değişiklik harita-menü panel yükseklik uyumunu sağlar.

---

## ADIM 2 — Region Detail Panel DC Kartlarını Zenginleştirme (P2-P5)

### 2.1 Mevcut Durum (satır 401-438)

Şu an her DC kartı sadece şunları gösteriyor:
- DC adı + health badge
- Power (kW) metriği
- "Rack Details" butonu

### 2.2 Hedef Durum

Her DC kartı şunları gösterecek:

```
dmc.Paper (DC kartı)
  ├── Row 1: DC adı (sol) + Health% badge (sağ)
  ├── Row 2: dmc.SimpleGrid(cols=4, spacing="xs")
  │   ├── CPU RingProgress (size=64, thickness=5)
  │   ├── RAM RingProgress (size=64, thickness=5)
  │   ├── Storage RingProgress (size=64, thickness=5)
  │   └── Sayısal Metrikler Stack
  │       ├── "{n} Hosts" + ikon
  │       ├── "{n} VMs" + ikon
  │       └── "{n} kW" + ikon
  ├── dmc.Divider(my="xs")
  ├── Row 3: Architecture bilgisi (VMware/Nutanix/IBM) texti
  └── Row 4: "Rack Details" butonu (sağa dayalı)
```

### 2.3 Gerekli Veri

`api.get_dc_details(dc_id, tr)` zaten şu verileri döndürüyor (mevcut callback'te çekiliyor):

| Alan | Kaynak | Kullanım |
|------|--------|----------|
| `intel.cpu_cap`, `intel.cpu_used` | ✅ Mevcut | CPU RingProgress |
| `intel.ram_cap`, `intel.ram_used` | ✅ Mevcut | RAM RingProgress |
| `intel.storage_cap`, `intel.storage_used` | ✅ Çekilmeli | Storage RingProgress |
| `intel.hosts`, `intel.vms` | ✅ Çekilmeli | Host/VM sayıları |
| `power.hosts`, `power.lpar_count` | ✅ Çekilmeli | Toplam host/VM'e katkı |
| `platforms.vmware`, `platforms.nutanix`, `platforms.ibm` | ✅ Çekilmeli | Architecture text |

### 2.4 RingProgress Bileşeni Detayı

Her gauge için:

```python
dmc.Stack(
    gap=2,
    align="center",
    children=[
        dmc.RingProgress(
            size=64,
            thickness=5,
            roundCaps=True,
            sections=[{"value": cpu_pct, "color": _pct_color(cpu_pct)}],
            label=dmc.Text(f"{cpu_pct:.0f}%", ta="center", fw=700, size="xs"),
        ),
        dmc.Text("CPU", size="xs", fw=600, c="#A3AED0"),
    ],
)
```

> **🔮 MİMAR NOTU — Neden `size=64`?**
> Eski `build_dc_info_card` V5'te `size=90` kullanılıyordu ama o tam genişlik bir karttı. Şimdi `SimpleGrid(cols=3)` içinde kartlar daha dar → `size=64` uygun düşer. Pin-click kartı tam genişlik olduğu için orada `size=80` kullanılabilir.

### 2.5 Architecture Text Hesaplama

```python
arch_items = []
if vmware.get("clusters", 0) > 0 or vmware.get("hosts", 0) > 0:
    arch_items.append(f"VMware ({vmware.get('clusters', 0)}C, {vmware.get('hosts', 0)}H)")
if nutanix.get("hosts", 0) > 0:
    arch_items.append(f"Nutanix ({nutanix.get('hosts', 0)}H)")
if ibm.get("hosts", 0) > 0:
    arch_items.append(f"IBM ({ibm.get('hosts', 0)}H, {ibm.get('lpars', 0)}L)")
arch_text = " · ".join(arch_items) if arch_items else "—"
```

Bu hesaplama `build_region_detail_panel` fonksiyonunun döngüsünün içine eklenecek.

---

## ADIM 3 — Pin-Click Detay Kartını Zenginleştirme (P6)

### 3.1 Mevcut Durum (satır 678-758)

`build_dc_info_card` şu an:
- DC adı + lokasyon + ThemeIcon
- Health badge
- Power kW
- "Rack Details" butonu

**Eski V5'teki RingProgress gauge'lar, Host/VM sayıları, Architecture text kaldırılmış.**

### 3.2 Hedef Durum

Pin tıklandığında gösterilen kart eski zenginliğini geri kazanacak:

```
dmc.Paper
  ├── Header: ThemeIcon + DC adı + lokasyon (sol) | Health badge (sağ)
  ├── dmc.Divider
  ├── dmc.SimpleGrid(cols=4, spacing="lg")
  │   ├── CPU RingProgress (size=80, thickness=7)
  │   ├── RAM RingProgress (size=80, thickness=7)
  │   ├── Storage RingProgress (size=80, thickness=7)
  │   └── Metrik Stack
  │       ├── "{n} Hosts"
  │       ├── "{n} VMs"
  │       └── "{n} kW"
  ├── dmc.Divider
  ├── Architecture text satırı
  └── "Rack Details" butonu (sağa dayalı)
```

### 3.3 Gerekli Ek Veri

`build_dc_info_card` fonksiyonu zaten `api.get_dc_details` çağırıyor ve `intel`, `power`, `energy`, `platforms` sözlüklerini çözümlüyor. Eksik olan:
- `storage_cap`, `storage_used` → `intel` dict'ten çekilecek
- `platforms` → Architecture text hesaplanacak (aynı 2.5 mantığı)

---

## ADIM 4 — Accordion Varsayılan Açık Durum (P7)

### 4.1 Sorun

`_build_region_menu` fonksiyonunda (satır 356):
```python
value=[]
```

Hiçbir kıta açık olmuyor. Kullanıcı sadece kapalı accordion başlıkları görüyor — ilk izlenim kötü.

### 4.2 Çözüm

```python
value=["Turkey Region"]
```

Türkiye bölgesi varsayılan açık — DC yoğunluğu en fazla burada. Kullanıcı hemen İstanbul/Ankara/İzmir NavLink'lerini görür.

---

## ADIM 5 — ScrollArea Yükseklik Düzeltmesi (P8)

### 5.1 Sorun

- Panel: `h=600`
- Header (Regions + ikon): ~32px
- Divider + margins: ~16px
- Kalan: ~552px
- ScrollArea: `h=520` → 32px boşluk kalıyor

### 5.2 Çözüm

```python
dmc.ScrollArea(h=530, ...)
```

Panel `p="lg"` (padding ~20px) olduğundan gerçek iç alan: `600 - 40 (padding) - 32 (header) - 16 (divider+mb)` ≈ `512`. ScrollArea `h=510` olarak ayarlanmalı.

> **🔮 MİMAR NOTU:** Sabit piksel yerine CSS `calc()` kullanmak daha sağlam olur ama Dash inline style'larında `calc()` sorunlu olabiliyor. Manuel hesaplama yeterli.

---

## ADIM 6 — Detay Paneli Boş Durum (Welcome State) (U1)

### 6.1 Hedef

Sayfa ilk yüklendiğinde `global-detail-panel` boş. Yerine:

```python
html.Div(
    style={"textAlign": "center", "padding": "48px 0"},
    children=[
        DashIconify(icon="solar:map-point-search-bold-duotone", width=48, color="#A3AED0"),
        dmc.Text(
            "Select a region from the menu or click a pin on the map",
            c="#A3AED0",
            size="sm",
            mt="md",
        ),
    ],
)
```

Bu `build_global_view` layout'unda `global-detail-panel`'ın initial `children`'ına konacak.

---

## ADIM 7 — DC Kart Hover Efekti (U2)

### 7.1 CSS Eklemesi

`assets/style.css`'e eklenecek:

```css
.detail-dc-card {
    transition: transform 0.25s cubic-bezier(0.25, 0.8, 0.25, 1),
                box-shadow 0.25s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.detail-dc-card:hover {
    transform: translateY(-4px);
    box-shadow:
        0px 16px 40px rgba(67, 24, 255, 0.12),
        0px 6px 16px rgba(67, 24, 255, 0.06) !important;
}
```

### 7.2 Python Tarafı

`build_region_detail_panel` ve `build_dc_info_card` fonksiyonlarındaki DC kartı `dmc.Paper`'larına `className="detail-dc-card"` eklenecek.

---

## ADIM 8 — Menü NavLink Health Göstergesi (U3)

### 8.1 Hedef

Her NavLink'in `rightSection`'ındaki badge'e ek olarak, bölgenin ortalama health'ine göre renk kodlu bir nokta gösterilecek.

### 8.2 Uygulama

`_build_region_menu` fonksiyonunda `summaries` verisinden her bölgenin ortalama CPU+RAM health'i hesaplanır:

```python
region_health = {}
for dc in summaries:
    sn = (dc.get("site_name") or "").upper().strip()
    stats = dc.get("stats", {})
    cpu = stats.get("used_cpu_pct", 0.0)
    ram = stats.get("used_ram_pct", 0.0)
    health = (cpu + ram) / 2.0
    region_health.setdefault(sn, []).append(health)

avg_health = {k: sum(v) / len(v) for k, v in region_health.items() if v}
```

NavLink'in `leftSection`'ına bayrak ikonunun yanına veya `description` prop'una health bilgisi eklenebilir. En zarif çözüm NavLink'in `description` prop'unu kullanmak:

```python
dmc.NavLink(
    label=site_data["label"],
    description=f"Avg Health: {avg:.0f}%",
    ...
)
```

---

## ADIM 9 — Region Menu Panel Header Badge (U4)

### 9.1 Mevcut (satır 643-650)

```python
dmc.Group(
    justify="flex-start",
    align="center",
    mb="sm",
    children=[
        DashIconify(icon="solar:map-bold-duotone", width=20, color="#4318FF"),
        dmc.Text("Regions", fw=700, size="md", c="#2B3674"),
    ],
)
```

### 9.2 Hedef

```python
dmc.Group(
    justify="space-between",
    align="center",
    mb="sm",
    children=[
        dmc.Group(gap="sm", children=[
            DashIconify(icon="solar:map-bold-duotone", width=20, color="#4318FF"),
            dmc.Text("Regions", fw=700, size="md", c="#2B3674"),
        ]),
        dmc.Badge(
            f"{len(summaries)} DCs",
            variant="light",
            color="indigo",
            size="sm",
        ),
    ],
)
```

`summaries` verisi `build_global_view` scope'unda mevcut, `_build_region_menu`'ye zaten geçiriliyor. Panel header oluşturulan yerde toplam DC sayısı `len(summaries)` ile alınabilir.

---

## DOSYA BAZINDA DEĞİŞİKLİK ÖZETİ

### `src/pages/global_view.py`

| # | İşlem | Fonksiyon | Satır |
|---|-------|-----------|-------|
| 1 | Height 650→600 | `_create_map_figure` | 285 |
| 2 | Accordion `value=["Turkey Region"]` | `_build_region_menu` | 356 |
| 3 | ScrollArea `h=510` | `build_global_view` | 654 |
| 4 | Panel header'a toplam DC badge | `build_global_view` | 643-650 |
| 5 | Boş durum placeholder | `build_global_view` | 670-672 |
| 6 | DC kartları zenginleştir (RingProgress, Host/VM, Storage, Architecture) | `build_region_detail_panel` | 378-438 |
| 7 | DC kartlara `className="detail-dc-card"` | `build_region_detail_panel` | 402 |
| 8 | Her NavLink'e `description` (avg health) | `_build_region_menu` | 317-329 |
| 9 | Pin-click kartı zenginleştir (RingProgress, Storage, Architecture) | `build_dc_info_card` | 678-758 |
| 10 | Pin-click karta `className="detail-dc-card"` | `build_dc_info_card` | 699 |

### `assets/style.css`

| # | İşlem |
|---|-------|
| 1 | `.detail-dc-card` hover efekti ekle |

### `app.py`

_Bu adımda **değişiklik yok**._ Tüm callback altyapısı V6.0'da tamamlandı.

---

## UYGULAMA SIRALAMASI (Executer Checklist)

| Sıra | İşlem | Dosya | Durum |
|------|-------|-------|-------|
| 1 | `_create_map_figure` → data branch height 650→600 | `global_view.py` | ⬜ |
| 2 | Accordion `value=["Turkey Region"]` | `global_view.py` | ⬜ |
| 3 | ScrollArea h=510 düzeltmesi | `global_view.py` | ⬜ |
| 4 | Panel header'a toplam DC badge + justify="space-between" | `global_view.py` | ⬜ |
| 5 | Boş durum placeholder (welcome state) | `global_view.py` | ⬜ |
| 6 | NavLink'lere description (avg health) | `global_view.py` | ⬜ |
| 7 | `build_region_detail_panel` DC kartlarına RingProgress + Storage + Host/VM + Architecture | `global_view.py` | ⬜ |
| 8 | `build_region_detail_panel` DC kartlarına `className="detail-dc-card"` | `global_view.py` | ⬜ |
| 9 | `build_dc_info_card` RingProgress + Storage + Architecture geri getir | `global_view.py` | ⬜ |
| 10 | `build_dc_info_card` kartına `className="detail-dc-card"` | `global_view.py` | ⬜ |
| 11 | CSS: `.detail-dc-card` hover efekti | `style.css` | ⬜ |
| 12 | Test: Menüden Istanbul tıkla → DC kartlarında CPU/RAM/Storage gauge'ları görünsün | Tarayıcı | ⬜ |
| 13 | Test: Pin tıkla → zengin detay kartı (gauge + host/vm + architecture) görünsün | Tarayıcı | ⬜ |
| 14 | Test: Sayfa ilk yüklenme → welcome placeholder görünsün | Tarayıcı | ⬜ |
| 15 | Test: Accordion → Turkey Region varsayılan açık | Tarayıcı | ⬜ |
| 16 | Test: DC kartlarına hover → yukarı kayma + gölge animasyonu | Tarayıcı | ⬜ |
| 17 | Test: Menu NavLink'lerde avg health → description satırı gösterilsin | Tarayıcı | ⬜ |

---

## ⚠️ CTO'NUN İHLAL EDİLEMEZ YASALARI (V6.0'dan Devralınan)

### YASA 1 — SIFIR YORUM SATIRI
Executer'ın yazacağı kodlarda **TEK BİR** açıklama satırı (`#`) veya docstring (`"""..."""`) **BULUNMAYACAKTIR**.

### YASA 2 — MEVCUT VERİ AKIŞINI KORUMA
`site_name` akışı ve `api.get_all_datacenters_summary()` → `api.get_dc_details()` zinciri değişmeyecek.

### YASA 3 — CALLBACK YAPISINA DOKUNMA
V6.0'da oluşturulan 7 callback'in yapısı (Input/Output/State) değişmeyecek. Sadece callback'lerin çağırdığı fonksiyonların iç yapısı güncellenecek.

---

> **SON:** Bu polish planı `global_view.py`'da ~150 satırlık iyileştirme ve `style.css`'te ~12 satırlık CSS ekleme gerektirir. `app.py`'da değişiklik yoktur. Tüm değişiklikler mevcut fonksiyonların içinde olacak — yeni fonksiyon veya callback eklenmeyecek.
