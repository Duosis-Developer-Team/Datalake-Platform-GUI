# Zabbix Monitoring Sorguları ve Hesaplamaları

> Kaynak dosyalar:
> - `services/datacenter-api/app/db/queries/zabbix_network.py`
> - `services/datacenter-api/app/db/queries/zabbix_storage.py`
> - `services/datacenter-api/app/services/dc_service.py` (sorguları çağıran servis metotları)
> - `services/datacenter-api/app/routers/datacenters.py` (HTTP endpoint'leri)
> - `src/pages/dc_view.py`, `src/services/api_client.py` (Dash UI tarafı)
>
> Cross-reference: [README](README.md), [04-ibm-storage-san.md](04-ibm-storage-san.md)

---

## Genel Bakış

Bu doküman, Zabbix'ten toplanan **network device/interface** ve **storage device/disk**
metriklerini sorgulayan SQL'leri ve bunların üzerine kurulan servis hesaplamalarını belgeler.

İki ayrı izleme alanı vardır:

- **Network izleme** (Zabbix Network) — switch/router benzeri network cihazlarının port
  sayıları, ICMP kaybı ve interface bant genişliği (95. persentil).
- **Storage izleme** (Zabbix Intel Storage) — depolama cihazlarının kapasitesi (total/used/free)
  ve disk seviyesinde IOPS / latency / sıcaklık / health durumu.

**Aktif kullanım durumu (dürüst not):** Bu sorgular UI'da **aktif olarak kullanılıyor**.
DC View ekranında iki ayrı alt sekme (subtab) bu verilerle beslenir:
- `_build_network_dashboard_subtab(...)` → **Network Dashboard** alt sekmesi
  (port KPI'ları, Top-N 95. persentil bar grafiği, interface bant genişliği tablosu).
- `_build_intel_storage_subtab(...)` → **Intel Storage** alt sekmesi
  (kapasite kartı, kapasite trendi; ek olarak disk-list / disk-trend / disk-health endpoint'leri).

Tüm sorgular DC bazlıdır (DC-scoped). DC kapsamı, NetBox envanteri üzerinden çözümlenir:
`zabbix_*_device_metrics.loki_id` (text) → `discovery_netbox_inventory_device.id` (int8),
ardından NetBox lokasyon/site/ad alanları `public.loki_locations` ile eşleştirilip üst DC adı
çıkarılır (diğer DC eşlemeleriyle aynı yaklaşım).

---

## Veri Kaynakları

Toplam 4 Zabbix tablosu kullanılır (hepsi `public` şemasında):

### 1. `public.zabbix_network_device_metrics`
Network cihazı (host) bazlı snapshot'lar. Kullanılan kolonlar:

| Kolon | Açıklama |
|---|---|
| `loki_id` | NetBox device id (text; `'^[0-9]+$'` regex'i ile sayısal olanlar filtrelenir) |
| `host` | Zabbix host adı |
| `total_ports_count` | Cihazdaki toplam port sayısı |
| `active_ports_count` | Aktif port sayısı |
| `icmp_loss_pct` | ICMP paket kaybı yüzdesi |
| `icmp_status` | ICMP durum alanı (yalnızca `IS NOT NULL` satırlar alınır) |
| `collection_timestamp` | Ölçüm zaman damgası (latest-per-loki_id ve zaman aralığı filtresi için) |

### 2. `public.zabbix_network_interface_metrics`
Cihaz interface'leri bazlı snapshot'lar. Kullanılan kolonlar:

| Kolon | Açıklama |
|---|---|
| `host` | Zabbix host adı (cihaza bağlama için) |
| `interface_name` | Interface adı |
| `interface_alias` | Interface alias (NULL olabilir; `COALESCE(..., '')` ile dedup'ta normalize edilir) |
| `operational_status` | Interface operasyonel durumu |
| `speed` | Interface hızı (bps) |
| `bits_received` | Alınan bit/sn (rx) |
| `bits_sent` | Gönderilen bit/sn (tx) |
| `collection_timestamp` | Ölçüm zaman damgası |
| `id` | Dedup için tie-breaker (`... DESC`) |

### 3. `public.zabbix_storage_device_metrics`
Depolama cihazı bazlı kapasite snapshot'ları. Kullanılan kolonlar:

| Kolon | Açıklama |
|---|---|
| `loki_id` | NetBox device id (text; sayısal regex filtresi) |
| `host` | Zabbix host adı |
| `total_capacity_bytes` | Toplam kapasite (byte) |
| `used_capacity_bytes` | Kullanılan kapasite (byte) |
| `free_capacity_bytes` | Boş kapasite (byte) |
| `health_status` | Cihaz health durumu (yalnızca `IS NOT NULL`) |
| `collection_timestamp` | Ölçüm zaman damgası |

### 4. `public.zabbix_storage_disk_metrics`
Disk seviyesi performans/health snapshot'ları. Kullanılan kolonlar:

| Kolon | Açıklama |
|---|---|
| `host` | Bağlı olduğu storage host'u |
| `disk_name` | Disk adı |
| `total_iops` | Toplam IOPS |
| `latency_ms` | Gecikme (ms) |
| `temperature_c` | Sıcaklık (°C) |
| `total_capacity_bytes` | Disk toplam kapasite (byte) |
| `free_capacity_bytes` | Disk boş kapasite (byte) |
| `health_status` | Disk health durumu |
| `running_status` | Disk çalışma durumu |
| `collection_timestamp` | Ölçüm zaman damgası |
| `id` | Dedup tie-breaker |

> **Not:** Tüm device sorguları ayrıca `public.discovery_netbox_inventory_device` (alias `dev`)
> ve `public.loki_locations` tablolarına join yapar; bunlar Zabbix tabloları değil, NetBox/DC
> eşleme kaynaklarıdır.

---

## Sorgular

### Network — `NETWORK_DEVICES_FOR_DC_LATEST`

```sql
WITH dc_map AS (
    SELECT
        distinct name AS location_name,
        CASE
            WHEN parent_id IS NULL THEN name
            when parent_name = 'DH3' then 'DC13'
            ELSE parent_name
        END AS dc_name
    FROM public.loki_locations
    WHERE
        CASE
            WHEN parent_id IS NULL THEN name
            when parent_name = 'DH3' then 'DC13'
            ELSE parent_name
        END IS NOT NULL
),
latest AS (
    SELECT DISTINCT ON (ndm.loki_id)
        ndm.loki_id,
        ndm.host,
        ndm.total_ports_count,
        ndm.active_ports_count,
        ndm.icmp_loss_pct,
        ndm.collection_timestamp
    FROM public.zabbix_network_device_metrics ndm
    WHERE
        ndm.icmp_status IS NOT NULL
        AND ndm.collection_timestamp BETWEEN %s AND %s
        AND ndm.loki_id ~ '^[0-9]+$'
    ORDER BY
        ndm.loki_id,
        ndm.collection_timestamp DESC
)
SELECT
    ndm.loki_id,
    ndm.host,
    dev.name AS device_name,
    dev.manufacturer_name,
    dev.device_role_name,
    dev.location_name,
    dev.site_name,
    ndm.total_ports_count,
    ndm.active_ports_count,
    ndm.icmp_loss_pct,
    ndm.collection_timestamp
FROM latest ndm
JOIN public.discovery_netbox_inventory_device dev
    ON dev.id = ndm.loki_id::bigint
    AND dev.status_value = 'active'
JOIN dc_map m
    ON m.location_name IN (dev.location_name, dev.site_name, dev.name)
WHERE m.dc_name = %s
ORDER BY dev.manufacturer_name NULLS LAST, dev.device_role_name NULLS LAST, dev.name NULLS LAST;
```

**Ne yapar:** Belirtilen DC'deki her NetBox cihazı (loki_id) için, zaman aralığı içindeki ve
`icmp_status IS NOT NULL` olan **en güncel** Zabbix snapshot'ını döner (loki_id başına bir satır).
NetBox ile join + DC eşlemesi yapar.

**Parametreler:** sırayla `start_ts`, `end_ts`, `dc_code`.

**Dönen sütunlar:** `loki_id`, `host`, `device_name`, `manufacturer_name`, `device_role_name`,
`location_name`, `site_name`, `total_ports_count`, `active_ports_count`, `icmp_loss_pct`,
`collection_timestamp`.

Servis kullanımı: `_resolve_zabbix_dc_devices(...)` bu sorguyu çağırır ve `devices`, `hosts`,
`loki_ids` üreten ortak çözümleyicidir. Diğer network metotları (port-summary, 95th, interface-table)
host listesini bu metottan alır.

---

### Network — `DEVICE_PORT_SUMMARY_LATEST`

```sql
WITH devices AS (
    WITH dc_map AS (
    SELECT
        distinct name AS location_name,
        CASE
            WHEN parent_id IS NULL THEN name
            when parent_name = 'DH3' then 'DC13'
            ELSE parent_name
        END AS dc_name
    FROM public.loki_locations
    WHERE
        CASE
            WHEN parent_id IS NULL THEN name
            when parent_name = 'DH3' then 'DC13'
            ELSE parent_name
        END IS NOT NULL
    ),
    latest AS (
        SELECT DISTINCT ON (ndm.loki_id)
            ndm.loki_id,
            ndm.host,
            ndm.total_ports_count,
            ndm.active_ports_count,
            ndm.icmp_loss_pct,
            ndm.collection_timestamp
        FROM public.zabbix_network_device_metrics ndm
        WHERE
            ndm.icmp_status IS NOT NULL
            AND ndm.collection_timestamp BETWEEN %s AND %s
            AND ndm.loki_id ~ '^[0-9]+$'
        ORDER BY
            ndm.loki_id,
            ndm.collection_timestamp DESC
    )
    SELECT
        ndm.loki_id,
        ndm.host,
        ndm.total_ports_count,
        ndm.active_ports_count,
        ndm.icmp_loss_pct
    FROM latest ndm
    JOIN public.discovery_netbox_inventory_device dev
        ON dev.id = ndm.loki_id::bigint
        AND dev.status_value = 'active'
    JOIN dc_map m
        ON m.location_name IN (dev.location_name, dev.site_name, dev.name)
    WHERE m.dc_name = %s
)
SELECT
    COUNT(*)::bigint AS device_count,
    COALESCE(SUM(total_ports_count), 0)::bigint AS total_ports,
    COALESCE(SUM(active_ports_count), 0)::bigint AS active_ports,
    COALESCE(AVG(COALESCE(icmp_loss_pct, 0)), 0)::double precision AS avg_icmp_loss_pct
FROM devices;
```

**Ne yapar:** DC'deki latest-per-loki_id cihaz kümesi üzerinden port KPI özetini hesaplar:
cihaz sayısı, toplam port, aktif port, ortalama ICMP kaybı.

**Parametreler:** sırayla `start_ts`, `end_ts`, `dc_code`.

**Dönen sütunlar:** `device_count`, `total_ports`, `active_ports`, `avg_icmp_loss_pct`.

> **Dürüst not:** Bu SQL tanımlı olsa da, servis tarafında `get_network_port_summary(...)` bu SQL'i
> doğrudan çalıştırmaz; aynı KPI'ları `_resolve_zabbix_dc_devices(...)` sonucundan **Python tarafında**
> `len()` / `sum()` / ortalama ile hesaplar (opsiyonel manufacturer/role/device filtrelerini Python'da
> uygulayabilmek için). Yani bu sorgu şu an dolaylı/yedek konumda.

---

### Network — `DEVICE_LIST_LATEST`

```sql
WITH dc_map AS (
    SELECT
        distinct name AS location_name,
        CASE
            WHEN parent_id IS NULL THEN name
            when parent_name = 'DH3' then 'DC13'
            ELSE parent_name
        END AS dc_name
    FROM public.loki_locations
    WHERE
        CASE
            WHEN parent_id IS NULL THEN name
            when parent_name = 'DH3' then 'DC13'
            ELSE parent_name
        END IS NOT NULL
),
latest AS (
    SELECT DISTINCT ON (ndm.loki_id)
        ndm.loki_id,
        ndm.host,
        ndm.total_ports_count,
        ndm.active_ports_count,
        ndm.icmp_loss_pct,
        ndm.collection_timestamp
    FROM public.zabbix_network_device_metrics ndm
    WHERE
        ndm.icmp_status IS NOT NULL
        AND ndm.collection_timestamp BETWEEN %s AND %s
        AND ndm.loki_id ~ '^[0-9]+$'
    ORDER BY
        ndm.loki_id,
        ndm.collection_timestamp DESC
)
SELECT DISTINCT
    dev.manufacturer_name,
    dev.device_role_name,
    dev.name AS device_name
FROM latest ndm
JOIN public.discovery_netbox_inventory_device dev
    ON dev.id = ndm.loki_id::bigint
    AND dev.status_value = 'active'
JOIN dc_map m
    ON m.location_name IN (dev.location_name, dev.site_name, dev.name)
WHERE
    m.dc_name = %s
    AND (%s IS NULL OR dev.manufacturer_name = %s)
    AND (%s IS NULL OR dev.device_role_name = %s)
ORDER BY
    dev.manufacturer_name NULLS LAST,
    dev.device_role_name NULLS LAST,
    dev.name NULLS LAST;
```

**Ne yapar:** Filtre seçenekleri için (Manufacturer → Device Role → Device hiyerarşisi)
distinct cihaz listesi döner. Opsiyonel manufacturer/role parametreleri NULL ise ilgili filtre
yok sayılır.

**Parametreler:** sırayla `start_ts`, `end_ts`, `dc_code`, `manufacturer_name?`, `manufacturer_name?`,
`device_role_name?`, `device_role_name?` (her opsiyonel filtre `%s IS NULL OR col = %s` deseninde
iki kez geçirilir).

**Dönen sütunlar:** `manufacturer_name`, `device_role_name`, `device_name`.

> **Dürüst not:** `get_network_filters(...)` servis metodu da bu SQL'i doğrudan kullanmaz; filtre
> hiyerarşisini `_resolve_zabbix_dc_devices(...)` cihaz listesinden Python'da kurar. Bu SQL tanımlı
> fakat şu an çağrılmamaktadır.

---

### Network — `INTERFACE_LIST_BY_HOST_LATEST`

```sql
WITH latest_iface AS (
    SELECT DISTINCT ON (zndi.host, zndi.interface_name, COALESCE(zndi.interface_alias, ''))
        zndi.host,
        zndi.interface_name,
        zndi.interface_alias,
        zndi.operational_status,
        zndi.speed,
        zndi.collection_timestamp
    FROM public.zabbix_network_interface_metrics zndi
    WHERE
        zndi.host = ANY(%s)
        AND zndi.collection_timestamp BETWEEN %s AND %s
    ORDER BY
        zndi.host,
        zndi.interface_name,
        COALESCE(zndi.interface_alias, ''),
        zndi.collection_timestamp DESC
)
SELECT
    interface_name,
    interface_alias,
    operational_status,
    speed
FROM latest_iface
ORDER BY interface_name, interface_alias NULLS LAST;
```

**Ne yapar:** Verilen host listesi için, her (host, interface_name, alias) kombinasyonunun en güncel
snapshot'ından interface listesini döner.

**Parametreler:** sırayla `hosts` (list[str]), `start_ts`, `end_ts`.

**Dönen sütunlar:** `interface_name`, `interface_alias`, `operational_status`, `speed`.

> **Dürüst not:** Bu SQL `dc_service.py` içinde **çağrılmıyor** (grep ile servis kullanımı yok).
> Tanımlı ancak şu an UI tarafından tüketilmiyor.

---

### Network — `INTERFACE_95TH_PERCENTILE`

```sql
WITH deduped AS (
    SELECT DISTINCT ON (zndi.host, zndi.interface_name, COALESCE(zndi.interface_alias, ''), zndi.collection_timestamp)
        zndi.host,
        zndi.interface_name,
        zndi.interface_alias,
        zndi.speed,
        zndi.bits_received,
        zndi.bits_sent,
        zndi.collection_timestamp
    FROM public.zabbix_network_interface_metrics zndi
    WHERE
        zndi.host = ANY(%s)
        AND zndi.collection_timestamp BETWEEN %s AND %s
    ORDER BY
        zndi.host,
        zndi.interface_name,
        COALESCE(zndi.interface_alias, ''),
        zndi.collection_timestamp,
        zndi.id DESC
),
bucketed AS (
    SELECT
        time_bucket('1 hour', d.collection_timestamp) AS ts,
        d.host,
        d.interface_name,
        d.interface_alias,
        d.speed,
        AVG(COALESCE(d.bits_received, 0))::double precision AS avg_rx_bps,
        AVG(COALESCE(d.bits_sent, 0))::double precision AS avg_tx_bps
    FROM deduped d
    GROUP BY 1,2,3,4,5
),
ranked AS (
    SELECT
        interface_name,
        interface_alias,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_rx_bps) AS p95_rx_bps,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_tx_bps) AS p95_tx_bps,
        MAX(speed) AS max_speed_bps
    FROM bucketed
    GROUP BY interface_name, interface_alias
)
SELECT
    interface_name,
    interface_alias,
    COALESCE(p95_rx_bps, 0)::double precision AS p95_rx_bps,
    COALESCE(p95_tx_bps, 0)::double precision AS p95_tx_bps,
    COALESCE(p95_rx_bps, 0) + COALESCE(p95_tx_bps, 0) AS p95_total_bps,
    COALESCE(max_speed_bps, 0)::double precision AS speed_bps
FROM ranked
ORDER BY p95_total_bps DESC;
```

**Ne yapar:** Interface bant genişliğinin 95. persentilini hesaplar. Önce ham noktaları
`time_bucket('1 hour', ...)` ile saatlik kovalara indirger (ortalama rx/tx), sonra kovalar üzerinden
`percentile_cont(0.95)` ile rx ve tx için ayrı p95 hesaplar. Toplam p95 = rx + tx. Per-interface
max `speed` döner. p95_total_bps'e göre azalan sıralanır.

**Parametreler:** sırayla `hosts` (list[str]), `start_ts`, `end_ts`.

**Dönen sütunlar:** `interface_name`, `interface_alias`, `p95_rx_bps`, `p95_tx_bps`, `p95_total_bps`,
`speed_bps`.

Servis kullanımı: `get_network_95th_percentile(...)`. Host listesi `_resolve_zabbix_dc_devices`'ten
gelir; sonuçların ilk `top_n` (varsayılan 20) satırı alınıp her satıra `utilization_pct` eklenir
(aşağıdaki Formüller bölümüne bakınız).

---

### Network — `INTERFACE_BANDWIDTH_TABLE_P95`

```sql
WITH deduped AS (
    SELECT DISTINCT ON (zndi.host, zndi.interface_name, COALESCE(zndi.interface_alias, ''), zndi.collection_timestamp)
        zndi.host,
        zndi.interface_name,
        zndi.interface_alias,
        zndi.speed,
        zndi.bits_received,
        zndi.bits_sent,
        zndi.collection_timestamp
    FROM public.zabbix_network_interface_metrics zndi
    WHERE
        zndi.host = ANY(%s)
        AND zndi.collection_timestamp BETWEEN %s AND %s
    ORDER BY
        zndi.host,
        zndi.interface_name,
        COALESCE(zndi.interface_alias, ''),
        zndi.collection_timestamp,
        zndi.id DESC
),
bucketed AS (
    SELECT
        time_bucket('1 hour', d.collection_timestamp) AS ts,
        d.host,
        d.interface_name,
        d.interface_alias,
        d.speed,
        AVG(COALESCE(d.bits_received, 0))::double precision AS avg_rx_bps,
        AVG(COALESCE(d.bits_sent, 0))::double precision AS avg_tx_bps
    FROM deduped d
    GROUP BY 1,2,3,4,5
),
p95 AS (
    SELECT
        interface_name,
        interface_alias,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_rx_bps) AS p95_rx_bps,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_tx_bps) AS p95_tx_bps,
        MAX(speed) AS max_speed_bps
    FROM bucketed
    GROUP BY interface_name, interface_alias
)
SELECT
    interface_name,
    interface_alias,
    COALESCE(p95_rx_bps, 0)::double precision AS p95_rx_bps,
    COALESCE(p95_tx_bps, 0)::double precision AS p95_tx_bps,
    (COALESCE(p95_rx_bps, 0) + COALESCE(p95_tx_bps, 0)) AS p95_total_bps,
    COALESCE(max_speed_bps, 0)::double precision AS speed_bps
FROM p95
WHERE
    (%s = '' OR interface_name ILIKE %s OR COALESCE(interface_alias, '') ILIKE %s)
ORDER BY p95_total_bps DESC, interface_name
LIMIT %s OFFSET %s;
```

**Ne yapar:** `INTERFACE_95TH_PERCENTILE` ile aynı p95 mantığını kullanır, ek olarak arama
(`search` boş değilse `interface_name`/`interface_alias` üzerinde `ILIKE`) ve sayfalama
(`LIMIT`/`OFFSET`) destekler. Tablo görünümü içindir.

**Parametreler:** sırayla `hosts` (list[str]), `start_ts`, `end_ts`, `search` (str, boş olabilir),
`like` (`%search%`), `like` (tekrar), `limit`, `offset`.

**Dönen sütunlar:** `interface_name`, `interface_alias`, `p95_rx_bps`, `p95_tx_bps`, `p95_total_bps`,
`speed_bps`.

Servis kullanımı: `get_network_interface_table(...)`. Sayfa boyutu 1–200 arası clamp edilir
(varsayılan 50). Sorgudan önce `SET statement_timeout = '90000'` (90 sn) uygulanır — yavaş
DISTINCT ON / p95 CTE'sinin worker'ı kilitleyip container'ı OOM ile öldürmesini engellemek için.

---

### Storage — `STORAGE_DEVICES_FOR_DC_LATEST`

```sql
WITH dc_map AS (
    SELECT
        distinct name AS location_name,
        CASE
            WHEN parent_id IS NULL THEN name
            when parent_name = 'DH3' then 'DC13'
            ELSE parent_name
        END AS dc_name
    FROM public.loki_locations
    WHERE
        CASE
            WHEN parent_id IS NULL THEN name
            when parent_name = 'DH3' then 'DC13'
            ELSE parent_name
        END IS NOT NULL
),
latest AS (
    SELECT DISTINCT ON (sdm.loki_id)
        sdm.loki_id,
        sdm.host,
        sdm.total_capacity_bytes,
        sdm.used_capacity_bytes,
        sdm.free_capacity_bytes,
        sdm.health_status,
        sdm.collection_timestamp
    FROM public.zabbix_storage_device_metrics sdm
    WHERE
        sdm.health_status IS NOT NULL
        AND sdm.collection_timestamp BETWEEN %s AND %s
        AND sdm.loki_id ~ '^[0-9]+$'
    ORDER BY
        sdm.loki_id,
        sdm.collection_timestamp DESC
)
SELECT
    latest.loki_id,
    latest.host,
    dev.name AS storage_device_name,
    dev.manufacturer_name,
    dev.device_role_name,
    dev.location_name,
    dev.site_name,
    latest.total_capacity_bytes,
    latest.used_capacity_bytes,
    latest.free_capacity_bytes,
    latest.health_status,
    latest.collection_timestamp
FROM latest
JOIN public.discovery_netbox_inventory_device dev
    ON dev.id = latest.loki_id::bigint
    AND dev.status_value = 'active'
JOIN dc_map m
    ON m.location_name IN (dev.location_name, dev.site_name, dev.name)
WHERE m.dc_name = %s
ORDER BY latest.host;
```

**Ne yapar:** DC'deki her storage cihazı (loki_id) için, zaman aralığındaki ve
`health_status IS NOT NULL` olan **en güncel** snapshot'ı döner. NetBox join + DC eşlemesi.

**Parametreler:** sırayla `start_ts`, `end_ts`, `dc_code`.

**Dönen sütunlar:** `loki_id`, `host`, `storage_device_name`, `manufacturer_name`,
`device_role_name`, `location_name`, `site_name`, `total_capacity_bytes`, `used_capacity_bytes`,
`free_capacity_bytes`, `health_status`, `collection_timestamp`.

Servis kullanımı: Storage tarafının **merkezî** sorgusudur. `get_zabbix_storage_devices(...)`
(cihaz seçici listesi; toplam kapasiteye göre azalan sıralanır), `get_zabbix_storage_capacity(...)`
(toplam/kullanılan/boş özeti — opsiyonel `host` filtresiyle), `get_zabbix_storage_trend(...)`,
`get_zabbix_disk_list(...)`, `get_zabbix_disk_trend(...)` ve `get_zabbix_disk_health(...)` hep önce
bu sorguyla DC'ye ait geçerli host setini bulur (host scoping/doğrulama).

---

### Storage — `STORAGE_CAPACITY_SUMMARY_LATEST`

```sql
WITH latest AS (
    SELECT DISTINCT ON (sdm.host)
        sdm.host,
        sdm.total_capacity_bytes,
        sdm.used_capacity_bytes,
        sdm.free_capacity_bytes,
        sdm.collection_timestamp
    FROM public.zabbix_storage_device_metrics sdm
    WHERE
        sdm.host = ANY(%s)
        AND sdm.health_status IS NOT NULL
        AND sdm.collection_timestamp BETWEEN %s AND %s
    ORDER BY
        sdm.host,
        sdm.collection_timestamp DESC
)
SELECT
    COUNT(*)::bigint AS storage_device_count,
    COALESCE(SUM(total_capacity_bytes), 0)::bigint AS total_capacity_bytes,
    COALESCE(SUM(used_capacity_bytes), 0)::bigint AS used_capacity_bytes,
    COALESCE(SUM(free_capacity_bytes), 0)::bigint AS free_capacity_bytes
FROM latest;
```

**Ne yapar:** Verilen host listesi için her host'un en güncel snapshot'ını alıp kapasite
toplamlarını (cihaz sayısı, total/used/free byte) döner.

**Parametreler:** sırayla `hosts` (list[str]), `start_ts`, `end_ts`.

**Dönen sütunlar:** `storage_device_count`, `total_capacity_bytes`, `used_capacity_bytes`,
`free_capacity_bytes`.

> **Dürüst not:** `get_zabbix_storage_capacity(...)` bu SQL'i **çağırmaz**; özeti
> `STORAGE_DEVICES_FOR_DC_LATEST` satırlarından Python'da `sum()` ile hesaplar (ve opsiyonel
> `host` filtresini Python'da uygular). Bu SQL tanımlı fakat şu an kullanılmıyor.

---

### Storage — `STORAGE_CAPACITY_TREND_DAILY`

```sql
WITH latest_per_host_per_day AS (
    SELECT DISTINCT ON (time_bucket('1 day', sdm.collection_timestamp), sdm.host)
        time_bucket('1 day', sdm.collection_timestamp) AS day,
        sdm.host,
        sdm.used_capacity_bytes,
        sdm.total_capacity_bytes
    FROM public.zabbix_storage_device_metrics sdm
    WHERE
        sdm.host = ANY(%s)
        AND sdm.health_status IS NOT NULL
        AND sdm.collection_timestamp BETWEEN %s AND %s
    ORDER BY
        time_bucket('1 day', sdm.collection_timestamp),
        sdm.host,
        sdm.collection_timestamp DESC
)
SELECT
    day AS ts,
    COALESCE(SUM(used_capacity_bytes), 0)::bigint AS used_capacity_bytes,
    COALESCE(SUM(total_capacity_bytes), 0)::bigint AS total_capacity_bytes
FROM latest_per_host_per_day
GROUP BY 1
ORDER BY 1;
```

**Ne yapar:** Günlük kapasite trendi üretir. Her (gün, host) için o günün en güncel snapshot'ını alıp
(`DISTINCT ON` + `time_bucket('1 day', ...)`), gün bazında host'lar üzerinden used/total toplar.

**Parametreler:** sırayla `hosts` (list[str]), `start_ts`, `end_ts`.

**Dönen sütunlar:** `ts` (gün), `used_capacity_bytes`, `total_capacity_bytes`.

Servis kullanımı: `get_zabbix_storage_trend(...)`. Host seti `STORAGE_DEVICES_FOR_DC_LATEST`'ten
çözülür (opsiyonel `host` filtresiyle), sonra bu sorgu çalıştırılır; her noktaya `used_pct` eklenir.

---

### Storage — `STORAGE_DISK_LIST_BY_HOST`

```sql
SELECT DISTINCT disk_name
FROM public.zabbix_storage_disk_metrics
WHERE host = ANY(%s)
  AND collection_timestamp BETWEEN %s AND %s
ORDER BY disk_name;
```

**Ne yapar:** Seçili host(lar) için distinct disk adlarını döner (disk seçici listesi).

**Parametreler:** sırayla `hosts` (list[str]), `start_ts`, `end_ts`.

**Dönen sütunlar:** `disk_name`.

Servis kullanımı: `get_zabbix_disk_list(...)`. Önce host'un bu DC'ye ait olduğu
`STORAGE_DEVICES_FOR_DC_LATEST` ile doğrulanır; geçerli değilse boş liste döner.

---

### Storage — `STORAGE_DISK_TREND_DAILY`

```sql
WITH latest_per_day AS (
    SELECT DISTINCT ON (
        time_bucket('1 day', sdm.collection_timestamp),
        sdm.host,
        sdm.disk_name
    )
        time_bucket('1 day', sdm.collection_timestamp) AS day,
        sdm.host,
        sdm.disk_name,
        sdm.total_iops,
        sdm.latency_ms,
        sdm.total_capacity_bytes,
        sdm.free_capacity_bytes
    FROM public.zabbix_storage_disk_metrics sdm
    WHERE
        sdm.host = ANY(%s)
        AND sdm.disk_name = %s
        AND sdm.collection_timestamp BETWEEN %s AND %s
    ORDER BY
        time_bucket('1 day', sdm.collection_timestamp),
        sdm.host,
        sdm.disk_name,
        sdm.collection_timestamp DESC
)
SELECT
    day AS ts,
    COALESCE(AVG(total_iops), 0)::double precision AS avg_iops,
    COALESCE(AVG(latency_ms), 0)::double precision AS avg_latency_ms,
    COALESCE(SUM(total_capacity_bytes), 0)::bigint AS total_capacity_bytes,
    COALESCE(SUM(free_capacity_bytes), 0)::bigint AS free_capacity_bytes
FROM latest_per_day
GROUP BY 1
ORDER BY 1;
```

**Ne yapar:** Belirli bir disk için günlük trend serisi üretir. Her (gün, host, disk_name) için o
günün en güncel snapshot'ını alır, gün bazında IOPS/latency ortalaması ve kapasite toplamı döner.

**Parametreler:** sırayla `hosts` (list[str]), `disk_name` (str), `start_ts`, `end_ts`.

**Dönen sütunlar:** `ts` (gün), `avg_iops`, `avg_latency_ms`, `total_capacity_bytes`,
`free_capacity_bytes`.

Servis kullanımı: `get_zabbix_disk_trend(...)`. `host` veya `disk_name` yoksa boş seri döner; host
DC doğrulamasından geçer.

---

### Storage — `DISK_HEALTH_PERFORMANCE`

```sql
WITH latest_health AS (
    SELECT DISTINCT ON (sdm.host, sdm.disk_name)
        sdm.host,
        sdm.disk_name,
        sdm.health_status,
        sdm.running_status,
        sdm.collection_timestamp
    FROM public.zabbix_storage_disk_metrics sdm
    WHERE
        sdm.host = ANY(%s)
        AND sdm.collection_timestamp BETWEEN %s AND %s
        AND sdm.health_status IS NOT NULL
    ORDER BY
        sdm.host,
        sdm.disk_name,
        sdm.collection_timestamp DESC
),
stats AS (
    SELECT
        disk.host,
        disk.disk_name,
        AVG(COALESCE(disk.total_iops, 0))::double precision AS avg_total_iops,
        AVG(COALESCE(disk.latency_ms, 0))::double precision AS avg_latency_ms,
        AVG(COALESCE(disk.temperature_c, 0))::double precision AS avg_temperature_c
    FROM (
        SELECT DISTINCT ON (sdm.host, sdm.disk_name, sdm.collection_timestamp)
            sdm.host,
            sdm.disk_name,
            sdm.total_iops,
            sdm.latency_ms,
            sdm.temperature_c
        FROM public.zabbix_storage_disk_metrics sdm
        WHERE
            sdm.host = ANY(%s)
            AND sdm.collection_timestamp BETWEEN %s AND %s
        ORDER BY
            sdm.host,
            sdm.disk_name,
            sdm.collection_timestamp,
            sdm.id DESC
    ) disk
    GROUP BY 1,2
)
SELECT
    stats.disk_name,
    latest_health.health_status,
    COALESCE(stats.avg_total_iops, 0)::double precision AS avg_total_iops,
    COALESCE(stats.avg_latency_ms, 0)::double precision AS avg_latency_ms,
    COALESCE(stats.avg_temperature_c, 0)::double precision AS avg_temperature_c,
    latest_health.running_status
FROM stats
JOIN latest_health
  ON latest_health.host = stats.host
 AND latest_health.disk_name = stats.disk_name
ORDER BY stats.avg_total_iops DESC, stats.avg_latency_ms DESC, stats.disk_name
LIMIT %s;
```

**Ne yapar:** Disk health & performans özet tablosu üretir. İki bileşeni birleştirir:
- `latest_health`: (host, disk_name) başına **en güncel** `health_status` ve `running_status`.
- `stats`: zaman aralığı boyunca (host, disk_name) başına **ortalama** IOPS / latency / sıcaklık
  (önce timestamp bazında dedup edilerek). avg IOPS, sonra avg latency, sonra disk_name'e göre sıralı.

**Parametreler:** sırayla `hosts`, `start_ts`, `end_ts` (latest_health için), ardından `hosts`,
`start_ts`, `end_ts` (stats için tekrar), `limit` (servis varsayılanı 500).

**Dönen sütunlar:** `disk_name`, `health_status`, `avg_total_iops`, `avg_latency_ms`,
`avg_temperature_c`, `running_status`.

Servis kullanımı: `get_zabbix_disk_health(...)`. DC'nin tüm host'ları
`STORAGE_DEVICES_FOR_DC_LATEST`'ten çözülür, sonra bu sorgu `limit=500` ile çalıştırılır.

---

## Hesaplamalar / Formüller

### Latest-snapshot deseni (latest-per-X)
Tüm device/disk metriklerinde çift sayımı önlemek için `SELECT DISTINCT ON (...) ... ORDER BY ...
collection_timestamp DESC` deseni kullanılır:
- Network device: `DISTINCT ON (loki_id)`
- Network interface listesi: `DISTINCT ON (host, interface_name, COALESCE(alias,''))`
- Storage device: `DISTINCT ON (loki_id)` veya özetlerde `DISTINCT ON (host)`
- Disk health: `DISTINCT ON (host, disk_name)`

### Downsampling (time_bucket)
- Interface p95: `time_bucket('1 hour', ...)` ile saatlik ortalamalar.
- Storage/disk trendi: `time_bucket('1 day', ...)` ile günlük en güncel/ortalama.

### 95. persentil bant genişliği
`percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_rx_bps)` (ve tx için ayrı).
`p95_total_bps = p95_rx_bps + p95_tx_bps`.

### Utilization yüzdesi (servis tarafı, Python)
`get_network_95th_percentile` ve `get_network_interface_table` içinde, satır başına:
```
utilization_pct = (p95_total / speed * 100.0) if speed > 0 else 0.0
```
Genel port doluluğu (yalnızca 95th servisinde):
```
overall_port_utilization_pct = (sum(p95_total) / sum(speed) * 100.0) if sum(speed) > 0 else 0.0
```

### Port KPI özeti (servis tarafı, Python)
`get_network_port_summary` içinde latest-per-device cihaz listesinden:
```
device_count   = len(devices)
total_ports    = Σ total_ports_count
active_ports   = Σ active_ports_count
avg_icmp_loss  = Σ icmp_loss_pct / device_count   (device_count > 0 ise, değilse 0)
```

### Storage kapasite kullanım yüzdesi (servis tarafı, Python)
`get_zabbix_storage_trend` içinde her gün için:
```
used_pct = (used_bytes / total_bytes * 100.0) if total_bytes > 0 else 0.0
```

---

## Birim Dönüşümleri

SQL'ler ham birimlerde döner (byte ve bit/sn); dönüşüm **UI katmanında** (`src/pages/dc_view.py`) yapılır:

- **Byte → GB** (Intel Storage kapasite kartı, ikilik tabanlı):
  `bytes_to_gb = lambda b: (float(b) / (1024.0 ** 3)) if b else 0.0`
- **bps → Gbps** (Network Dashboard p95 grafiği/tablosu, ondalık tabanlı):
  `_bps_to_gbps(value_bps) = float(value_bps or 0) / 1e9`

Latency `ms`, sıcaklık `°C`, IOPS birimsiz olarak doğrudan gösterilir.

---

## Caching

Tüm servis metotları `app.services.cache_service` (alias `cache`) üzerinden cache kullanır:
- Her metot kendi `cache_key`'ini DC + zaman aralığı + (varsa) filtre/host/disk/sayfa parametreleriyle kurar.
  Örn. `dc_zabbix_net_devices:{DC}:{manu}:{role}:{dev}:{start}:{end}`,
  `dc_zabbix_storage_devices:{DC}:{start}:{end}`, `dc_zabbix_disk_health:{DC}:{start}:{end}`.
- Önce `cache.get(cache_key)`; isabet varsa SQL çalışmadan döner. Aksi halde sorgu çalışır ve
  `cache.set(cache_key, result)` ile yazılır.
- TTL: `cache.set(...)` çağrılarında açık TTL verilmez; backend varsayılanı `settings.cache_ttl_seconds`
  kullanılır. Varsayılan değer **1200 saniye (20 dk)** (`services/datacenter-api/app/config.py`).

---

## Özet

- **Network sorguları** (`zabbix_network.py`): cihaz latest snapshot'ı + port KPI + filtre listesi +
  interface listesi + 95. persentil bant genişliği (Top-N ve sayfalı tablo). UI'da **Network Dashboard**
  alt sekmesini besler.
- **Storage sorguları** (`zabbix_storage.py`): cihaz latest snapshot'ı + kapasite özeti + günlük kapasite
  trendi + disk listesi + disk trendi + disk health/performans özeti. UI'da **Intel Storage** alt sekmesini
  ve disk endpoint'lerini besler.
- Ortak desen: NetBox/loki_locations üzerinden DC scoping, `DISTINCT ON` ile latest-per-X, `time_bucket`
  ile downsampling, `percentile_cont(0.95)` ile p95.
- **Aktif kullanım:** Endpoint'ler `routers/datacenters.py` altında (`/network/*`, `/zabbix-storage/*`)
  tanımlı ve Dash UI (`api_client.py` → `dc_view.py`) tarafından tüketiliyor — **aktif kullanımda**.
- **Kullanılmayan/dolaylı SQL'ler (dürüst not):** `DEVICE_PORT_SUMMARY_LATEST`, `DEVICE_LIST_LATEST`,
  `STORAGE_CAPACITY_SUMMARY_LATEST` SQL'leri tanımlı olsa da servis tarafında doğrudan çağrılmıyor; ilgili
  KPI/özetler `_resolve_zabbix_dc_devices` / `STORAGE_DEVICES_FOR_DC_LATEST` sonuçlarından Python'da
  hesaplanıyor (filtreleri Python'da uygulamak için). `INTERFACE_LIST_BY_HOST_LATEST` ise hiç çağrılmıyor.

İlgili dokümanlar: [README](README.md), [04-ibm-storage-san.md](04-ibm-storage-san.md).
