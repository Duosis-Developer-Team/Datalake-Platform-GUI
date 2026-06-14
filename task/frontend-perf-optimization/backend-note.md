# Backend Performans Notu — datacenter-api / DB

**Kime:** Can (backend) · **Tarih:** 2026-06-14 · **Kaynak:** 7-agent canlı performans ölçümü (GUI + backend, gerçek sayılar)

## Özet
GUI'deki "her şey çok yavaş / donuyor" şikayetinin **baskın sebebi frontend değil — datacenter-api + remote DB.** Ölçüldü: ağır endpoint'ler **7d penceresinde bile 20-60s**, 30d'de daha kötü. GUI render maliyeti toplam sürenin **<%1'i (~30-50ms)**. Yani sayfa yavaş çünkü bu çağrıları bekliyor. GUI tarafında yapılabilecekleri yaptık (paralel çağrı, GUI-cache, lazy-mount, boş-veri/isim fix'leri); kalan yavaşlık **backend'de çözülmeli.**

## crm-engine — 2 platform bug'ı (2026-06-15 bulundu/düzeltildi, ops kalıcı çözüm gerek)

1. **crm-engine `depends_on: datacenter-api (healthy)` zamanlama tuzağı:** datacenter-api'nin açılış warm'ı uzun sürünce (dakikalar) crm-engine "Created" kalıp hiç başlamıyor → tüm sellable kapalı. Compose'da `condition: service_healthy` + uzun warm = kırılgan. Öneri: datacenter-api healthcheck'ini warm'dan ayır (server bind olunca healthy), ya da crm-engine dependency condition'ını `service_started` yap.
2. **webui-db'ye migration'lar otomatik uygulanmıyor:** init script'leri (`/docker-entrypoint-initdb.d`) yalnız BOŞ volume'da çalışır. Mevcut webui-db volume'u **012'de takılıydı**; 013-021 hiç uygulanmamıştı → `gui_panel_infra_source.manual_total` kolonu yoktu → her sellable çağrısı **500 (UndefinedColumn)**. Elle 013-021 uyguladım (idempotent). **Kalıcı çözüm:** startup'ta bir migration-runner (mevcut volume'lara da uygulayan) ekleyin, sadece init-on-empty'ye güvenmeyin.

## Ölçülen darboğazlar (öncelik sırası)

### 0. ⚠️ EN KRİTİK: `GET /api/v1/dashboard/overview` = **83 saniye** (cold, 7d)
- Ölçüldü (2026-06-15): overview endpoint'i **83.1s** dönüyor, `/datacenters/summary` ise 0.0s (cache'li). Yani Executive Dashboard / ana sayfa her cold yüklemede 83s bekliyor → GUI timeout'a düşüp **0 gösteriyor.** Hiçbir makul interactive timeout 83s'yi kurtaramaz.
- **Yapılması gereken:** overview'i server-side cache'le (summary gibi) ve/veya altındaki ağır aggregate sorgularını optimize et. Bu tek endpoint ana sayfa deneyimini öldürüyor.

### 1. Heavy compute endpoint'leri server-side cache'lenmiyor → her çağrıda yeniden hesap
- `GET /compute/hyperconverged` (özet panel): **her çağrıda ~23s** (warm dahil) — cache yok, üstelik `SELECT DISTINCT CLUSTER_UUID` sorgusunu **istek başına 4 kez** çalıştırıyor.
- `GET /compute/classic?clusters=...` (cluster-filtreli): **15-39s cold**, aynısı tekrar istenince yine 15s — sonuç cache'lenmiyor.
- **Yapılması gereken:** bu endpoint'lerin sonucunu Redis'te (dc+window+clusters anahtarıyla) cache'le; aynı/yakın istek tekrar geldiğinde DB'ye gitme.

### 2. İki SQL sorgu ailesi DB'yi dövüyor (index/rewrite gerek)
15 dakikada **353 sorgu = ~1.867 saniye SQL.** En ağır ikisi:
- `SELECT DISTINCT CLUSTER_UUID::TEXT ...` — **6173 satır full-scan, 21-75s.** İstek başına birçok kez.
- `SELECT DISTINCT ON (VMNAME) ...` — **6-52s, çoğu 0 satır dönüyor** (boşuna tarama).
- **Yapılması gereken:** ilgili tablolara `(dc, cluster, timestamp)` / `(vmname, timestamp)` index'i; VM'i olmayan cluster'lar için VMNAME sorgusunu atla; `DISTINCT` yerine pencere fonksiyonu/materialized view değerlendir.

### 3. 30 günlük pencere her sorguyu ~4x büyütüyor
- 7d ile 20-45s olan sorgular 30d'de **>60s**. Geniş pencereler özellikle (1) ve (2)'deki cache+index olmadan kullanılamıyor.

### 4. crm-engine boş DC'ler için `computed_at` dönmüyor
- Sellable snapshot'ı olmayan DC'lerde (örn. DC13) crm-engine boş payload + `computed_at=None` dönüyor. GUI eskiden bunu cache'leyemiyordu (düzelttik, GUI tarafı artık negatif-cache yapıyor). **Backend tarafında:** zero-result DC'ler için de `computed_at` marker'ı dönmek normal cache yolunu temizler.

### 5. AuraNotify SLA (10.34.8.154:5001) — HTTP 500 + retry backoff
- `GET /api/customers/list` ve downtime çağrıları zaman zaman **500** dönüyor; her build'de ~4.5s retry backoff'a sebep oluyor. SLA servisinin 500'leri + erişilebilirliği gözden geçirilmeli.

## GUI tarafında zaten yapıldığımız (referans)
- Cluster-filtre fan-out azaltma (P3), nested lazy-mount (P5), host-row in-process slicing (P8 — **bu desen mükemmel çalışıyor: cluster toggle 2-12ms cache hit**), request coalescing (C1), stale-while-revalidate (C2), negatif-sonuç cache, isim-boş-kalma fix'i.
- **Not:** P8 (host-row'ları clusters'sız bir kez çek + in-process böl) deseni **compute panellerine de uygulanabilirdi** ama filtresiz `/compute/classic` 30d'de >60s olduğu için onu da backend cache/index olmadan kurtaramadık. (1)+(2) çözülünce GUI tarafında bu deseni de uygularız.

## Ortam notu
Bu ölçümler **lokal app + VPN üzerinden remote DB** ile alındı. Production'da backend+DB yan yana ve server-side cache çalışıyorsa süreler çok daha iyi olabilir — yani lokal yavaşlık prod sorununu abartıyor olabilir. Yine de (1) ve (2) her ortamda fayda sağlar.
