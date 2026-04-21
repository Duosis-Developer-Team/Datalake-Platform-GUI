# Executor Prompt: DC Detay Sayfaları — İkon Standardizasyonu + Dinamik Chart Görünürlüğü

> **Tek kural:** API / backend / callback mantığı değişmez. Yalnızca `src/pages/dc_view.py` içindeki `_kpi()` çağrılarındaki ikon ve `SimpleGrid` / `_chart_card` render koşulları güncellenir.

---

## BÖLÜM 1 — İKON STANDARDIZASYONU

### Sorun

`_kpi()` fonksiyonu her yerde kullanılıyor ancak ikonlar tutarsız:

| Mevcut durum | Problem |
|---|---|
| `solar:server-bold-duotone` | "Total Hosts", "IBM Hosts", "Total Devices" — 3 farklı kavram, aynı ikon |
| `solar:laptop-bold-duotone` | "Total VMs / LPARs", "LPARs" — farklı kavramlar, aynı ikon |
| `material-symbols:bolt-outline` | "IBM kWh", "vCenter kWh", "Total kWh" — 3 farklı satır, aynı ikon |
| `solar:storage-bold-duotone` ve `solar:database-bold-duotone` | İkisi de storage için kullanılıyor, ikisi de aynı hissi veriyor |
| `solar:ram-bold-duotone` | RAM için bu ikon `solar` set'inde belirsiz görünüm |

### Çözüm: Global İkon Sözlüğü

`dc_view.py` dosyasının başına (importların altına, fonksiyonların üstüne) şu sabit sözlüğü ekle:

```python
# ── KPI Icon Standard — her kavram için tek ikon ──────────────────────────
_DC_ICONS: dict[str, str] = {
    # Compute / Hosts
    "hosts":            "solar:server-2-bold-duotone",
    "ibm_hosts":        "solar:server-square-bold-duotone",
    "vms":              "solar:display-bold-duotone",
    "lpars":            "solar:programming-bold-duotone",
    "vios":             "solar:settings-minimalistic-bold-duotone",
    "clusters":         "solar:layers-bold-duotone",
    "platforms":        "solar:layers-minimalistic-bold-duotone",

    # CPU / RAM / Storage
    "cpu":              "solar:cpu-bolt-bold-duotone",
    "ram":              "solar:database-bold-duotone",
    "storage":          "solar:hard-drive-2-bold-duotone",
    "storage_systems":  "solar:server-path-bold-duotone",
    "disk":             "solar:hard-drive-bold-duotone",

    # Network / Ports
    "total_devices":    "solar:devices-bold-duotone",
    "active_ports":     "solar:plug-circle-bolt-bold-duotone",
    "total_ports":      "solar:port-bold-duotone",
    "no_link_ports":    "solar:plug-circle-remove-bold-duotone",
    "disabled_ports":   "solar:pause-circle-bold-duotone",
    "licensed_ports":   "solar:ticket-sale-bold-duotone",
    "port_availability":"solar:graph-up-bold-duotone",

    # Energy / Power
    "ibm_power_kw":     "material-symbols:power-rounded",
    "vcenter_kw":       "material-symbols:cloud-outlined",
    "total_kw":         "material-symbols:flash-on",
    "ibm_kwh":          "solar:battery-charge-bold-duotone",
    "vcenter_kwh":      "solar:battery-half-bold-duotone",
    "total_kwh":        "solar:bolt-bold-duotone",

    # Physical Inventory
    "device_roles":     "solar:widget-4-bold-duotone",
    "top_role":         "solar:crown-bold-duotone",
    "manufacturers":    "solar:buildings-bold-duotone",

    # Storage subtab
    "total_capacity":   "solar:hard-drive-2-bold-duotone",
    "used_capacity":    "solar:pie-chart-2-bold-duotone",
    "utilization":      "solar:chart-square-bold-duotone",

    # IBM Power summary
    "ram_assigned":     "solar:chip-bold-duotone",
    "ibm_storage":      "solar:server-minimalistic-bold-duotone",
    "last_updated":     "solar:clock-circle-bold-duotone",
}
```

### Hangi _kpi() çağrıları değişecek (satır referansı + yeni ikon)

Aşağıdaki tabloyu uygula. Satır numaraları mevcut `dc_view.py`'ye göredir:

| Satır | Title | Mevcut ikon | Yeni ikon (`_DC_ICONS` key) |
|---|---|---|---|
| 677 | `"Total Hosts"` | `solar:server-bold-duotone` | `_DC_ICONS["hosts"]` |
| 678 | `"Total VMs / LPARs"` | `solar:laptop-bold-duotone` | `_DC_ICONS["vms"]` |
| 679 | `"CPU Capacity"` | `solar:cpu-bold-duotone` | `_DC_ICONS["cpu"]` |
| 680 | `"RAM Capacity"` | `solar:ram-bold-duotone` | `_DC_ICONS["ram"]` |
| 767 | `"IBM Hosts"` | `solar:server-bold-duotone` | `_DC_ICONS["ibm_hosts"]` |
| 768 | `"VIOS"` | `solar:server-square-bold-duotone` | `_DC_ICONS["vios"]` |
| 769 | `"LPARs"` | `solar:laptop-bold-duotone` | `_DC_ICONS["lpars"]` |
| 770 | `"Last Updated"` | `solar:clock-circle-bold-duotone` | `_DC_ICONS["last_updated"]` |
| 991 | `"IBM Power"` (Energy, Power tab) | `material-symbols:bolt-outline` | `_DC_ICONS["ibm_power_kw"]` |
| 992 | `"Consumption"` | `material-symbols:bolt-outline` | `_DC_ICONS["ibm_kwh"]` |
| 1137 | `"Active Ports"` | `solar:signal-bold-duotone` | `_DC_ICONS["active_ports"]` |
| 1138 | `"No Link / Offline Ports"` | `solar:port-bold-duotone` | `_DC_ICONS["no_link_ports"]` |
| 1139 | `"Admin Disabled Ports"` | `solar:pause-circle-bold-duotone` | `_DC_ICONS["disabled_ports"]` |
| 1140 | `"Licensed Ports"` | `solar:ticket-bold-duotone` | `_DC_ICONS["licensed_ports"]` |
| 1290 | `"Total Hosts"` | `solar:server-bold-duotone` | `_DC_ICONS["hosts"]` |
| 1291 | `"Total VMs / LPARs"` | `solar:laptop-bold-duotone` | `_DC_ICONS["vms"]` |
| 1292 | `"CPU Capacity"` | `solar:cpu-bold-duotone` | `_DC_ICONS["cpu"]` |
| 1293 | `"RAM Capacity"` | `solar:ram-bold-duotone` | `_DC_ICONS["ram"]` |
| 1370 | `"IBM Hosts"` | `solar:server-bold-duotone` | `_DC_ICONS["ibm_hosts"]` |
| 1371 | `"LPARs"` | `solar:laptop-bold-duotone` | `_DC_ICONS["lpars"]` |
| 1372 | `"RAM Assigned"` | `solar:ram-bold-duotone` | `_DC_ICONS["ram_assigned"]` |
| 1374 | `"Storage"` | `solar:database-bold-duotone` | `_DC_ICONS["ibm_storage"]` |
| 1386 | `"IBM Power"` | `material-symbols:power-rounded` | `_DC_ICONS["ibm_power_kw"]` |
| 1387 | `"vCenter"` | `material-symbols:cloud` | `_DC_ICONS["vcenter_kw"]` |
| 1388 | `"Total"` | `material-symbols:flash-on` | `_DC_ICONS["total_kw"]` |
| 1392 | `"IBM kWh"` | `material-symbols:bolt-outline` | `_DC_ICONS["ibm_kwh"]` |
| 1393 | `"vCenter kWh"` | `material-symbols:bolt-outline` | `_DC_ICONS["vcenter_kwh"]` |
| 1394 | `"Total kWh"` | `material-symbols:bolt-outline` | `_DC_ICONS["total_kwh"]` |
| 1584 | `"Total Devices"` | `solar:server-bold-duotone` | `_DC_ICONS["total_devices"]` |
| 1585 | `"Device Roles"` | `solar:widget-4-bold-duotone` | `_DC_ICONS["device_roles"]` |
| 1686 | `"Total Devices"` | `solar:server-bold-duotone` | `_DC_ICONS["total_devices"]` |
| 1687 | `"Active Ports"` | `solar:signal-bold-duotone` | `_DC_ICONS["active_ports"]` |
| 1688 | `"Total Ports"` | `solar:port-bold-duotone` | `_DC_ICONS["total_ports"]` |
| 1689 | `"Port Availability"` | `solar:graph-bold-duotone` | `_DC_ICONS["port_availability"]` |
| 2173 | `"Storage Systems"` | `solar:database-bold-duotone` | `_DC_ICONS["storage_systems"]` |
| 2174 | `"Total Capacity"` | `solar:storage-bold-duotone` | `_DC_ICONS["total_capacity"]` |
| 2175 | `"Used Capacity"` | `solar:storage-bold-duotone` | `_DC_ICONS["used_capacity"]` |
| 2176 | `"Utilization"` | `solar:graph-bold-duotone` | `_DC_ICONS["utilization"]` |

> **Not:** `app.py` içinde de `dc_view._kpi(...)` çağrıları var (satır 1346–1349). Onlarda da aynı sözlüğü içe aktarıp (`from src.pages.dc_view import _DC_ICONS`) aynı değişimi uygula.

---

## BÖLÜM 2 — DİNAMİK CHART GÖRÜNÜRLÜĞÜ

### Sorun

Bazı DC'lerde belirli metrikler (CPU, RAM, Storage) tamamen 0 ya da boş geliyor. Bu durumda:
- `create_premium_gauge_chart(0, "CPU Usage", ...)` → boş/anlamlısız görsel
- `SimpleGrid(cols=3, children=[chart1, chart2, chart3])` → 3 slot tam dolu olduğunda grid 3 kolonlu; ama 1 chart boşsa "boş kart" ortada kalıyor
- Kullanıcı "veri yoksa chart olmasın; kalan chartlar orantılı dolsun" istiyor

### Çözüm: `_maybe_chart()` yardımcı fonksiyonu + dinamik grid

#### Adım 1: Yardımcı fonksiyonlar

`dc_view.py` dosyasına `_chart_card()` hemen altına şu iki fonksiyonu ekle:

```python
def _has_value(*values) -> bool:
    """Return True if at least one value is meaningfully non-zero."""
    for v in values:
        try:
            if float(v or 0) > 0:
                return True
        except (TypeError, ValueError):
            pass
    return False


def _dynamic_chart_grid(items: list, spacing: str = "lg") -> html.Div | None:
    """
    Verilen (has_data: bool, graph_component) çiftlerinden yalnızca
    has_data==True olanları _chart_card'a sarar ve dinamik grid'e koyar.

    - 0 item  → None (bölüm tamamen gizlenir)
    - 1 item  → tek kart, tam genişlik (cols=1)
    - 2 item  → cols=2
    - 3+ item → cols=3
    """
    visible = [graph_comp for has_data, graph_comp in items if has_data]
    if not visible:
        return None
    cols = min(len(visible), 3)
    return dmc.SimpleGrid(
        cols=cols,
        spacing=spacing,
        style={"marginTop": "12px"},
        children=[_chart_card(g) for g in visible],
    )
```

#### Adım 2: Uygulama noktaları

Her `dmc.SimpleGrid(cols=3, ...)` veya `dmc.SimpleGrid(cols=2, ...)` chart grid'ini şu pattern ile değiştir:

---

##### 2a. `_build_compute_tab()` — Resource Utilization (satır ~683–707)

**Mevcut:**
```python
dmc.SimpleGrid(cols=3, spacing="lg", children=[
    _chart_card(dcc.Graph(figure=cpu_gauge, ...)),
    _chart_card(dcc.Graph(figure=ram_gauge, ...)),
    _chart_card(dcc.Graph(figure=stor_gauge, ...)),
]),
```

**Yeni:**
```python
_dynamic_chart_grid([
    (_has_value(cpu_cap),  dcc.Graph(figure=cpu_gauge,  config={"displayModeBar": False}, style={"height": "100%", "width": "100%"})),
    (_has_value(mem_cap),  dcc.Graph(figure=ram_gauge,  config={"displayModeBar": False}, style={"height": "100%", "width": "100%"})),
    (_has_value(stor_cap), dcc.Graph(figure=stor_gauge, config={"displayModeBar": False}, style={"height": "100%", "width": "100%"})),
]),
```

Eğer `_dynamic_chart_grid` `None` döndürürse bölüm başlığı da render edilmesin:
```python
chart_grid = _dynamic_chart_grid([...])
# Sonra:
html.Div(
    className="nexus-card",
    style={"padding": "20px"},
    children=[
        _section_title("Resource Utilization", "..."),
        chart_grid,
    ],
) if chart_grid else None,
```

---

##### 2b. `_build_power_tab()` — Memory + CPU gauge (satır ~772–783)

```python
_dynamic_chart_grid([
    (_has_value(mem_total),    dcc.Graph(figure=create_gauge_chart(mem_assigned, mem_total or 1, "Memory Assigned", color="#05CD99"), config={"displayModeBar": False}, style={"height": "100%", "width": "100%"})),
    (_has_value(cpu_assigned), dcc.Graph(figure=create_gauge_chart(cpu_used, cpu_assigned, "CPU Used", color="#4318FF"),               config={"displayModeBar": False}, style={"height": "100%", "width": "100%"})),
]),
```

---

##### 2c. `_build_summary_tab()` — Resource Utilization charts (satır ~1303–1318)

```python
chart_grid = _dynamic_chart_grid([
    (_has_value(total_cpu_cap),  dcc.Graph(figure=create_premium_gauge_chart(cpu_pct,  "CPU Usage",     color="#4318FF"), config={"displayModeBar": False}, style={"height": "100%", "width": "100%"})),
    (_has_value(total_mem_cap),  dcc.Graph(figure=create_premium_gauge_chart(mem_pct,  "RAM Usage",     color="#05CD99"), config={"displayModeBar": False}, style={"height": "100%", "width": "100%"})),
    (_has_value(total_stor_cap), dcc.Graph(figure=create_premium_gauge_chart(stor_pct, "Storage Usage", color="#FFB547"), config={"displayModeBar": False}, style={"height": "100%", "width": "100%"})),
])
# Wrapper:
html.Div(
    className="nexus-card",
    style={"padding": "20px"},
    children=[
        _section_title("Resource Utilization", "Capacity vs. workload allocation (all VMware compute)"),
        chart_grid,
    ],
) if chart_grid else None,
```

---

##### 2d. `_build_intel_storage_subtab()` — 3 donut (satır ~2033–2039)

```python
total_bytes = zabbix_storage_capacity.get("total_bytes", 0) or 0
used_bytes  = zabbix_storage_capacity.get("used_bytes",  0) or 0
free_bytes  = max(0, total_bytes - used_bytes)

_dynamic_chart_grid([
    (total_bytes > 0, dcc.Graph(id="intel-donut-total", figure=donut_total, config={"displayModeBar": False})),
    (used_bytes  > 0, dcc.Graph(id="intel-donut-used",  figure=donut_used,  config={"displayModeBar": False})),
    (free_bytes  > 0, dcc.Graph(id="intel-donut-free",  figure=donut_free,  config={"displayModeBar": False})),
]),
```

---

##### 2e. `_build_ibm_storage_subtab()` — Used / Free breakdown chart (satır ~2184–2195)

```python
_dynamic_chart_grid([
    (bool(labels), dcc.Graph(figure=breakdown_fig, config={"displayModeBar": False}, style={"height": "250px"})),
    (bool(systems), dcc.Graph(figure=used_fig,      config={"displayModeBar": False}, style={"height": "250px"})),
]),
```

---

#### Adım 3: Section başlığı + grid birlikte None guard

Aşağıdaki pattern'i tüm değiştirilen bölümlerde uygula:

```python
_chart_section = _dynamic_chart_grid([...])
# Wrapper div:
html.Div(
    className="nexus-card",
    style={"padding": "20px"},
    children=filter(None, [
        _section_title("Başlık", "Altyazı"),
        _chart_section,
    ]),
) if _chart_section is not None else None,
```

> `dmc.Stack` içinde `None` çocuklar sorunsuz görmezden gelinir (Dash/DMC bunu handle eder).

---

## BÖLÜM 3 — TEST CHECKLİSTİ

- [ ] **İkon test:** Summary tab → KPI kutularında Total Hosts, Total VMs, CPU, RAM ikonları farklı
- [ ] **İkon test:** Power tab → IBM Hosts ≠ Total Hosts ikonu; LPARs ≠ VMs ikonu
- [ ] **İkon test:** Energy Breakdown → IBM kWh, vCenter kWh, Total kWh üçü farklı ikon
- [ ] **İkon test:** Physical Inventory → Total Devices ≠ Total Hosts ikonu
- [ ] **Dinamik test:** Sadece Classic verisi olan DC → Resource Utilization'da yalnızca CPU + RAM gösteriliyorsa Storage chart yok; grid 2-kolon oluyor
- [ ] **Dinamik test:** Sadece 1 chart varsa full-width (cols=1) görünüyor
- [ ] **Dinamik test:** Hiç veri yoksa bölüm başlığıyla birlikte section kaldırılıyor
- [ ] **Regresyon:** Tüm verisi olan DC'de her şey normal 3-kolon görünüyor
- [ ] **Regresyon:** Power tab çift gauge (mem + cpu) her ikisi de data varsa 2-kolon; biri yoksa full-width

---

## BÖLÜM 4 — SCOPE DIŞI (DOKUNMA)

- `assets/style.css` — değişiklik gerekmez
- `api_client.py`, `db_service.py` — değişiklik gerekmez
- Callback mantığı (`app.py` içindeki callback fonksiyonları) — ikonlar dışında değişiklik gerekmez
- `src/components/backup_panel.py` — bu prompt kapsamında değil
- `src/components/charts.py` — değişiklik gerekmez

---

## BÖLÜM 5 — ÖNEMLİ UYARILAR

1. `_dynamic_chart_grid` `None` döndürdüğünde Dash `dmc.Stack` içine `None` koyma; wrapper `html.Div` veya `dmc.Stack`'in `children` listesinde `filter(None, [...])` kullan.

2. `_has_value()` sadece 0 / None / boş kontrolü yapar. `pct` değerleri (0–100) için `cpu_cap > 0` gibi ham kapasite değerini kontrol et, pct'yi değil — zira `cpu_cap > 0` ama `cpu_pct == 0.0` olan DC'ler olabilir.

3. `_DC_ICONS` sözlüğündeki solar: ve material-symbols: ikonların hepsinin `dash_iconify` içinde mevcut olduğunu varsayıyoruz (mevcut kod zaten bu set'i kullanıyor).
