# Backend Brief — Rack (Kolokasyon) Satılabilir Tarafı

**Kime:** Backend / crm-engine ekibi
**Konu:** Fiziksel rack'ler için "satılabilir" (kolokasyon boş-U) kapasitesini crm-engine'e bağlama
**Bağlam:** Floor Map'te rack'leri U-doluluğa göre renklendirdik (frontend, ayrı iş — `feat/floor-map-rack-fill-coloring`). Renk zaten *görsel* satılabilirliği gösteriyor (boş=satılacak yer var → yeşil, dolu → kırmızı). Ama **sayısal/TL "satılabilir" değeri** yok. Bu brief onu nasıl bağlayacağımızı özetliyor.

## 1. Sorun

Rack tarafında "satılabilir" kavramı **hesaplanmıyor**. Virtualization sellable (vCPU/RAM/Storage) var ama kolokasyon (rack U / kabinet) sellable'ı yok.

## 2. Kritik bulgu — panel ZATEN tanımlı, sadece bağlı değil

İki kolokasyon paneli migration'da **zaten tanımlı**:

| panel_key | label | family | resource_kind | display_unit |
|---|---|---|---|---|
| `dc_hosting_u` | DC Barındırma — U | dc_hosting | other | U |
| `dc_hosting_kabinet` | DC Barındırma — Kabinet | dc_hosting | other | Adet |

Kaynak: `services/customer-api/migrations/webui/006_seed_panel_definitions.sql`

**Ama `007_seed_panel_infra_sources.sql`'de infra source'ları YOK** → SellableService bu paneller için **0** hesaplıyor. Yani "bağlama" işi = bu panelin infra source'unu yapılandırmak; yeni bir hesap motoru yazmaya gerek yok.

## 3. Önerilen yapılandırma (dc_hosting_u — MVP)

Mevcut sellable formülü aynen çalışır: `sellable = max(total × eşik% − allocated, 0)` + utilization gate.

- **Total (kapasite):** `discovery_loki_rack.u_height` toplamı (DC bazında)
- **Allocated (kullanılan):** rack'lerdeki cihazların `device_type.u_height` toplamı (dolu U)
- **Filter:** `site_name ILIKE :dc_pattern`
- **Eşik:** %80 (`gui_crm_sellable_potential_threshold_config`, konfigüre edilebilir)
- **Ratio constraint:** YOK (resource_kind='other' → CPU/RAM/Storage coupling yok, standalone)
- **Fiyat:** TL/U (`gui_crm_price_override` veya katalog)

Sonuç: `sellable_u = max(total_u × 0.80 − used_u, 0)`, `potential_tl = sellable_u × TL/U`. crm-engine bunu `dc_hosting` family'si olarak otomatik yayınlar (virt_* aileleri gibi).

Referans hesap: `shared/sellable/computation.py` (apply_threshold / apply_utilization_gate), `services/customer-api/app/services/sellable_service.py`.

## 4. Veri durumu

| Veri | Durum |
|---|---|
| Toplam rack U (`discovery_loki_rack.u_height`) | ✅ var |
| Dolu U (`device_type.u_height` toplamı) | ✅ var (`crm_potential.py:136-144` dc_rack_capacity CTE zaten hesaplıyor) |
| Boş U = fark | ✅ türetilir |
| Güç kapasitesi (`kabin_enerji`) | ⚠️ **STRING** ("12 kW") — sayısal değil, parse gerekir |
| Cihaz başına güç çekişi | ❌ yok (PDU metering / tahmin gerekir) |

**Sonuç:** U-bazlı kolokasyon sellable **hemen yapılabilir**. Güç-bazlı sellable (Faz 2) `kabin_enerji`'yi sayısala çevirmeyi + güç çekiş takibini gerektirir → ayrı iş.

## 5. Frontend'in ricası — verimlilik için toplu endpoint

Floor Map renklendirme şu an **her rack için ayrı** `get_rack_devices` çağırıyor (~78 rack = 78 çağrı, paralel + cache'li). Backend bir **toplu per-rack doluluk endpoint'i** verirse (ör. `GET /datacenters/{dc}/racks/occupancy` → `[{rack_name, occupied_u, u_height}]`) floor map tek çağrıyla renklenir. Opsiyonel ama floor map'i belirgin hızlandırır.

## 6. Frontend'in bu turda yaptığı (bilgi)

- Rack'ler U-doluluğa göre renkleniyor: boş/kapalı→mavi, <%50→yeşil (satılabilir alan var), %50-80→turuncu, >%80→kırmızı.
- Hover popup: "Doluluk: 35/47U (%74)", "Boş (satılabilir): 12U", durum etiketi.
- İki-fazlı: önce status-renkli anında çizer, cihaz verisi gelince doluluğa göre yeniden renklendirir.

Bu görsel taraf, dc_hosting_u bağlanınca DC-seviyesi TL sellable ile tamamlanır (sellable dashboard + floor map hover'a TL eklenebilir).

## Özet / aksiyon

1. `dc_hosting_u` paneli için `007`-tarzı infra source ekle (total=rack u_height, allocated=device u_height, eşik %80).
2. TL/U fiyatı gir.
3. (Opsiyonel) Toplu per-rack doluluk endpoint'i ekle.

→ crm-engine kolokasyon sellable'ı otomatik hesaplar, mevcut sellable pipeline'ına girer.
