# TASK-11 — DC View Network Sayfası Performans Optimizasyonu

**Tip:** Performans / UX · **Efor:** M · **Öncelik:** Orta-Yüksek

## Hedef
DC view network sayfasında donmalar yaşanıyor. Arayüz performansı artırılacak ve bekleme anları için
**loading animasyonu** eklenecek.

## Mevcut durum

`src/pages/dc_view.py` **6068 satır** — network bölümü ~2597-3300 arası:

```python
NETWORK_TOP_SCOPES = ["overview", "switch", "router_uplink", "firewall", "load_balancer"]
_build_network_zabbix_section(...)     # ~3210
_build_network_interface_page(...)     # ~2802
_build_network_firewall_page(...)      # ~3089
_build_network_load_balancer_page(...) # ~3157
_network_page_flags / _network_kpi_labels / _network_interface_table_columns ...
```

Beslendiği endpoint'ler (`services/datacenter-api/app/routers/datacenters.py`):
```
/datacenters/{dc}/network/filters            /network/port-summary
/datacenters/{dc}/network/95th-percentile     /network/interface-table
/datacenters/{dc}/network/interface-export    /network/firewall-summary
/datacenters/{dc}/network/load-balancer-summary
```

SQL: `services/datacenter-api/app/db/queries/zabbix_network.py`
— TimescaleDB `time_bucket` (1 saat) ile downsampling var, "latest per `loki_id`" ile çift sayım engelleniyor.

**Tablo ailesi (rol bazlı, bkz. datalake-platform-knowledge-base/raw/zabbix-network-role-based-collector-2026-06-10.md):**
`raw_zabbix_network_interface_metrics_v` (birleşik view — sorguların çoğu bunu kullanır),
`raw_zabbix_network_backbone_interface_metrics`, `_leaf_`, `_spine_`, `_switch_shared_`,
`_management_`, `_router_uplink_metrics`, `_firewall_metrics`, `_device_health_metrics`.
Scope→tablo seçimi `zabbix_network.py :: build_interface_95th_percentile_sql(scope)` içinde.

## Donma nedenleri — sıralı şüpheli listesi

1. **Tek callback'te tüm scope'lar** — sekme değişiminde hepsi yeniden hesaplanıyor
2. **Interface tablosu sayfalama yok** — binlerce port satırı tek `dash_table`'a basılıyor (tarayıcı kilidi)
3. **30d aralığında 95p sorgusu** — `time_bucket` olsa da geniş pencerede ağır
4. **Loading state yok** — kullanıcı "dondu" sanıyor (aslında bekliyor)
5. **Server-side hesap frontend'de** — Python'da pandas dönüşümü callback içinde
6. **Cache yok/kısa** — network endpoint'leri `dl:fecache:*` katmanını kullanıyor mu doğrulanmalı

## Yapılacaklar

### Ölçüm (önce)
- [ ] Chrome DevTools Performance: sekme geçişi ve ilk yükte main-thread bloğu (ms)
- [ ] `curl -w "%{time_total}"` ile her endpoint'in soğuk/sıcak süresi
- [ ] Payload boyutu (`interface-table` kaç satır, kaç KB)
- [ ] Grafana Faro RUM verisi varsa gerçek kullanıcı süreleri (`docs/FARO_FRONTEND.md`)

### Backend
- [ ] `interface-table`'a **server-side pagination + sıralama + filtre** ekle (`limit`, `offset`, `sort`, `q`)
- [ ] 95p sorgusunu pencere büyüklüğüne göre bucket'la (1d→5dk, 7d→1sa, 30d→6sa)
- [ ] Network endpoint'lerini Redis cache'e bağla; TTL ≥ 4× refresh, `last_good` shadow key
- [ ] Ağır kolonları (per-interface trend) ayrı endpoint'e taşı — tablo ilk yükte trend çekmesin

### Frontend
- [ ] Sekme başına **lazy render**: yalnızca aktif scope'un içeriği oluşturulsun
- [ ] `dash_table` → `page_action="custom"` + `virtualization=True`
- [ ] Skeleton/loading: `docs/LOADING_UX_DESIGN.md` standardı —
      panel bazlı `dcc.Loading` (tek widget) + tam sayfa için iki fazlı shell + skeleton
- [ ] `dcc.Store` ile ham veriyi tarayıcıda tutup filtreyi client-side yapmak yerine
      server-side'a taşı (payload küçülür)
- [ ] `prevent_initial_call` ve `State` kullanımıyla gereksiz callback tetiklemelerini kes

## Doğrulama

```bash
DC=DC13; BASE=http://10.134.52.250:8000/api/v1/datacenters/$DC/network
for ep in filters port-summary 95th-percentile interface-table firewall-summary load-balancer-summary; do
  printf "%-24s " "$ep"
  curl -s -o /tmp/$ep.json -w "%{time_total}s %{size_download}B\n" "$BASE/$ep?range=30d"
done
python3 -c "
import json;d=json.load(open('/tmp/interface-table.json'))
rows=d.get('rows') or d.get('data') or []
print('interface satır sayısı:', len(rows))
"
```

```sql
-- Zabbix network veri hacmi (yükün kaynağı)
SELECT COUNT(*) AS satir,
       COUNT(DISTINCT loki_id) AS cihaz,
       MIN(collection_timestamp) AS ilk, MAX(collection_timestamp) AS son
FROM   public.raw_zabbix_network_interface_metrics_v
WHERE  collection_timestamp > now() - interval '30 days';

-- En ağır DC hangisi
SELECT loki_id, COUNT(*) FROM public.raw_zabbix_network_interface_metrics_v
WHERE collection_timestamp > now() - interval '7 days'
GROUP BY 1 ORDER BY 2 DESC LIMIT 20;

-- TimescaleDB hypertable mı, chunk'lar sağlıklı mı
SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name ILIKE '%zabbix_network%';
```

## Kabul kriterleri
- [ ] Sekme geçişinde main-thread bloğu **< 200 ms**
- [ ] `interface-table` ilk yük payload'ı **< 500 KB** (sayfalama devrede)
- [ ] Tüm network endpoint'leri sıcak cache'te p95 **< 800 ms**
- [ ] Her bekleme anında görsel geri bildirim var (skeleton veya panel spinner) — beyaz ekran yok
- [ ] 30d aralığında sayfa donmuyor (manuel test + Faro/DevTools kanıtı)
- [ ] Gösterilen sayılar optimizasyon öncesiyle aynı (regresyon testi)

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, docs/FRONTEND_PERFORMANCE.md,
docs/LOADING_UX_DESIGN.md, task/frontend-perf-optimization/*, task/query-map/08-zabbix-monitoring.md,
src/pages/dc_view.py (satır ~2597-3300 network bölümü), src/pages/dc_view_callbacks.py,
services/datacenter-api/app/db/queries/zabbix_network.py,
services/datacenter-api/app/routers/datacenters.py (network endpoint'leri)

Görev: DC View Network sayfasındaki donmaları gider ve loading animasyonu ekle.

1. ÖLÇ önce: 6 network endpoint'i için süre ve payload boyutu; interface-table satır sayısı.
   Ölçüm tablosunu raporla. Ölçmeden optimize etme.
2. Backend:
   - /network/interface-table'a server-side pagination (limit, offset, sort_by, sort_dir, q) ekle.
     Geriye dönük uyumluluk: parametre verilmezse mevcut davranış (ama üst limit koy).
   - 95th-percentile sorgusunda time_bucket aralığını pencereye göre seç (1d=5m, 7d=1h, 30d=6h).
   - Network endpoint'lerini mevcut cache_backend'e bağla; TTL 3600, {key}:last_good shadow key.
3. Frontend (dc_view.py):
   - Sekme başına lazy render: yalnızca aktif NETWORK_TOP_SCOPES elemanı build edilsin.
   - dash_table: page_action="custom" + virtualization=True, sunucudan sayfa çek.
   - Loading: docs/LOADING_UX_DESIGN.md §2'ye göre - tek panel yenilenmesinde dcc.Loading,
     tam sayfa geçişinde iki fazlı shell + dmc.Skeleton. Yeni pattern icat etme.
   - Gereksiz callback tetiklemelerini prevent_initial_call ve State ile kes.
4. Regresyon: optimizasyon öncesi/sonrası KPI ve tablo toplamlarını karşılaştıran test yaz.
5. Sonuç raporunda önce/sonra ölçüm tablosu ver.

Kısıt: Gösterilen sayılar değişmemeli. dc_view.py 6000+ satır - network bölümünü ayrı modüle
çıkarmayı değerlendir (src/pages/dc_view_network.py) ama davranışı bozma.
```

## İlgili
TASK-14 aynı endpoint ailesini (network billing / 95p) kullanıyor — **birlikte test edin**.
