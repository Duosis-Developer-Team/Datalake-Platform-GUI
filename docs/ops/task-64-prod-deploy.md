# TASK-64 (AI release note'lar) — prod'a çıkarma

dc13 test ortamında 2026-08-03'te uçtan uca doğrulandı. Bu dosya aynı işi prod'da
sırasıyla yapmak için.

Gereken commit: `8553cc6f` veya sonrası (`origin/main`).

## 0. Önce: prod nasıl koşuyor?

Adımların çoğu aynı, yalnızca 2. adım (image) ikiye ayrılıyor:

- **docker compose** ile koşuyorsa (dc13'teki gibi) → 2A
- **Kubernetes** ile koşuyorsa (`k8s/` manifestleri) → 2B

Emin değilsen prod host'ta `docker ps | grep bulutistan` çalıştır. Container'lar
çıkıyorsa compose'dur.

## 1. Kod

    cd <repo dizini>          # dc13'te: /opt/Datalake-Platform-GUI
    git pull
    git log --oneline -1      # 8553cc6f veya sonrası olmalı

## 2A. Image — docker compose ortamı

İki servis birden gerekiyor. Yalnız frontend'i atarsan "Yeniden üret" 404 alır.

    docker compose --profile microservice up -d --build app chatbot-api

`--profile microservice` şart: `app` servisi profil altındaki `redis`'e
`depends_on` veriyor, profilsiz `docker compose up` "undefined service redis"
ile patlar.

## 2B. Image — Kubernetes ortamı

`k8s/frontend/deployment.yaml:19-20` ve `k8s/chatbot-api/deployment.yaml:19-20`
`image: ...:latest` + `imagePullPolicy: IfNotPresent` kullanıyor. Bu yüzden
**`kubectl rollout restart` yeni image'ı ÇEKMEZ** — node'daki eski `latest`
katmanını kullanmaya devam eder. SHA'lı tag ile açıkça set et:

    SHA=$(git rev-parse --short HEAD)
    kubectl set image deploy/bulutistan-frontend    frontend=bulutistan-frontend:$SHA
    kubectl set image deploy/bulutistan-chatbot-api chatbot-api=bulutistan-chatbot-api:$SHA
    kubectl rollout status deploy/bulutistan-frontend
    kubectl rollout status deploy/bulutistan-chatbot-api

Hiçbir uygulama manifesti `namespace:` bildirmiyor (yalnızca `k8s/monitoring/*`
bildiriyor: `bulutistan-monitoring`). Prod başka bir namespace kullanıyorsa her
komuta `-n <namespace>` ekle.

## 3. Elle yapılmayan iki şey

Bunlar için komut çalıştırma, kendiliğinden oluyor:

- **DB migration**: auth DB v5 (`sql/migrations/004_release_notes.sql`) container
  açılırken uygulanıyor (`src/auth/auth_db_migrations.py:168`).
- **Yetki**: `sec:settings_platform_versions:regenerate` katalogda
  (`src/auth/permission_catalog.py:523`) ve başlangıçta DB'ye senkronlanıyor.
  Admin rolü tüm yetkileri otomatik alıyor.

## 4. LLM anahtarı — var mı?

Değeri ekrana basmadan kontrol:

    docker exec bulutistan-chatbot-api sh -c '[ -n "$BULUTISTAN_LLM_API_KEY" ] && echo VAR || echo YOK'

k8s'te:

    kubectl get secret bulutistan-llm-secret -o name

**VAR / secret duruyorsa** yapacak bir şey yok; chatbot zaten aynı anahtarı
kullanıyor.

**YOK ise** anahtarı `.env.local`'a tek satır ekle (`docker-compose.yml:544` bu
dosyayı chatbot-api'ye veriyor), sonra `docker compose --profile microservice
restart chatbot-api`. **`.env`'e ASLA yazma** — `.gitignore`'da adı geçse de bu
repoda `.env` git tarafından takip ediliyor, oraya yazılan secret commit'lenir.
Kontrol: `git ls-files --error-unmatch .env` (`git check-ignore` takipli
dosyalarda yanıltır).

Anahtar olmadan panel yine çalışır; not metnini model değil, commit'lerden
üretilen deterministik özet yazar.

## 5. Backfill — atlanırsa özellik bozuk görünür

Eski sürümlerin notu yok. Çalıştırmazsan panelde her kart "Bu sürümde kullanıcıya
dönük değişiklik yok." der.

Önce kuru prova — DB'ye dokunmaz, hiçbir kurulum istemez:

    python3 scripts/backfill_platform_versions.py --dry-run

Sonra gerçeği. Script hem `git log` (host'ta var) hem `psycopg2` (yalnızca
container'da var) istiyor; **container'da çalıştırılamaz**, çünkü `.git`
`.dockerignore`'un ilk satırı ve `Dockerfile:19-22` `git` binary'sini kurmuyor.
Bu yüzden host'a iki paket:

    apt install -y python3-psycopg2 python3-dotenv
    python3 scripts/backfill_platform_versions.py

`Backfilled N releases.` yazmalı. Script idempotent (`ON CONFLICT (version) DO
NOTHING` + mevcut değişiklik satırı varsa atlama), iki kez çalıştırmak zararsız.

DB ayarı gerekmiyor: `src/auth/config.py:11-15` varsayılanları `localhost:5433`
ve compose auth-db'yi `5433:5432` ile host'a açıyor. Hedef `5433`, `5432` değil —
`5432` başka bir Postgres.

## 6. Doğrulama

    curl -s localhost:8080/health

    curl -s -o /dev/null -w '%{http_code}\n' \
      -X POST localhost:8080/api/v1/release-notes/generate \
      -H 'Content-Type: application/json' -d '{}'

**422** = route ayakta, image yeni. **404** = chatbot-api eski image'da.
(Container içinden adres `http://chatbot-api:8000`, host'tan `localhost:8080`.)

Sonra panelde `Administration > Platform > Versions`, bir sürümde
**"Yeniden üret"**. Sekme başlığı "Updating..." olur — Dash'in callback
göstergesi, donma değil. Üç deneme × 60 sn, yani en kötü ~3 dakika.

Canlı log:

    docker logs -f --tail 50 datalake-platform-gui-app 2>&1 | grep -i release

## 7. Sorun çıkarsa

**`unparsable`** — model cevabı JSON'a çevrilemedi. Log artık `chars=` ve
`tail=` basıyor: kuyruk `}` ile bitmiyorsa çıktı kesilmiş demektir, sebep
`RELEASE_NOTE_MAX_TOKENS` (varsayılan 4000). Bu hata dc13'te `max_tokens=1200`
ile görülmüştü ve yalnızca uzun sürümlerde çıkıyordu.

**`not_configured`** — 4. adımdaki anahtar yok.

**Maddeler commit başlığı gibi okunuyorsa** — prompt'a kural değil ÖRNEK ekle
(`services/chatbot-api/app/routers/release_notes.py`, `_SYSTEM`). Kural listesi
tek başına bu davranışı değiştirmedi.

Hiçbir hata kullanıcıya yansımaz: her yol deterministik nota düşer, `body` boş
kalmaz.

## Not: release ingest token gerekmiyor

Üretme/onaylama döngüsünün tamamı panelde ve pod içinde kapanıyor. Token yalnızca
release'i dışarıdan açan script'ler için (`scripts/new_release.py`,
`scripts/regenerate_release_notes.py`). Bkz. `release-ingest-token.md`.
