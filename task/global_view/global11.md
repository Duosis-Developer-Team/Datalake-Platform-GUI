# ✨ GLOBAL MAP VIEW V11.0 — "The Globe.gl Revolution" Custom Dash Component Mimari Planı

> **Versiyon:** 11.0  
> **Tarih:** 2026-04-05  
> **Hazırlayan:** Baş Planlayıcı & Sistem Mimarı (Antigravity)  
> **Hedef:** Plotly'nin 3D haritasını tamamen sistemden söküp, gerçek bir NASA dokulu, atmosfer parlaması (glow) olan "Holographic Globe" hissi veren özel bir Dash React bileşeni (dash_globe_component) entegre etmek.

**DİKKAT:** Bu aşama (V11.0) projenin kalbini değiştirecek devasa bir front-end operasyonudur. Aşağıdaki adımlar en ufak virgülüne kadar eksiksiz uygulanmak zorundadır. Executer asla inisiyatif alamaz, plandaki kodların aynısını sıfır yorum kuralına uyarak yapıştırmak zorundadır.

---

## 1. MİMARİ ALTYAPI: REACT CUSTOM COMPONENT OLUŞTURMA

Projenin içinde yeni bir folder açılıp react-to-dash boilerplate yüklenecektir.

### 1.1 Terminal Komutları ve Kurulum
Terminalde (Workspace root alanında) aşağıdaki komutları sırasıyla çalıştıracaksın:
```bash
npx @plotly/dash-component-boilerplate dash_globe_component
cd dash_globe_component
npm install react-globe.gl globe.gl
```

### 1.2 `DashGlobe.react.js` (React Mimarisi)
Bileşen klasörü oluştuktan sonra `dash_globe_component/src/lib/components/DashGlobe.react.js` dosyasına git. İçini tamamen SİL ve sadece şu kusursuz React bileşenini yapıştır. 
*(Kurallar: Açıklama satırı (#, //) koyma, Night/Dark moddan kaçın. Açık, aydınlık atmosfer rengi seçilmiştir.)*

```javascript
import React, { useRef, useEffect } from 'react';
import PropTypes from 'prop-types';
import Globe from 'react-globe.gl';

const DashGlobe = (props) => {
    const { id, setProps, pointsData, focusRegion, globeImageUrl, width, height } = props;
    const globeRef = useRef();

    useEffect(() => {
        if (globeRef.current) {
            globeRef.current.controls().autoRotate = true;
            globeRef.current.controls().autoRotateSpeed = 0.5;
            globeRef.current.controls().enableZoom = true;
        }
    }, []);

    useEffect(() => {
        if (focusRegion && globeRef.current) {
            globeRef.current.pointOfView({ 
                lat: focusRegion.lat, 
                lng: focusRegion.lng, 
                altitude: focusRegion.altitude || 1.2 
            }, 1000);
        }
    }, [focusRegion]);

    const handlePointClick = (point) => {
        if (setProps) {
            setProps({ clickedPoint: point });
        }
        if (globeRef.current) {
            globeRef.current.pointOfView({ lat: point.lat, lng: point.lng, altitude: 0.8 }, 800);
        }
    };

    return (
        <div id={id} style={{ width: width || '100%', height: height || '100%' }}>
            <Globe
                ref={globeRef}
                globeImageUrl={globeImageUrl || '//unpkg.com/three-globe/example/img/earth-blue-marble.jpg'}
                backgroundColor="rgba(255,255,255,0)"
                atmosphereColor="#e6f2ff"
                atmosphereAltitude={0.15}
                pointsData={pointsData}
                pointLabel="site_name"
                pointColor="color"
                pointRadius="size"
                pointAltitude={0.02}
                onPointClick={handlePointClick}
                width={width}
                height={height}
            />
        </div>
    );
};

DashGlobe.defaultProps = {
    pointsData: [],
    focusRegion: null,
    clickedPoint: null,
    globeImageUrl: '//unpkg.com/three-globe/example/img/earth-blue-marble.jpg',
    width: 800,
    height: 600
};

DashGlobe.propTypes = {
    id: PropTypes.string,
    setProps: PropTypes.func,
    pointsData: PropTypes.array,
    focusRegion: PropTypes.object,
    clickedPoint: PropTypes.object,
    globeImageUrl: PropTypes.string,
    width: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    height: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
};

export default DashGlobe;
```

### 1.3 Paketi Derleme (NPM Build)
Python ile köprü kuracak olan `dash_globe_component` Python kütüphanesini üretmek için terminalde (aynı klasör içinde):
```bash
npm run build
pip install -e .
```

---

## 2. PYTHON EKRANI ENTEGRASYONU (`global_view.py` DEĞİŞİKLİKLERİ)

Ana dizinden `src/pages/global_view.py` dosyasını aç. Aşağıdaki eksiksiz operasyonları sağla.

### 2.1 Veri Hazırlayıcı Fonksiyonu Refactor Et
Eski `_build_map_dataframe` DataFrame dönüyordu. Bunu SİL ve yerine native dictionary dönen YENİ veri fonksiyonunu koy:
```python
def _build_globe_data(summaries):
    data = []
    for dc in summaries:
        lat = dc.get("lat")
        lng = dc.get("lon")
        cpu_u = dc.get("cpu_used", 0)
        cpu_c = dc.get("cpu_cap", 1) or 1
        cpu_pct = cpu_u / cpu_c
        ram_u = dc.get("ram_used", 0)
        ram_c = dc.get("ram_cap", 1) or 1
        ram_pct = ram_u / ram_c

        health = (cpu_pct + ram_pct) / 2
        
        # Gece teması olmadığı için açık/prestijli renkler!
        color = "#ff4d4f" if health >= 0.7 else ("#ffba00" if health >= 0.4 else "#00e676")
        
        if lat and lng:
            data.append({
                "lat": float(lat),
                "lng": float(lng),
                "dc_id": dc.get("id"),
                "size": 0.05,
                "color": color,
                "site_name": dc.get("site_name", "")
            })
    return data
```

### 2.2 Plotly'i Yok Et ve Custom Componenti Ekle
Sayfanın en üstünde yeni kütüphanemizi import et:
```python
import dash_globe_component
```

Sayfa `layout()` fonksiyonunun içinde yer alan, haritayı basan `dcc.Graph(id="global-map-graph", figure=map_fig, ...)` bloğunu **TAMAMEN SİL**. (Yer tutucu figür kodlarını vs de temizle).
Bunun yerine o bloğa şunu yerleştir:
```python
        globe_data_array = _build_globe_data(summaries)
        
        # Harita divinin içine yerleşecek
        html.Div(
            style={"position": "relative", "width": "100%", "height": "600px", "overflow": "hidden", "borderRadius": "12px", "background": "transparent"},
            children=[
                dash_globe_component.DashGlobe(
                    id="global-map-graph",
                    pointsData=globe_data_array,
                    focusRegion=None,
                    width="100%",
                    height=600
                ),
            ]
        ),
```

---

## 3. CALLBACK ZİNCİRİNİ YENİDEN BAĞLAMA (`app.py` DEĞİŞİKLİKLERİ)

Orijinal Plotly `clickData` yapısı `DashGlobe.clickedPoint` prop'una dönüştüğü için `app.py` üzerinde aşağıdaki amansız köklü değişiklikleri yapmalısın.

### 3.1 GEREKSİZ Clientside JS Callbacklerini SİL (Zoom Yapısı İptal)
`app.py` içerisinde "Kamerayı Döndürmek (Fly-to) için Plotly'e yazılan" `app.clientside_callback(...)` şeklindeki kamera animasyon javascriptini SİL. (Çünkü DashGlobe bunu prop aracılığıyla `useEffect` içinde doğal olarak çözmektedir).

### 3.2 Menü Seçiminden Kameraya Odak (Yeni Callback Ekleyeceksin)
Yine `app.py` içine şu tamamen YENİ React-globe tetikleyicisini ekle:
```python
@app.callback(
    dash.Output("global-map-graph", "focusRegion"),
    dash.Input("selected-region-store", "data"),
    dash.State("app-time-range", "data"),
    prevent_initial_call=True
)
def update_globe_camera(region, time_range):
    if not region:
        return dash.no_update
        
    from src.services import api_client as api
    from src.queries.default_dates import default_time_range
    tr = time_range or default_time_range()
    summaries = api.get_all_datacenters_summary(tr)
    
    region_upper = region.upper().strip()
    dcs = [dc for dc in summaries if (dc.get("site_name") or "").upper().strip() == region_upper]
    
    if not dcs:
        return dash.no_update
        
    # Regiondaki ilk DC'yi merkez al
    target_dc = dcs[0]
    lat = target_dc.get("lat")
    lng = target_dc.get("lon")
    if lat is not None and lng is not None:
        return {"lat": float(lat), "lng": float(lng), "altitude": 1.2}
        
    return dash.no_update
```

### 3.3 Pin Tıklama Panelinin (Info-card) React'e Uyarlanması
Eski `update_global_detail_from_pin` callback'i, Plotly'nin karmaşık `customdata` objesinden parse ediyordu. Şimdi React direkt temiz JSON iletiyor. Callbacki aşağıdaki gibi **DİREKT DEĞİŞTİR**:

```python
@app.callback(
    dash.Output("global-detail-panel", "children"),
    dash.Input("global-map-graph", "clickedPoint"),
    dash.State("app-time-range", "data"),
    prevent_initial_call=True,
)
def update_global_detail_from_pin(clicked_point, time_range):
    if not clicked_point:
        return []

    dc_id = clicked_point.get("dc_id")
    site_name = clicked_point.get("site_name", "")
    
    if not dc_id:
        return []
        
    from src.queries.default_dates import default_time_range
    tr = time_range or default_time_range()
    
    from src.pages.global_view import build_dc_info_card
    return build_dc_info_card(dc_id, tr, site_name=site_name)
```

---

## SON UYARI

> [!CAUTION] SIFIR HATALI KOPYALAMA
> Executer! Bu plan eksiksiz bir mimari direktiftir. Yukarıdaki kodları, belirtilen hedeflere KELİMESİ KELİMESİNE taşıyacaksın. Gereksiz bir `#` işareti veya Plotly kırıntısı projeyi çökertebilir. Gece temasından (Dark Mode) kesinlikle kaçın ve `atmosphereColor="#e6f2ff"` parametresinin o güzel aydınlık hissiyatına dokunma!
