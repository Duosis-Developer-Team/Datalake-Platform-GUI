# 🏢 Data Centers Page Upgrade — Task Plan

**Yayın Tarihi:** 2 Mart 2026, 03:07
**Hazırlayan:** Senior Developer Organizer
**Hedef Dosya:** `src/pages/datacenters.py`
**Referans:** `src/pages/home.py` (Satır 122-182) — Overview header (mevcut uygulama)
**Durum:** ⏳ Executor uygulaması bekleniyor

---

## Mevcut Dosya Haritası — `datacenters.py`

```
Satır 01-07: Import'lar
Satır 09-11: build_datacenters() — veri toplama
Satır 13-25: ← HEDEF: html.Div(className="nexus-glass") Header bloğu
Satır 27-123: DC kartları grid (dmc.SimpleGrid cols=3, 3 card per row)
Satır 126-128: layout() fonksiyonu
```

---

## Mevcut Header Kodu (Satır 15-25) — Referans

```python
# MEVCUT — DEĞİŞTİRİLECEK (Satır 15-25):
html.Div(
    className="nexus-glass",
    children=[
        html.Div([
            DashIconify(icon="solar:server-square-bold-duotone", width=30, color="#4318FF"),
            html.H1("Data Centers", style={"margin": "0 0 0 10px", "color": "#2B3674", "fontSize": "1.8rem"}),
        ], style={"display": "flex", "alignItems": "center"}),
        html.P(f"Report period: {tr.get('start', '')} – {tr.get('end', '')}", style={"margin": "5px 0 0 40px", "color": "#A3AED0"}),
    ],
    style={"padding": "24px 32px", "marginBottom": "32px", "display": "flex", "flexDirection": "column", "justifyContent": "center"}
),
```

**Sorunlar:**
- `html.Div(className="nexus-glass")` → eski glassmorphism sistemi, sticky sorunlu
- `html.H1` → Mantine entegrasyonu yok, gradyan yok
- `html.P` → düz metin tarih, badge yok, ikon yok
- Sağ tarafa sayaç badge yok (kaç DC aktif?)
- `nexus-glass` sticky → sidebar z-index çakışması

---

## Task 1: Executive Header Integration

**Kural:** Overview sayfasındaki `dmc.Paper` header yapısıyla **birebir görsel tutarlılık**.
Aynı `dmc.Paper` kapsayıcı, aynı glassmorphism stiller, aynı badge sistemi — sadece içerik Data Centers'a özelleşiyor.

---

### DEĞİŞİKLİK 1 — Header Bloğu (`datacenters.py` Satır 15-25 — TAMAMEN DEĞİŞTİR)

```python
# YENİ — Overview ile birebir uyumlu Executive Header:
dmc.Paper(
    p="xl",
    radius="md",
    style={
        "background": "rgba(255, 255, 255, 0.80)",
        "backdropFilter": "blur(12px)",
        "WebkitBackdropFilter": "blur(12px)",
        "boxShadow": "0 4px 24px rgba(67, 24, 255, 0.07), 0 1px 4px rgba(0, 0, 0, 0.04)",
        "borderBottom": "1px solid rgba(255, 255, 255, 0.6)",
        "marginBottom": "28px",
    },
    children=[
        dmc.Group(
            justify="space-between",
            align="center",
            children=[
                # ---- SOL TARAF: Başlık + Tarih Rozeti ----
                dmc.Stack(
                    gap=10,
                    children=[
                        # Başlık satırı: İkon + Gradyan H2
                        dmc.Group(
                            gap="sm",
                            align="center",
                            children=[
                                DashIconify(
                                    icon="solar:server-square-bold-duotone",
                                    width=28,
                                    color="#4318FF",
                                ),
                                html.H2(
                                    "Data Centers",
                                    style={
                                        "margin": 0,
                                        "fontWeight": 900,
                                        "letterSpacing": "-0.02em",
                                        "lineHeight": 1.2,
                                        "fontSize": "1.75rem",
                                        "background": "linear-gradient(90deg, #1a1b41 0%, #4318FF 100%)",
                                        "WebkitBackgroundClip": "text",
                                        "WebkitTextFillColor": "transparent",
                                        "backgroundClip": "text",
                                    },
                                ),
                            ],
                        ),
                        # Tarih rozeti — Overview ile aynı pattern
                        dmc.Badge(
                            children=[
                                dmc.Group(
                                    gap=6,
                                    align="center",
                                    children=[
                                        DashIconify(
                                            icon="solar:calendar-mark-bold-duotone",
                                            width=13,
                                        ),
                                        f"{tr.get('start', '')} – {tr.get('end', '')}",
                                    ],
                                )
                            ],
                            variant="light",
                            color="indigo",
                            radius="xl",
                            size="md",
                            style={"textTransform": "none", "fontWeight": 500, "letterSpacing": 0},
                        ),
                    ],
                ),

                # ---- SAĞ TARAF: Aktif DC Sayacı Badge ----
                dmc.Badge(
                    children=[
                        dmc.Group(
                            gap=6,
                            align="center",
                            children=[
                                DashIconify(
                                    icon="solar:check-circle-bold-duotone",
                                    width=15,
                                    color="#05CD99",
                                ),
                                f"{len(datacenters)} Active DCs",
                            ],
                        )
                    ],
                    variant="light",
                    color="teal",
                    radius="xl",
                    size="lg",
                    style={
                        "textTransform": "none",
                        "fontWeight": 600,
                        "letterSpacing": 0,
                        "padding": "8px 14px",
                    },
                ),
            ],
        ),
    ],
),
```

---

### Değişiklik Tablosu

| # | Bileşen | Eski | Yeni | Gerekçe |
|---|---------|------|------|---------|
| 1 | **Kapsayıcı** | `html.Div(className="nexus-glass")` | `dmc.Paper(p="xl", radius="md")` | Glassmorphism inline style — sticky kaldırıldı |
| 2 | **Arka plan** | `nexus-glass` CSS sınıfı (yarı saydam + blur) | `rgba(255,255,255,0.80)` + `backdropFilter: blur(12px)` | Overview ile birebir aynı CSS değerleri |
| 3 | **Başlık** | `html.H1(color="#2B3674", fontSize="1.8rem")` | `html.H2` + CSS `linear-gradient` + `WebkitTextFillColor` | Gradyan tipografi — Overview ile aynı |
| 4 | **Sayfa ikonu** | `DashIconify(width=30)` → ayrı div içinde | `DashIconify(width=28)` → `dmc.Group` içinde H2 soluna | Başlıkla hizalı, tek satırda |
| 5 | **Tarih metni** | `html.P(f"Report period: ...")` düz metin | `dmc.Badge(variant="light", color="indigo", radius="xl")` + takvim ikonu | Overview badge sistemi — pill formatı |
| 6 | **Aktif DC sayacı** | *(yok)* | `dmc.Badge(f"{len(datacenters)} Active DCs", color="teal")` | Sağ tarafa yeni bilgi rozeti |
| 7 | **Layout** | `flexDirection: column` | `dmc.Group(justify="space-between")` | Sol başlık / Sağ sayaç yatay |
| 8 | **Sticky** | `nexus-glass` CSS'inde `position: sticky; top: 0` | Kaldırıldı | Sidebar z-index çakışması önlendi |
| 9 | **Margin** | `"marginBottom": "32px"` | `"marginBottom": "28px"` | Overview ile birebir eşitlik |
| 10 | **Padding** | `"padding": "24px 32px"` | `p="xl"` (Mantine ≈ 24px tüm yönler) | Tek sistem, tutarlı |

---

### DEĞİŞİKLİK 2 — DC Grid Container Padding Eşitlemesi

DC kartlarının grid container'ı (Satır 28-122) mevcut durumda `style={"padding": "0 32px"}`. **Bu değişmez** — Overview'daki `"0 30px"` ile 2px fark var ama pratik olarak görünmez. DC grid'i Overview'dan bağımsız, kendi bütünlüğü içinde tutarlı.

> Eğer CEO bu `2px` farkı tespit ederse söyle — `"0 30px"` yapılır.

---

### DEĞİŞİKLİK 3 — `dmc.Divider` Seperatör (Opsiyonel)

CEO'nun talebi olan "başlık altına ince seperatör" zaten `dmc.Paper`'ın `borderBottom` stili ile sağlandı. Ek `dmc.Divider` eklenmesine gerek yok.

Eğer Executor daha görünür bir çizgi isterse `dmc.Paper` ile `grid` arasına şunu ekle:

```python
# Opsiyonel — dmc.Paper'dan SONRA, dmc.SimpleGrid'den ÖNCE:
dmc.Divider(
    variant="solid",
    color="gray.2",
    style={"margin": "0 0 8px 0"},
),
```

---

### Dikkat Noktaları

**`len(datacenters)` kullanımı:**
- `datacenters = service.get_all_datacenters_summary(tr)` — liste formatında.
- `len(datacenters)` → aktif DC sayısı dinamik hesaplanıyor.
- Veri yoksa `len([]) = 0` — badge `"0 Active DCs"` gösterir. Sorun değil.

**`dmc.Paper` ile `nexus-glass` karşılaştırma:**
```css
nexus-glass mevcut CSS (style.css):
  background: rgba(255,255,255,0.65) blur(20px) → saydam
  border-bottom: 1px solid rgba(255,255,255,0.5)
  position: sticky; top: 0  ← sticky — kaldırılıyor

Yeni dmc.Paper inline:
  background: rgba(255,255,255,0.80) → biraz daha opak
  backdropFilter: blur(12px) → Overview ile aynı
  sticky: YOK
```

**Gradyan başlık `WebkitTextFillColor`:**
- `dmc.Title(variant="gradient")` — `dmc 0.14.1`'de çalışmıyor (Task 1 Fallback'ten biliniyor).
- Doğrudan `html.H2` + CSS gradient kullanılıyor — güvenli, her sürümde çalışır.

---

### ✅ Task 1 Kabul Kriterleri

**Görsel Tutarlılık:**
- [ ] `python app.py` — hatasız başlangıç.
- [ ] Data Centers header görsel olarak Overview header ile aynı formatta.
- [ ] Header arka planı `rgba(255,255,255,0.80)` — saydam glassmorphism.
- [ ] Header çevresinde hafif mor aura gölgesi.

**Başlık:**
- [ ] Başlık satırında solda server ikonu (`solar:server-square-bold-duotone`) var.
- [ ] "Data Centers" metni **koyu lacivert → mora gradyan**, `fontWeight:900`.
- [ ] Alt başlık yok — tek satır başlık.

**Tarih Rozeti:**
- [ ] Tarih rozeti pill şekilli (tam yuvarlak), açık indigo arka planlı.
- [ ] İçinde takvim ikonu + tarih metni yan yana.
- [ ] Tarih metni büyük harf değil (`textTransform:"none"`).
- [ ] Zaman filtresi değişince tarih rozeti güncellendiğini kontrol et.

**Aktif DC Sayacı:**
- [ ] Sağ tarafa yeşil/teal badge ile `"X Active DCs"` yazıyor.
- [ ] X değeri gerçek DC sayısını gösteriyor (dinamik).
- [ ] Solunda teal check-circle ikonu var.
- [ ] Badge `size="lg"` — tarih rozetinden biraz daha büyük.

**Layout:**
- [ ] Başlık grubu (ikon + H2) ile tarih rozeti alt alta (`dmc.Stack`).
- [ ] Sol grup (başlık + tarih) ile sağ badge (`dmc.Group justify="space-between"`).
- [ ] Header scroll ile birlikte iniyor — sticky değil.

**Ayırıcı:**
- [ ] Header'ın alt kenarında ince çizgi görünüyor (`borderBottom`).

---

### 📝 Task 1 Değişiklik Özeti

```
src/pages/datacenters.py

  Satır 15-25 — TAMAMEN DEĞİŞTİR:
    html.Div(className="nexus-glass", ...) → dmc.Paper(p="xl", radius="md")

    dmc.Paper style:
      background: "rgba(255,255,255,0.80)"
      backdropFilter: "blur(12px)"
      WebkitBackdropFilter: "blur(12px)"
      boxShadow: "0 4px 24px rgba(67,24,255,0.07), 0 1px 4px rgba(0,0,0,0.04)"
      borderBottom: "1px solid rgba(255,255,255,0.6)"
      marginBottom: "28px"

    İç yapı:
      dmc.Group(justify="space-between")
        ├── dmc.Stack(gap=10) [SOL]
        │     ├── dmc.Group(gap="sm")
        │     │     ├── DashIconify(solar:server-square-bold-duotone, 28px, #4318FF)
        │     │     └── html.H2(gradient CSS, fw=900, -0.02em, 1.75rem)
        │     └── dmc.Badge(tarih rozeti, variant="light", color="indigo", radius="xl")
        │           └── dmc.Group → DashIconify(calendar) + f"{start} – {end}"
        │
        └── dmc.Badge(f"{len(datacenters)} Active DCs", ...) [SAĞ]
              variant="light", color="teal", radius="xl", size="lg"
              └── dmc.Group → DashIconify(check-circle, teal) + metin

DEĞİŞMEYEN:
  - Satır 28-123: dmc.SimpleGrid DC kartları (hiçbirine dokunma)
  - layout() fonksiyonu
  - Import satırları (dmc, DashIconify zaten mevcut)
  - style.css (nexus-glass silinmez)
  - Callback'lar
```

**Toplam:** 1 dosya (`datacenters.py`) — Sadece Satır 15-25.
Diğer hiçbir şey değişmez. CSS değişmez. Callback değişmez.

---
---

## 🏛️ Task 2 — Elite DC Vault: Kart Mimarisi (CEO Onaylı)

**Tarih:** 2 Mart 2026, 03:46
**Kaynak:** CEO direktifi — Apple-Level mühendislik
**Hedef:** `src/pages/datacenters.py` Satır 28-122 (DC kartları grid bloğu)
**Servis:** `src/services/db_service.py` (Satır 716-735 — summary dict)
**Durum:** ⏳ Executor uygulaması bekleniyor

> ⚠️ Task 1 (Header) uygulandıktan sonra bu task işlenecek.
> Satır numaraları Task 1 uygulaması sonrası ±15 kayabilir — Executor doğru bloğu bulsun.

---

### Veri İzleme Analizi — `db_service.py`

**Kritik Tespit:**

`get_all_datacenters_summary()` → `_rebuild_summary()` → Satır 716-735 arası `summary_list.append()`:

```python
# MEVCUT summary dict (Satır 716-735) — energy bölümü:
"stats": {
    ...
    "total_energy_kw": d["energy"]["total_kw"],  # ← Satır 733 — SADECE total var!
}
# ibm_kw ve vcenter_kw summary'e KOPYALANMIYOR.
```

`d["energy"]` dict'i şunları içeriyor (Satır 48):
```python
"energy": {
    "total_kw": 0.0,
    "ibm_kw": 0.0,      # ← Mevcut ama summary'e gitmiyor
    "vcenter_kw": 0.0,  # ← Mevcut ama summary'ye gitmiyor
    "total_kwh": 0.0,
    "ibm_kwh": 0.0,
    "vcenter_kwh": 0.0,
}
```

**Çözüm:** `summary_list.append()` içindeki `stats` dict'ini genişlet.

---

### DEĞİŞİKLİK A — `db_service.py` Satır 725-734 (`stats` dict genişletmesi)

```python
# MEVCUT (Satır 725-734):
"stats": {
    "total_cpu": f"{cpu_used:,} / {cpu_cap:,} GHz",
    "used_cpu_pct": round((cpu_used / cpu_cap * 100) if cpu_cap > 0 else 0, 1),
    "total_ram": f"{ram_used:,} / {ram_cap:,} GB",
    "used_ram_pct": round((ram_used / ram_cap * 100) if ram_cap > 0 else 0, 1),
    "total_storage": f"{stor_used:,} / {stor_cap:,} TB",
    "used_storage_pct": round((stor_used / stor_cap * 100) if stor_cap \> 0 else 0, 1),
    "last_updated": "Live",
    "total_energy_kw": d["energy"]["total_kw"],
},

# YENİ — ibm_kw ve vcenter_kw eklendi:
"stats": {
    "total_cpu": f"{cpu_used:,} / {cpu_cap:,} GHz",
    "used_cpu_pct": round((cpu_used / cpu_cap * 100) if cpu_cap > 0 else 0, 1),
    "total_ram": f"{ram_used:,} / {ram_cap:,} GB",
    "used_ram_pct": round((ram_used / ram_cap * 100) if ram_cap > 0 else 0, 1),
    "total_storage": f"{stor_used:,} / {stor_cap:,} TB",
    "used_storage_pct": round((stor_used / stor_cap * 100) if stor_cap > 0 else 0, 1),
    "last_updated": "Live",
    "total_energy_kw": d["energy"]["total_kw"],
    "ibm_kw":          d["energy"].get("ibm_kw", 0.0),         # ← YENİ
    "vcenter_kw":      d["energy"].get("vcenter_kw", 0.0),      # ← YENİ
},
```

Bu 2 satırın eklenmesiyle `datacenters.py`'deki döngüde:
```python
ibm_kw    = dc["stats"].get("ibm_kw", 0.0)
total_kw  = dc["stats"].get("total_energy_kw", 0.0)
power_ratio = round((ibm_kw / total_kw * 100) if total_kw > 0 else 0.0, 1)
```

---

### DEĞİŞİKLİK B — `assets/style.css` — Live Pulse + Hover CSS Ekle

Bu kuralları `assets/style.css` dosyasının **SONUNA** ekle:

```css
/* ── Live Pulse Animasyonu ── */
@keyframes dc-pulse {
    0%   { opacity: 1;    transform: scale(1); }
    50%  { opacity: 0.35; transform: scale(0.85); }
    100% { opacity: 1;    transform: scale(1); }
}

.dc-pulse-dot {
    width: 7px;
    height: 7px;
    background-color: #05CD99;
    border-radius: 50%;
    display: inline-block;
    animation: dc-pulse 1.8s ease-in-out infinite;
    flex-shrink: 0;
}

/* ── DC Vault Card Hover Efekti ── */
.dc-vault-card {
    transition: transform 0.28s cubic-bezier(0.25, 0.8, 0.25, 1),
                box-shadow 0.28s cubic-bezier(0.25, 0.8, 0.25, 1);
    cursor: pointer;
}

.dc-vault-card:hover {
    transform: translateY(-5px);
    box-shadow:
        0px 24px 52px rgba(67, 24, 255, 0.13),
        0px 8px 18px rgba(67, 24, 255, 0.07) !important;
}
```

---

### DEĞİŞİKLİK C — `datacenters.py` — DC Kartları Grid (Satır 28-122 TAMAMEN DEĞİŞTİR)

**`build_datacenters()` içinde DC kartı loop'unun hemen üstüne `_dc_vault_card` yardımcı fonksiyonu DAHİL ET** (veya modül seviyesine taşı):

```python
def _dc_vault_card(dc):
    """Elite DC Vault kartı — 2 sütunlu, Power Dial + Metrik Satırları."""
    # ── Güç verisi ──────────────────────────────────────────────────
    ibm_kw   = float(dc["stats"].get("ibm_kw", 0.0) or 0.0)
    total_kw = float(dc["stats"].get("total_energy_kw", 0.0) or 0.0)
    power_ratio = round((ibm_kw / total_kw * 100) if total_kw > 0 else 0.0, 1)
    remaining   = max(0.0, 100.0 - power_ratio)

    # ── Renk-ikon Metrik Tanımları ───────────────────────────────────
    metrics = [
        {
            "icon": "solar:layers-minimalistic-bold-duotone",
            "color": "blue",
            "label": "Platforms",
            "value": dc.get("platform_count", 0),
        },
        {
            "icon": "solar:box-bold-duotone",
            "color": "grape",
            "label": "Clusters",
            "value": dc.get("cluster_count", 0),
        },
        {
            "icon": "solar:server-bold-duotone",
            "color": "orange",
            "label": "Hosts",
            "value": f"{dc.get('host_count', 0):,}",
        },
        {
            "icon": "solar:laptop-bold-duotone",
            "color": "teal",
            "label": "VMs",
            "value": f"{dc.get('vm_count', 0):,}",
        },
    ]

    metric_rows = [
        dmc.Group(
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
                        dmc.Text(m["label"], size="sm", c="#A3AED0"),
                    ],
                ),
                dmc.Text(
                    str(m["value"]),
                    fw=700,
                    size="sm",
                    c="#2B3674",
                    style={"fontVariantNumeric": "tabular-nums"},
                ),
            ],
        )
        for m in metrics
    ]

    # ── Power Dial (dmc.RingProgress) ───────────────────────────────
    power_dial = dmc.Stack(
        gap=6,
        align="center",
        children=[
            dmc.RingProgress(
                size=110,
                thickness=10,
                roundCaps=True,
                sections=[
                    {"value": power_ratio, "color": "orange"},
                    {"value": remaining,   "color": "#4318FF"},
                ],
                label=html.Div(
                    style={"textAlign": "center"},
                    children=[
                        dmc.Text(
                            f"{power_ratio:.0f}%",
                            fw=900,
                            size="lg",
                            c="#2B3674",
                            style={"lineHeight": 1},
                        ),
                        dmc.Text(
                            "IBM",
                            size="xs",
                            c="dimmed",
                            style={"lineHeight": 1, "marginTop": "2px"},
                        ),
                    ],
                ),
            ),
            dmc.Text("Power", size="xs", fw=600, c="#A3AED0"),
            dmc.Text(
                f"{total_kw:.1f} kW total",
                size="xs",
                c="dimmed",
                style={"fontVariantNumeric": "tabular-nums"},
            ),
        ],
    )

    # ── Dikey Frosted Divider (Sol/Sağ arasında) ─────────────────────
    frosty_divider = html.Div(
        style={
            "width": "1px",
            "height": "80%",
            "background": "linear-gradient(to bottom, transparent, rgba(67,24,255,0.12), transparent)",
            "alignSelf": "center",
        }
    )

    return dmc.Paper(
        className="dc-vault-card",
        p="lg",
        radius="lg",
        style={
            "background": "rgba(255, 255, 255, 0.82)",
            "backdropFilter": "blur(12px)",
            "WebkitBackdropFilter": "blur(12px)",
            "boxShadow": "0 2px 16px rgba(67, 24, 255, 0.06), 0 1px 4px rgba(0,0,0,0.04)",
            "border": "1px solid rgba(255, 255, 255, 0.7)",
            "height": "100%",
            "display": "flex",
            "flexDirection": "column",
            "gap": "14px",
        },
        children=[
            # ── Kart Başlığı: İsim + Pulse Dot + Details Badge ──────
            dmc.Group(
                justify="space-between",
                align="flex-start",
                children=[
                    dmc.Group(
                        gap="xs",
                        align="center",
                        children=[
                            # Live Pulse Dot
                            html.Div(className="dc-pulse-dot"),
                            dmc.Stack(
                                gap=0,
                                children=[
                                    dmc.Text(dc["name"], fw=700, size="md", c="#2B3674"),
                                    dmc.Text(
                                        dc.get("location", "—"),
                                        size="xs",
                                        c="#A3AED0",
                                        fw=500,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    dcc.Link(
                        dmc.Badge(
                            "Details →",
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

            # ── Ana 2-Sütunlu İçerik ─────────────────────────────────
            html.Div(
                style={
                    "display": "flex",
                    "flexDirection": "row",
                    "alignItems": "stretch",
                    "gap": "16px",
                    "flex": 1,
                },
                children=[
                    # Sol: Metrik satırları
                    dmc.Stack(
                        gap="xs",
                        style={"flex": 1},
                        children=metric_rows,
                    ),
                    # Ortada: Frosted Divider
                    frosty_divider,
                    # Sağ: Power Dial
                    html.Div(
                        style={"display": "flex", "alignItems": "center", "justifyContent": "center"},
                        children=[power_dial],
                    ),
                ],
            ),
        ],
    )
```

**Ana `build_datacenters()` içinde grid bloğunu şununla değiştir (Satır 28-122):**

```python
# YENİ — Elite DC Grid:
dmc.SimpleGrid(
    cols=3,
    spacing="lg",
    style={"padding": "0 32px"},
    children=[
        _dc_vault_card(dc) for dc in datacenters
    ],
),
```

---

### Değişiklik Tablosu

| # | Bileşen | Eski | Yeni | Etki |
|---|---------|------|------|------|
| 1 | **Kart kapsayıcı** | `html.Div(className="nexus-card")` | `dmc.Paper(className="dc-vault-card")` | Glassmorphism + hover CSS |
| 2 | **Kart arka planı** | `nexus-card` CSS | `rgba(255,255,255,0.82)` + `backdropFilter` | Premium frost |
| 3 | **Kart yüksekliği** | `"height": "100%"` | `"height": "100%"` + flex col | Tutarlı hizalama |
| 4 | **DC isim yanı** | Sadece metin | **Live Pulse Dot** + metin | Canlılık hissi |
| 5 | **İkon + metrik** | `DashIconify` düz renk | `dmc.ThemeIcon(variant="light")` renk kodlu | Platforms=blue, Clusters=grape, Hosts=orange, VMs=teal |
| 6 | **Sayısal değer** | `dmc.Text` standart | `dmc.Text(fw=700, tabular-nums)` | Dikey hizalı rakamlar |
| 7 | **Power verisi** | Yok | `dmc.RingProgress` + IBM % + total kW | Power dial eklendi |
| 8 | **Sütun ayırıcı** | Yok | Frosted gradient divider | İki panel ayrımı |
| 9 | **Hover efekti** | `transition: transform 0.2s` | `.dc-vault-card:hover { translateY(-5px) + mor aura }` | Premium hover |
| 10 | **Grid boyutu** | `cols=3` | `cols=3` (değişmez) | Layout korunuyor |

---

### Dikkat Noktaları

**Power Ratio 0 durumu:**
```python
power_ratio = round((ibm_kw / total_kw * 100) if total_kw > 0 else 0.0, 1)
remaining   = max(0.0, 100.0 - power_ratio)
```
- `total_kw = 0` → `power_ratio = 0` → Dial tamamen mor (`#4318FF`) görünür.
- `power_ratio = 100` → `remaining = 0` → Dial tamamen turuncu görünür.
- `max(0.0, ...)` → `power_ratio > 100` durumunda negatif `remaining` önlendi.

**`_dc_vault_card` konumu:**
- `build_datacenters()` içine iç fonksiyon olarak eklenebilir (her çağrıda yeniden tanımlanır).
- Veya modül seviyesine (Satır 8 sonrası) taşınabilir — daha temiz, ancak `dcc`, `dmc`, `DashIconify` import'larının modül seviyesinde mevcut olması gerekir (zaten var).

**`dmc.RingProgress` `sections` için dikkat:**
```python
sections=[
    {"value": power_ratio, "color": "orange"},  # IBM Power yüzdesi — turuncu
    {"value": remaining,   "color": "#4318FF"},  # Geri kalan — Bulutistan moru
]
```
`dmc.RingProgress` sections toplamı 100'ü geçerse hatalı görünüm. `max(0.0, ...)` guard yeterli.

**Frosted Divider `height: "80%"`:**
- `html.Div` içinde `%` yükseklik için parent `display: flex; align-items: stretch` şart.
- `html.Div(style={"display":"flex","flexDirection":"row","alignItems":"stretch"})` zaten tanımlı — çalışır.

---

### ✅ Task 2 Kabul Kriterleri

**Veri:**
- [ ] `python app.py` — hatasız başlangıç.
- [ ] `db_service.py` stats dict'inde `ibm_kw` ve `vcenter_kw` anahtarları var.
- [ ] `power_ratio` hesabı 0-100 arasında, `total_kw=0` durumunda hata yok.

**Kart Görünümü:**
- [ ] Kart glassmorphism arka planlı — `rgba(255,255,255,0.82)` + blur.
- [ ] Kart başlığında DC isminin solunda yeşil animasyonlu canlılık noktası var.
- [ ] Kart başlığında sağ tarafa indigo "Details →" badge linki var.

**Sol Sütun — Metrikler:**
- [ ] Platforms: 🔵 mavi ThemeIcon.
- [ ] Clusters: 🟣 grape (mor) ThemeIcon.
- [ ] Hosts: 🟠 turuncu ThemeIcon.
- [ ] VMs: 🟢 teal ThemeIcon.
- [ ] Sayılar sağa hizalı, `tabular-nums`, `fw=700`.

**Ortada Frosted Divider:**
- [ ] İki sütun arasında ince, soluk, dikey gradyan çizgi var.

**Sağ Sütun — Power Dial:**
- [ ] `dmc.RingProgress` görünüyor — turuncu IBM dilimi + mor kalan dilim.
- [ ] Halka ortasında `"XX%"` (bold) + `"IBM"` (dimmed) yazısı.
- [ ] Halkanın altında `"Power"` etiketi ve `"X.X kW total"` bilgisi.

**Hover:**
- [ ] Kart hover'da `translateY(-5px)` + derinleşen mor aura gölge.
- [ ] Geçiş akıcı — `0.28s cubic-bezier`.

**Live Pulse:**
- [ ] DC ismi yanındaki yeşil nokta sürekli olarak soluklaşıp belirginleşiyor.
- [ ] Animasyon döngüsü `1.8s ease-in-out infinite`.

---

### 📝 Task 2 Değişiklik Özeti

```
src/services/db_service.py
  Satır 733-734 — stats dict'e 2 yeni satır:
    "ibm_kw":     d["energy"].get("ibm_kw", 0.0)
    "vcenter_kw": d["energy"].get("vcenter_kw", 0.0)

assets/style.css — SONUNA 2 CSS kuralı ekle:
  @keyframes dc-pulse (0% → 50% → 100% opacity + scale)
  .dc-pulse-dot (7px yeşil daire, animation: dc-pulse)
  .dc-vault-card (transition: transform + box-shadow)
  .dc-vault-card:hover (translateY(-5px) + mor aura gölge)

src/pages/datacenters.py
  Yeni yardımcı fonksiyon (build_datacenters içinde veya modül seviyesi):
    _dc_vault_card(dc):
      ibm_kw, total_kw, power_ratio hesabı
      4 metrik satırı (ThemeIcon renk kodlu)
      dmc.RingProgress(size=110, orange+indigo)
      frosted gradient divider
      dc-pulse-dot + live pulse
      dmc.Paper(className="dc-vault-card", glassmorphism)

  Satır 28-122 grid bloğu — TAMAMEN DEĞİŞTİR:
    dmc.SimpleGrid(cols=3, children=[_dc_vault_card(dc) for dc in datacenters])

DEĞİŞMEYEN:
  - Task 1 header (dmc.Paper glassmorphism)
  - layout() fonksiyonu
  - dmc.SimpleGrid cols=3 (sadece içerik değişiyor)
  - Callback'lar
```

**Toplam:** 3 dosya —
- `db_service.py` (2 satır ekleme)
- `style.css` (4 CSS kuralı + 1 keyframe)
- `datacenters.py` (1 yeni fonksiyon + grid bloğu değişimi)

---

## Güncelleme — 2026-04-02 (DC görünen ad + availability katalog)

- **Kart başlığı:** `format_dc_display_name(name, description)` — NetBox `loki_locations` `name` + `description` (örn. `DC13 - Equinix IL2 DC`). Dosya: `src/utils/dc_display.py`, `src/pages/datacenters.py`.
- **API:** `GET /api/v1/datacenters/summary` ve DC detail `meta` alanına `description` eklendi (`datacenter-api` + `schemas.py`).
- **DC Availability sekmesi:** `data/product_catalog.xlsx` (sheet `Ana Servis Kategorileri`) ile tüm servis ağacı; AuraNotify kategori eşlemesi `src/services/product_catalog.py`.
