🎓 Lessons Learned & Pattern Prevention
Bu dosya, Datalake-GUI projesinin geliştirilmesi sırasında karşılaşılan teknik zorlukları, mimari hataları ve kullanıcı düzeltmelerini kayıt altına almak için kullanılır.

Senior Developer (Claude) için Kural: Herhangi bir hata veya kullanıcı uyarısından sonra bu dosyayı güncellemeden görevi "tamamlandı" olarak işaretleme.

## 📝 Pattern Tracking Table
Tarih	Hata/Sorun	Kök Neden	Çözüm/Yeni Kural
2026-02-23	Port Çakışması	İki servis aynı portu denedi	architecture.md'deki port tablosuna sadık kalınacak
2026-02-23	.env CRLF hatası	Windows satır sonu \r DB şifresine ekleniyordu	.env dosyası her zaman LF formatında tutulacak; `file .env` komutuyla kontrol edilecek
2026-02-23	DB_USER yanlışlığı	Kullanıcı adı `datalakeui` yerine `bulutlake` olmalıydı	.env içindeki DB_USER her zaman gerçek DB kullanıcısıyla eşleştirilecek
2026-02-24	curl eksik — healthcheck kırık	python:3.11-slim base image curl içermiyor; healthcheck CMD curl kullanıyor	Tüm servis Dockerfile'larına `curl` paketi eklenecek; healthcheck yazılmadan önce test edilecek
2026-02-25	DMC v2.6.0 kuruldu (PHASE.md v0.14+ belirtiyordu)	requirements.txt versiyon pinlenmemiş → pip en yeni sürümü yükledi	requirements.txt'te DMC versiyonunu sabitlemek yerine test sonucu uyumlu olduğu doğrulandı; yeni API (v2.x) v0.14+'la geriye dönük uyumlu

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

### 7. Task 3.2 UI/UX Dersleri (Bulutistan Kurumsal Görsel Standardı)

Glassmorphism CSS Pattern: `background: rgba(255,255,255,0.82)` + `backdrop-filter: blur(18px)` + `border: 1px solid rgba(...)` üçlüsü zorunlu. Body üzerinde mesh radial-gradient olmadan etki yarı düzeyde kalır; arka plan rengi + gradient birlikte çalışmalıdır.

Floating Sidebar Tekniği: `AppShellNavbar` öğesini şeffaf yap (`background: transparent !important`, `border-right: none !important`, padding ekle). Gerçek görsel cam paneli iç `dmc.Box(className="sidebar-float", h="100%")` ile oluştur. Bu sayede Mantine'nin CSS Grid layout'u bozulmaz; padding sayesinde sidebar ekrandan boşluklu görünür.

Dash Assets Auto-Load: `assets/` klasöründeki .css dosyaları Dash tarafından otomatik serve edilir — Dockerfile veya docker-compose değişikliği gerektirmez. `rebuild + /assets/style.css` HTTP 200 ile test edilir.

NavLink Active Indicator (Pseudo-element): `.mantine-NavLink-root[data-active]::before` + `position: absolute; left: 0; width: 4px` ile sol neon şerit oluşturulur. Parent `position: relative` zorunlu. ÖNEMLİ: NavLink root'a `overflow: hidden` verme — pseudo-element görünmez olur. Şerit; `linear-gradient(180deg, #4c6ef5, #845ef7)` + `box-shadow: 0 0 8px rgba(76,110,245,0.65)` ile neon etkisi sağlar.

CSS `!important` Zorunluluğu: Mantine/DMC bileşenleri yüksek özgüllüklü inline style + Mantine sınıf hiyerarşisi kullanır. `AppShell-navbar` arka planı, `dc-card` arka planı, `NavLink` border-radius gibi görsel geçersiz kılmalar için `!important` gereklidir; aksi hâlde Mantine kendi stilini baskılar.

### 8. Task 3.3 Öğrenilen Dersler (Plotly Chart Entegrasyonu)

DMC v2.x LoadingOverlay Positional Arg Tuzağı: `dmc.LoadingOverlay(dmc.Stack(...), visible=False)` yazıldığında Dash `dmc.Stack` bileşenini `transitionProps` prop'u olarak yorumlar. Kök neden: DMC v2.6.0 Python binding'inde `LoadingOverlay.__init__` ilk parametresi `transitionProps`'tur, `children` değildir. Kural: DMC bileşenlerine child geçerken `children=` keyword argümanı her zaman açık yazılmalıdır — `dmc.LoadingOverlay(children=..., visible=False)`.

Plotly Şeffaf Background Zorunluluğu: Glassmorphism Paper wrapper içinde Plotly grafiklerin kendi arka planı `paper_bgcolor="rgba(0,0,0,0)"` + `plot_bgcolor="rgba(0,0,0,0)"` olarak ayarlanmalıdır. Aksi takdirde grafik kendi beyaz kutusunu çizer ve glassmorphism etkisi yok olur.

go.Pie Merkez Annotation: `hole=0.62` ile donut efekti oluşturulur. Ortada yüzde göstermek için `fig.update_layout(annotations=[dict(text="<b>X%</b>", x=0.5, y=0.5, showarrow=False)])` kullanılır — bu Plotly'nin built-in özelliğidir, HTML/CSS ile yapılmaz.

Filtre Paneli Placeholder Stratejisi: `dmc.Select` bileşeni gerçek filtreleme mantığı olmadan eklendi. Bu, Task 3.4 callback altyapısı için "receiver" placeholder görevi görür — UI görsel tutarlılığı sağlar, callback olmadan işlevsel değildir. Placeholder data: cluster sayısına göre `[{"label": f"Cluster {i+1}", "value": f"c{i+1}"}]` ile üretilir.

Plotly Requirements Explicit Pin: `dash` paketi `plotly`'yi bağımlılık olarak çeker, ancak `requirements.txt`'e explicit yazmak imaj reproducibility'sini artırır. Kural: kullanılan her ana kütüphane `requirements.txt`'te açıkça listelenmeli.

### 9. Task 3.3 (Callback) Öğrenilen Dersler (Canlı Filtre & dcc.Store)

dcc.Store ile Sayfa-Düzeyinde Veri Kalıcılığı (Task 3.3 Callback): `layout()` fonksiyonu her çağrıldığında API verisini `dcc.Store(id="dc-detail-store", data=detail_raw)` ile browser'a yazar. Callback'ler bu veriyi `State("dc-detail-store", "data")` ile alır — böylece callback tetiklendiğinde tekrar API çağrısı yapılmaz. Bu pattern, render-time veriyi callback-time'a taşımanın doğru yoludur.

prevent_initial_call=True Zorunluluğu (Task 3.3 Callback): `@callback` dekoratörüne `prevent_initial_call=True` eklenmezse, sayfa ilk yüklendiğinde callback tetiklenir ve `dcc.Store` henüz dolu olmayabilir (None gelir). Bu, pre-rendered figürlerin boş figürlerle ezilmesine yol açar. `prevent_initial_call=True` → callback yalnızca kullanıcı etkileşimiyle tetiklenir; ilk render korunur.

_dash-dependencies ile Callback Doğrulama: `curl http://localhost:8050/_dash-dependencies` endpoint'i kayıtlı tüm callback'lerin input/output/state listesini JSON olarak döndürür. `grep` ile belirli bir `id`'nin output olarak kayıtlı olup olmadığı doğrulanabilir — bu, `dash.register_page()` import hatasının alternatif test yoludur.

Oransal Simülasyon Tasarımı (Task 3.3 Callback): API cluster bazlı kırılım sunmadığında "Cluster N" filtresi için deterministik ağırlık formülü: `usage_weight = N / sum(1..k)`, `cap_weight = 1/k`. Bu model; tüm cluster ağırlıklarının toplamının 1.0'a eşit olmasını, yüksek indeksli cluster'ların daha fazla yük taşımasını ve kapasitenin eşit bölünmesini garanti eder. Simülasyon parametresi tek yerden (`_apply_cluster_filter`) yönetilir.

Power Filtresi "Veri Yok" Pattern'i (Task 3.3 Callback): `power-source-filter` "vcenter" değerini aldığında bar grafiği 4 sütuna genişler (IBM Hosts, IBM VMs, vCenter Hosts=0, vCenter VMs=0) ve KPI metni "Veri Yok" olarak güncellenir. Bu pattern, API'den gerçek vCenter verisi gelmeden önce UI'ın "slot"ları görsel olarak hazırlamasını sağlar — gerçek veri geldiğinde yalnızca callback mantığı değiştirilir, layout değişmez.

### 10. Task 3.4 Öğrenilen Dersler (Auto-Refresh & Unified Callback)

"Zombisiz" Auto-Refresh Mimarisi (Task 3.4): `layout()` içinde `dcc.Interval(interval=900_000, n_intervals=0)` + `dmc.Box(id="...-content", children=initial_content)` kombinasyonu. `prevent_initial_call=True` ile callback ilk render'da tetiklenmez — pre-rendered içerik anında gösterilir. 15dk sonra interval `n_intervals=1`'e geçince callback tetiklenir → API'den taze veri → içerik güncellenir. Kullanıcı hiçbir "flash" veya yenileme görmez.

Birden Fazla Callback'ten Tek Unified Callback'e (Task 3.4): `Output("X", "prop")` aynı anda iki farklı callback'te kullanamaz — Dash `DuplicateCallbackError` fırlatır. Çözüm: tüm çakışan output'ları tek callback'e topla. Birden fazla `Input` olabilir; `ctx.triggered_id` ile hangi input'un tetiklediği belirlenir ve buna göre iş mantığı dallanır. Bu pattern hem "filtre değişimi" hem "interval tetiklenimi" senaryolarını tek yerde yönetir.

`ctx.triggered_id` ile Tetikleyici Ayırt Etme (Task 3.4): `from dash import ctx` ile import edilir. `ctx.triggered_id` string olarak tetikleyici bileşenin `id`'sini döndürür. Kullanım: `if ctx.triggered_id == "my-interval": fetch_fresh_data()`. Bu sayede tek callback birden fazla senaryoyu temiz biçimde yönetir — ayrı callback'ler yazmaya gerek kalmaz.

dc-code-store Pattern'i (Task 3.4): `dcc.Interval` callback'i sayfa `dc_code`'unu bilemez çünkü `dc_code` URL parametresinden `layout()` fonksiyonuna gelir ve callback'lere geçmez. Çözüm: `dcc.Store(id="dc-code-store", data=dc_code)` ile `dc_code`'u browser'a yaz; callback'te `State("dc-code-store", "data")` ile oku. Bu, URL parametrelerini callback'lere taşımanın standart Dash pattern'idir.

Sessiz Başarısızlık (Silent Fail) Pattern'i (Task 3.4): Auto-refresh callback'te API çağrısı `try/except Exception: pass` ile sarılır. Başarısız olunca mevcut `detail_data` (store'dan gelen State) aynen `Output("dc-detail-store", "data")` olarak döndürülür. Bu sayede API geçici olarak kapandığında grafiklerin son başarılı veriyle gösterilmesi sağlanır; kullanıcı boş ekran görmez.

### 11. Task 3.5 Öğrenilen Dersler (Executive Overview — Sparklines, Donut, Timeline)

go.Scatter Area Chart (Sparkline): `fill="tozeroy"` ile sıfır çizgisine kadar dolu alan, `shape="spline"` ile yumuşatılmış eğri oluşturulur. `mode="lines"` zorunlu — "markers" veya "lines+markers" kullanılırsa Sparkline görünümü bozulur. `fillcolor="rgba(r,g,b,0.12)"` ile hafif şeffaf gölge elde edilir; tam opak fill Premium görünümü bozar.

Sparkline Axes Gizleme: `xaxis=dict(visible=False)` + `yaxis=dict(visible=False)` ile eksenler ve tick'ler tamamen gizlenir. `margin=dict(l=0,r=0,t=0,b=0)` ile boşluk sıfırlanır — dcc.Graph'ın style={"height": "80px"} ile birlikte kullanılır.

dmc.Timeline v2.x API: `dmc.Timeline(children=[...], active=N, bulletSize=22, lineWidth=2, color="indigo")` — `children` keyword zorunlu (positional arg yerine). `dmc.TimelineItem(title=..., bullet=DashIconify(...), children=[...])` — `title` prop str veya Dash component alır; `dmc.Group([title_text, badge])` geçilebilir. `bullet` prop tam Dash component (DashIconify) alır.

Mock Zaman Serisi Determinizmi: API olmadan Sparkline için veri üretirken `random` kullanılmamalı — her render farklı değer üretir ve sayfayı tutarsız gösterir. Bunun yerine saat bazlı sabit liste (sabah/öğle/akşam mantıklı eğrisi) tercih edilir — deterministik, test edilebilir, gerçekçi.

CANLI Badge Pattern'i (Status Indicator): `dmc.Badge("CANLI", color="teal", variant="dot", size="lg")` ile sayfa başlığının yanına canlılık indikatörü eklenir. `variant="dot"` → yalnızca sol tarafta renkli nokta gösterir, dolu badge yerine minimal görünüm sağlar. `dmc.Group(justify="space-between")` ile başlık solda, badge sağda konumlanır.

### 12. Task 4.3 Öğrenilen Dersler (Unit Tests — pytest + DI İzolasyonu)

**Container Build Tutarsızlığı — Test Dosyaları (Task 4.3):**
Test dosyası yerel olarak güncellendiğinde (örn. conftest.py'e fix eklendi), container eski versiyonu taşımaya devam eder. `docker compose up --build` sadece uygulama kaynak kodunu yeniden build eder — test dosyaları `COPY services/query-service/ .` ile kopyalanır. Eğer container build'den önce test dosyası güncellenmediyse eski versiyon container'da kalır. Kural: Test dosyası değişikliği sonrası her zaman `docker compose up --build -d <service>` veya `docker cp` uygula; container'daki dosyayı `docker exec ... python -c "open(...).read()"` ile doğrula.

**httpx.Response + raise_for_status() — request Zorunluluğu (Task 4.3):**
`httpx.Response(status_code=200, content=...)` → `resp.raise_for_status()` → `RuntimeError: Cannot call raise_for_status as the request instance has not been set on this response.`
Kök neden: httpx, `Response._request` None ise `raise_for_status()` çağrısını reddeder. Test mock'larında `httpx.Response` oluşturulurken `request=` parametresi HER ZAMAN zorunludur:
```python
dummy_request = httpx.Request("GET", url)
resp = httpx.Response(200, content=b"[]", request=dummy_request)  # ← zorunlu
```
Bu kural httpx 0.28.x (test edilen versiyon) ile doğrulandı.

**pytest Nested Test Discovery Sorunu (Task 4.3):**
Container'da `/app/tests/tests/` nested dizini varsa pytest her test dosyasını iki kez keşfeder (toplam 2N test). Bu, eski Docker layer'larından, yanlış dizinde `pytest` çalıştırmaktan veya CI/CD artifact kalıntısından kaynaklanır. Tespit: `docker exec ... ls /app/tests/` ile nested dizin varlığını kontrol et. Çözüm: `shutil.rmtree('/app/tests/tests')` veya `pytest tests/ --ignore=tests/tests/` flag'i.

**FastAPI dependency_overrides ile Tam DI İzolasyonu (Task 4.3):**
`app.dependency_overrides[get_db_client] = lambda: mock_db_client` kalıbı; `get_db_client` dependency'sini (ve bunu kullanan tüm alt dependency'leri) override eder. Override, bağımlılık fonksiyonunu REFERANS olarak anahtar (key) alır — bu nedenle conftest.py ve router'ın aynı Python modülünden import etmesi zorunludur (aynı fonksiyon objesi). Lifespan (gerçek bağlantılar) çalışmaya devam eder; ancak endpoint handler'lar override'dan alır. Bu sayede testler gerçek servislere ihtiyaç duymadan çalışır.

**AsyncMock(spec=) + Attribute Assignment (Task 4.3):**
`client = AsyncMock(spec=httpx.AsyncClient); client.get = _mock_get` kalıbı doğru çalışır. `client.get` `_mock_get`'e (async fonksiyon) eşlenir; `await client.get(url)` doğrudan `_mock_get(url)` çalıştırır. `spec=` ile `side_effect=` veya `return_value=` ayarlamak gerekli değildir — direkt attribute assignment yeterlidir ve daha okunabilirdir.

---

## 🚦 Nasıl Güncellenir?
Bir hata ile karşılaşıldığında şu adımları izle:
Sorunun kök nedenini (Root Cause) analiz et.
Çözümü uygula.
Çözümün kalıcı olması için bir "yazılım kuralı" türet ve bu tabloya ekle.
skills.md dosyasında bu hatayı engelleyecek bir madde eksikse orayı da güncelle.