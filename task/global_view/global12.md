# FAZ 8.0 (REVİZYON 2): Floor Map — Premium Light Tema, Ana Ekran

## Konsept Değişikliği

**Önceki (KÖTÜ):** Koyu mavi, yeşil scanner çizgisi, siber güvenlik estetiği, ayrı tam ekran.
**Yeni (DOĞRU):** Sunbird dcTrack referansı — açık tema, temiz grid, ana sayfayla entegre, premium sade.

---

## Kullanıcı Akışı

```
Globe (DC pinleri)
    │
    ▼ [DC pinine 1. tıklama]
DC Info Kartı görünür (sağ panel) + globe yaklaşır
    │
    ▼ [Aynı DC pinine 2. tıklama]
Floor Map doğrudan açılır — aynı sayfa içinde, temiz fade animasyonu
    │
    ▼ [← Geri butonu]
Globe'a dön
```

**Ara bina animasyon ekranı YOK.** Geçiş 300ms CSS opacity/scale fade.

---

## 2. Katman Mimarisi

```
html.Div(id="globe-layer")       ← Mevcut globe + sağ panel
html.Div(id="floor-map-layer")   ← Floor map (display:none → block, fade-in animasyonu)
```

`building-blueprint-layer` → **komple kaldırıldı**
`blueprint-scan-timer` → **kaldırıldı**
`blueprint-dc-label` → **kaldırıldı**

---

## 3. Floor Map Tasarımı (Sunbird Referansı)

### Renk Paleti
- Arka plan: `#F4F7FE` (açık mavi-gri, Sunbird tarzı)
- Hall kutuları: beyaz kart, ince border
- Active rack: `#05CD99` (teal, dolu)
- Inactive: `#FF4D4F` (kırmızı)
- Planned: `#4385F4` (mavi)

### Layout
```
┌─────────────────────────────────────────────┐
│ ← DC13   Floor Map — Rack Layout   78 Active│
├─────────────────────────────────────────────┤
│ ┌─ DH4 ──┐  ┌─ DH5 ──┐  ┌─ DH7 ──────────┐│
│ │ ■■■■   │  │ ■      │  │ ■■■■■■■■■■     ││
│ │ ───────│  │ ───────│  │ ───────────    ││
│ │ ■■■■■■ │  │ ■■■■■■ │  │ ■■■■■■■■■■     ││
│ └────────┘  └────────┘  └────────────────┘│
├─────────────────────────────────────────────┤
│  Sağda: seçilen rack detayı                 │
└─────────────────────────────────────────────┘
```

### Plotly Figure Ayarları
- `plot_bgcolor`: `rgba(0,0,0,0)` (şeffaf, kart arka planı CSS'den gelir)
- `paper_bgcolor`: `rgba(0,0,0,0)`
- Hall kutuları: beyaz `rgba(255,255,255,1)` fill, açık gri border
- Aisle çizgisi: `rgba(163,174,208,0.3)` noktalı çizgi
- Rack hover: beyaz tooltip, temiz tipografi

---

## 4. CSS Animasyonu

```css
@keyframes floorMapEnter {
    from { opacity: 0; transform: translateY(12px) scale(0.98); }
    to   { opacity: 1; transform: translateY(0) scale(1.0); }
}
.floor-map-layer-animate {
    animation: floorMapEnter 0.35s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}
```

**Kaldırılacak CSS:**
- `.blueprint-grid-bg`
- `.blueprint-building-container`, `.blueprint-building-icon`, `@keyframes buildingReveal`, `@keyframes buildingGlow`
- `.blueprint-dc-title`
- `.blueprint-scan-text`, `@keyframes blink-pulse`
- `.glass-progress-bar`
- `.cyber-scanner-line`, `@keyframes scan`

---

## 5. Callback Değişiklikleri (app.py)

### Kaldırılacaklar
- `view_controller` → blueprint case kaldırılır, sadece `globe` / `floor_map`
- `advance_to_floor_map` → **silinir** (blueprint timer yok)
- `blueprint-scan-timer` referansları → **silinir**

### Güncellenecek: `detect_second_click_drilldown`
```python
Output: current-view-mode.data → "floor_map"  (direkt, blueprint yok)
Output: floor-map-layer.children → build_floor_map_layout(...)  (YENİ output)
```

### Güncellenecek: `view_controller`
```python
if mode == "floor_map": return hidden, shown, ...
return shown, hidden, ...   (blueprint state yok)
```

---

## CTO Constraint Check
- Sıfır yorum satırı
- Siber güvenlik estetik → yok
- Açık tema, Sunbird referansı
- Tek tıkla doğrudan floor map (ara ekran yok)
