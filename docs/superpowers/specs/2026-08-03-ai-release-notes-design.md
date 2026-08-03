# TASK-64 (faz 2) — AI ile üretilen release note'lar + panel yenilemesi

**Tarih:** 2026-08-03
**Repo:** Datalake-Platform-GUI
**Branch:** `worktree-task-64-ai-release-notes` (`origin/development`'tan)
**Durum:** Tasarım onaylandı, spec incelemesi bekliyor
**Öncülü:** `docs/superpowers/specs/2026-07-23-application-versioning-panel-design.md`

## Problem

TASK-64'ün ilk fazı Administration altına bir sürüm paneli getirdi. Panel çalışıyor
ama iki eksiği var:

1. **Kartlarda ham git commit satırları görünüyor.** `feat(gui): add lazy toggle to
   net interface tab` gibi. Bu yazı geliştirici için bile zar zor okunuyor, platform
   kullanıcısı için hiçbir şey ifade etmiyor.
2. **İleriye dönük kayıt yok.** Panel 24 sürümlük geçmişi `scripts/backfill_platform_versions.py`
   ile git log'undan bir kere üretti. Yeni bir deploy yapıldığında ortada sürüm kaydı
   oluşturan hiçbir mekanizma yok — `service_deployments` satırları düşüyor ama
   `platform_releases`'e hiçbir şey yazılmıyor.

Ayrıca panelin görsel düzeni 24 sürüm için tasarlanmamış: hepsi aynı anda, aynı
boyutta, sol tarafta uzayıp giden bir timeline çizgisiyle alt alta duruyor.

## Hedefler

1. **Okunabilir notlar.** Her sürümün altında "Neler Eklendi / Neler Düzeltildi"
   formatında, insan diliyle yazılmış maddeler. Ham commit satırları kartta görünmez.
2. **Tek komutla kayıt.** Deploy sonrası `python scripts/new_release.py` çalıştırılır;
   son kayıttan bu yana atılan commit'ler sunucuya gider, sürüm açılır, notu yazılır.
3. **Uydurma yok.** Modelin yazdığı her madde en az bir gerçek commit'e dayanmak
   zorunda; dayanmayan madde koda düşmeden silinir.
4. **Geçmiş de düzelsin.** Mevcut 24 sürüm bir kere aynı işlemden geçer.
5. **Panel profesyonel görünsün.** Canlı sürüm öne çıkar, geçmiş sakin bir liste olur.

## Kapsam dışı (YAGNI)

- **GitHub API'den otomatik commit çekme.** Konuşuldu, bilinçli olarak ertelendi.
  Ayrı onay sürecine tabi. Bu tasarım onun önünü kapatmıyor: ingest endpoint'i commit
  listesini gövdede alıyor, listeyi kimin topladığını umursamıyor — ileride bir
  GitHub katmanı aynı endpoint'e yazar.
- **Not metnini elle düzenleme.** "Yeniden üret" var, serbest metin editörü yok.
- **Çoklu dil.** Notlar Türkçe cümle + İngilizce terim. Tek dil.
- **Sürümü geri alma / deploy tetikleme.** Panel okuma amaçlı kalır.
- **CI build-arg yaması** (`docs/superpowers/patches/task-64-ci-build-args.patch`).
  Seçenek 1 (script) seçildiği için gereksizleşti; yama dosyası duruyor ama bu işin
  parçası değil.

## Dil ve ton kuralı

- Cümle Türkçe, teknik terim İngilizce: *"Chatbot yanıtlarında streaming açıldı."*
- Hedef kitle karışık: iç geliştirici ekip + iç platform kullanıcıları.
- Detaylı ama boğucu değil. Bir madde bir cümle.
- Commit prefix'leri (`feat:`, `fix(gui):`) ve sha'lar madde metninde geçmez.

---

## Mimari

### Neden bu şekil

Üç zorlayıcı gerçek tasarımı belirledi — üçü de manifest/kod okunarak doğrulandı:

1. **admin-api production'da yok.** `k8s/` altında `admin-api` manifesti yok,
   `.github/workflows/main.yml` onu build etmiyor (yalnızca datacenter-api,
   customer-api, query-api, chatbot-api, Frontend). admin-api sadece
   `docker-compose.yml`'de, yani local geliştirmede var.
2. **Bu yüzden production'da GUI auth DB'ye doğrudan yazıyor.**
   `k8s/frontend/configmap.yaml`'de `ADMIN_API_URL` yok →
   `src/services/admin_client.py:18`'de `_USE_API = False` →
   okuma/yazma `src/auth/versions_crud.py` üzerinden gidiyor.
   **Üretim kodu admin-api'ye konulursa production'da hiç çalışmaz.**
3. **LLM anahtarı zaten chatbot-api'de ve GUI zaten chatbot-api'ye erişiyor.**
   `k8s/frontend/configmap.yaml:7` → `CHATBOT_API_URL: "http://bulutistan-chatbot-api"`,
   `k8s/chatbot-api/deployment.yaml:26` → `secretRef: bulutistan-llm-secret`.
   `src/services/chatbot_client.py` bu hattı kullanıyor ve JWT taşıyor.

Sonuç: **yeni secret, yeni servis, yeni configmap satırı, yeni ingress kuralı yok.**
LLM çağrısı chatbot-api'ye eklenir, GUI oradan ister, veriyi GUI kendi yazar.

### Akış

```
  scripts/new_release.py                 (senin makinen, deploy sonrası tek komut)
        │  git log <son-sha>..HEAD
        │  POST /internal/platform/releases     X-Release-Token: <token>
        ▼
  GUI / Dash Flask server  (k8s: bulutistan-frontend, ingress "/" buraya)
        │
        ├─1─▶ TRT gününe göre release bul-veya-aç  (CalVer YYYY.MM.N)
        ├─2─▶ release_changes satırlarını yaz      (commit_sha ile dedupe)
        ├─3─▶ body = deterministic_note(...)       (kod yazar, source='auto')
        │        ↳ sürüm bu andan itibaren gösterilebilir
        ├─4─▶ chatbot-api  POST /api/v1/release-notes/generate
        │         └──▶ api.bulutistan.ai   (anahtar burada, mevcut LLMClient)
        ├─5─▶ doğrula → boşsa onarım turu → fallback model → yine boşsa 'auto' kal
        └─6─▶ sağ çıkan çıktı draft_body'ye  (panelde GÖRÜNMEZ)
                                    │
        ◀────── script notu gösterir, sen "e" dersin ──────┐
        │                                                  │
        └─7─▶ confirm: draft_body → body, source='model' ──┘
                                    │
  Panel  /administration/platform/versions  ◀────┘  (her zaman body'yi gösterir)
```

Ingress `/api/v1/...` prefix'lerini başka servislere yönlendirdiği için ingest yolu
**`/internal/...`** altında; `/` prefix'i frontend'e gittiğinden ek ingress kuralı
gerekmiyor.

---

## Veri modeli

Yeni migration `sql/migrations/004_release_notes.sql`, `auth_db_migrations.py` içinde
**schema version 5** bloğu (mevcut en yüksek 4).

### Yeni tablo: `release_notes`

Sürüm başına tek satır. Gösterilen not (`body`) ile onay bekleyen model çıktısı
(`draft_body`) aynı satırda, ayrı kolonlarda durur.

| kolon | tip | not |
|---|---|---|
| `id` | serial PK | |
| `release_id` | int **UNIQUE** FK → `platform_releases(id)` ON DELETE CASCADE | sürüm başına tek satır |
| `headline` | text null | **gösterilen** tek cümlelik özet |
| `body` | jsonb NOT NULL | **gösterilen** not — aşağıdaki yapı |
| `source` | varchar(16) NOT NULL | `model` \| `auto` — gösterilen notu kim yazdı |
| `draft_headline` | text null | onay bekleyen model çıktısı |
| `draft_body` | jsonb null | onay bekleyen model çıktısı; onaylanınca `body`'ye taşınır |
| `model` | varchar(64) null | notu üreten model adı |
| `input_fingerprint` | varchar(64) NOT NULL | notu besleyen sha kümesinin sha256'sı |
| `generated_at` | timestamptz DEFAULT NOW() | |

`body` yapısı — üç kova, her madde metin + dayandığı sha'lar:

```json
{
  "added":    [{"text": "Colocation raporuna rack seviyesinde doluluk eklendi.",
                "shas": ["4f2a1b3", "9c3d0e7"]}],
  "fixed":    [{"text": "Customer view'da cache eskimesi giderildi.",
                "shas": ["81d4c31"]}],
  "improved": [{"text": "DC View network interface sekmesi lazy-load ile açılıyor.",
                "shas": ["ad6c78e"]}]
}
```

**Neden `body` ve `draft_body` ayrı:**

`body` **her zaman doludur** ve panel her zaman onu gösterir. `draft_body` onay
bekleyen model çıktısıdır ve panelde görünmez.

- Sürüm açıldığı anda `body`, koddan üretilen özetle doldurulur (`source='auto'`).
  Yani sürüm daha ilk saniyeden itibaren gösterilebilir bir içeriğe sahiptir.
- Model çıktısı doğrulamadan geçerse `draft_body`'ye yazılır.
- Onaylandığında (`confirm`) `draft_body` → `body`, `source='model'`,
  `draft_body = NULL`.
- Reddedildiğinde (`reject`) yalnızca `draft_body` silinir; `body` yerinde kalır.

**Bu şemanın anlamı: "not yok" diye bir durum yoktur.** Model düşse de, JSON'u
bozuk gelse de, bütün maddeleri elense de, sen reddetsen de sürümün gösterilecek
bir notu vardır. Panelin ham commit listesine düşeceği bir yol tasarımda mevcut
değildir.

**`input_fingerprint` neden var:** aynı sürüme sonradan commit eklenirse
(gün içi ikinci deploy) parmak izi değişir; panel notun bayatladığını bilir ve
yeniden üretimi tetikler.

**Mevcut `platform_releases.title` / `notes` kolonları kullanılmıyor.** İlk fazdan
kalma, boş duruyorlar. Tek doğruluk kaynağı `release_notes` olsun diye bilerek
dokunulmuyor — iki yazıcı tek satıra yazmasın.

### Değişmeyen tablolar

`platform_releases`, `release_changes`, `service_deployments` olduğu gibi kalır.
`release_changes` ham commit kaydı olarak devam eder; artık kartta gösterilmez,
notun kaynağı ve doğrulama referansı olarak kullanılır.

---

## Bileşenler

### 1. `scripts/new_release.py` (yeni)

Kullanıcının çalıştırdığı tek komut.

- **Sınırı bulur:** sunucudan `GET /internal/platform/releases/last-sha` ile en son
  kaydedilmiş commit sha'sını alır. Sunucuda hiç kayıt yoksa `--since <sha>`
  parametresi zorunlu olur (sessizce tüm geçmişi göndermez).
- **Commit'leri okur:** `git log <last>..HEAD --reverse --date=short
  --pretty=format:%h%x1f%ad%x1f%s` — backfill script'iyle aynı format.
- **Merge commit'lerini atar** (`--no-merges`); gürültü.
- **Gönderir:** `POST /internal/platform/releases`, `X-Release-Token` header'ıyla.
  Sunucu sürümü açar, değişiklikleri yazar, notu **taslak olarak** üretir ve geri
  döner. Taslak panelde görünmez.
- **Gösterir ve sorar** — işin en önemli adımı. Üretilen notu terminale basar:

  ```
  2026.08.1 · 3 Ağustos 2026 · 7 commit

  Neler Eklendi
    • Colocation raporuna rack seviyesinde doluluk eklendi.
    • Chatbot yanıtlarında streaming açıldı.

  Neler Düzeltildi
    • Customer view'da cache eskimesi giderildi.

  Kaydedeyim mi? [e = evet / h = hayır / y = yeniden üret]
  ```

  - `e` → `POST .../note/confirm` — taslak `ok` olur, panelde görünür.
  - `h` → `POST .../note/reject` — yalnızca taslak silinir. Sürümün gösterilen
    notu (`body`) kod-yazımı `auto` özet olarak yerinde kalır; panel boş kalmaz.
  - `y` → `POST .../note/regenerate` — yeni taslak üretilir, tekrar sorulur.
    Üst üste en fazla 3 deneme; sonra `h` gibi davranır ve durumu bildirir.
- **`--yes`:** soruyu atlar, doğrudan onaylar. Acele edilen gün için.
- **`--dry-run`:** hiçbir şey göndermez, ne göndereceğini basar.
- Etkileşimli olmayan ortamda (TTY yok) `--yes` verilmemişse **taslakta bırakır ve
  çıkar** — sessizce onaylamaz.
- Yapılandırma: `RELEASE_INGEST_URL` ve `RELEASE_INGEST_TOKEN`, gitignore'lu local
  env dosyasından okunur (projenin local-env creds kuralı).

**Neden onay adımı taslak üzerinden yürüyor:** onaylanan metin script'ten geri
gönderilseydi, tokene sahip olan istediği metni panele yazdırabilirdi. Metin
sunucuda kalır, script yalnızca "evet/hayır" der.

### 2. GUI ingest endpoint'i (yeni)

`src/routes/release_ingest.py`, `app.py`'de Flask `server`'a bağlanır.

**`POST /internal/platform/releases`**

Kimlik doğrulama: `X-Release-Token` header'ı `RELEASE_INGEST_TOKEN` env değişkeniyle
`hmac.compare_digest` ile karşılaştırılır.
- Env tanımlı değilse → **503**, "feature disabled". Asla açık kapı bırakmaz.
- Uyuşmazlık → **403**.

Gövde:
```json
{"commits": [{"sha": "4f2a1b3", "date": "2026-08-03", "subject": "feat(gui): ..."}],
 "environment": "production"}
```

Davranış:
1. Bugünün **Europe/Istanbul** takvim tarihini bulur.
2. O tarihe ait `platform_releases` satırı varsa onu kullanır, yoksa açar.
   CalVer `YYYY.MM.N` — `N`, o ay içinde açılmış sürümlerin sayısı + 1
   (`released_at` aynı yıl-ay olan satırlar sayılır; ay başında 1'den başlar).
   `source='deploy'`.
3. `release_changes` satırlarını yazar. `commit_sha` o sürümde zaten varsa atlar
   (script iki kere çalıştırılırsa kayıt ikizlenmez).
4. **`body`'yi hemen `deterministic_note` ile doldurur** (`source='auto'`) —
   sürüm daha ilk saniyeden gösterilebilir hale gelir.
5. Not üretim merdivenini çağırır (senkron); model çıktısı sağ çıkarsa
   **`draft_body`** olarak yazılır. `body`'ye dokunulmaz.
6. Döner: `{"version", "created", "changes_added", "note_status", "note_body",
   "dropped"}` — `note_status` ∈ {`draft`, `auto`}; `dropped`, doğrulamada elenen
   madde sayısı ve gerekçeleri.

**`POST /internal/platform/releases/{version}/note/confirm`** — taslağı `ok` yapar.
Taslak yoksa 404, zaten `ok` ise 200 (idempotent).

**`POST /internal/platform/releases/{version}/note/reject`** — taslak satırını
siler. Sürüme ve değişikliklere dokunmaz.

**`POST /internal/platform/releases/{version}/note/regenerate`** — yeni taslak
üretir, döner. Var olan taslağın üzerine yazar.

Dördü de aynı `X-Release-Token` kontrolünden geçer.

**`GET /internal/platform/releases/last-sha`** — aynı token kontrolü; **en son
eklenen** `release_changes` satırının `commit_sha` değerini döner (yoksa `null`).
"En son" = en yüksek `release_changes.id`, yani ekleme sırası. Commit'ler git
sırasıyla (`--reverse`) yazıldığı için bu, en son gönderilen commit'e karşılık
gelir; tabloda git topolojisi tutulmadığından başka bir sıralama tanımlı değil.

### 3. Not üretimi — GUI tarafı (yeni)

`src/services/release_notes.py`. Kritik nokta: **doğrulama mantığı saf fonksiyon**,
LLM olmadan unit test edilebilir.

- `build_payload(release) -> dict` — sürümün `release_changes` satırlarını
  chatbot-api'nin beklediği şekle çevirir.
- `validate_note(raw, allowed_shas) -> tuple[dict, list[str]]` — **saf fonksiyon.**
  Kurallar bu sırayla uygulanır; her eleme gerekçesiyle birlikte döner:

  1. **Bilinmeyen kova atılır.** `added` / `fixed` / `improved` dışındaki anahtarlar
     yok sayılır.
  2. **Sha doğrulaması.** Bir maddenin `shas` listesindeki her sha `allowed_shas`
     içinde olmalı; olmayan sha listeden çıkarılır.
  3. **Bir commit yalnızca bir maddede.** Daha önceki bir madde tarafından
     kullanılmış sha, sonraki maddeden düşürülür (ilk gelen alır).
     *Bunun sonucu:* madde sayısı commit sayısını **matematiksel olarak geçemez.*
     Model tek commit'i üç maddeye bölerek not şişiremez.
  4. **Uzunluk sınırı.** `text` 200 karakteri geçen madde silinir. Ortadan kesmek
     bozuk görünür; bilgi zaten ham değişiklik listesinde duruyor.
  5. **Metin temizliği.** `text` içinde sha benzeri token (7–40 haneli hex) veya
     conventional-commit prefix'i (`feat:`, `fix(gui):` …) varsa **silinmez,
     temizlenir**. Bu kozmetik bir kural.
  6. **Boş madde silinir.** 2–5'ten sonra geçerli sha'sı kalmayan veya `text`'i
     boşalan madde düşer.
  7. **Hiçbir madde sağ çıkmazsa** → boş sonuç döner; çağıran taraf merdivenin
     bir sonraki basamağına geçer.

  **Neden eleme, tümden reddetme değil:** madde başına sha zorunluluğu (2+3)
  uydurmayı zaten madde düzeyinde kesiyor. Bir maddenin bozuk olması, doğru
  yazılmış diğer üçünü çöpe atmayı gerektirmiyor. Hiçbir madde kalmadığında
  sonuç boş döner ve merdivenin bir sonraki basamağı devreye girer.
- `deterministic_note(changes) -> dict` — **saf fonksiyon, LLM yok, hiç
  başarısız olmaz.** `release_changes` satırlarından kodla özet üretir:
  - `headline`: Türkçe sayı cümlesi — *"7 değişiklik: 3 yeni özellik, 3 düzeltme,
    1 iyileştirme."* Sıfır olan tür cümleye girmez.
  - Maddeler: her değişiklik için `text` = (varsa `SCOPE: `) + commit
    subject'inin prefix'i ayıklanmış, baş harfi büyütülmüş hali; `shas=[sha]`.
  - Kaynağı commit subject'i olduğu için maddeler çoğunlukla İngilizce olur.
    **Bu yüzden `source='auto'` iken maddeler kartın gövdesinde değil, alttaki
    kapalı teknik bölümde gösterilir** (aşağıya bakın) — kartta yalnızca Türkçe
    `headline` görünür. Ham commit satırı hiçbir koşulda kartın gövdesine çıkmaz.
- `generate_for_release(release_id) -> dict` — **kademeli deneme merdiveni.**
  Amaç, `auto` özete düşmeyi son çare haline getirmek:

  | # | Deneme | Ne değişir |
  |---|---|---|
  | 1 | Birincil model, standart prompt | — |
  | 2 | **Onarım turu** — aynı model | Prompt'a somut şikâyet eklenir: hangi sha'lar geçersizdi, hangi madde çok uzundu, JSON mu bozuktu. Model neyi düzelteceğini bilir. |
  | 3 | **Fallback model** (`chatbot_fallback_model`), sıkı prompt | Format kuralları daraltılır, örnek çıktı verilir |
  | 4 | `deterministic_note` | LLM yok; her zaman sonuç verir |

  1–3 arasında ilk **en az bir maddesi sağ çıkan** sonuç kazanır ve `draft_body`'ye
  yazılır. `LLMClient`'ın kendi taşıma katmanı yeniden denemeleri (bağlantı hatası,
  zaman aşımı) bunun altında zaten çalışır; buradaki merdiven *içerik* hatalarına
  karşıdır.

  4. adıma inildiğinde `body` zaten `auto` özettir (sürüm açılırken yazılmıştı),
  yeni bir şey yazılmaz; sonuç `note_status="auto"` olarak bildirilir ve script
  bunu ekranda açıkça söyler.
- `mint_service_token()` — script tetiklediğinde Flask request context'inde
  kullanıcı yok, `api_client._auth_headers()` boş döner ve chatbot-api 401 verir.
  Bu yüzden `src/auth/api_jwt.py`'ye `create_service_token(subject="release-bot")`
  eklenir: mevcut `create_api_token` ile aynı imza/secret, `sub="release-bot"`,
  `typ="service"`. chatbot-api'nin `verify_api_user`'ı `sub`'ın boş olmamasına
  bakıyor, DB'de kullanıcı aramıyor — auth tarafında **değişiklik gerekmiyor**.

### 4. chatbot-api endpoint'i (yeni)

`services/chatbot-api/app/routers/release_notes.py`,
`main.py`'de `prefix="/api/v1/release-notes"` ile kaydedilir, mevcut
`verify_api_user` bağımlılığıyla.

**`POST /api/v1/release-notes/generate`**

Gövde: `{"version", "released_at", "changes": [{"sha", "type", "summary"}]}`

- Mevcut `app.services.llm_client.get_llm_client()` kullanılır — yeni istemci,
  yeni ayar, yeni anahtar yok. `chatbot_temperature` (0.2) ve mevcut model +
  fallback zinciri aynen geçerli.
- **Servis stateless kalır: DB'ye dokunmaz.** Girdi commit listesi, çıktı JSON not.
- Model yanıtı parse edilemezse veya LLM düşerse → HTTP **200** +
  `{"status": "failed", "reason": ...}`. Bu, chatbot-api'nin mevcut sözleşmesi
  (operasyonel hatalar 200 döner, yalnızca bozuk istek 422).

Prompt sözleşmesi (system mesajı):
- Türkçe cümle, İngilizce teknik terim.
- Yalnızca `{"headline", "added", "fixed", "improved"}` anahtarlı JSON.
- Her madde `{"text", "shas"}`; `shas` **girdide verilen sha'lardan** seçilecek.
- **Bir commit yalnızca bir maddede kullanılacak.** İlgili commit'ler tek maddede
  birleştirilecek, bölünmeyecek.
- Bir madde tek cümle, en fazla 200 karakter.
- Commit prefix'i ve sha metne yazılmayacak.
- `chore`/`docs`/`build`/`ci` tipindekiler yazılmayacak — onlar sayıya girer.
- Uygun madde yoksa kova boş bırakılacak; doldurmak için uydurulmayacak.

### 5. Uydurmaya karşı savunma — özet

Prompt'a güvenmiyoruz; kod zorluyor:

| Risk | Önlem | Nerede |
|---|---|---|
| Olmayan özellik yazması | Her madde sha alıntılamak zorunda; sha girdi kümesinde değilse madde silinir | `validate_note` |
| Notu şişirmesi (1 commit → 5 madde) | Bir commit yalnızca bir maddede kullanılabilir; madde sayısı commit sayısını geçemez | `validate_note` |
| Roman yazması | 200 karakteri geçen madde silinir | `validate_note` |
| Sha / commit prefix'i sızdırması | Metin otomatik temizlenir | `validate_note` |
| Sayıları uydurması | Rozet sayıları `release_changes` satırlarından kodda hesaplanır, modelden hiç alınmaz | `versions.py` |
| Tümünü uydurması | Merdivenin 2. ve 3. basamağı devreye girer; oradan da sonuç çıkmazsa kod-yazımı `auto` özet gösterilir | `generate_for_release` |
| JSON yerine düzyazı | Onarım turunda somut şikâyetle tekrar sorulur; sürerse fallback model; sürerse `auto` özet | `generate_for_release` |
| LLM tamamen erişilemez | `auto` özet zaten `body`'de yazılı; panel hiç etkilenmez | `deterministic_note` |
| **Commit gerçek ama model yanlış yorumlamış** | **Onay adımı — model çıktısı `draft_body`'de bekler, sen onaylamadan panelde görünmez** | `new_release.py` + confirm endpoint |
| Bayat not | `input_fingerprint` sha kümesiyle uyuşmuyorsa panel "güncellenmedi" işareti gösterir | `versions.py` |

**Katmanların iş bölümü:** ilk dördü mekanik hataları kodla keser. Onay adımı ise
kodun göremediği tek şeyi yakalar: commit gerçek, sha doğru, format düzgün, ama
cümlenin anlamı yanlış. Bunu ancak insan görür — o yüzden varsayılan davranış
sormaktır, `--yes` bilinçli bir tercihtir.

### 6. "Yeniden üret" butonu

- Panelde her sürüm satırında, yalnızca yetkisi olana görünür.
- Yeni izin düğümü: `sec:settings_platform_versions:regenerate`,
  `permission_catalog.py`'de mevcut `page:settings_platform_versions` (satır 505)
  grubunun altına eklenir.
- **Callback'in kendisi de yetkiyi kontrol eder** — düğmenin gizlenmesi tek başına
  yetmez (bkz. floor-map izin boşluğu dersi).
- Callback modülü: `src/pages/settings/platform/versions_callbacks.py`,
  `app.py`'de `# noqa: F401` ile import edilir (mevcut settings callback deseni).
- **Buradaki üretim taslak aşamasından geçmez, doğrudan `ok` yazar.** Gerekçe:
  kullanıcı sonucu o anda ekranda görüyor ve beğenmezse butona tekrar basabiliyor;
  script akışındaki "görmeden yayına girme" riski burada yok. Onay adımı,
  arkasında insan olmayan otomatik yol içindir.

### 7. Geçmişin bir kereye mahsus yazılması

`scripts/regenerate_release_notes.py` (yeni):
- `source='auto'` olan (yani model notu hiç onaylanmamış) sürümleri sırayla
  işler.
- `--limit N` ve `--version X` ile parça parça çalıştırılabilir.
- İdempotent: `--force` verilmedikçe `source='model'` olan notu yeniden üretmez.
- **`--preview`:** üretir, ekrana basar, **kaydetmez.** Prompt'u ayarlamak için
  önce birkaç sürümde bununla bakılır.
- Onay modeli: varsayılan olarak her sürümü tek tek sorar (script'le aynı `e/h/y`).
  24 sürümü tek tek onaylamak istemiyorsan `--yes` ile toplu geçilir — ama önerilen
  yol önce `--preview --limit 3` ile örneğe bakıp prompt'u bir kez ayarlamak.
- Mevcut 24 sürüm / 835 değişiklik bu script'le bir kere geçirilir.

---

## Panel yenilemesi

`src/pages/settings/platform/versions.py` yeniden düzenlenir. Dosya şu an 273 satır
ve iki iş yapıyor (veri şekillendirme + render); render yardımcıları
`versions_view.py`'ye ayrılır, `versions.py` sayfa girişini tutar.

### Yeni düzen

**Canlı sürüm — üstte tek geniş kart.** Sürüm numarası, tarihi, yeşil "Yayında"
rozeti, notlar açık halde. Sayfaya girenin ilk gördüğü şey.

**Geçmiş — kapalı satırlar.** Kalan sürümler kart değil, tek satır:
`2026.07.4 · 24 Tem · 3 yeni · 5 düzeltme ›`. Tıklayınca açılır (`dmc.Accordion`).
Sol taraftaki timeline rail'i (dot + dikey çizgi) kaldırılır — 24 öğede gürültü
yapıyor; yerine sürüm numarası sabit genişlikli sol kolonda hizalanır.

**Ay/yıl ayraçları.** `Temmuz 2026`, `Haziran 2026` başlıkları listeyi böler.

**Arama kutusu.** `dmc.TextInput`; not metinlerinde ve sürüm numarasında arar.
Filtreleme callback'te yapılır, veri `dcc.Store`'da tutulur (her tuşta DB'ye
gidilmez).

**Sayı şeridi çerçeveye alınır.** Bugünkü çıplak `24 releases / 835 changes / —`
yerine `dmc.Paper` içinde üç kutu.

**Teknik detaylar arkaya.** `sha 4f2a1b` satırları ("Service deployments" bloğu)
en alta, kapalı bölüme iner.

**Panel her zaman `body`'yi gösterir, `draft_body`'yi asla.** Onaylanmamış model
çıktısı panelde görünmez; onay gelene kadar kod-yazımı `auto` özet görünür.

**Ham commit satırı kartın gövdesine hiçbir koşulda çıkmaz.** `source='auto'` iken
kartta Türkçe `headline` (*"7 değişiklik: 3 yeni özellik, 3 düzeltme, 1
iyileştirme."*) ve sessiz bir **"otomatik özet"** rozeti görünür; commit'ten türeyen
madde metinleri alttaki kapalı teknik bölümde durur. Ham `release_changes`
listesi, sha'larla birlikte, yalnızca o kapalı bölümde — yani isteyerek açıldığında
— erişilebilir kalır. Denetim izi kaybolmuyor, sadece varsayılan görüntü olmaktan
çıkıyor.

**İki durum işareti.** (a) Sürümün `input_fingerprint`'i o sürümün mevcut sha
kümesiyle uyuşmuyorsa kartta sessiz bir "not güncellenmedi" işareti çıkar —
yeniden üretilmesi gerektiğini söyler. (b) En son sürümün üzerinden 7 günden fazla
geçtiyse sayfanın üstünde "uzun süredir sürüm kaydedilmedi" bilgi notu görünür.
İkincisinin sınırı için aşağıdaki riskler bölümüne bakın.

### Renkler

`versions.py` içinde koda gömülü hex kodları (`#4318FF`, `#12B76A`, `#EEF0FF`,
`#E3EAFC`) Mantine tema değişkenleriyle değiştirilir
(`var(--mantine-color-indigo-6)` vb.). Bugün karanlık temada bozuk görünen kısım
düzelir ve panel platformun geri kalanıyla aynı dili konuşur.

### "Yayında" rozeti — bilinen hatanın kapanışı

Bugün rozet hiç yanmıyor: `versions.py:252` sürüm dizgisini
`service_deployments.version` ile karşılaştırıyor, ama o tablodaki bütün satırlar
`version='local'` veya sha içeriyor; CalVer ile string eşleşmesi hiç tutmuyor
(QA raporundaki **DB-5**).

Yeni akışta sürüm satırı **deploy anında** açıldığı için "en yeni `platform_releases`
satırı = canlı sürüm" doğru ve deterministik bir kural haline gelir. Rozet buna
bağlanır; `service_deployments` yalnızca servis detay bloğunu beslemeye devam eder.
Üstteki sayı şeridindeki "live version" tiresi de böylece kalkar.

---

## Veri erişim deseni

Mevcut `_USE_API` deseni korunur ama tek bir bilinçli sapmayla:

- **Okuma** (`list_platform_releases`) mevcut dispatch'ten geçmeye devam eder:
  `admin_client` → API varsa admin-api, yoksa `versions_crud`. Notun listeye
  eklenmesi için `services/admin-api/app/routers/versions.py` de not alanlarını
  döndürecek şekilde güncellenir; iki yol aynı şekli döndürür.
- **Yazma** (ingest ve yeniden üretme) doğrudan `versions_crud` üzerinden auth DB'ye
  yapılır, `_USE_API` durumundan bağımsız olarak.
  **Gerekçe:** GUI süreci auth DB bağlantısına her ortamda sahip (login, izinler ve
  migration'lar zaten oradan geçiyor), ve production'da admin-api yok. Yazma için
  admin-api'ye endpoint eklemek, production'da hiç çalışmayacak kod üretmek olurdu.

---

## Yapılandırma

Yeni ortam değişkenleri:

| değişken | nerede | not |
|---|---|---|
| `RELEASE_INGEST_TOKEN` | GUI (k8s secret) + geliştirici makinesi (gitignore'lu env) | Rastgele üretilir. Tanımsızsa endpoint 503 döner, özellik kapalı olur. |
| `RELEASE_INGEST_URL` | yalnızca geliştirici makinesi | Script'in hedefi. |

**LLM tarafı için yeni değişken yok.** `BULUTISTAN_LLM_API_KEY`,
`BULUTISTAN_LLM_BASE_URL`, model adları zaten chatbot-api'de tanımlı ve çalışıyor.

`RELEASE_INGEST_TOKEN` k8s'te yeni bir secret olarak oluşturulur ve
`k8s/frontend/deployment.yaml`'a `secretRef` olarak bağlanır (dosyada şu an hiç
`secretRef` bloğu yok, ilk o eklenir). Gerçek değer repoya girmez; mevcut
`k8s/chatbot-api/secret-reference.yaml` deseninde bir referans dosyası bırakılır.

---

## Test stratejisi

- **Migration:** iki kere çalıştır, tablo ve `schema_migrations` satırı sabit kalsın.
- **`validate_note` (en kritik):** saf fonksiyon, LLM'siz.
  - Geçerli sha → madde korunur.
  - Uydurma sha → madde silinir.
  - Karışık sha (biri geçerli biri değil) → madde korunur, geçersiz sha atılır.
  - **Aynı sha iki maddede → ikincisi düşer; iki commit'ten beş madde çıkamaz.**
  - **201 karakterlik madde → silinir; 200 karakterlik madde → kalır.** (Sınır
    değerleri açıkça test edilir.)
  - **Metinde sha veya `feat(gui):` prefix'i → temizlenir, madde kalır.**
  - **Temizlik sonrası metin boşalırsa → madde silinir.**
  - Tüm maddeler uydurma → boş sonuç (çağıran merdivende ilerler).
  - Bilinmeyen kova adı → atılır.
  - Boş `text` → atılır.
- **Ingest endpoint'i:** token yok → 503/403; geçerli token → sürüm açılır; aynı
  commit iki kere → ikinci çağrıda `changes_added=0`; gün içi ikinci çağrı yeni
  sürüm açmaz, mevcut günün sürümüne ekler; **üretilen not `draft` doğar.**
- **Onay akışı:** `confirm` → `ok`; ikinci kez `confirm` → 200, durum değişmez
  (idempotent); `reject` → not satırı silinir ama `platform_releases` ve
  `release_changes` **yerinde kalır**; `regenerate` → yeni taslak, eskisinin
  üzerine yazar; taslak yokken `confirm` → 404.
- **Script onay davranışı:** `e` → confirm çağrılır; `h` → reject çağrılır ve çıkış
  kodu 0 (hata değil, tercih); `y` → regenerate; üst üste 3 `y` sonrası döngü
  kırılır; `--yes` soruyu atlar; TTY yokken `--yes` verilmemişse taslakta bırakıp
  çıkar ve **confirm çağırmaz**.
- **CalVer/TRT sınırı:** TRT'de 23:50 ve ertesi gün 00:10 → **iki ayrı** sürüm.
  UTC ile TRT'nin ayrıştığı saatler açıkça test edilir.
- **chatbot-api router:** LLM mock'lanır — geçerli JSON → 200 + not; bozuk çıktı →
  200 + `failed`; `LLMError` → 200 + `failed` (500 değil).
- **Panel:** `source='model'` → onaylanmış not render edilir; `source='auto'` →
  Türkçe headline + "otomatik özet" rozeti, madde metinleri **gövdede değil**
  teknik bölümde; `draft_body` dolu → panelde **görünmez**; hiç sürüm yok →
  mevcut boş durum korunur; bayat `input_fingerprint` → güncellenmedi işareti.
  **Regresyon testi: hiçbir render yolunda ham commit subject'i kartın gövdesine
  girmez.**
- **İzin:** `sec:settings_platform_versions:regenerate` olmayan kullanıcı callback'i
  doğrudan tetiklerse reddedilir (buton gizli olsa bile).
- **Script:** `--dry-run` hiçbir HTTP isteği yapmaz; merge commit'leri listeye
  girmez; `last-sha` boşken `--since` olmadan çalışmayı reddeder.

## Kurulum sırası

1. **Migration** — `004_release_notes.sql` + `auth_db_migrations.py` v5 bloğu.
2. **`versions_crud`** — not okuma/yazma fonksiyonları + idempotent release açma.
3. **`validate_note` + `deterministic_note`** — saf fonksiyonlar, testleriyle.
   (LLM yok. Bu adım bitince panel, model hiç devreye girmeden dolu görünür.)
4. **chatbot-api endpoint'i** — router + prompt + mock'lu testler.
5. **`chatbot_client` + `create_service_token`** — GUI'den servise hat.
6. **Ingest endpoint'i** — token kontrolü, CalVer/TRT, dedupe, taslak üretimi.
7. **Onay endpoint'leri** — `confirm` / `reject` / `regenerate`; merdivenin
   onarım turu + fallback model basamakları.
8. **`scripts/new_release.py`** — commit toplama + onay döngüsü; uçtan uca ilk
   gerçek çalıştırma.
9. **Panel yenilemesi** — düzen, renkler, arama, "Yayında" rozeti düzeltmesi.
10. **"Yeniden üret" butonu** — izin düğümü + callback.
11. **`scripts/regenerate_release_notes.py`** — önce `--preview` ile prompt ayarı,
    sonra mevcut 24 sürüm bir kere geçirilir.
12. **k8s/compose yapılandırması** — `RELEASE_INGEST_TOKEN` bağlanır.

Adım 3'e kadar hiçbir LLM çağrısı gerekmiyor; doğrulama mantığı model olmadan
tamamlanıp test edilebilir.

## Riskler ve açık uçlar

- **Not kalitesi ölçülemedi.** Modelin Türkçe cümle + İngilizce terim kuralına ne
  kadar uyacağı ilk gerçek üretime kadar bilinmiyor. Prompt ilk 24 sürümün
  çıktısına bakılarak bir kez ayarlanacak; bunun için regenerate script'inde
  `--preview` (üret, göster, kaydetme) modu var. Bu risk onay adımıyla
  sınırlandırılmış durumda: kalite düşükse not panele hiç çıkmıyor, `y` ile
  yeniden üretiliyor veya `h` ile atılıyor — her iki durumda da panelde
  kod-yazımı `auto` özet kalır, ham commit listesi değil.
- **Script çalıştırılmazsa sürüm kaydı düşmez.** Bilinçli kabul edilen zayıflık
  (Seçenek 1 kararı). Panelin en üstünde, en son kaydedilen commit ile `HEAD`
  arasında fark varsa **"kaydedilmemiş deploy var"** uyarısı gösterilir — ama bu
  uyarı ancak sunucu HEAD'i bilirse çalışır, ki bilmiyor. **Bu yüzden uyarı v1'de
  şu şekle indirgeniyor:** en son sürümün üzerinden 7 günden fazla geçtiyse
  "uzun süredir sürüm kaydedilmedi" bilgi notu. Gerçek fark tespiti ertelenen
  GitHub katmanına bağlı.
- **Tek paylaşılan token.** Kişi bazlı değil. İç araç için kabul edilebilir; sızarsa
  yapılabilecek en kötü şey sahte sürüm kaydı açmaktır (veri okunamaz, silinemez).
  Endpoint yalnızca ekleme yapar, silme/güncelleme yolu yoktur.
- **`released_at` = kaydın atıldığı gün, deploy günü değil.** Script deploy'dan
  saatler sonra çalıştırılırsa tarih kayar. Kabul edilen yaklaşıklık; ilk fazın
  backfill tarihlerindeki aynı dürüst sınırlama.
- **Geriye dönük 835 değişiklik tek seferde model masrafı çıkarır.** `--limit` ile
  parça parça çalıştırılabilir; bir kerelik iş.
