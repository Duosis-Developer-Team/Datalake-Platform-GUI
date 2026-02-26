## Amaç

Bu doküman, `Datalake-Platform-GUI` uygulamasını **Docker** ve **Docker Compose** kullanarak çalıştırmak için gereken adımları açıklar.  
İki temel senaryo desteklenir:

- **Harici PostgreSQL veritabanına bağlanan uygulama container’ı**
- **Docker Compose içinde ek bir PostgreSQL (`db`) servisi ile çalışan uygulama container’ı**

Uygulama, container içinde **gunicorn** ile WSGI modunda (`app:server`) çalıştırılır.

---

## Ön Gereksinimler

- Docker Engine (Windows için Docker Desktop veya WSL2 üzerinden Docker)
- Docker Compose (Docker Desktop ile birlikte gelir, `docker compose` komutu)
- Bu repository’nin lokal klonu

```bash
git clone <REPO_URL>
cd Datalake-Platform-GUI
```

> Not: Production benzeri çalıştırma için ayrıca harici PostgreSQL sunucusu veya Compose içindeki `db` servisi gerekir.

---

## Ortam Değişkenleri (`.env`)

Uygulama, veritabanı bağlantı bilgisini ortam değişkenlerinden okur ve `app.py` içinde `.env` dosyası otomatik yüklenir.

Kullanılabilen değişkenler:

- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASS`

### 1. `env.example` Kullanımı

Root dizinde örnek bir dosya vardır: `env.example`.

Bu dosyayı `.env` olarak kopyalayın:

```bash
cp env.example .env
```

Ardından kendi ortamınıza göre düzenleyin.

#### Harici PostgreSQL için örnek

- `env.example` içindeki **“External PostgreSQL database (existing server)”** bloğunu kullanın.
- Örnek:

```env
DB_HOST=10.134.16.6
DB_PORT=5000
DB_NAME=bulutlake
DB_USER=datalakeui
DB_PASS=changeme
```

Değerleri kendi gerçek veritabanı bilgilerinizle değiştirin.

#### Docker Compose içi PostgreSQL (`db` servisi) için örnek

- `env.example` içindeki **“Docker Compose PostgreSQL service ("db")”** bloğunu açın (yorumdan çıkarın) ve harici DB bloğunu gerekirse yorum satırı yapın.

```env
DB_HOST=db
DB_PORT=5432
DB_NAME=bulutlake
DB_USER=datalakeui
DB_PASS=changeme
```

> Not: Bu değerler, `docker-compose.yml` içindeki `db` servisi ile uyumludur (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`).

---

## Docker İmajı Oluşturma

Root dizindeki `Dockerfile`, uygulamayı production’a yakın bir şekilde paketler:

- Baz imaj: `python:3.10-slim`
- Sistem bağımlılıkları: `build-essential`, `libpq-dev`
- Python bağımlılıkları: `requirements.txt`
- Çalıştırma komutu: `gunicorn app:server --bind 0.0.0.0:8050 --workers 4`

İmajı build etmek için:

```bash
docker build -t datalake-platform-gui .
```

Build başarılı ise imaj listede görünecektir:

```bash
docker images | grep datalake-platform-gui
```

---

## Senaryo 1: Sadece Uygulama Container’ı + Harici PostgreSQL

Bu senaryoda:

- PostgreSQL zaten başka bir yerde çalışıyor (örnek: kurumsal veritabanı).
- Container sadece web arayüzünü (Dash) içeriyor.

### Adımlar

1. `.env` dosyanızı harici PostgreSQL bilgileriyle doldurun (bkz. yukarıdaki bölüm).
2. Docker imajını build edin (bir kez yeterli):

   ```bash
   docker build -t datalake-platform-gui .
   ```

3. Container’ı doğrudan `docker` ile çalıştırın:

   ```bash
   docker run --rm -p 8050:8050 --env-file .env datalake-platform-gui
   ```

4. Tarayıcıdan erişin:

   - `http://localhost:8050`

Container’ı durdurmak için çalıştığı terminalde `Ctrl+C` yeterlidir.

> Not: Bu şekilde çalıştırırken `docker-compose.yml` kullanmak zorunda değilsiniz; tek imaj / tek container senaryosu için yeterlidir.

---

## Senaryo 2: Docker Compose ile Uygulama + Harici PostgreSQL

Bu senaryoda da veritabanı harici; ancak uygulamayı `docker-compose.yml` içindeki `app` servisi üzerinden yönetmek istersiniz.

### Adımlar

1. `.env` dosyanızı harici PostgreSQL bilgileriyle doldurun.
2. Compose ile build ve run:

   ```bash
   docker compose build app
   docker compose up app
   ```

3. Tarayıcıdan erişim:

   - `http://localhost:8050`

4. Durdurmak için:

   ```bash
   docker compose down
   ```

> Not: Bu senaryoda `db` servisi kullanılmaz; sadece `app` servisi ayağa kaldırılır.

---

## Senaryo 3: Docker Compose ile Uygulama + Dahili PostgreSQL (`db` Servisi)

Bu senaryoda hem uygulama hem de PostgreSQL aynı `docker-compose.yml` içinde tanımlıdır:

- `app` servisi: Dash / gunicorn uygulaması
- `db` servisi: Resmi `postgres:15` imajı

### 1. Ortam Değişkenleri

`.env` dosyanızı aşağıdaki gibi ayarlayın:

```env
DB_HOST=db
DB_PORT=5432
DB_NAME=bulutlake
DB_USER=datalakeui
DB_PASS=changeme
```

`docker-compose.yml` içindeki `db` servisi şu ortam değişkenlerini kullanır:

- `POSTGRES_DB=bulutlake`
- `POSTGRES_USER=datalakeui`
- `POSTGRES_PASSWORD=change_me`

Bu iki tarafın (app ve db) birbiriyle uyumlu olması gerekir. İsterseniz hem `.env` hem de `docker-compose.yml` içindeki değerleri birlikte güncelleyebilirsiniz.

### 2. Servisleri Ayağa Kaldırma

`db` servisi, `profiles: ["with-db"]` altında işaretlenmiştir. Bu profili etkinleştirerek çalıştırın:

```bash
docker compose --profile with-db up
```

Bu komut:

- `db` servisindeki PostgreSQL container’ını başlatır.
- `app` servisi için imaj yoksa build eder, sonra uyguyu çalıştırır.

Ardından tarayıcıdan erişin:

- `http://localhost:8050`

Servisleri arka planda (detached) çalıştırmak isterseniz:

```bash
docker compose --profile with-db up -d
```

Durdurmak için:

```bash
docker compose --profile with-db down
```

Veri kalıcılığı için `pgdata` adlı named volume kullanılır (PostgreSQL data dizini).

---

## Temel Smoke Test Komutları

Geliştirme veya CI ortamında hızlı bir doğrulama için aşağıdaki komutlar önerilir:

1. Dockerfile geçerliliği ve bağımlılıklar:

   ```bash
   docker build -t datalake-platform-gui .
   ```

2. Compose dosyası söz dizimi ve birleşik yapı:

   ```bash
   docker compose config
   ```

3. Sadece uygulama servisini harici DB ile ayağa kaldırma:

   ```bash
   docker compose up app
   ```

4. Uygulama + dahili db profili ile ayağa kaldırma:

   ```bash
   docker compose --profile with-db up
   ```

> Not: Uygulama açıldıktan sonra `http://localhost:8050` adresine erişebiliyor olmanız temel smoke test olarak yeterlidir. DB bağlantı problemlerinde loglar üzerinden hata mesajlarını kontrol edin.

---

## Sorun Giderme

- **Port çakışması (8050 veya 5432 zaten kullanımda)**  
  - Windows’ta ilgili portu kullanan prosesleri kapatın veya `docker-compose.yml` içindeki port eşlemesini değiştirin (örneğin `8051:8050`).

- **DB bağlantı hatası (connection refused, timeout, authentication failed)**  
  - `.env` içindeki `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS` değerlerini kontrol edin.
  - Harici DB kullanıyorsanız container’ın bu adrese network üzerinden erişebildiğinden emin olun.
  - Dahili `db` servisini kullanıyorsanız, profilin aktif olduğuna ve container’ın sağlıklı çalıştığına bakın:

    ```bash
    docker compose --profile with-db ps
    docker compose logs db
    ```

- **Uygulama açılıyor ama sayfalar boş / veri yok**  
  - Genellikle DB’de veri olmaması veya beklenen şemaların eksik olması ile ilgilidir.
  - Gerekli tablolar ve görünümler için repository içindeki SQL dokümanlarını (`docs/All Tables` altındaki dosyalar) inceleyip veritabanına uygulayın.

---

## Geliştirme İpuçları

- Kod üzerinde sık değişiklik yapıyorsanız, her değişiklikte yeniden build etmek yerine:
  - Geliştirme sırasında **container dışında** (`python app.py`) çalışmaya devam edip Docker’ı sadece test/deploy aşamasında kullanabilirsiniz.
  - Alternatif olarak volume bind ile source kodu container’a mount edip, container içinde `python app.py` gibi bir komut ile debug modunda çalıştıracak ayrı bir Dockerfile/override compose tanımlayabilirsiniz (bu dokümanın kapsamı dışında bırakıldı).

---

Bu yapı ile uygulamayı hem lokal geliştirme ortamında hem de production’a yakın bir şekilde Docker üzerinden yönetebilirsiniz. Harici veritabanı ve Compose içi veritabanı senaryoları arasında `.env` ve `docker compose` komutları ile kolayca geçiş yapabilirsiniz.

