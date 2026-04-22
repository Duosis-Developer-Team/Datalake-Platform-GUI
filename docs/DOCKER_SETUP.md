## Amaç

Bu sayfa **Türkçe hızlı başlangıç** içindir. Güncel mimari (Dash + dört FastAPI servisi + `auth-db` + isteğe bağlı Redis ve harici PostgreSQL), ortam değişkenleri tabloları ve detaylı topoloji için mutlaka şu dokümana bakın: **[TOPOLOGY_AND_SETUP.md](TOPOLOGY_AND_SETUP.md)** (İngilizce).

---

## 1. Ortam dosyası

Kök dizinde tek örnek dosya vardır: **`.env.example`**.

```bash
cp .env.example .env
```

`.env` içinde en azından şunları gerçek ortamınıza göre doldurun:

- **`DB_*`**: Metrik/envanter PostgreSQL (API servisleri için). Container içinden host’taki bir veritabanına bağlanıyorsanız `localhost` yerine `host.docker.internal` veya erişilebilir IP kullanın.
- **`AUTH_*`**: Auth veritabanı (Compose’ta `auth-db`; lokal geliştirmede genelde `localhost:5433`).
- **`DATACENTER_API_URL`**, **`CUSTOMER_API_URL`**, **`QUERY_API_URL`**, **`ADMIN_API_URL`**: API’ler nerede çalışıyorsa (host portları veya Compose servis adları).

Tam değişken listesi: [`.env.example`](../.env.example).

---

## 2. Tam mikroservis yığını (önerilen)

Redis + üç veri API’si + `admin-api` + Dash `app` + `auth-db` birlikte açılır.

```bash
docker compose --profile microservice up -d
```

Profili kalıcı yapmak için `.env` içinde:

```env
COMPOSE_PROFILES=microservice
```

sonra:

```bash
docker compose up -d
```

Arayüz: `http://localhost:8050`

---

## 3. Harici PostgreSQL (metrics DB)

`microservice` profili **metrics/inventory PostgreSQL’i başlatmaz**; `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS` değerleri `.env` üzerinden **sizin sağladığınız** sunucuya işaret etmelidir.

---

## 4. İsteğe bağlı: Compose içinde yerel Postgres (`with-db`)

Sadece geliştirme / offline deneme için `docker-compose.yml` içindeki `db` servisi:

```bash
docker compose --profile with-db up -d
```

`.env` içinde `DB_HOST=db`, `DB_PORT=5432` ve `docker-compose.yml` içindeki `db` kimlik bilgileriyle uyumlu kullanıcı/şifre kullanın. Ayrıntı: [TOPOLOGY_AND_SETUP.md](TOPOLOGY_AND_SETUP.md).

---

## 5. Sadece Dash uygulaması (API’ler başka yerde)

API’ler host’ta çalışıyorsa `.env` içinde URL’leri `http://host.docker.internal:PORT` gibi erişilebilir adreslere ayarlayın; sonra örneğin:

```bash
docker compose up -d app
```

---

## 6. Legacy: tek imaj, yalnızca UI container’ı

Eski “tek konteyner + harici DB” senaryosu hâlâ mümkündür: imajı build edip `--env-file .env` ile çalıştırın. Üretim benzeri kurulum ve servis sırası için yine **[TOPOLOGY_AND_SETUP.md](TOPOLOGY_AND_SETUP.md)** ve kök **[`docker-compose.yml`](../docker-compose.yml)** referans alınmalıdır.

```bash
docker build -t datalake-platform-gui .
docker run --rm -p 8050:8050 --env-file .env datalake-platform-gui
```

---

## 7. Doğrulama ve sorun giderme

```bash
docker compose config
```

Port **8050** veya veritabanı bağlantı sorunları: [APP_RESTART.md](APP_RESTART.md) ve [TOPOLOGY_AND_SETUP.md](TOPOLOGY_AND_SETUP.md) içindeki troubleshooting bölümlerine bakın.

OpenTelemetry: [OTEL_COLLECTOR.md](OTEL_COLLECTOR.md).
