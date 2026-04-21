# Executor Prompt: DC Liste Kartları — Donut Görünümü + Üst Şerit Renk Birliği

> **Hedef okuyucu:** Kodu değiştirecek agent / geliştirici.  
> **Kapsam:** `src/pages/datacenters.py` + `assets/style.css` (gerekirse çok küçük yardımcı).  
> **Kural:** API sözleşmesi ve veri anlamı değişmesin; yalnızca görselleştirme ve stil. Yeni endpoint veya yeni alan **gerekmeden** mevcut `dc` / `stats` alanlarıyla çalış.

---

## 0. Referans görseller (workspace)

1. **Hedef kart görünümü (referans):**  
   `assets/composer-annotation-384e5725-bcc6-4f1a-b681-a8dfbe87555f.png`  
   - Üstte ince **yeşil** accent çizgi.  
   - Orta bölüm: solda metrik satırları; sağda **çift halkalı** donut: dış turuncu/amber (IBM power payı), iç indigo/mor (CPU kullanımı), merkezde büyük **%** + **IBM**, altında **Power** + **kW**.  
   - Altta CPU / RAM ince progress bar’lar.

2. **Konsept çizim (nested / çok dilimli güç):**  
   `assets/IMG_0907-c4ed28a6-3573-41e0-a00b-ea39bae12cbd.png`  
   - İç daire + dış halkada **birden fazla dilim** (rakamlar örnek: 36, 18, 64; toplam vurgu **128 kW**).  
   - Amaç: “tek IBM yüzdesi”den ziyade **güç dağılımını** halkada okunur kılmak (mevcut veriyle mümkün olduğu kadar).

---

## 1. Problem özeti

| # | İstenen |
|---|--------|
| A | Bazı kartlarda üst accent **yeşil**, bazılarında **gri** (ve SLA’ya göre turuncu/kırmızı). Kullanıcı **tüm kartlarda üst şeridin aynı renk** (referanstaki yeşil / marka yeşili) olmasını istiyor. |
| B | Donut / ring alanı referans görseldeki gibi **çift halka + merkez tipografi + Power satırı**; mümkünse çizime yakın **çok dilimli dış halka** (veri: `ibm_kw`, `total_energy_kw`, türetilen “geri kalan güç”). |

---

## 2. Mevcut kod (bilmen gereken yerler)

- **Kart:** `src/pages/datacenters.py` → `_dc_vault_card(dc, sla_entry=None)`  
  - `stats`: `ibm_kw`, `total_energy_kw`, `used_cpu_pct`, `used_ram_pct`  
  - `power_ratio = ibm_kw / total_kw * 100` (total 0 ise 0)  
  - Şu an: `dmc.RingProgress` × 2 (dış IBM %, iç CPU %), `accent_class` = `dc-accent-healthy|moderate|high|idle` → CSS’te **üst border** rengi.

- **Üst şerit CSS:** `assets/style.css` → `.dc-accent-healthy`, `.dc-accent-moderate`, `.dc-accent-high`, `.dc-accent-idle` (kart `className` ile birleşiyor).

- **SLA pulse:** Aynı dosyada `pulse_class` (`dc-pulse-dot-ok|warn|critical`) — **bunu koru** veya kullanıcı “sadece üst çizgi birleşsin” dediyse pulse’u olduğu gibi bırak.

---

## 3. Görev A — Üst accent rengini birleştir

**İstenen davranış:** Tüm DC vault kartlarında üstteki 3px accent **aynı renk** (referans: `#05CD99` veya tasarım token’ı ile aynı yeşil).

**Uygulama seçenekleri (birini seç, tutarlı ol):**

1. **En basit:** `_dc_vault_card` içinde `accent_class`’ı her zaman `dc-accent-healthy` yap (veya yeni tek class `dc-accent-brand`). SLA/total_kw için `pulse_class` ve gerekirse başka görsel sinyaller kalsın.  
2. **Alternatif:** `dc-accent-moderate|high|idle` sınıflarından **sadece `border-top` kaldır**; yerine sabit yeşil için `::before` veya tek `.dc-vault-card-accent-unified` kuralı yaz.

**Kabul kriteri:** Grid’de ardışık kartlarda üst çizgi rengi **gözle tek ton**; gri üst şerit **kalmamalı** (idle DC’ler için bile aynı yeşil isteniyorsa ona göre).

---

## 4. Görev B — Donut / ring görünümü

### 4.1 Minimum (referans PNG ile birebir)

- **Çift halka korunacak:**  
  - Dış: IBM güç oranı (`power_ratio` / `remaining`). Renk: amber `#FFB547` + track `rgba(67,24,255,0.10)`.  
  - İç: CPU (`cpu_pct`). Renk: `#4318FF` + track `rgba(67,24,255,0.07)`.  
- **Merkez:** Büyük yüzde = IBM oranı (`power_ratio`), alt satır **IBM** (küçük, gri).  
- **Alt yazı:** **Power** + `{total_kw:.1f} kW` (mevcut gibi).  
- **Boyut / kalınlık:** Referanstaki oranlara yakın (ör. dış ~116–128px, thickness dış 11–14, iç biraz daha ince); piksel değerlerini tek seferde sabitle, tüm kartlarda aynı olsun.

### 4.2 İsteğe bağlı geliştirme (beyaz tahta — veriyle mümkün olduğu kadar)

Mevcut alanlarla anlamlı bir **dış halka çok dilim** önerisi (API değişmeden):

- `total_kw = total_energy_kw`  
- `ibm_kw`  
- `other_kw = max(0, total_kw - ibm_kw)`  

Dış halkayı **iki dilim** olarak göster: IBM payı, diğeri (track veya ikinci renk). Merkezde hâlâ toplam gücün yüzdesi veya **128 kW** benzeri olarak `f"{total_kw:.1f} kW"` metni ring altında kalabilir; çizimdeki 36/18/64 gibi sayılar **gerçek kW değerleri** değilse etiketleri “IBM kW” / “Other kW” gibi açık yaz.

**Plotly `go.Pie` ile nested donut** Mantine `RingProgress` yerine kullanılabilir — ama kart içi layout ve yükseklik sabit kalmalı. Eğer Plotly kullanırsan: `paper_bgcolor` şeffaf, `margin` sıkı, `height` sabit (~160–200px), legend minimal veya yok.

**Kabul kriteri:**  
- Görsel olarak referans PNG’ye yakın “premium” çift halka.  
- Beyaz tahtadaki gibi tam üç rastgele sayı **zorunlu değil**; veri yoksa iki dilim yeter.  
- CPU/RAM footer bar’ları **korunmalı** (kullanıcı aynı sayfada bunları da kullanıyor).

---

## 5. Test checklist

- [ ] `/datacenters` aç: en az 6 kart; **hepsinde üst accent aynı renk**.  
- [ ] Uzun DC adı olan kartta **Details** hâlâ sağ üstte (mümkünse `dc_5.md` truncation planı ile uyumlu).  
- [ ] `total_kw == 0` olan DC: ring boş/0 gösterimi bozulmamalı; accent yine birleşik renk (ürün kararı).  
- [ ] SLA düşük olan DC: pulse rengi değişebilir ama **üst çizgi** yine birleşik (A görevi).  
- [ ] Regresyon: export butonları, summary strip, aurora arka plan, stagger animasyonlar çalışır.

---

## 6. Bilinçli olarak dokunma (scope dışı)

- `dc_view.py`, `global_view.py`, backend `dc_service` — **bu prompt kapsamında değil** (sadece liste kartı).  
- `permission_catalog` — değişiklik gerekmez.

---

## 7. Özet cümle (executor’a kopyala)

**Türkçe tek paragraf:**  
`datacenters.py` içindeki `_dc_vault_card` ve `assets/style.css` içindeki `.dc-accent-*` kurallarını güncelle: (1) Tüm DC kartlarında üstteki accent çizgisini referanstaki gibi **tek ve aynı yeşil tonda** birleştir; SLA için pulse/dot ayrı kalsın. (2) Sağdaki güç görselini referans PNG’deki gibi **çift halkalı donut** olarak koru veya iyileştir; mümkünse `total_energy_kw` / `ibm_kw` / kalan ile dış halkada **çok dilimli** dağılım göster; merkezde IBM %, altında Power kW; alttaki CPU/RAM bar’ları koru. API ve callback mantığına dokunma.

---

## 8. Dosya listesi (PR açıklaması için)

| Dosya | Beklenen değişiklik |
|-------|---------------------|
| `src/pages/datacenters.py` | `accent_class` mantığı ve/veya ring bileşeni (Plotly opsiyonel) |
| `assets/style.css` | Birleşik accent; gerekirse ring container hizası |

**Bitti tanımı:** Kullanıcının gönderdiği iki görseldeki beklenti karşılanır; üst şerit rengi tüm kartlarda tutarlıdır; donut referansla uyumludur.
