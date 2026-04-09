# EXECUTOR PROMPT & PLAN — Global Map View V10.0: 3D Hologram Modal Pivot

Sen, projenin CTO kurallarına harfiyen uyan üst düzey bir AI kod yazarısın (Executer). 
Bu dosyayı baştan sona dikkatlice oku. Haritaya bağladığımız holografik şöleni iptal edip, bunu `global_view.py` kartlarındaki "Detail" butonlarına basıldığında ekranı kaplayan bağımsız bir "Ara Katman Modal" şölenine dönüştüreceksin. 

**İnisiyatif kullanmayacaksın, koddaki mantığı kendin yorumlamayacaksın, aşağıdaki kodların birebir aynısını hedef dosyalardaki ilgili kısımlarla değiştireceksin.**

---

## ⛔ İHLAL EDİLEMEZ CTO KURALLARI ⛔

1. **SIFIR YORUM KURALI:** Asla, hiçbir `.py` dosyasına (Python) ekstra `#` yorumu veya `"""..."""` blok açmak yok. Yalnızca kodu yaz. Koddaki işlevleri açıklama ihtiyacı hissetme.
2. **KAPSAM SINIRI:** Sadece planda adı geçen dosyalara (`global_view.py`, `app.py`, `style.css`) dokunacaksın.
3. `region_drilldown.py` REZERVEDİR, asla değiştirilmeyecek ve okunmayacak.

---

## 1. DOSYA DEĞİŞİKLİKLERİ: `src/pages/global_view.py`

### A. Harita Üzerindeki V9 Overlay'in İptali & Global Modal'ın Eklenmesi
`layout()` fonksiyonundaki harita `dcc.Graph(id="global-map-graph", ...)` nesnesinin hemen altında veya etrafında bulunan, `id="map-3d-overlay"` bloğunu **tamamen siliyorsun**. 

Bunun yerine, sayfanın ana `layout` dizisinin **en son satırına** şu Div bloğunu ekliyorsun:

```python
        html.Div(
            id="global-3d-modal-container",
            style={
                "position": "fixed", "top": 0, "left": 0, "width": "100%", "height": "100%", 
                "backgroundColor": "rgba(4, 10, 35, 0.8)", "backdropFilter": "blur(12px)",
                "WebkitBackdropFilter": "blur(12px)",
                "zIndex": 9999, "display": "none", "alignItems": "center", "justifyContent": "center"
            },
            children=[]
        )
```

### B. "Detail" Butonlarının Açılabilir Modal Butonuna (Pattern Matching) Çevrilmesi
"DC Kartları" üzerindeki "Detail" butonları şu an `dcc.Link` sarılı olarak bulunuyor ve `href` barındırıyor. O sarımı koparıp at ve aşağıdaki **tam kod blokları ile değiştir.**

**Değişiklik Noktası 1 (`build_region_detail_panel` içinde satır 624-637 arası):**

```python
                    dmc.Group(justify="flex-end", children=[
                        dmc.Button(
                            "Detail",
                            id={"type": "open-3d-hologram-btn", "index": dc_id},
                            variant="light",
                            color="indigo",
                            radius="md",
                            size="xs",
                            rightSection=DashIconify(icon="solar:magic-stick-3-bold-duotone", width=14),
                        ),
                    ]),
```

**Değişiklik Noktası 2 (`build_dc_info_card` içinde satır 1086-1099 arası):**

```python
            dmc.Group(justify="flex-end", children=[
                dmc.Button(
                    "Detail",
                    id={"type": "open-3d-hologram-btn", "index": dc_id},
                    variant="light",
                    color="indigo",
                    radius="md",
                    size="sm",
                    rightSection=DashIconify(icon="solar:magic-stick-3-bold-duotone", width=16),
                ),
            ]),
```

### C. 3D Hologram Scene İçindeki Yönlendirme (Racks Details) Butonu
`build_3d_rack_overlay` isimli fonksiyonun içinde yer alan (hologram zemininde oluşturulan kutunun en altındaki) butonu (eski adıyla Detailed View) aşağıdaki blok ile **DEĞİŞTİR**:

```python
                    dmc.Group(
                        justify="flex-end",
                        mt="xl",
                        style={"pointerEvents": "auto"},
                        children=[
                            dcc.Link(
                                dmc.Button(
                                    "Racks Details", 
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
```

---

## 2. DOSYA DEĞİŞİKLİKLERİ: `app.py`

### A. Harita Tıklama Yöneticisinin (Callback) V9 Kısmından Arındırılması
Haritanın tıklanma callback'i (`handle_map_click_and_overlay`) içindeki hologram özelliklerini yokedip eski, MİNİMAL (sadece Info kartı açan) haline çevrilecek:

```python
@app.callback(
    dash.Output("global-detail-panel", "children"),
    dash.Input("global-map-graph", "clickData"),
    dash.State("app-time-range", "data"),
    prevent_initial_call=True,
)
def update_global_detail_from_pin(click_data, time_range):
    if not click_data or "points" not in click_data or not click_data["points"]:
        return []
    point = click_data["points"][0]
    custom = point.get("customdata")
    if not custom or not custom[0]:
        return []
    dc_id = custom[0]
    site_name = custom[7] if len(custom) > 7 else ""
    from src.queries.default_dates import default_time_range
    tr = time_range or default_time_range()
    
    from src.pages.global_view import build_dc_info_card
    return build_dc_info_card(dc_id, tr, site_name=site_name)
```

### B. MÜKEMMEL MODAL CALLBACK'İ (YENİ EKLENECEK)
`app.py` dosyasına (eski map_click'in altına veya ana dosyada boş bir alana) **YENİ** pattern-matching global modal aç/kapa callback'ini ekle:

```python
from dash.dependencies import Input, Output, State, ALL
import json

@app.callback(
    Output("global-3d-modal-container", "children"),
    Output("global-3d-modal-container", "style"),
    Input({"type": "open-3d-hologram-btn", "index": ALL}, "n_clicks"),
    Input("close-3d-overlay-btn", "n_clicks"),
    State("global-3d-modal-container", "style"),
    prevent_initial_call=True
)
def toggle_3d_hologram_modal(btn_clicks, close_clicks, current_style):
    import dash
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update

    trig = ctx.triggered[0]["prop_id"].split(".")[0]

    if trig == "close-3d-overlay-btn":
        new_style = current_style.copy() if current_style else {}
        new_style["display"] = "none"
        new_style["pointerEvents"] = "none"
        return [], new_style

    try:
        trig_dict = json.loads(trig)
    except:
        return dash.no_update, dash.no_update

    if trig_dict.get("type") == "open-3d-hologram-btn":
        if all(x is None for x in btn_clicks):
            return dash.no_update, dash.no_update

        dc_id = trig_dict.get("index")
        if not dc_id:
            return dash.no_update, dash.no_update

        from src.services import api_client as api
        from src.pages.global_view import build_3d_rack_overlay
        
        info = api.get_dc_details(dc_id, "now-1h")
        dc_name = info.get("meta", {}).get("name", dc_id)
        
        racks_resp = api.get_dc_racks(dc_id)
        racks = racks_resp.get("racks", [])
        
        if racks:
            content = build_3d_rack_overlay(dc_id, dc_name, racks)
            new_style = current_style.copy() if current_style else {}
            new_style["display"] = "flex"
            new_style["pointerEvents"] = "auto"
            return content, new_style
        else:
            return [], current_style

    return dash.no_update, dash.no_update
```

---

## 3. DOSYA DEĞİŞİKLİKLERİ: `assets/style.css`

`hologram-scene` class'ını ekranın tam ortasında durabilmesi için eski `margin-top: -40px;` ayarını sıfırla. 

```css
.hologram-scene {
    perspective: 1400px;
    pointer-events: auto;
    width: 650px;
    max-height: 560px;
    margin-top: 0;
}
```
