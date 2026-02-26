📜 Workflow Orchestration Rules (Senior Dev / Claude)
Bu dosya, Senior Developer (Claude) için çalışma prensiplerini, operasyonel standartları ve mimari disiplini belirler.

## 1. Context-Aware Development & Planning
Plan Mode Default: 3 adımdan uzun veya mimari karar gerektiren her görev için önce docs/todolist.md üzerinde bir plan sun ve onay al.
Architecture First: Herhangi bir kod değişikliğinden önce docs/architecture.md ve skeleton.md dosyalarını incele. Mevcut mikroservis yapısına sadık kal.
Stop & Re-plan: Eğer süreç beklenmedik bir yöne evrilirse (hata, kütüphane uyuşmazlığı vb.), dur ve stratejiyi güncelle; asla körü körüne devam etme.
Detailed Specs: Belirsizliği azaltmak için uygulama öncesinde detaylı spesifikasyonları önceden yaz.

## 2. Advanced Execution Strategy
Subagent Strategy: Ana bağlamı (main context) temiz tutmak için araştırma, paralel analiz veya keşif görevlerini alt ajanlara (subagents) devret.
Shared-First Approach: Yeni bir veri modeli oluşturulacaksa, önce shared/schemas/ altında tanımla.
DRY Principle: Tekrarı önlemek için yardımcı fonksiyonları shared/utils/ altında tutarak 'Don't Repeat Yourself' prensibini uygula.
Verification Before Done: Bir görevi tamamlamadan önce çalıştığını kanıtla. Logları kontrol et, testleri çalıştır ve Staff Engineer seviyesinde bir onaydan geçip geçemeyeceğini kendine sor.

## 3. Self-Improvement & Quality Loop
Lessons Learned: Herhangi bir kullanıcı düzeltmesinden veya kritik hatadan sonra docs/lessons.md dosyasını güncelle.
Pattern Prevention: Aynı hatayı tekrarlamamak için kendine kurallar yaz ve bu dersleri her oturum başında gözden geçir.
Demand Elegance: Karmaşık mantıkları docs/legacy/ altındaki dökümanlarla karşılaştırarak refactor et.
Staff Level Standards: Eğer çözüm "hacky" hissettiriyorsa, bildiğin her şeyi kullanarak en zarif ve sürdürülebilir çözümü uygula.
Autonomous Fixing: Bir hata raporu aldığında elini korkak alıştırma; loglara bak, kök nedeni bul ve kullanıcıdan yönlendirme beklemeden çöz.

## 4. Core Principles & Task Management
Simplicity First: Her değişikliği olabildiğince basit tut. Sadece gerekli olan kodlara dokunarak yan etki riskini minimize et.
No Laziness: Geçici yamalardan kaçın. Senior Developer standartlarında kök neden odaklı kalıcı çözümler üret.
Traceable Progress: İlerlemeyi docs/todolist.md üzerinden check-box'lar ile takip et ve her adımda yapılan değişikliklerin yüksek seviyeli özetini sun.

## 5. Acquired Skills & Architecture Patterns (Task 4.1 — 2026-02-25)

### Redis Time-Series: Sliding Window (Kayan Pencere) Mimarisi
- **Veri Yapısı:** Redis List kullanılarak kayan pencere zaman serisi oluşturulur.
  - `LPUSH <key> <json>` — yeni ölçüm her zaman listenin **soluna** eklenir (en yeni = index 0).
  - `LTRIM <key> 0 N-1` — listenin boyutunu N ile sınırlar; eski veriler otomatik düşer.
  - `LRANGE <key> 0 -1` — tüm listeyi okur; `reversed()` ile kronolojik sıraya çevrilir.
- **Atomik Yazma:** `redis.pipeline()` ile `LPUSH` + `LTRIM` çifti tek bir ağ turu (round-trip) içinde atomik olarak çalıştırılır. Yarım yazma riski sıfırdır.
- **Veri Formatı:** Her liste elemanı JSON string: `{"ts": "<ISO-8601 UTC>", "v": <float>}`. Bu format; zaman damgası bağımsızlığını ve kolay parse'ı garanti eder.
- **Pencere Parametreleri (Task 4.1):** max=30 nokta × 5dk = 2.5 saatlik kayan pencere. Proje gereksinimlerine göre kolayca ayarlanabilir.

### FastAPI Background Tasks: Lifespan ile Yönetilen Arka Plan Görevi
- **Başlatma:** `asyncio.create_task(coro)` ifadesi `lifespan` context manager'ının **`yield`'inden önce** çağrılır. Bu, task'ın HTTP isteklerinin kabulüyle tamamen eş zamanlı başlamasını sağlar.
- **Warm-Up Pattern:** Sonsuz döngüden (`while True: await asyncio.sleep(N)`) **önce** `await _take_sample(...)` çağrısı yapılır. Böylece servis ilk açılışında grafik verisi için interval süresini beklemek gerekmez.
- **Temiz Kapatma (Graceful Shutdown):** `task.cancel()` + `with suppress(asyncio.CancelledError): await task` kalıbı; task'ın iptal sinyalini yakalamasını ve kaynakları serbest bırakmasını sağlar. `suppress` importu `contextlib`'den gelir.
- **Kaynak Paylaşımı:** Background task, `app.state.db_client` ve `app.state.redis` üzerinden mevcut lifespan client'larını kullanır — yeni bağlantı açmaz. Bu; bağlantı havuzu (connection pool) disiplinini korur.
- **Hata Toleransı:** `_take_sample` içindeki tüm hata türleri (`httpx.RequestError`, `HTTPStatusError`, `KeyError`, `redis Exception`) yakalanır; warn log bırakılır ve döngü bölünmeden devam eder. Servis hiçbir zaman durmaz.

### Pydantic Sözleşmesi: TrendSeries + OverviewTrends
- `TrendSeries(labels: list[str], values: list[float])` — tek bir metriğin zaman serisini temsil eden generic DTO.
- `OverviewTrends` — birden fazla `TrendSeries`'i bir yanıt zarfında toplayan üst model. `shared/schemas/responses.py` içinde tanımlı; tüm katmanlar (query-service router, GUI api_client) bu sözleşmeye sadık kalır.

### Dash Sparkline: Gerçek Zamanlı Güncelleme
- `dcc.Interval(interval=300_000, n_intervals=0)` + `@callback(prevent_initial_call=False)` kombinasyonu; sayfa açılır açılmaz ve ardından her 5 dakikada bir veri çeker.
- `no_update` (Dash `dash.no_update`) ile sessiz degradation: API hata verirse veya Redis boşsa mevcut figür korunur, sayfa çökmez.
- ISO-8601 timestamp'leri `datetime.fromisoformat()` + `.strftime("%H:%M")` ile kullanıcı dostu saat etiketlerine dönüştürülür.

## 6. Acquired Skills & Architecture Patterns (Task 4.2 — 2026-02-25)

### Merkezi Loglama: Python Hiyerarşik Logging Mimarisi

- **Tek entry-point yapılandırma ilkesi:** `logging.basicConfig()` veya `setup_logger()` sadece servisin giriş noktasında (`main.py`, `app.py`) **bir kez** çağrılır. Modüllerde (providers, services, tasks) bu yapılandırma tekrarlanmaz.
- **`getLogger(__name__)` pattern'i korunur:** Her modül `logging.getLogger(__name__)` ile kendi child logger'ını açar. Python'un hiyerarşik yapısı, parent logger'daki format/handler'ı otomatik olarak tüm child'lara yayar. Bu nedenle her dosyaya `setup_logger()` veya `basicConfig()` yazmak **yanlıştır ve duplicate log üretir**.
- **Named logger (root değil):** `setup_logger("query-service")` → `logging.getLogger("query-service")` döner. `src.tasks.sampler` gibi child logger'lar propagation zinciri sayesinde parent'a ulaşır ve aynı formatı kullanır.
- **Idempotency:** `if logger.handlers: return logger` koruması; Dash hot-reload veya test ortamlarında `setup_logger()` birden fazla çağrılsa bile duplicate handler eklenmez.
- **stdout StreamHandler:** Docker/Kubernetes log sürücüleri stdout'u toplar. `stderr` yalnızca kritik sistem hataları için ayrılır. `sys.stdout` kullanımı container log izlemeyle tam uyumludur.
- **LOG_LEVEL env override:** `os.getenv("LOG_LEVEL", "INFO")` → production'da INFO, geliştirme/debug ortamında `DEBUG` seviyesi `.env` dosyasından ayarlanabilir. Kod değişikliği gerekmez.

### API İstemcisi Hata Yönetimi Pattern'i (gui-service/api_client.py)
- **Granüler exception yakalama:** `requests.exceptions.Timeout`, `HTTPError`, `RequestException` ayrı `except` bloklarında yakalanır — böylece log mesajı hata türüne özel bilgi içerir (`"zaman aşımı"` vs `"HTTP 503"` vs `"bağlantı reddedildi"`).
- **Re-raise stratejisi:** `logger.error(...)` + `raise` kombinasyonu: hata loglanır, exception yeniden fırlatılır. Çağıran Dash callback `except Exception: return no_update` ile sessizce devam eder. Bu pattern "log-and-rethrow" olarak adlandırılır ve katmanlar arası hata sorumluluğunu net biçimde ayırır.
- **Timeout sabiti:** `_TIMEOUT = 120` — query-service'in cold start süresine (~74s) güvenli marj bırakılır. Tek bir sabit; 3 fonksiyon aynı değeri kullanır (DRY).

