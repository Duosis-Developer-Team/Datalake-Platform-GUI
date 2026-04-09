# ✨ GLOBAL MAP VIEW V9.0 — 3D Holografik Rack Şöleni

> **Versiyon:** 9.0  
> **Tarih:** 2026-04-02  
> **Hazırlayan:** Baş Planlayıcı & Sistem Mimarı  
> **Hedef:** Harita üzerinde DC pinine tıklandığında, pin merkeze geldiği an tam ekranın ortasında holografik bir 3D container yükselir. Bu container içerisinde `hall_name` (salon: dh1, dh2 vb.) bazlı gruplanmış odalar birer server çekmecesi (blade) efektiyle dışarı çıkar. Odaların içindeki kabinetler (rack kartları) veri odaklı ve hover efektli yapılarıyla "şelale" animasyonuyla yerlerine oturur.

---

## 1. MİMARİ & UYGULAMA STRATEJİSİ

- **Map Konteynerı Üzerinde Manipülasyon:** Plotly haritasının container `div`'ini `position: relative` olarak kullanacağız. Tıklama sonrası 1100ms süren globe dönüşü bittiğinde ortasında belirmesi için, absolute pozisyonlu bir `#map-3d-overlay` yaratacağız.
- **Backend Modifikasyonu:** V8.0'daki SQL sorgusundan eksik olan `l.name AS hall_name` yapısını ekleyeceğiz. Bu veri, kabinetlerin hangi odada olduklarını gösterecek.
- **Dash Callback Yapısı:** Tıklama anında haritanın altındaki mevcut bilgi paneli açılırken (V5.1 ile gelen özellik), aynı callback ikinci ve üçüncü `Output` ile Overlay div'in içeriğini (`children`) doldurup görünür (`style` display: flex) yapacak. Çarpı butonuna (X) tıklandığında yine aynı callback sahneyi görünmez (`display: none`) yapacak.

---

## 2. ADIM ADIM İMPLEMENTASYON DÖKÜMÜ

### ADIM 1: Backend Veri Zenginleştirmesi (Datacenter-API)

**1.1 SQL Güncellemesi**
Dosya: `services/datacenter-api/app/db/queries/discovery_rack.py`
*(Not: Bu dosya henüz oluşturulmamışsa V8.0 ile oluşturulmalıdır. İçindeki RACKS_BY_DC sorgusuna l.name eklenir.)*

```sql
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
    r.site_id,
    l.name AS hall_name
FROM public.discovery_loki_rack r
JOIN public.discovery_loki_location l
    ON r.location_id = l.id::varchar
WHERE (l.name = %s OR l.parent_name = %s)
ORDER BY l.name, r.name
"""
```

**1.2 Servis Güncellemesi**
Dosya: `services/datacenter-api/app/services/dc_service.py`
`get_dc_racks()` metodu içindeki `columns` array'inin en sonuna `"hall_name"` eklenir. Rack parse döngüsü onu da alıp Dictionary'ye koysun.

```python
    columns = [
        "id", "name", "display_name", "status", "status_description",
        "u_height", "kabin_enerji", "pdu_a_ip", "pdu_b_ip", "rack_type",
        "serial", "asset_tag", "tenant_name", "facility_id",
        "weight", "max_weight", "weight_unit",
        "description", "comments",
        "first_observed", "last_observed", "location_id", "site_id",
        "hall_name",
    ]
```

---

### ADIM 2: Frontend Layout ve 3D Overlay Fonksiyonu

**Dosya:** `src/pages/global_view.py`

**2.1 Layout Değişikliği:**
Mevcut `global-map-graph` div'ini saran container'a `position: relative` garantisi verip, altına Overlay ekliyoruz:

```python
html.Div(
    style={"position": "relative", "width": "100%", "height": "600px", "overflow": "hidden", "borderRadius": "12px"},
    children=[
        dcc.Graph(
            id="global-map-graph",
            figure=map_fig,
            config={"displayModeBar": False, "scrollZoom": True, "responsive": True},
            style={"height": "600px", "width": "100%", "position": "relative", "zIndex": 1},
        ),
        html.Div(
            id="map-3d-overlay",
            style={
                "position": "absolute", "top": 0, "left": 0, 
                "width": "100%", "height": "100%", 
                "pointerEvents": "none", 
                "zIndex": 100, 
                "display": "none", 
                "alignItems": "center", "justifyContent": "center"
            },
            children=[]
        )
    ],
),
```

**2.2 Saf Dash UI ile Sahne Oluşturucu (Dosya: `src/pages/global_view.py` içine importların altına konacak)**

```python
def build_3d_rack_overlay(dc_id, dc_name, racks):
    if not racks:
        return []

    grouped = {}
    for r in racks:
        h = r.get("hall_name") or "Main Hall"
        grouped.setdefault(h, []).append(r)

    layer_delay = 1
    hall_layers = []

    for hall, r_list in grouped.items():
        cards = []
        for i, r in enumerate(r_list):
            name = str(r.get("name") or "?")
            u = r.get("u_height") or 0
            pwr = r.get("kabin_enerji") or "—"
            status = (r.get("status") or "unknown").lower()

            scolor = "#05CD99" if status == "active" else ("#4385F4" if status == "planned" else "#FFB547")

            card = html.Div(
                className="rack-micro-card",
                style={"--card-delay": str(i)},
                children=[
                    html.Div(
                        style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"},
                        children=[
                            html.Span(name, style={"fontWeight": "800", "color": "#2B3674", "fontSize": "13px"}),
                            html.Span("●", style={"color": scolor, "fontSize": "12px", "textShadow": f"0 0 8px {scolor}"})
                        ]
                    ),
                    html.Div(
                        style={"display": "flex", "gap": "6px", "alignItems": "center", "marginTop": "6px"},
                        children=[
                            DashIconify(icon="solar:ruler-bold-duotone", width=12, color="#A3AED0"),
                            html.Span(f"{u}U", style={"fontSize": "11px", "color": "#A3AED0", "fontWeight": "600"}),
                            html.Span("·", style={"color": "#A3AED0", "margin": "0 2px"}),
                            DashIconify(icon="solar:bolt-circle-bold-duotone", width=12, color="#A3AED0"),
                            html.Span(f"{pwr}", style={"fontSize": "11px", "color": "#A3AED0", "fontWeight": "600"})
                        ]
                    )
                ]
            )
            cards.append(card)

        hall_layers.append(
            html.Div(
                className="hall-layer",
                style={"--delay": str(layer_delay)},
                children=[
                    html.Div(
                        style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "12px"},
                        children=[
                            DashIconify(icon="solar:server-square-bold-duotone", width=18, color="#05CD99"),
                            html.Div(hall, className="hall-title")
                        ]
                    ),
                    html.Div(cards, className="rack-micro-grid")
                ]
            )
        )
        layer_delay += 1

    return html.Div(
        className="hologram-scene",
        children=[
            html.Div(
                className="dc-hologram-base",
                children=[
                    html.Div(
                        style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start", "marginBottom": "20px"},
                        children=[
                            html.Div([
                                dmc.Text(dc_name, c="white", fw=800, size="xl", style={"letterSpacing": "1px"}),
                                dmc.Text(f"{len(racks)} Cabinets Total", size="sm", style={"color": "rgba(255,255,255,0.7)", "marginTop": "2px"}),
                            ]),
                            dmc.ActionIcon(
                                DashIconify(icon="solar:close-circle-bold-duotone", width=26),
                                id="close-3d-overlay-btn",
                                variant="transparent",
                                color="gray",
                                size="lg",
                                style={"pointerEvents": "auto"}
                            )
                        ]
                    ),
                    html.Div(hall_layers, className="hologram-halls"),
                    dmc.Group(
                        justify="flex-end",
                        mt="xl",
                        style={"pointerEvents": "auto"},
                        children=[
                            dcc.Link(
                                dmc.Button(
                                    "Detailed View", 
                                    variant="white", 
                                    size="sm", 
                                    radius="md", 
                                    color="indigo",
                                    rightSection=DashIconify(icon="solar:arrow-right-bold-duotone", width=16)
                                ),
                                href=f"/dc-detail/{dc_id}",
                                style={"textDecoration": "none"}
                            )
                        ]
                    )
                ]
            )
        ]
    )
```

---

### ADIM 3: App.py Çift-Yönlü Kontrol

**Dosya:** `app.py`

`update_global_detail_from_pin` callback fonksiyonu adını `handle_map_click_and_overlay` olarak değiştirip Output yeteneklerini genişleteceğiz. Hem eski paneli, hem 3D kutuyu doldurur.

```python
@app.callback(
    dash.Output("global-detail-panel", "children"),
    dash.Output("map-3d-overlay", "children"),
    dash.Output("map-3d-overlay", "style"),
    dash.Input("global-map-graph", "clickData"),
    dash.Input("close-3d-overlay-btn", "n_clicks"),
    dash.State("app-time-range", "data"),
    dash.State("map-3d-overlay", "style"),
    prevent_initial_call=True,
)
def handle_map_click_and_overlay(click_data, close_clicks, time_range, current_style):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update, dash.no_update
        
    trig_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    if trig_id == "close-3d-overlay-btn":
        new_style = current_style or {}
        new_style["display"] = "none"
        new_style["pointerEvents"] = "none"
        return dash.no_update, dash.no_update, new_style
        
    if not click_data or "points" not in click_data or not click_data["points"]:
        return [], [], {"display": "none"}
        
    point = click_data["points"][0]
    custom = point.get("customdata")
    if not custom or not custom[0]:
        return [], [], {"display": "none"}
        
    dc_id = custom[0]
    site_name = custom[7] if len(custom) > 7 else ""
    dc_name = custom[1] if len(custom) > 1 else dc_id
    tr = time_range or default_time_range()
    
    from src.pages.global_view import build_dc_info_card, build_3d_rack_overlay
    from src.services import api_client as api
    
    info_card = build_dc_info_card(dc_id, tr, site_name=site_name)
    racks_resp = api.get_dc_racks(dc_id)
    racks = racks_resp.get("racks", [])
    
    if racks:
        overlay_content = build_3d_rack_overlay(dc_id, dc_name, racks)
        overlay_style = {
            "position": "absolute", "top": 0, "left": 0, "width": "100%", "height": "100%", 
            "pointerEvents": "none", "zIndex": 100, 
            "display": "flex", "alignItems": "center", "justifyContent": "center"
        }
    else:
        overlay_content = []
        overlay_style = {"display": "none", "pointerEvents": "none"}
        
    return info_card, overlay_content, overlay_style
```

---

### ADIM 4: CSS İle Animasyon Şöleni (style.css)

**Dosya:** `assets/style.css`

Tüm bu HTML bloklarının hayata geçmesini, perspektif almasını ve ardışık animasyonla sunulmasını sağlayan bölüm. Aynen eklenmelidir:

```css
/* ======================================================== */
/* GLOBAL 9.0: 3D HOLOGRAPHIC RACK OVERLAY                  */
/* ======================================================== */

.hologram-scene {
    perspective: 1400px;
    pointer-events: auto;
    width: 650px;
    max-height: 560px;
    margin-top: -40px; /* Görsel olarak merkezleme dengesi */
}

.dc-hologram-base {
    transform-style: preserve-3d;
    background: linear-gradient(145deg, rgba(12, 18, 48, 0.95) 0%, rgba(35, 45, 95, 0.95) 100%);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(67, 24, 255, 0.5);
    box-shadow: 0 30px 60px rgba(0, 0, 0, 0.4), inset 0 0 40px rgba(67, 24, 255, 0.15);
    border-radius: 16px;
    padding: 28px;
    width: 100%;
    max-height: 540px;
    overflow-y: auto;
    -ms-overflow-style: none;
    scrollbar-width: none;
    
    /* Doğma Animasyonu: Harita animasyonundan sonra (0.5s gecikme) başlar */
    animation: riseUpHologram 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    animation-delay: 0.5s;
    opacity: 0;
}

.dc-hologram-base::-webkit-scrollbar { display: none; }

.hologram-halls {
    display: flex;
    flex-direction: column;
    gap: 20px;
}

/* Çekmece gibi çıkan Salon/Oda */
.hall-layer {
    background: rgba(255, 255, 255, 0.03);
    border-radius: 10px;
    border-left: 4px solid #05CD99;
    padding: 16px;
    
    transform: translateZ(-150px) rotateX(-20deg);
    opacity: 0;
    
    animation: bladeSlideOut 0.8s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    animation-delay: calc(800ms + (var(--delay) * 180ms));
}

.hall-title {
    color: #FFF;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1px;
}

.rack-micro-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 12px;
}

/* Tekil Rack Mini Card */
.rack-micro-card {
    background: rgba(255, 255, 255, 0.95);
    border-radius: 8px;
    padding: 10px;
    border: 1px solid rgba(67, 24, 255, 0.15);
    
    transform: translateZ(50px) translateY(20px) scale(0.7);
    opacity: 0;
    
    animation: rackCardPop 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    animation-delay: calc(1100ms + (var(--delay) * 180ms) + (var(--card-delay) * 60ms));
    transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.25s ease;
}

.rack-micro-card:hover {
    transform: translateY(-5px) scale(1.08) translateZ(40px) !important;
    box-shadow: 0 12px 28px rgba(67, 24, 255, 0.3);
    border-color: #4318FF;
    cursor: default;
}

/* ================== KEYFRAMES ================== */

@keyframes riseUpHologram {
    0% { 
        opacity: 0; 
        transform: rotateX(60deg) rotateY(-15deg) translateY(200px) scale(0.7); 
    }
    100% { 
        opacity: 1; 
        transform: rotateX(15deg) rotateY(-5deg) translateY(0) scale(1); 
    }
}

@keyframes bladeSlideOut {
    0% { 
        opacity: 0; 
        transform: translateZ(-200px) translateY(50px) rotateX(-30deg); 
    }
    100% { 
        opacity: 1; 
        transform: translateZ(0) translateY(0) rotateX(0deg); 
    }
}

@keyframes rackCardPop {
    0% { 
        opacity: 0; 
        transform: translateZ(60px) translateY(30px) scale(0.5); 
    }
    100% { 
        opacity: 1; 
        transform: translateZ(0) translateY(0) scale(1); 
    }
}
```

---

## 3. CHECKLIST 

1. **`services/datacenter-api/app/db/queries/discovery_rack.py`** dosyasında SQL'de `l.name AS hall_name` eklendi.
2. **`services/datacenter-api/app/services/dc_service.py`** dosyasında `columns` arrayine `"hall_name"` eklendi.
3. Backend docker servisi yeniden başlatıldı (değişiklikleri okuması için).
4. **`src/pages/global_view.py`** dosyasına overlay container'ı (`map-3d-overlay`) ve `build_3d_rack_overlay` metotu yerleştirildi. (`dmc`, `dcc` vb kütüphanelerin importu ile uyumlu)
5. **`app.py`** te mevcut map callback'i iptal edilip, 3 Output'a sahip tam yetkili `handle_map_click_and_overlay` hook'a yazıldı.
6. **`assets/style.css`** içerisine CSS 3D kuralları hatasız şekilde aktarıldı.
7. Haritada tıklanınca holografik büyüme ve kaydırarak (staggered delay) objeleri açma başarıyla simüle ediliyor. Kapatma butonu sorunsuz çalışıyor.
