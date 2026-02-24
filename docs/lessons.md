🎓 Lessons Learned & Pattern Prevention
Bu dosya, Datalake-GUI projesinin geliştirilmesi sırasında karşılaşılan teknik zorlukları, mimari hataları ve kullanıcı düzeltmelerini kayıt altına almak için kullanılır.

Senior Developer (Claude) için Kural: Herhangi bir hata veya kullanıcı uyarısından sonra bu dosyayı güncellemeden görevi "tamamlandı" olarak işaretleme.

## 📝 Pattern Tracking Table
Tarih	Hata/Sorun	Kök Neden	Çözüm/Yeni Kural
2026-02-23	Port Çakışması	İki servis aynı portu denedi	architecture.md'deki port tablosuna sadık kalınacak
2026-02-23	.env CRLF hatası	Windows satır sonu \r DB şifresine ekleniyordu	.env dosyası her zaman LF formatında tutulacak; `file .env` komutuyla kontrol edilecek
2026-02-23	DB_USER yanlışlığı	Kullanıcı adı `datalakeui` yerine `bulutlake` olmalıydı	.env içindeki DB_USER her zaman gerçek DB kullanıcısıyla eşleştirilecek
2026-02-24	curl eksik — healthcheck kırık	python:3.11-slim base image curl içermiyor; healthcheck CMD curl kullanıyor	Tüm servis Dockerfile'larına `curl` paketi eklenecek; healthcheck yazılmadan önce test edilecek

## 🛠️ Öğrenilen Dersler (Kategorik)
### 1. Mimari ve Mikroservis Yönetimi
Servis İletişimi: Servisler arası asenkron yapıda Timeout hatalarını önlemek için merkezi bir retry mekanizması shared/utils altında planlanmalıdır.

Port Disiplini: architecture.md dosyasında tanımlanan port haritası dışına çıkılmamalıdır.

Pattern Tutarlılığı (Task 2.1): Yeni bir servis yazılırken mevcut servisin DI desenini birebir yansıt. db-service'te `asyncpg.Pool` → `app.state.pool` → `get_pool()` idi; query-service'te aynı yapı `httpx.AsyncClient` → `app.state.db_client` → `get_db_client()` oldu. Bu tutarlılık yeni servislerin okunmasını ve bakımını kolaylaştırır.

Timeout Disiplini (Task 2.1): httpx.AsyncClient'ın varsayılan timeout'u 5 saniyedir. Downstream servis 74 saniye alabiliyorsa bu değer bilinçli olarak 90 saniyeye çıkarılmalıdır. Her servis arası istemci oluşturulurken downstream'in gerçek p99 yanıt süresi timeout olarak ayarlanmalıdır.

Todolist Önceliği (Task 2.1): PHASE.md ile todolist.md çakıştığında her zaman todolist.md sıralaması esas alınır. Görev kapsamı todolist.md'deki tekil task tanımına göre daraltılır; scope creep'e izin verilmez.

### 2. Kodlama ve Refactoring (Legacy -> Modern)
Tip Güvenliği: Pydantic modelleri (shared/schemas) tanımlanmadan servisler arası veri transferi yapılmamalıdır.

Legacy Logic: Eski koddaki SQL sorguları taşınırken, performans artışı için asyncpg veya benzeri asenkron sürücüler tercih edilmelidir.

TODO Marker Disiplini (Task 2.1): Bir taskın kapsamı dışında kalan mantık asla yazılmaz; bunun yerine açık `# TODO Task X.X: <açıklama>` yorumu bırakılır. Bu, hem scope creep'i önler hem de bir sonraki task'ın başlangıç noktasını netleştirir.

### 3. Docker ve Altyapı
Build Süresi: .dockerignore dosyasının eksikliği imaj boyutlarını artırabilir. Gereksiz dosyalar (venv, pycache) her zaman hariç tutulmalıdır.

Volume Kalıcılığı: Veritabanı veya log verilerinin Docker konteyneri silindiğinde kaybolmaması için named volumes kullanımı zorunludur.

curl Zorunluluğu (Task 2.1 / Yeni Ev): python:3.11-slim base image curl içermez. docker-compose.yml'de `CMD curl` kullanan healthcheck tanımı varsa ilgili Dockerfile'a mutlaka `apt-get install -y curl` eklenmelidir. Aksi takdirde container `health: starting` durumunda kalır ve `depends_on: service_healthy` zinciri bir sonraki servisi asla başlatmaz.

Soğuk Başlangıç Farkı (Task 2.1): İlk sorgu (soğuk) ile sonraki sorgular (sıcak) arasında ciddi süre farkı olabilir (74s / 39s). Test sonuçlarına her zaman ikinci çalışmanın süresi yazılmalıdır; tek çalışma sonucu yanıltıcıdır.

### 4. Task 2.2 Öğrenilen Dersler (Provider Adapter Katmanı)


Adapter Doğrulama Değeri (Task 2.2): Provider sınıfları yalnızca mimari soyutlama sağlamaz; validasyon + loglama ile gerçek veri kalitesi sorunlarını da yakalar. NutanixProvider ilk çalıştırmada `storage_cap=258TB` anomalisini loğa yazdırdı; bu sorun daha önce fark edilmemişti.

Bireysel Sorgu vs Batch Sorgu Farkı (Task 2.2): db-service'teki bireysel SQL sorguları (`vq.CPU`, `vq.MEMORY` vb.) zaman filtresi içermiyor (`ORDER BY timestamp DESC LIMIT 1`). Batch sorgular `AND timestamp >= NOW() - INTERVAL '4 hours'` içeriyor. Bu fark `get_dc_detail()` ile `get_summary()` arasında farklı (bazen hatalı) değer döndürülmesine yol açabiliyor. Task 2.4 integration testinde db-service düzeyinde ele alınmalı.

TODO Temizliği (Task 2.2): Bir task tamamlandığında, o task'a ait tüm `# TODO Task X.X` yorumları gerçek kodla değiştirilmeli. Bir sonraki task'a ait TODO'lar (burada `# TODO Task 2.3`) korunmalı — bu hem scope'u netleştirir hem de sıradaki görevin başlangıç noktasını gösterir.

### 5. Task 2.3 Öğrenilen Dersler (Redis Cache-Aside)

Docker Exec Latency Yanıltıcılığı (Task 2.3): `docker exec container curl ...` komutu ~250ms process-spawn overhead'i ekler. Cache HIT testi 293ms gösterse de gerçek Redis yanıtı sub-millisecond'dır. Gerçek latency ölçümü için servis içinden `time.time()` veya FastAPI middleware kullanılmalıdır; docker exec süreleri yanıltıcıdır.

Silent Fail Prensibi (Task 2.3): Redis bağlantı hatası query-service'i çökertmemeli. GET hatası → warn log + db-service'e düşme; SET hatası → warn log + veri yine döndürülür. Bu pattern, Redis'in opsiyonel bir hız katmanı olmasını sağlar; kritik yolda değildir.

decode_responses=True Zorunluluğu (Task 2.3): `aioredis.from_url(url, encoding="utf-8", decode_responses=True)` ile Redis'ten gelen değerler str olarak döner. Bu olmadan `bytes` gelir ve `model_validate_json(cached)` hata fırlatır. Decode_responses her zaman True olarak ayarlanmalıdır.

Cache Key Tasarımı (Task 2.3): Liste endpoint'i için `json.dumps([s.model_dump(mode="json") for s in enriched])` + `[Model.model_validate(item) for item in json.loads(cached)]` pattern'i kullanılır. Tekil model için `model.model_dump_json()` + `Model.model_validate_json(cached)` daha temizdir.

### 6. Task 2.4 Öğrenilen Dersler (Veri Akışı & Teknik Borç)

Time Filter Varsayımı Yanıltıcılığı (Task 2.4): Bireysel SQL sorguları zaman filtresi eklendikten sonra "anormal yüksek" değerlerin düzeleceği varsayımı yanlış çıktı. Gerçek kök neden veri birim dönüşüm hatasıydı (storage_capacity bytes → TB dönüşümü yapılmıyordu). Bir uyarının "neden" tetiklendiği anlaşılmadan fix yapılmamalı — unit test veya DB sorgusuyla temel değeri doğrula.

Decimal + Float Tipi Karışıklığı (Task 2.4): asyncpg, PostgreSQL NUMERIC/DECIMAL sütunlarını Python `decimal.Decimal` olarak döndürür. Kod `(row[0] or 0) / 1024` gibi bir işlem yaptığında `0 or 0 = 0` (int), `0 / 1024 = 0.0` (float) olur. Daha sonra `Decimal + float` toplandığında `TypeError` patlar. Fix: `float(row[0] or 0)` ile explicit cast yapılmalı.

Nutanix storage_capacity Birimi (Task 2.4): `nutanix_cluster_metrics.storage_capacity` bytes cinsinden (TB değil). `SQL: storage_capacity / 2` (dedup) sonrası `_aggregate_dc`'de `/ (1024 ** 4)` uygulanarak TB'a çevrilir. Bu fix öncesinde değer 258 trilyon TB gösteriyordu; sonrasında ~3957 TB/cluster (makul).

Cache + Rebuild Tutarsızlığı (Task 2.4): `db-service` rebuild sonrası yeni kod aktif oldu ancak `query-service` Redis cache'teki eski hatalı değerleri servis etmeye devam etti. Her db-service kod değişikliğinde `redis-cli FLUSHALL` ile ilgili cache anahtarları temizlenmelidir; aksi hâlde testler eski veriye göre sonuç verir.

Provider Eşik Kalibrasyonu (Task 2.4): Sanity check eşikleri (örn. `STORAGE_SANITY_LIMIT_TB`) gerçek veri aralıklarına göre kalibre edilmeli. Birim fix sonrası gerçek cluster storage değerleri 1000–6000 TB aralığına düştü; eski 1000 TB eşiği false positive üretmeye başladı. Eşik 10000 TB (10 PB/cluster) olarak güncellendi.

## 🚦 Nasıl Güncellenir?
Bir hata ile karşılaşıldığında şu adımları izle:
Sorunun kök nedenini (Root Cause) analiz et.
Çözümü uygula.
Çözümün kalıcı olması için bir "yazılım kuralı" türet ve bu tabloya ekle.
skills.md dosyasında bu hatayı engelleyecek bir madde eksikse orayı da güncelle.