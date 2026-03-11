# Bulutistan Dashboard — Mikro Servis Dönüşümü: Öğretiler (Lessons Learned)

> Bu dosya, mevcut kod tabanından çıkarılan kritik öğretileri ve yeni yapıya aktarılırken
> KESİNLİKLE korunması gereken davranışları belgeler.
> Executer her göreve başlamadan önce bu dosyayı OKUMAK ZORUNDADIR.

---

## ÖGRT-001: _DC_CODE_RE Regex Yapısı — DOKUNULMAZ

**Kaynak:** `src/services/db_service.py`, satır 19

**Mevcut pattern:**
```python
_DC_CODE_RE = re.compile(r'(DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+)', re.IGNORECASE)
```

**Neden kritik:**
IBM Power sunucularının host/VM isimleri düzensiz ve öngörülemez formatlarda geliyor.
Örneğin bir IBM sunucu adı `srv-DC14-hmc01` veya `ICT11-vios-prod` gibi olabilir.
Bu regex, sunucu adı string'inden datacenter kodunu (DC14, ICT11 vb.) çıkarmak için kullanılıyor.

**Kullanım yerleri:**
- `_fetch_all_batch()` → `_extract_dc()` iç fonksiyonu (satır 548-554)
- IBM host, VIOS, LPAR, memory ve CPU batch sonuçlarını DC bazında gruplama

**Aktarım kuralları:**
1. Regex pattern'i birebir korunmalı — tek bir karakter bile değiştirilmemeli
2. `re.IGNORECASE` flag'i kaldırılmamalı
3. Yeni DC prefixleri eklenirse (örn: `KZ\d+`) pattern'e eklenmeli, mevcut gruplar silinmemeli
4. Pattern'in test edilmesi için aşağıdaki girdiler referans olarak kullanılmalı:
   - `"srv-DC14-hmc01"` → `DC14`
   - `"ICT11-vios-prod"` → `ICT11`
   - `"AZ11-lpar-db"` → `AZ11`
   - `"UZ11-power-app"` → `UZ11`
   - `"random-server-name"` → `None` (eşleşme yok)

---

## ÖGRT-002: ThreadPoolExecutor Paralel Batch Sorgu Mekanizması — KRİTİK

**Kaynak:** `src/services/db_service.py`, `_fetch_all_batch()` metodu (satır 475-722)

**Mevcut çalışma şekli:**
```
4 ayrı thread → 4 ayrı DB bağlantısı → 4 sorgu grubu paralel çalışır
├── Thread 1: Nutanix sorguları (6 batch query)
├── Thread 2: VMware sorguları (5 batch query)
├── Thread 3: IBM sorguları (5 batch query)
└── Thread 4: Energy sorguları (4 batch query)
```

**Neden kritik:**
Sıralı çalışma ~90 ayrı DB roundtrip gerektirirken, bu yapı ~10 batch sorgu ile aynı veriyi çekiyor.
Performans farkı: sıralı ~12s → paralel ~3s (4x hızlanma).

**Aktarım kuralları:**
1. Mikro servis yapısında her servis kendi batch sorgularını paralel çalıştırabilir
2. Ancak `dc-service` IBM verisini `platform-service`'ten çekerken aynı paralel mantık uygulanmalı
3. `ThreadPoolExecutor(max_workers=4)` ayarı: her servisin kendi thread sayısı DB bağlantı pool boyutunu aşmamalı
4. `as_completed` yerine `.result()` ile sıralı bekleme kullanılıyor — bu bilinçli bir tercih; hata izolasyonu için uygun

---

## ÖGRT-003: IBM Veri Aggregasyonunun Python Tarafında Yapılması

**Kaynak:** `src/services/db_service.py`, satır 547-608

**Mevcut davranış:**
IBM sorguları PostgreSQL'de `regexp_matches` KULLANMIYOR.
Ham satırlar (host name, metrik değerler) veritabanından çekilir.
DC kodu çıkarma ve gruplama TAMAMEN Python tarafında `_DC_CODE_RE` ile yapılır.

**Neden bu şekilde:**
PostgreSQL'deki IBM tablosunda DC kodu ayrı bir kolon olarak tutulmuyor.
Sunucu adı string'i içinden regex ile çıkarılıyor.
Server-side regex (`regexp_matches`) performans açısından sorunluydu ve kaldırıldı.

**Aggregasyon mantığı (korunmalı):**
- `ibm_h`: Host isimleri DC bazında `set()` ile toplanır → `len()` ile unique sayım
- `ibm_vios`: VIOS isimleri DC bazında `set()` ile toplanır → `len()` ile unique sayım
- `ibm_lpar`: LPAR isimleri DC bazında `set()` ile toplanır → `len()` ile unique sayım
- `ibm_mem`: Memory değerleri DC bazında `list()` ile toplanır → ortalaması alınır
- `ibm_cpu`: CPU değerleri DC bazında `list()` ile toplanır → ortalaması alınır

**Aktarım kuralları:**
1. `set()` ile unique sayım mantığı korunmalı — `list()` ile değiştirilmemeli (duplikasyon hatası verir)
2. Memory ve CPU için ortalama (`sum / len`) mantığı korunmalı — toplam değil, ortalama gösteriliyor
3. Bu aggregasyon mantığı yeni `platform-service` veya `dc-service` içinde aynen bulunmalı

---

## ÖGRT-004: Birim Dönüşüm Formülleri — BİREBİR AKTARILMALI

**Kaynak:** `src/services/db_service.py`, `_aggregate_dc()` metodu (satır 329-424)

**Kritik dönüşümler:**

| Platform | Metrik  | Kaynak Birim      | Dönüşüm            | Hedef   |
|----------|---------|--------------------|---------------------|---------|
| Nutanix  | Memory  | TiB                | × 1024              | GB      |
| VMware   | Memory  | Bytes              | ÷ 1024³             | GB      |
| Nutanix  | Storage | TB                 | Olduğu gibi         | TB      |
| VMware   | Storage | Bytes              | ÷ 1024⁴             | TB      |
| Nutanix  | CPU     | GHz                | Olduğu gibi         | GHz     |
| VMware   | CPU     | Hz                 | ÷ 1,000,000,000     | GHz     |
| IBM+vC   | Energy  | Watt               | ÷ 1000              | kW      |

**Aktarım kuralları:**
1. Bu dönüşüm formülleri mikro-servis'e tam olarak kopyalanmalı
2. Birim testi: bilinen girdiler ile beklenen çıktılar karşılaştırılmalı
3. `float()` ile type coercion korunmalı — DB'den `Decimal` tipi gelebilir

---

## ÖGRT-005: Cache Stratejisi ve TTL Senkronizasyonu

**Kaynak:** `src/services/cache_service.py` + `src/services/scheduler_service.py`

**Mevcut strateji:**
- Cache TTL: 20 dakika (`DEFAULT_TTL = 1200`)
- Scheduler yenileme: 15 dakika (`REFRESH_INTERVAL_MINUTES = 15`)
- TTL > Scheduler aralığı → stale veri asla sunulmaz (5 dakika güvenlik marjı)

**Cache key formatı (korunmalı):**
```
dc_details:{dc_code}:{start_date}:{end_date}
all_dc_summary:{start_date}:{end_date}
global_dashboard:{start_date}:{end_date}
global_overview:{start_date}:{end_date}
customer_assets:{customer_name}:{start_date}:{end_date}
```

**Aktarım kuralları:**
1. Redis'e geçişte TTL > Scheduler aralığı kuralı korunmalı
2. Cache key formatı mikro servisler arası tutarlı olmalı
3. `warm_cache()` → startup sırasında 7 günlük veri yüklenir (blocking)
4. `warm_additional_ranges()` → startup sonrası 30 gün ve önceki ay yüklenir (background)
5. Scheduler `misfire_grace_time=60` ayarı korunmalı — container restart sonrası kaçırılan job'lar tolere edilir

---

## ÖGRT-006: DC Lokasyon Eşleme ve Fallback Listesi

**Kaynak:** `src/services/db_service.py`, satır 24-42

**Mevcut davranış:**
- DC listesi dinamik olarak `loki_locations` tablosundan çekilir
- Sorgu başarısız olursa `_FALLBACK_DC_LIST` kullanılır
- İki sorgu denenir: önce status filtreli (`DC_LIST`), sonra filtresiz (`DC_LIST_NO_STATUS`)

**Bilinen veri sorunu:**
`DC_LOCATIONS` sözlüğünde `ICT11` anahtarı iki kez tanımlı (satır 39-40):
```python
"ICT11": "Almanya",
"ICT11": "İngiltere",  # Bu satır öncekini ezer
```
Python dict davranışı gereği son değer ("İngiltere") geçerlidir.
Bu bir veri sorunu olabilir — mikro servis dönüşümünde doğrulanmalıdır.

**Aktarım kuralları:**
1. Fallback mekanizması korunmalı — DB erişilemezken dashboard çökmemeli
2. `_canonical_dc()` fonksiyonu (satır 611-625) DC isim eşleme mantığını içerir ve korunmalıdır
3. ICT11 duplikasyonu kontrol edilmeli

---

## ÖGRT-007: Customer Resource Sorgu Pattern'leri

**Kaynak:** `src/services/db_service.py`, `get_customer_resources()` (satır 909-1225)

**Grafana uyumlu pattern'ler:**
```
Intel (VMs):        "{customer_name}-%"     → prefix + tire
Power/Backup:       "{customer_name}%"      → basit prefix
Storage/NetBackup:  "%{customer_name}%"     → contains
Zerto:              "{customer_name}%-%"    → prefix + tire pattern
```

**Aktarım kuralları:**
1. Bu LIKE pattern'leri Grafana dashboard'larıyla uyumlu — değiştirilmemeli
2. `customer-service` içinde birebir kullanılmalı
3. Yeni müşteri eklendiğinde pattern mantığı test edilmeli

---

## ÖGRT-008: _EMPTY_DC Fallback Yapısı

**Kaynak:** `src/services/db_service.py`, `_EMPTY_DC()` fonksiyonu (satır 45-66)

**Mevcut davranış:**
DB erişilemediğinde sıfırlanmış bir DC detay dict'i döner.
Dashboard çökmek yerine boş/sıfır değerlerle render edilir.

**Aktarım kuralları:**
1. Her mikro servisin kendi "boş yanıt" şablonu olmalı
2. API gateway, downstream servis timeout'unda bu şablonu cache'ten sunabilmeli
3. Frontend asla `null` veya `undefined` almamalı — her zaman yapısal tutarlı JSON dönmeli

---

## Yeni Öğreti Ekleme Formatı

```markdown
## ÖGRT-XXX: [Başlık]

**Kaynak:** [dosya yolu, satır numaraları]

**Mevcut davranış:**
[Ne yapıyor, nasıl çalışıyor]

**Neden kritik:**
[Neden bu şekilde yapılmış, alternatif neden reddedilmiş]

**Aktarım kuralları:**
1. [Kural 1]
2. [Kural 2]
```
