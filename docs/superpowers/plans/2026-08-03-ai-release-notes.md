# AI Release Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Platform Versions paneli, ham commit listesi yerine her release için LLM'in yazdığı, insan onayından geçmiş bir release note göstersin.

**Architecture:** `scripts/new_release.py` git log'u okuyup GUI'nin `/internal/platform/releases` endpoint'ine gönderir. GUI önce kodla yazılmış deterministik notu `body`'ye yazar (bu adım asla başarısız olmaz), sonra chatbot-api üzerinden LLM'den not ister; LLM çıktısı saf bir doğrulayıcıdan geçer ve **görünmeyen** `draft_body` alanına yazılır. Script notu terminalde gösterir, kullanıcı onaylarsa `draft_body` → `body` taşınır ve `source='model'` olur. Yeni servis, yeni secret, yeni ingress kuralı yok.

**Tech Stack:** Dash + dash-mantine-components (Flask sunucu), FastAPI + Pydantic (chatbot-api), PostgreSQL (`bulutauth`), psycopg2, PyJWT (HS256), pytest, Python 3.11.

## Global Constraints

Her task'ın gereksinimleri bu bölümü kapsar:

- **Dil:** Cümleler Türkçe, teknik terimler İngilizce (release, commit, sha, note, draft, endpoint). Kod, değişken adı, log mesajı ve commit mesajı İngilizce.
- **Python:** Test ve script çalıştırmada **daima** `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python` (3.11.15). Sistemdeki `python3` 3.9'dur ve `|` tip birleşimlerinde `TypeError` verir. Bu dokümanda `$PY` bu yolun kısaltmasıdır.
- **Branch:** `worktree-task-64-ai-release-notes`, tabanı `origin/development`. Merge hedefi `development`.
- **Bullet metni ≤ 200 karakter.** Uzunu düzeltilmez, atılır.
- **Bir commit sha'sını en fazla bir bullet kullanabilir.** İlk kullanan alır. Bu kural bullet sayısını commit sayısıyla matematiksel olarak sınırlar.
- **Rozet/sayaç değerleri yalnızca kodda hesaplanır.** Modelden gelen hiçbir sayı ekrana çıkmaz.
- **Ham commit subject'i kartın gövdesinde asla görünmez.** Ham subject sadece katlanmış "Teknik detay" bölümünde durur.
- **`release_notes.body` her zaman doludur.** Model başarısız olsa bile kodla yazılmış not oradadır; `body` hiçbir kod yolunda boş bırakılmaz.
- **Secret commit edilmez.** `RELEASE_INGEST_TOKEN` gitignore'lu env dosyasında ve k8s secret'ında durur; repoya sadece `secret-reference.yaml` şablonu girer.
- **Token env'i tanımsızsa ingest endpoint'i 503 döner.** Hiçbir koşulda açık moda düşmez. Token uyuşmazlığı 403'tür.
- **Karşılaştırma `hmac.compare_digest` ile yapılır.**
- **TRT sınırı:** Release'in günü `Europe/Istanbul` takvim günüdür (`ZoneInfo("Europe/Istanbul")`).
- **CalVer:** `YYYY.MM.N` — `N` o ay içindeki sıra numarası, 1'den başlar.

## File Structure

**Yeni dosyalar**

| Dosya | Sorumluluk |
|---|---|
| `sql/migrations/004_release_notes.sql` | `release_notes` tablosunun DDL'i |
| `src/services/release_notes.py` | Saf fonksiyonlar (parse/validate/deterministic) + üretim merdiveni |
| `src/routes/__init__.py` | Yeni paket |
| `src/routes/release_ingest.py` | Flask endpoint'leri (`/internal/platform/...`) |
| `services/chatbot-api/app/routers/release_notes.py` | LLM çağrısı yapan stateless router |
| `src/pages/settings/platform/versions_view.py` | Panelin saf render yardımcıları |
| `src/pages/settings/platform/versions_callbacks.py` | "Yeniden üret" callback'i |
| `scripts/new_release.py` | Release açan + notu onaylatan CLI |
| `scripts/regenerate_release_notes.py` | Geçmiş release'lerin notunu yeniden üreten CLI |
| `k8s/frontend/secret-reference.yaml` | Sadece şablon, gerçek token yok |
| `docs/ops/release-ingest-token.md` | Token'ın nasıl üretilip yerleştirileceği |

**Değiştirilen dosyalar**

| Dosya | Değişiklik |
|---|---|
| `src/auth/auth_db_migrations.py` | v5 bloğu + `_read_migration_004_sql()` |
| `src/auth/versions_crud.py` | Release açma/change ekleme + not okuma/yazma fonksiyonları |
| `src/auth/api_jwt.py` | `create_service_token()` |
| `src/services/chatbot_client.py` | `generate_release_note()` |
| `src/auth/permission_catalog.py` | `sec:settings_platform_versions:regenerate` |
| `src/pages/settings/platform/versions.py` | Panel yeniden tasarımı, veri toplama katmanı |
| `src/app.py` | `register_release_ingest_routes(server)` + callback modülü importu |
| `services/chatbot-api/app/main.py` | Yeni router'ın kaydı |
| `services/admin-api/app/models.py` | `ReleaseOut`'a not alanları (okuma paritesi) |
| `docker-compose.yml` | `app` servisine `RELEASE_INGEST_TOKEN` |
| `k8s/frontend/deployment.yaml` | `secretRef` bloğu |

**Test dosyaları**

`tests/test_platform_versions_migration.py` (genişletilir) · `tests/test_versions_crud_notes.py` · `tests/test_release_notes_service.py` · `services/chatbot-api/app/tests/test_release_notes_contract.py` · `tests/test_chatbot_client_release_notes.py` · `tests/test_release_ingest_endpoint.py` · `tests/test_release_note_ladder.py` · `tests/test_new_release_script.py` · `tests/test_platform_versions_page.py` (onarılır + genişletilir) · `tests/test_platform_versions_regenerate.py` · `tests/test_regenerate_release_notes_script.py`

**Bilinen kırık test (baseline):** `tests/test_platform_versions_page.py::test_visible_change_filter_hides_chore` şu an `_split_changes` çağırıyor, o fonksiyon `_group_changes` olarak yeniden adlandırılmış. Bu işten önce de kırıktı; Task 9'da kapatılıyor.

---

### Task 1: Migration 004 — `release_notes` tablosu (schema v5)

**Files:**
- Create: `sql/migrations/004_release_notes.sql`
- Modify: `src/auth/auth_db_migrations.py`
- Test: `tests/test_platform_versions_migration.py`

**Interfaces:**
- Consumes: mevcut `_sql_dir()`, `_exec_sql_statements(cur, sql)`, `schema_migrations` tablosu (en son uygulanan sürüm 4).
- Produces: `release_notes` tablosu ve `m._read_migration_004_sql() -> str`. Task 2 bu tabloya yazar.

- [ ] **Step 1: Migration SQL'ini yaz**

`sql/migrations/004_release_notes.sql`:

```sql
-- 004_release_notes.sql — AI ile üretilen release note'lar (TASK-64 faz 2).
-- Her platform_releases satırının en fazla bir notu olur (release_id UNIQUE).
-- body: yayınlanan not. draft_body: onay bekleyen taslak, panelde asla gösterilmez.

CREATE TABLE IF NOT EXISTS release_notes (
    id                serial PRIMARY KEY,
    release_id        integer NOT NULL UNIQUE REFERENCES platform_releases(id) ON DELETE CASCADE,
    headline          text,
    body              jsonb NOT NULL,
    source            varchar(16) NOT NULL DEFAULT 'auto',
    draft_headline    text,
    draft_body        jsonb,
    model             varchar(64),
    input_fingerprint varchar(64) NOT NULL,
    generated_at      timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_release_notes_release ON release_notes(release_id);
```

- [ ] **Step 2: Başarısız testi yaz**

`tests/test_platform_versions_migration.py` dosyasının sonuna ekle (dosyadaki `_Cur`/`_Conn` sınıfları aynen kullanılır):

```python
def test_migration_v5_creates_release_notes_table(monkeypatch):
    applied: set[int] = set()
    executed: list[str] = []
    monkeypatch.setattr(m, "_read_schema_sql", lambda: "CREATE TABLE IF NOT EXISTS schema_migrations ();")
    monkeypatch.setattr(m, "_migration_v2_rename_settings", lambda cur: None)
    monkeypatch.setattr(m, "_read_migration_002_sql", lambda: "")

    m.run_auth_db_migrations(_Conn(applied, executed))

    joined = " ".join(executed)
    assert "release_notes" in joined
    assert "input_fingerprint" in joined
    assert "draft_body" in joined
    assert 5 in applied


def test_migration_004_read_sql_nonempty():
    sql = m._read_migration_004_sql()
    assert "release_notes" in sql
    assert "ON DELETE CASCADE" in sql
```

- [ ] **Step 3: Testin başarısız olduğunu gör**

Run: `$PY -m pytest tests/test_platform_versions_migration.py -v`
Expected: `test_migration_v5_creates_release_notes_table` FAIL (`assert 5 in applied`), `test_migration_004_read_sql_nonempty` FAIL (`AttributeError: _read_migration_004_sql`).

- [ ] **Step 4: Migration okuyucusunu ve v5 bloğunu yaz**

`src/auth/auth_db_migrations.py` — `_read_migration_003_sql` fonksiyonunun hemen altına:

```python
def _read_migration_004_sql() -> str:
    p = _sql_dir() / "migrations" / "004_release_notes.sql"
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return ""
```

Aynı dosyada v4 bloğunun hemen ardına (v4 bloğunun birebir aynası):

```python
    cur.execute("SELECT 1 FROM schema_migrations WHERE version = 5")
    if not cur.fetchone():
        m004 = _read_migration_004_sql()
        if m004.strip():
            _exec_sql_statements(cur, m004)
            cur.execute(
                """INSERT INTO schema_migrations (version, description)
                   VALUES (5, 'release notes') ON CONFLICT (version) DO NOTHING"""
            )
            logger.info("Auth DB migration v5 applied (release notes)")
        else:
            logger.warning("004 migration SQL missing; v5 not recorded")
```

- [ ] **Step 5: Testlerin geçtiğini gör**

Run: `$PY -m pytest tests/test_platform_versions_migration.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add sql/migrations/004_release_notes.sql src/auth/auth_db_migrations.py tests/test_platform_versions_migration.py
git commit -m "feat(task-64): release_notes table (auth DB schema v5)"
```

---

### Task 2: `versions_crud` — release açma, change ekleme, not okuma/yazma

**Files:**
- Modify: `src/auth/versions_crud.py`
- Modify: `services/admin-api/app/models.py:222-250`
- Test: `tests/test_versions_crud_notes.py`

**Interfaces:**
- Consumes: Task 1'in `release_notes` tablosu; mevcut `db.fetch_all(sql, params=None)` ve `db.execute(sql, params=None)`.
- Produces:
  - `get_release_by_version(version: str) -> dict | None`
  - `open_release(version: str, released_at: str, title: str | None = None) -> int`
  - `add_release_changes(release_id: int, changes: list[dict]) -> int`
  - `last_ingested_sha() -> str | None`
  - `get_release(release_id: int) -> dict | None` (`changes` iliştirilmiş)
  - `month_release_count(year: int, month: int) -> int`
  - `get_release_note(release_id: int) -> dict | None`
  - `upsert_note(release_id: int, *, body: dict, source: str, input_fingerprint: str, headline: str | None = None, model: str | None = None) -> None`
  - `set_draft_note(release_id: int, *, draft_headline: str | None, draft_body: dict, model: str) -> None`
  - `confirm_draft_note(release_id: int) -> bool`
  - `reject_draft_note(release_id: int) -> bool`
  - `list_platform_releases()` artık her release'e `note` anahtarı iliştirir.
  - Task 6, 7, 9, 11 bunları kullanır.

- [ ] **Step 1: Başarısız testi yaz**

`tests/test_versions_crud_notes.py`:

```python
"""versions_crud'un release açma ve not yazma yolları — DB'siz."""

from __future__ import annotations

import json
from unittest.mock import patch

from src.auth import versions_crud


class _FakeDB:
    """fetch_all/execute'u SQL'deki anahtar kelimeye göre yönlendiren sahte DB."""

    def __init__(self):
        self.releases: list[dict] = []
        self.changes: list[dict] = []
        self.notes: dict[int, dict] = {}
        self.executed: list[tuple[str, tuple]] = []

    def fetch_all(self, sql, params=None):
        s = " ".join(sql.lower().split())
        params = params or ()
        if "from platform_releases where version" in s:
            return [r for r in self.releases if r["version"] == params[0]]
        if "from release_changes where release_id" in s:
            return [c for c in self.changes if c["release_id"] == params[0]]
        if "from release_notes where release_id" in s:
            n = self.notes.get(params[0])
            return [n] if n else []
        return []

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.lower().split()), tuple(params or ())))


def _install(db):
    return patch.multiple(
        versions_crud.db,
        fetch_all=db.fetch_all,
        execute=db.execute,
    )


def test_open_release_returns_existing_id_without_insert():
    db = _FakeDB()
    db.releases.append({"id": 7, "version": "2026.08.1"})
    with _install(db):
        rid = versions_crud.open_release("2026.08.1", "2026-08-03")
    assert rid == 7
    assert not any("insert into platform_releases" in s for s, _ in db.executed)


def test_add_release_changes_skips_already_recorded_sha():
    db = _FakeDB()
    db.changes.append({"release_id": 7, "commit_sha": "aaaaaaaaaaaa"})
    with _install(db):
        n = versions_crud.add_release_changes(
            7,
            [
                {"change_type": "feat", "summary": "yeni panel", "commit_sha": "aaaaaaaaaaaa"},
                {"change_type": "fix", "summary": "rozet düzeltildi", "commit_sha": "bbbbbbbbbbbb"},
            ],
        )
    assert n == 1
    inserts = [p for s, p in db.executed if "insert into release_changes" in s]
    assert len(inserts) == 1
    assert inserts[0][3] == "bbbbbbbbbbbb"


def test_add_release_changes_truncates_sha_to_12():
    db = _FakeDB()
    with _install(db):
        versions_crud.add_release_changes(
            7, [{"change_type": "feat", "summary": "x", "commit_sha": "a" * 40}]
        )
    inserts = [p for s, p in db.executed if "insert into release_changes" in s]
    assert inserts[0][3] == "a" * 12


def test_upsert_note_serialises_body_as_json():
    db = _FakeDB()
    body = {"added": [{"text": "Yeni panel", "shas": ["abc123abc123"]}], "fixed": [], "improved": []}
    with _install(db):
        versions_crud.upsert_note(7, body=body, source="auto", input_fingerprint="f" * 16)
    sql, params = [e for e in db.executed if "insert into release_notes" in e[0]][0]
    assert "on conflict (release_id) do update" in sql
    assert json.loads(params[2]) == body
    assert params[3] == "auto"


def test_confirm_draft_note_is_false_when_no_draft():
    db = _FakeDB()
    db.notes[7] = {"release_id": 7, "draft_body": None}
    with _install(db):
        assert versions_crud.confirm_draft_note(7) is False
    assert not any("set headline = draft_headline" in s for s, _ in db.executed)


def test_confirm_draft_note_promotes_draft_and_sets_source_model():
    db = _FakeDB()
    db.notes[7] = {"release_id": 7, "draft_body": {"added": [], "fixed": [], "improved": []}}
    with _install(db):
        assert versions_crud.confirm_draft_note(7) is True
    sql = [s for s, _ in db.executed if "set headline = draft_headline" in s][0]
    assert "source = 'model'" in sql
    assert "draft_body = null" in sql


def test_reject_draft_note_clears_draft_only():
    db = _FakeDB()
    db.notes[7] = {"release_id": 7, "draft_body": {"added": [], "fixed": [], "improved": []}}
    with _install(db):
        assert versions_crud.reject_draft_note(7) is True
    sql = [s for s, _ in db.executed if "update release_notes" in s][0]
    assert "draft_body = null" in sql
    assert "body =" not in sql.split("where")[0].replace("draft_body =", "")
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `$PY -m pytest tests/test_versions_crud_notes.py -v`
Expected: 7 FAIL — `AttributeError: module 'src.auth.versions_crud' has no attribute 'open_release'` vb.

- [ ] **Step 3: Fonksiyonları yaz**

`src/auth/versions_crud.py` — dosyanın başına `import json` ekle, sonuna:

```python
_NOTE_COLS = (
    "release_id, headline, body, source, draft_headline, draft_body, "
    "model, input_fingerprint, generated_at"
)


def get_release_by_version(version: str) -> dict | None:
    rows = db.fetch_all(
        "SELECT id, version, released_at, title, notes, source "
        "FROM platform_releases WHERE version = %s",
        (version,),
    )
    return rows[0] if rows else None


def month_release_count(year: int, month: int) -> int:
    rows = db.fetch_all(
        "SELECT COUNT(*) AS n FROM platform_releases "
        "WHERE EXTRACT(YEAR FROM released_at) = %s AND EXTRACT(MONTH FROM released_at) = %s",
        (year, month),
    )
    return int(rows[0]["n"]) if rows else 0


def open_release(version: str, released_at: str, title: str | None = None) -> int:
    """`version` için release id'sini döndürür; yoksa oluşturur. Idempotent."""
    existing = get_release_by_version(version)
    if existing:
        return int(existing["id"])
    db.execute(
        "INSERT INTO platform_releases (version, released_at, title, source) "
        "VALUES (%s, %s, %s, 'auto') ON CONFLICT (version) DO NOTHING",
        (version, released_at, title),
    )
    row = get_release_by_version(version)
    if not row:
        raise RuntimeError(f"release could not be opened: {version}")
    return int(row["id"])


def add_release_changes(release_id: int, changes: list[dict]) -> int:
    """Bu release'e daha önce yazılmamış change'leri ekler; eklenen sayıyı döndürür."""
    seen = {
        str(r["commit_sha"])
        for r in db.fetch_all(
            "SELECT commit_sha FROM release_changes WHERE release_id = %s", (release_id,)
        )
        if r.get("commit_sha")
    }
    inserted = 0
    for c in changes or []:
        sha = str(c.get("commit_sha") or "")[:12]
        if not sha or sha in seen:
            continue
        db.execute(
            "INSERT INTO release_changes (release_id, change_type, summary, commit_sha, scope) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                release_id,
                str(c.get("change_type") or "other"),
                str(c.get("summary") or ""),
                sha,
                c.get("scope"),
            ),
        )
        seen.add(sha)
        inserted += 1
    return inserted


def last_ingested_sha() -> str | None:
    rows = db.fetch_all(
        "SELECT rc.commit_sha FROM release_changes rc "
        "JOIN platform_releases pr ON pr.id = rc.release_id "
        "ORDER BY pr.released_at DESC, rc.id DESC LIMIT 1"
    )
    return str(rows[0]["commit_sha"]) if rows and rows[0].get("commit_sha") else None


def get_release(release_id: int) -> dict | None:
    rows = db.fetch_all(
        "SELECT id, version, released_at, title, notes, source "
        "FROM platform_releases WHERE id = %s",
        (release_id,),
    )
    if not rows:
        return None
    rel = dict(rows[0])
    rel["changes"] = [
        dict(c)
        for c in db.fetch_all(
            "SELECT change_type, summary, commit_sha, scope "
            "FROM release_changes WHERE release_id = %s ORDER BY id",
            (release_id,),
        )
    ]
    return rel


def get_release_note(release_id: int) -> dict | None:
    rows = db.fetch_all(
        f"SELECT {_NOTE_COLS} FROM release_notes WHERE release_id = %s", (release_id,)
    )
    return dict(rows[0]) if rows else None


def upsert_note(
    release_id: int,
    *,
    body: dict,
    source: str,
    input_fingerprint: str,
    headline: str | None = None,
    model: str | None = None,
) -> None:
    db.execute(
        "INSERT INTO release_notes "
        "(release_id, headline, body, source, model, input_fingerprint) "
        "VALUES (%s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (release_id) DO UPDATE SET "
        "headline = EXCLUDED.headline, body = EXCLUDED.body, source = EXCLUDED.source, "
        "model = EXCLUDED.model, input_fingerprint = EXCLUDED.input_fingerprint, "
        "generated_at = NOW()",
        (release_id, headline, json.dumps(body, ensure_ascii=False), source, model, input_fingerprint),
    )


def set_draft_note(
    release_id: int, *, draft_headline: str | None, draft_body: dict, model: str
) -> None:
    db.execute(
        "UPDATE release_notes SET draft_headline = %s, draft_body = %s, model = %s "
        "WHERE release_id = %s",
        (draft_headline, json.dumps(draft_body, ensure_ascii=False), model, release_id),
    )


def confirm_draft_note(release_id: int) -> bool:
    """Taslağı yayına alır. Taslak yoksa hiçbir şey yazmaz ve False döner."""
    note = get_release_note(release_id)
    if not note or not note.get("draft_body"):
        return False
    db.execute(
        "UPDATE release_notes SET headline = draft_headline, body = draft_body, "
        "source = 'model', draft_headline = NULL, draft_body = NULL, generated_at = NOW() "
        "WHERE release_id = %s",
        (release_id,),
    )
    return True


def reject_draft_note(release_id: int) -> bool:
    """Taslağı siler; yayındaki `body`'ye dokunmaz."""
    db.execute(
        "UPDATE release_notes SET draft_headline = NULL, draft_body = NULL WHERE release_id = %s",
        (release_id,),
    )
    return True
```

- [ ] **Step 4: `list_platform_releases`'a notu iliştir**

Aynı dosyada, `list_platform_releases()` içinde release'lere `changes`/`services` iliştiren döngünün hemen öncesine not sözlüğünü kur, döngü içinde ata:

```python
    notes = {
        int(r["release_id"]): dict(r)
        for r in db.fetch_all(f"SELECT {_NOTE_COLS} FROM release_notes")
    }
```

ve her release için:

```python
        rel["note"] = notes.get(int(rel["id"]))
```

- [ ] **Step 5: Testlerin geçtiğini gör**

Run: `$PY -m pytest tests/test_versions_crud_notes.py tests/test_versions_crud.py -v`
Expected: all passed.

- [ ] **Step 6: admin-api okuma paritesi**

`services/admin-api/app/models.py` — `ReleaseOut`'a not alanlarını ekle (yazma yolu prod'da GUI'dedir; burası yalnızca okuma paritesi içindir):

```python
class ReleaseNoteOut(BaseModel):
    headline: str | None = None
    body: dict = {}
    source: str = "auto"
    model: str | None = None
    generated_at: datetime | None = None
```

ve `ReleaseOut` gövdesine:

```python
    note: ReleaseNoteOut | None = None
```

- [ ] **Step 7: Commit**

```bash
git add src/auth/versions_crud.py services/admin-api/app/models.py tests/test_versions_crud_notes.py
git commit -m "feat(task-64): release open/ingest and note read-write in versions_crud"
```

---

### Task 3: Saf fonksiyonlar — parse, TRT tarihi, deterministik not, doğrulayıcı

**Files:**
- Create: `src/services/release_notes.py`
- Test: `tests/test_release_notes_service.py`

**Interfaces:**
- Consumes: hiçbir şey. Bu task tamamen saf fonksiyonlardan oluşur; DB'ye ve ağa dokunmaz.
- Produces:
  - `parse_commit_subject(subject: str) -> tuple[str, str, str | None]` → `(change_type, temiz_özet, scope)`
  - `trt_date(dt: datetime | None = None) -> date`
  - `calver(d: date, seq: int) -> str`
  - `fingerprint(changes: list[dict]) -> str`
  - `deterministic_note(changes: list[dict]) -> dict`
  - `validate_note(raw: dict, allowed_shas: set[str]) -> dict`
  - `build_payload(release: dict, changes: list[dict]) -> dict`
  - `BUCKETS: tuple[str, str, str]` = `("added", "fixed", "improved")`
  - Task 4, 6, 7, 8, 9, 11 bunları kullanır.

- [ ] **Step 1: Başarısız testi yaz**

`tests/test_release_notes_service.py`:

```python
"""release_notes saf fonksiyonları — DB yok, ağ yok."""

from __future__ import annotations

from datetime import datetime, timezone

from src.services import release_notes as rn

SHA_A = "aaaaaaaaaaaa"
SHA_B = "bbbbbbbbbbbb"
ALLOWED = {SHA_A, SHA_B}


def _empty() -> dict:
    return {"added": [], "fixed": [], "improved": []}


# --- parse_commit_subject -------------------------------------------------

def test_parse_strips_conventional_prefix_and_scope():
    assert rn.parse_commit_subject("feat(panel): yeni rozet") == ("feat", "yeni rozet", "panel")


def test_parse_handles_breaking_marker():
    assert rn.parse_commit_subject("fix!: kritik hata") == ("fix", "kritik hata", None)


def test_parse_unknown_prefix_becomes_other():
    assert rn.parse_commit_subject("merge branch main") == ("other", "merge branch main", None)


# --- trt_date / calver ----------------------------------------------------

def test_trt_date_rolls_over_at_istanbul_midnight():
    # 2026-08-03 21:30 UTC = 2026-08-04 00:30 TRT
    dt = datetime(2026, 8, 3, 21, 30, tzinfo=timezone.utc)
    assert rn.trt_date(dt).isoformat() == "2026-08-04"


def test_calver_pads_month():
    assert rn.calver(rn.trt_date(datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)), 2) == "2026.08.2"


# --- fingerprint ----------------------------------------------------------

def test_fingerprint_is_order_independent():
    a = [{"commit_sha": SHA_A}, {"commit_sha": SHA_B}]
    b = [{"commit_sha": SHA_B}, {"commit_sha": SHA_A}]
    assert rn.fingerprint(a) == rn.fingerprint(b)


def test_fingerprint_changes_with_new_commit():
    a = [{"commit_sha": SHA_A}]
    b = [{"commit_sha": SHA_A}, {"commit_sha": SHA_B}]
    assert rn.fingerprint(a) != rn.fingerprint(b)


# --- deterministic_note ---------------------------------------------------

def test_deterministic_note_maps_types_to_buckets():
    note = rn.deterministic_note(
        [
            {"change_type": "feat", "summary": "yeni panel", "commit_sha": SHA_A},
            {"change_type": "fix", "summary": "rozet düzeltildi", "commit_sha": SHA_B},
        ]
    )
    assert note["added"][0]["text"] == "Yeni panel"
    assert note["added"][0]["shas"] == [SHA_A]
    assert note["fixed"][0]["text"] == "Rozet düzeltildi"
    assert note["improved"] == []


def test_deterministic_note_drops_internal_types():
    note = rn.deterministic_note([{"change_type": "chore", "summary": "bağımlılık", "commit_sha": SHA_A}])
    assert note == _empty()


def test_deterministic_note_never_raises_on_garbage():
    assert rn.deterministic_note([{}, {"change_type": None}, {"summary": ""}]) == _empty()


# --- validate_note --------------------------------------------------------

def test_validate_drops_unknown_buckets():
    out = rn.validate_note(
        {"added": [{"text": "iyi", "shas": [SHA_A]}], "removed": [{"text": "kötü", "shas": [SHA_B]}]},
        ALLOWED,
    )
    assert "removed" not in out
    assert len(out["added"]) == 1


def test_validate_drops_unknown_sha():
    out = rn.validate_note({"added": [{"text": "uydurma", "shas": ["cccccccccccc"]}]}, ALLOWED)
    assert out == _empty()


def test_validate_gives_a_sha_to_the_first_bullet_only():
    out = rn.validate_note(
        {
            "added": [{"text": "birinci", "shas": [SHA_A]}, {"text": "ikinci", "shas": [SHA_A]}],
        },
        ALLOWED,
    )
    assert [b["text"] for b in out["added"]] == ["birinci"]


def test_validate_caps_bullet_count_at_commit_count():
    raw = {"added": [{"text": f"madde {i}", "shas": [SHA_A, SHA_B]} for i in range(10)]}
    out = rn.validate_note(raw, ALLOWED)
    total = sum(len(out[b]) for b in rn.BUCKETS)
    assert total <= len(ALLOWED)


def test_validate_drops_overlong_text():
    out = rn.validate_note({"added": [{"text": "x" * 201, "shas": [SHA_A]}]}, ALLOWED)
    assert out == _empty()


def test_validate_cleans_sha_tokens_from_text():
    out = rn.validate_note({"added": [{"text": f"yeni panel ({SHA_A})", "shas": [SHA_A]}]}, ALLOWED)
    assert SHA_A not in out["added"][0]["text"]
    assert "yeni panel" in out["added"][0]["text"]


def test_validate_cleans_conventional_prefix_from_text():
    out = rn.validate_note({"added": [{"text": "feat(panel): yeni rozet", "shas": [SHA_A]}]}, ALLOWED)
    assert out["added"][0]["text"] == "yeni rozet"


def test_validate_drops_bullet_without_sha():
    out = rn.validate_note({"added": [{"text": "kaynaksız iddia", "shas": []}]}, ALLOWED)
    assert out == _empty()


def test_validate_returns_empty_on_non_dict():
    assert rn.validate_note("çöp", ALLOWED) == _empty()
    assert rn.validate_note(None, ALLOWED) == _empty()


def test_validate_survives_malformed_items():
    out = rn.validate_note({"added": ["düz metin", 42, {"text": "iyi", "shas": [SHA_A]}]}, ALLOWED)
    assert [b["text"] for b in out["added"]] == ["iyi"]


# --- build_payload --------------------------------------------------------

def test_build_payload_carries_only_allowed_fields():
    payload = rn.build_payload(
        {"version": "2026.08.1", "released_at": "2026-08-03"},
        [{"change_type": "feat", "summary": "yeni panel", "commit_sha": SHA_A, "scope": "panel"}],
    )
    assert payload["version"] == "2026.08.1"
    assert payload["changes"][0] == {
        "change_type": "feat",
        "summary": "yeni panel",
        "sha": SHA_A,
        "scope": "panel",
    }
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `$PY -m pytest tests/test_release_notes_service.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'src.services.release_notes'`.

- [ ] **Step 3: Saf fonksiyonları yaz**

`src/services/release_notes.py`:

```python
"""Release note üretiminin saf çekirdeği.

Bu modüldeki fonksiyonlar DB'ye ve ağa dokunmaz; hepsi aynı girdiye aynı çıktıyı verir.
Modelden gelen her şey `validate_note`'tan geçmeden hiçbir yere yazılmaz.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

BUCKETS: tuple[str, str, str] = ("added", "fixed", "improved")
MAX_TEXT = 200
_TRT = ZoneInfo("Europe/Istanbul")

# Conventional commit başlığı: tip, (scope), !, açıklama
_PREFIX_RE = re.compile(
    r"^(feat|fix|perf|chore|docs|refactor|test|style|build|ci)(\(([^)]+)\))?!?:\s*(.*)$",
    re.IGNORECASE,
)
# 7-40 karakterlik hex bloğu = sha benzeri jeton
_SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b", re.IGNORECASE)

# Okura gösterilen üç kova. Listede olmayan tip nota hiç girmez.
_TYPE_BUCKET = {"feat": "added", "fix": "fixed", "perf": "improved", "refactor": "improved"}


def parse_commit_subject(subject: str) -> tuple[str, str, str | None]:
    """('feat', 'temiz özet', 'scope'). Prefix yoksa ('other', subject, None)."""
    text = (subject or "").strip()
    m = _PREFIX_RE.match(text)
    if not m:
        return "other", text, None
    return m.group(1).lower(), m.group(4).strip(), (m.group(3) or None)


def trt_date(dt: datetime | None = None) -> date:
    """Verilen anın Europe/Istanbul takvim günü."""
    if dt is None:
        return datetime.now(_TRT).date()
    return dt.astimezone(_TRT).date()


def calver(d: date, seq: int) -> str:
    return f"{d.year}.{d.month:02d}.{seq}"


def fingerprint(changes: list[dict]) -> str:
    """Aynı commit kümesi = aynı parmak izi. Sıra fark etmez."""
    shas = sorted({str(c.get("commit_sha") or "")[:12] for c in changes or [] if c.get("commit_sha")})
    return hashlib.sha256("|".join(shas).encode("utf-8")).hexdigest()


def _empty_note() -> dict:
    return {b: [] for b in BUCKETS}


def deterministic_note(changes: list[dict]) -> dict:
    """Commit'lerden kodla yazılmış not. Asla hata vermez, asla boş sha üretmez."""
    note = _empty_note()
    for c in changes or []:
        bucket = _TYPE_BUCKET.get(str(c.get("change_type") or "").lower())
        if not bucket:
            continue
        sha = str(c.get("commit_sha") or "")[:12]
        text = str(c.get("summary") or "").strip()
        if not sha or not text:
            continue
        text = text[0].upper() + text[1:]
        note[bucket].append({"text": text[:MAX_TEXT], "shas": [sha]})
    return note


def _clean_text(text: str) -> str:
    text = _PREFIX_RE.sub(r"\4", text)
    text = _SHA_RE.sub("", text)
    text = re.sub(r"\(\s*\)|\[\s*\]", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" -–—:,;()")


def validate_note(raw, allowed_shas: set[str]) -> dict:
    """Modelin çıktısını kurallara indirger. Kurallar sırayla uygulanır.

    1. Bilinmeyen kova atılır.
    2. `allowed_shas` dışındaki sha atılır.
    3. Bir sha'yı yalnızca ilk bullet kullanabilir.
    4. 200 karakteri aşan metin düzeltilmez, atılır.
    5. Metindeki sha benzeri jetonlar ve conventional prefix temizlenir.
    6. Sha'sı kalmayan veya metni boşalan bullet atılır.
    7. Hiçbir bullet ayakta kalmadıysa boş not döner (çağıran merdivende ilerler).
    """
    clean = _empty_note()
    if not isinstance(raw, dict):
        return clean
    used: set[str] = set()
    for bucket in BUCKETS:
        items = raw.get(bucket)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_shas = item.get("shas")
            if not isinstance(raw_shas, list):
                continue
            shas = [str(s)[:12] for s in raw_shas if isinstance(s, str)]
            shas = [s for s in shas if s in allowed_shas and s not in used]
            text = str(item.get("text") or "").strip()
            if len(text) > MAX_TEXT:
                continue
            text = _clean_text(text)
            if not shas or not text:
                continue
            used.update(shas)
            clean[bucket].append({"text": text, "shas": shas})
    if not any(clean[b] for b in BUCKETS):
        return _empty_note()
    return clean


def build_payload(release: dict, changes: list[dict]) -> dict:
    """Modele gidecek gövde. Sadece bu alanlar gider; DB satırı olduğu gibi gönderilmez."""
    return {
        "version": str(release.get("version") or ""),
        "released_at": str(release.get("released_at") or "")[:10],
        "changes": [
            {
                "change_type": str(c.get("change_type") or "other"),
                "summary": str(c.get("summary") or ""),
                "sha": str(c.get("commit_sha") or "")[:12],
                "scope": c.get("scope"),
            }
            for c in changes or []
            if c.get("commit_sha")
        ],
    }
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Run: `$PY -m pytest tests/test_release_notes_service.py -v`
Expected: 21 passed.

- [ ] **Step 5: Commit**

```bash
git add src/services/release_notes.py tests/test_release_notes_service.py
git commit -m "feat(task-64): pure release-note core (parse, fingerprint, deterministic, validate)"
```

---

### Task 4: chatbot-api `release-notes` router

**Files:**
- Create: `services/chatbot-api/app/routers/release_notes.py`
- Modify: `services/chatbot-api/app/main.py`
- Test: `services/chatbot-api/app/tests/test_release_notes_contract.py`

**Interfaces:**
- Consumes: `app.services.llm_client.get_llm_client()` → `LLMClient.complete(messages, model=None, max_tokens=None) -> LLMResult(answer, model, usage)`, `LLMError(error_type, user_message, detail)`; `app.core.api_auth.verify_api_user`.
- Produces: `POST /api/v1/release-notes/generate`.
  İstek gövdesi: `{"version": str, "released_at": str, "changes": [{"change_type", "summary", "sha", "scope"}], "strict": bool, "complaint": str|null, "model": str|null}`.
  Yanıt: `{"status": "ok"|"failed", "headline": str|null, "body": {"added": [], "fixed": [], "improved": []}, "model": str|null, "detail": str|null}`.
  Task 5 bu sözleşmeyi çağırır.

**Not:** Bu router stateless'tır — DB'ye hiç dokunmaz. Operasyonel hatada 500 değil, **200 + `status="failed"`** döner; çağıran merdivende bir basamak ilerler.

- [ ] **Step 1: Başarısız testi yaz**

`services/chatbot-api/app/tests/test_release_notes_contract.py`:

```python
"""release-notes router sözleşmesi — LLM mock'lanır."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app
from app.routers import release_notes as router_mod
from app.services.llm_client import LLMError, LLMResult

client = TestClient(app)

_REQ = {
    "version": "2026.08.1",
    "released_at": "2026-08-03",
    "changes": [
        {"change_type": "feat", "summary": "yeni panel", "sha": "aaaaaaaaaaaa", "scope": "panel"},
    ],
}


def _mock_llm(monkeypatch, answer=None, error=None):
    class _FakeLLM:
        def __init__(self):
            self.seen = []

        def complete(self, messages, model=None, **kwargs):
            self.seen.append(messages)
            if error is not None:
                raise error
            return LLMResult(answer=answer, model="gpt-oss-120b", usage={})

    fake = _FakeLLM()
    monkeypatch.setattr(router_mod, "get_llm_client", lambda: fake)
    return fake


def test_generate_returns_parsed_body(monkeypatch):
    _mock_llm(
        monkeypatch,
        answer=json.dumps(
            {
                "headline": "Panel yenilendi",
                "added": [{"text": "Yeni panel eklendi", "shas": ["aaaaaaaaaaaa"]}],
                "fixed": [],
                "improved": [],
            },
            ensure_ascii=False,
        ),
    )
    r = client.post("/api/v1/release-notes/generate", json=_REQ)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["headline"] == "Panel yenilendi"
    assert data["body"]["added"][0]["shas"] == ["aaaaaaaaaaaa"]
    assert data["model"] == "gpt-oss-120b"


def test_generate_strips_code_fence(monkeypatch):
    _mock_llm(
        monkeypatch,
        answer='```json\n{"headline": "X", "added": [], "fixed": [], "improved": []}\n```',
    )
    data = client.post("/api/v1/release-notes/generate", json=_REQ).json()
    assert data["status"] == "ok"
    assert data["body"] == {"added": [], "fixed": [], "improved": []}


def test_generate_reports_failed_on_unparsable_answer(monkeypatch):
    _mock_llm(monkeypatch, answer="Tabii, işte release note'unuz!")
    r = client.post("/api/v1/release-notes/generate", json=_REQ)
    assert r.status_code == 200
    assert r.json()["status"] == "failed"
    assert r.json()["detail"] == "unparsable"


def test_generate_reports_failed_on_llm_error(monkeypatch):
    _mock_llm(monkeypatch, error=LLMError("upstream", "servis yanıt vermedi", "502"))
    r = client.post("/api/v1/release-notes/generate", json=_REQ)
    assert r.status_code == 200
    assert r.json()["status"] == "failed"
    assert r.json()["detail"] == "upstream"


def test_strict_mode_changes_the_system_prompt(monkeypatch):
    fake = _mock_llm(monkeypatch, answer='{"added": [], "fixed": [], "improved": []}')
    client.post("/api/v1/release-notes/generate", json={**_REQ, "strict": True})
    system = fake.seen[0][0]["content"]
    assert "KATI MOD" in system


def test_complaint_is_appended_to_the_user_message(monkeypatch):
    fake = _mock_llm(monkeypatch, answer='{"added": [], "fixed": [], "improved": []}')
    client.post(
        "/api/v1/release-notes/generate",
        json={**_REQ, "complaint": "Listede olmayan sha kullandın: zzz."},
    )
    user = fake.seen[0][1]["content"]
    assert "Listede olmayan sha kullandın" in user


def test_missing_buckets_are_filled_with_empty_lists(monkeypatch):
    _mock_llm(monkeypatch, answer='{"headline": "X", "added": [{"text": "a", "shas": []}]}')
    body = client.post("/api/v1/release-notes/generate", json=_REQ).json()["body"]
    assert body["fixed"] == []
    assert body["improved"] == []
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `$PY -m pytest services/chatbot-api/app/tests/test_release_notes_contract.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'app.routers.release_notes'`.

- [ ] **Step 3: Router'ı yaz**

`services/chatbot-api/app/routers/release_notes.py`:

```python
"""Release note üretimi. Stateless: DB'ye dokunmaz, durum tutmaz.

Operasyonel hatalarda HTTP 500 değil, 200 + status="failed" döner; çağıran taraf
kendi merdiveninde bir basamak ilerlesin diye.
"""

from __future__ import annotations

import json
import logging
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.api_auth import verify_api_user
from app.services.llm_client import LLMError, get_llm_client

logger = logging.getLogger(__name__)
router = APIRouter()

_BUCKETS = ("added", "fixed", "improved")
_FENCE_RE = re.compile(r"```(?:json)?", re.IGNORECASE)

_SYSTEM = """Sen bir release note yazarısın. Sana bir sürümün commit listesi verilir;
sen bunu son kullanıcının okuyacağı kısa bir nota çevirirsin.

Kurallar:
- Yalnızca JSON döndür. Açıklama, markdown, kod bloğu yok.
- Şema: {"headline": "...", "added": [...], "fixed": [...], "improved": [...]}
- Her madde şu biçimde: {"text": "...", "shas": ["<sha>"]}
- `shas` içindeki her değer, sana verilen commit listesindeki `sha` alanlarından biri OLMAK ZORUNDA.
- Bir sha'yı yalnızca tek bir maddede kullan.
- Sana verilmeyen hiçbir bilgiyi ekleme. Sayı, yüzde, tarih, kişi adı veya performans iddiası uydurma.
- Bir commit'in ne yaptığını anlamıyorsan onu hiç yazma. Eksik not, yanlış nottan iyidir.
- Metin Türkçe olsun; teknik terimleri (release, commit, panel, endpoint) İngilizce bırak.
- Her madde en fazla 200 karakter, tek cümle; "feat:" gibi prefix içermesin.
- headline: sürümü tek cümlede özetleyen Türkçe başlık, en fazla 80 karakter."""

_STRICT_SUFFIX = """

KATI MOD: Emin olmadığın her maddeyi at. Yalnızca commit özetinin doğrudan söylediğini yaz.
Hiçbir madde güvenli değilse boş listeler döndür."""


class ReleaseChangeIn(BaseModel):
    change_type: str = "other"
    summary: str = ""
    sha: str = ""
    scope: str | None = None


class ReleaseNoteRequest(BaseModel):
    version: str
    released_at: str = ""
    changes: list[ReleaseChangeIn] = Field(default_factory=list)
    strict: bool = False
    complaint: str | None = None
    model: str | None = None


class ReleaseNoteResponse(BaseModel):
    status: str
    headline: str | None = None
    body: dict = Field(default_factory=dict)
    model: str | None = None
    detail: str | None = None


def _parse_json(answer: str) -> dict | None:
    """Model çıktısından JSON nesnesini çıkarır. Çıkaramazsa None."""
    text = _FENCE_RE.sub("", answer or "").replace("```", "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


@router.post("/generate", response_model=ReleaseNoteResponse)
async def generate(
    req: ReleaseNoteRequest, _user=Depends(verify_api_user)
) -> ReleaseNoteResponse:
    system = _SYSTEM + (_STRICT_SUFFIX if req.strict else "")
    user = json.dumps(
        {
            "version": req.version,
            "released_at": req.released_at,
            "changes": [c.model_dump() for c in req.changes],
        },
        ensure_ascii=False,
    )
    if req.complaint:
        user += (
            "\n\nÖnceki denemen şu sebeple reddedildi: "
            + req.complaint
            + "\nBu sefer aynı hatayı yapma."
        )

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        result = get_llm_client().complete(messages, model=req.model, max_tokens=1200)
    except LLMError as exc:
        logger.warning("release note generation failed (%s): %s", exc.error_type, exc.detail)
        return ReleaseNoteResponse(status="failed", detail=exc.error_type)

    parsed = _parse_json(result.answer)
    if parsed is None:
        logger.warning("release note answer was not JSON")
        return ReleaseNoteResponse(status="failed", detail="unparsable")

    headline = parsed.get("headline")
    return ReleaseNoteResponse(
        status="ok",
        headline=str(headline) if headline else None,
        body={b: (parsed.get(b) if isinstance(parsed.get(b), list) else []) for b in _BUCKETS},
        model=result.model,
    )
```

- [ ] **Step 4: Router'ı kaydet**

`services/chatbot-api/app/main.py` — `chatbot` router'ının import satırına `release_notes`'u ekle, kayıt satırının hemen ardına:

```python
app.include_router(release_notes.router, prefix="/api/v1/release-notes", tags=["release-notes"])
```

- [ ] **Step 5: Testlerin geçtiğini gör**

Run: `$PY -m pytest services/chatbot-api/app/tests/ -v`
Expected: 7 yeni test passed, mevcut chatbot testleri hâlâ passed.

- [ ] **Step 6: Commit**

```bash
git add services/chatbot-api/app/routers/release_notes.py services/chatbot-api/app/main.py services/chatbot-api/app/tests/test_release_notes_contract.py
git commit -m "feat(task-64): stateless release-note generation endpoint in chatbot-api"
```

---

### Task 5: Servis token'ı + GUI'nin chatbot-api istemcisi

**Files:**
- Modify: `src/auth/api_jwt.py`
- Modify: `src/services/chatbot_client.py`
- Test: `tests/test_chatbot_client_release_notes.py`

**Interfaces:**
- Consumes: Task 4'ün `POST /api/v1/release-notes/generate` sözleşmesi; mevcut `CHATBOT_API_URL`.
- Produces:
  - `src.auth.api_jwt.create_service_token(subject: str = "release-bot") -> str`
  - `src.services.chatbot_client.generate_release_note(payload: dict, *, strict: bool = False, complaint: str | None = None, model: str | None = None, timeout: int = 60) -> dict`
    Dönen sözlük her zaman `status` anahtarını içerir (`"ok"` veya `"failed"`). Ağ hatasında bile exception fırlatmaz.
  - Task 6 bunu çağırır.

**Neden yeni auth yok:** `services/chatbot-api/app/core/api_auth.py` yalnızca `sub`'ın boş olmamasına bakar, DB'de kullanıcı aramaz. `sub="release-bot"` olan token hiçbir değişiklik gerekmeden doğrulanır.

- [ ] **Step 1: Başarısız testi yaz**

`tests/test_chatbot_client_release_notes.py`:

```python
"""GUI → chatbot-api release note çağrısı — ağ mock'lanır."""

from __future__ import annotations

from unittest.mock import patch

import jwt
import pytest
import requests

from src.auth import api_jwt
from src.services import chatbot_client


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def test_service_token_carries_subject_and_typ():
    token = api_jwt.create_service_token()
    claims = jwt.decode(token, api_jwt._API_SECRET, algorithms=["HS256"])
    assert claims["sub"] == "release-bot"
    assert claims["typ"] == "service"
    assert claims["exp"] > claims["iat"]


def test_generate_posts_to_release_notes_endpoint():
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        return _Resp({"status": "ok", "body": {"added": [], "fixed": [], "improved": []}})

    with patch.object(chatbot_client.requests, "post", fake_post):
        out = chatbot_client.generate_release_note({"version": "2026.08.1", "changes": []})

    assert seen["url"].endswith("/api/v1/release-notes/generate")
    assert seen["json"]["strict"] is False
    assert seen["headers"]["Authorization"].startswith("Bearer ")
    assert out["status"] == "ok"


def test_generate_forwards_strict_and_complaint():
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(json)
        return _Resp({"status": "ok", "body": {}})

    with patch.object(chatbot_client.requests, "post", fake_post):
        chatbot_client.generate_release_note({"version": "v"}, strict=True, complaint="sha uydurdun")

    assert seen["strict"] is True
    assert seen["complaint"] == "sha uydurdun"


@pytest.mark.parametrize(
    "boom",
    [requests.ConnectionError("down"), requests.Timeout("slow")],
)
def test_generate_returns_failed_instead_of_raising(boom):
    def fake_post(*a, **k):
        raise boom

    with patch.object(chatbot_client.requests, "post", fake_post):
        out = chatbot_client.generate_release_note({"version": "v"})

    assert out == {"status": "failed", "detail": "transport"}


def test_generate_returns_failed_on_http_error():
    with patch.object(chatbot_client.requests, "post", lambda *a, **k: _Resp({}, status=502)):
        assert chatbot_client.generate_release_note({"version": "v"})["status"] == "failed"


def test_generate_returns_failed_on_non_dict_json():
    with patch.object(chatbot_client.requests, "post", lambda *a, **k: _Resp(["liste"])):
        assert chatbot_client.generate_release_note({"version": "v"})["status"] == "failed"
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `$PY -m pytest tests/test_chatbot_client_release_notes.py -v`
Expected: FAIL — `AttributeError: module 'src.auth.api_jwt' has no attribute 'create_service_token'`.

- [ ] **Step 3: Servis token'ını yaz**

`src/auth/api_jwt.py` — `create_api_token`'ın altına:

```python
def create_service_token(subject: str = "release-bot") -> str:
    """Kullanıcıya bağlı olmayan, arka plan işleri için token.

    Karşı taraf (chatbot-api `core/api_auth.py`) yalnızca `sub`'ın dolu olmasına bakar,
    DB'de kullanıcı aramaz; bu yüzden servis token'ı olduğu gibi geçerlidir.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=_TTL_MIN),
        "typ": "service",
    }
    return jwt.encode(payload, _API_SECRET, algorithm=_ALGO)
```

- [ ] **Step 4: İstemci fonksiyonunu yaz**

`src/services/chatbot_client.py` — dosyanın sonuna:

```python
def generate_release_note(
    payload: dict,
    *,
    strict: bool = False,
    complaint: str | None = None,
    model: str | None = None,
    timeout: int = 60,
) -> dict:
    """chatbot-api'den release note ister.

    Asla exception fırlatmaz; her yolda `status` anahtarı olan bir sözlük döner,
    çünkü çağıran taraf başarısızlıkta merdivende ilerlemek zorunda.
    """
    body = dict(payload)
    body["strict"] = bool(strict)
    body["complaint"] = complaint
    body["model"] = model
    headers = {
        "Authorization": f"Bearer {create_service_token()}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            f"{CHATBOT_API_URL}/api/v1/release-notes/generate",
            json=body,
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("release note request failed: %s", exc)
        return {"status": "failed", "detail": "transport"}
    if not isinstance(data, dict) or "status" not in data:
        return {"status": "failed", "detail": "shape"}
    return data
```

Dosyanın başına import ekle: `from src.auth.api_jwt import create_service_token`. `logger` yoksa `logger = logging.getLogger(__name__)` satırını da ekle.

- [ ] **Step 5: Testlerin geçtiğini gör**

Run: `$PY -m pytest tests/test_chatbot_client_release_notes.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add src/auth/api_jwt.py src/services/chatbot_client.py tests/test_chatbot_client_release_notes.py
git commit -m "feat(task-64): service token and release-note client for chatbot-api"
```

---

### Task 6: Üretim merdiveni (`release_note_generator`)

**Files:**
- Create: `src/services/release_note_generator.py`
- Test: `tests/test_release_note_ladder.py`

**Interfaces:**
- Consumes: Task 2'nin `versions_crud` fonksiyonları, Task 3'ün saf fonksiyonları, Task 5'in `chatbot_client.generate_release_note`.
- Produces: `generate_for_release(release_id: int) -> dict`
  Dönen sözlük: `{"status": "draft"|"auto", "headline": str|None, "body": dict}`.
  Task 7 ve Task 11 bunu çağırır.

**Kritik davranış:** LLM'e gitmeden **önce** deterministik not `body`'ye yazılır. Böylece sonraki her adım başarısız olsa bile panelde daima kodla yazılmış bir not bulunur. Yalnızca not yoksa veya mevcut not `source='auto'` ise `body` tazelenir; insan onayından geçmiş (`source='model'`) not asla ezilmez.

- [ ] **Step 1: Başarısız testi yaz**

`tests/test_release_note_ladder.py`:

```python
"""Üretim merdiveni — DB ve chatbot-api mock'lanır."""

from __future__ import annotations

from unittest.mock import patch

from src.services import release_note_generator as gen

SHA_A = "aaaaaaaaaaaa"
SHA_B = "bbbbbbbbbbbb"

_RELEASE = {
    "id": 7,
    "version": "2026.08.1",
    "released_at": "2026-08-03",
    "changes": [
        {"change_type": "feat", "summary": "yeni panel", "commit_sha": SHA_A, "scope": "panel"},
        {"change_type": "fix", "summary": "rozet düzeltildi", "commit_sha": SHA_B, "scope": None},
    ],
}


class _Recorder:
    def __init__(self, existing_note=None):
        self.upserts: list[dict] = []
        self.drafts: list[dict] = []
        self.existing_note = existing_note

    def get_release(self, release_id):
        return dict(_RELEASE) if release_id == 7 else None

    def get_release_note(self, release_id):
        return self.existing_note

    def upsert_note(self, release_id, **kw):
        self.upserts.append(kw)

    def set_draft_note(self, release_id, **kw):
        self.drafts.append(kw)


def _install(rec, responses):
    calls = {"n": 0, "sent": []}

    def fake_generate(payload, *, strict=False, complaint=None, model=None):
        calls["sent"].append({"strict": strict, "complaint": complaint})
        i = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return responses[i]

    ctx = patch.multiple(
        gen.versions_crud,
        get_release=rec.get_release,
        get_release_note=rec.get_release_note,
        upsert_note=rec.upsert_note,
        set_draft_note=rec.set_draft_note,
    )
    ctx2 = patch.object(gen.chatbot_client, "generate_release_note", fake_generate)
    return ctx, ctx2, calls


def _ok(added_text="Yeni panel eklendi", sha=SHA_A, headline="Panel yenilendi"):
    return {
        "status": "ok",
        "headline": headline,
        "model": "gpt-oss-120b",
        "body": {"added": [{"text": added_text, "shas": [sha]}], "fixed": [], "improved": []},
    }


def test_body_is_written_before_any_llm_call():
    rec = _Recorder()
    ctx, ctx2, _ = _install(rec, [{"status": "failed", "detail": "upstream"}])
    with ctx, ctx2:
        out = gen.generate_for_release(7)
    assert rec.upserts[0]["source"] == "auto"
    assert rec.upserts[0]["body"]["added"][0]["text"] == "Yeni panel"
    assert out["status"] == "auto"
    assert out["body"]["fixed"][0]["text"] == "Rozet düzeltildi"


def test_successful_first_attempt_writes_draft_only():
    rec = _Recorder()
    ctx, ctx2, calls = _install(rec, [_ok()])
    with ctx, ctx2:
        out = gen.generate_for_release(7)
    assert calls["n"] == 1
    assert out["status"] == "draft"
    assert rec.drafts[0]["draft_body"]["added"][0]["text"] == "Yeni panel eklendi"
    assert rec.drafts[0]["model"] == "gpt-oss-120b"
    # Yayındaki body hâlâ deterministik nottur; taslak onaylanana kadar değişmez.
    assert len(rec.upserts) == 1


def test_hallucinated_sha_triggers_repair_round_with_complaint():
    rec = _Recorder()
    bad = {
        "status": "ok",
        "headline": "X",
        "model": "m",
        "body": {"added": [{"text": "uydurma", "shas": ["cccccccccccc"]}], "fixed": [], "improved": []},
    }
    ctx, ctx2, calls = _install(rec, [bad, _ok()])
    with ctx, ctx2:
        out = gen.generate_for_release(7)
    assert calls["n"] == 2
    assert "cccccccccccc" in calls["sent"][1]["complaint"]
    assert out["status"] == "draft"


def test_third_attempt_runs_in_strict_mode():
    rec = _Recorder()
    bad = {"status": "ok", "headline": None, "model": "m", "body": {"added": [], "fixed": [], "improved": []}}
    ctx, ctx2, calls = _install(rec, [bad, bad, _ok()])
    with ctx, ctx2:
        gen.generate_for_release(7)
    assert calls["sent"][2]["strict"] is True


def test_all_attempts_failing_falls_back_to_deterministic_note():
    rec = _Recorder()
    dud = {"status": "failed", "detail": "upstream"}
    ctx, ctx2, calls = _install(rec, [dud, dud, dud])
    with ctx, ctx2:
        out = gen.generate_for_release(7)
    assert calls["n"] == 3
    assert rec.drafts == []
    assert out["status"] == "auto"
    assert out["body"]["added"][0]["text"] == "Yeni panel"


def test_confirmed_note_is_never_overwritten():
    rec = _Recorder(existing_note={"release_id": 7, "source": "model", "body": {"added": []}})
    ctx, ctx2, _ = _install(rec, [_ok()])
    with ctx, ctx2:
        gen.generate_for_release(7)
    assert rec.upserts == []       # yayındaki insan onaylı nota dokunulmadı
    assert len(rec.drafts) == 1    # yalnızca taslak yazıldı


def test_auto_note_is_refreshed_when_new_commits_arrive():
    rec = _Recorder(existing_note={"release_id": 7, "source": "auto", "body": {"added": []}})
    ctx, ctx2, _ = _install(rec, [{"status": "failed", "detail": "upstream"}])
    with ctx, ctx2:
        gen.generate_for_release(7)
    assert len(rec.upserts) == 1
    assert len(rec.upserts[0]["body"]["added"]) == 1


def test_unknown_release_raises():
    rec = _Recorder()
    ctx, ctx2, _ = _install(rec, [_ok()])
    with ctx, ctx2:
        try:
            gen.generate_for_release(999)
        except ValueError as exc:
            assert "999" in str(exc)
        else:
            raise AssertionError("ValueError bekleniyordu")
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `$PY -m pytest tests/test_release_note_ladder.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'src.services.release_note_generator'`.

- [ ] **Step 3: Merdiveni yaz**

`src/services/release_note_generator.py`:

```python
"""Release note üretim merdiveni.

Basamaklar:
  1. Birincil model.
  2. Somut şikayetle onarım turu (modele tam olarak neyi yanlış yaptığı söylenir).
  3. Katı mod. chatbot-api'nin LLMClient'ı upstream hatasında zaten fallback modele düşer.
  4. Merdivenin altı: kodla yazılmış not. Bu not zaten `body`'de durduğu için ek iş gerekmez.

`body` hiçbir yolda boş kalmaz; ham commit subject'i de gövdeye hiç girmez, çünkü
deterministik not conventional prefix'i ayıklanmış özeti kullanır.
"""

from __future__ import annotations

import logging

from src.auth import versions_crud
from src.services import chatbot_client
from src.services import release_notes as rn

logger = logging.getLogger(__name__)

# (strict, şikayet üretilsin mi)
_ATTEMPTS = ((False, False), (False, True), (True, False))


def _allowed_shas(changes: list[dict]) -> set[str]:
    return {str(c.get("commit_sha") or "")[:12] for c in changes if c.get("commit_sha")}


def _complaint(raw_body, allowed: set[str]) -> str:
    """Reddedilen çıktı için modele verilecek somut gerekçe."""
    reasons: list[str] = []
    if not isinstance(raw_body, dict):
        raw_body = {}
    for bucket in rn.BUCKETS:
        items = raw_body.get(bucket)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                reasons.append("Maddeler nesne olmalı.")
                continue
            shas = [s for s in (item.get("shas") or []) if isinstance(s, str)]
            unknown = [s for s in shas if str(s)[:12] not in allowed]
            if unknown:
                reasons.append(f"Listede olmayan sha kullandın: {', '.join(unknown[:3])}.")
            if not shas:
                reasons.append("Bir maddeyi hiçbir commit'e bağlamadın.")
            if len(str(item.get("text") or "")) > rn.MAX_TEXT:
                reasons.append(f"Bir madde {rn.MAX_TEXT} karakteri aştı.")
    if not reasons:
        reasons.append("Çıktın doğrulamadan geçmedi; yalnızca sana verilen commit'leri kullan.")
    return " ".join(dict.fromkeys(reasons))[:500]


def generate_for_release(release_id: int) -> dict:
    """Notu üretir, taslağı yazar. Döner: {"status": "draft"|"auto", "headline", "body"}."""
    rel = versions_crud.get_release(release_id)
    if not rel:
        raise ValueError(f"release not found: {release_id}")

    changes = rel.get("changes") or []
    allowed = _allowed_shas(changes)
    auto_body = rn.deterministic_note(changes)

    # İnsan onaylı notu ezmeden, yayındaki gövdeyi her zaman dolu tut.
    existing = versions_crud.get_release_note(release_id)
    if existing is None or str(existing.get("source") or "auto") == "auto":
        versions_crud.upsert_note(
            release_id,
            body=auto_body,
            source="auto",
            input_fingerprint=rn.fingerprint(changes),
        )

    payload = rn.build_payload(rel, changes)
    last_raw: dict = {}
    for i, (strict, with_complaint) in enumerate(_ATTEMPTS, start=1):
        resp = chatbot_client.generate_release_note(
            payload,
            strict=strict,
            complaint=_complaint(last_raw, allowed) if with_complaint else None,
        )
        if resp.get("status") != "ok":
            logger.info("release note attempt %s failed: %s", i, resp.get("detail"))
            continue
        last_raw = resp.get("body") or {}
        clean = rn.validate_note(last_raw, allowed)
        if any(clean[b] for b in rn.BUCKETS):
            headline = resp.get("headline") or None
            versions_crud.set_draft_note(
                release_id,
                draft_headline=(str(headline)[:120] if headline else None),
                draft_body=clean,
                model=str(resp.get("model") or ""),
            )
            return {"status": "draft", "headline": headline, "body": clean}
        logger.info("release note attempt %s rejected by validator", i)

    logger.info("release %s falls back to the deterministic note", release_id)
    return {"status": "auto", "headline": None, "body": auto_body}
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Run: `$PY -m pytest tests/test_release_note_ladder.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/services/release_note_generator.py tests/test_release_note_ladder.py
git commit -m "feat(task-64): four-rung generation ladder with deterministic floor"
```

---

### Task 7: Ingest ve onay endpoint'leri

**Files:**
- Create: `src/routes/__init__.py`
- Create: `src/routes/release_ingest.py`
- Modify: `src/app.py` (`register_middleware(server)` çağrısının hemen ardı, ~satır 117)
- Test: `tests/test_release_ingest_endpoint.py`

**Interfaces:**
- Consumes: Task 2 (`versions_crud`), Task 3 (`release_notes`), Task 6 (`release_note_generator`).
- Produces: `register_release_ingest_routes(flask_app) -> None` ve şu yollar:
  - `GET  /internal/platform/releases/last-sha` → `{"last_sha": str|null}`
  - `GET  /internal/platform/releases/versions` → `{"versions": [str]}`
  - `POST /internal/platform/releases` — gövde `{"commits": [{"sha", "date", "subject"}], "version": str|null}` → 201 `{"version", "release_id", "changes_added", "note"}`
  - `POST /internal/platform/releases/<version>/note/confirm` → `{"confirmed": bool}`
  - `POST /internal/platform/releases/<version>/note/reject` → `{"rejected": true}`
  - `POST /internal/platform/releases/<version>/note/regenerate` → `{"note": {...}}`
  - Task 8 ve Task 11 bu yolları çağırır.

**Neden `/internal/`:** ingress `/api/v1/*` isteklerini başka servislere yönlendiriyor; bu yollar GUI'nin kendi Flask sunucusunda kalmak zorunda.

**Neden onaylanan metin gövdede taşınmıyor:** script yalnızca `confirm`/`reject` gönderir. Böylece token'ı ele geçiren biri panele istediği metni yazdıramaz — yayına yalnızca sunucunun kendi ürettiği ve doğruladığı taslak çıkabilir.

- [ ] **Step 1: Başarısız testi yaz**

`tests/test_release_ingest_endpoint.py`:

```python
"""Ingest ve onay endpoint'leri — token, TRT günü, dedupe, onay."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import flask
import pytest

from src.routes import release_ingest

TOKEN = "test-token-123"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("RELEASE_INGEST_TOKEN", TOKEN)
    app = flask.Flask(__name__)
    release_ingest.register_release_ingest_routes(app)
    return app.test_client()


def _hdr(token=TOKEN):
    return {"X-Release-Token": token}


_COMMITS = [
    {"sha": "aaaaaaaaaaaa", "date": "2026-08-03", "subject": "feat(panel): yeni rozet"},
    {"sha": "bbbbbbbbbbbb", "date": "2026-08-03", "subject": "fix: rozet hizası"},
]


def test_missing_token_env_returns_503(monkeypatch):
    monkeypatch.delenv("RELEASE_INGEST_TOKEN", raising=False)
    app = flask.Flask(__name__)
    release_ingest.register_release_ingest_routes(app)
    r = app.test_client().get("/internal/platform/releases/last-sha", headers=_hdr())
    assert r.status_code == 503


def test_empty_token_env_returns_503(monkeypatch):
    monkeypatch.setenv("RELEASE_INGEST_TOKEN", "   ")
    app = flask.Flask(__name__)
    release_ingest.register_release_ingest_routes(app)
    r = app.test_client().get("/internal/platform/releases/last-sha", headers=_hdr())
    assert r.status_code == 503


def test_wrong_token_returns_403(client):
    assert client.get("/internal/platform/releases/last-sha", headers=_hdr("nope")).status_code == 403


def test_missing_header_returns_403(client):
    assert client.get("/internal/platform/releases/last-sha").status_code == 403


def test_last_sha_returns_stored_value(client):
    with patch.object(release_ingest.versions_crud, "last_ingested_sha", lambda: "aaaaaaaaaaaa"):
        r = client.get("/internal/platform/releases/last-sha", headers=_hdr())
    assert r.status_code == 200
    assert r.get_json()["last_sha"] == "aaaaaaaaaaaa"


def test_versions_endpoint_lists_known_versions(client):
    with patch.object(
        release_ingest.versions_crud,
        "list_platform_releases",
        lambda: [{"version": "2026.08.1"}, {"version": "2026.07.1"}, {}],
    ):
        r = client.get("/internal/platform/releases/versions", headers=_hdr())
    assert r.get_json()["versions"] == ["2026.08.1", "2026.07.1"]


def test_versions_endpoint_is_token_gated(client):
    assert client.get("/internal/platform/releases/versions", headers=_hdr("nope")).status_code == 403


def test_ingest_computes_calver_from_trt_day(client):
    seen = {}

    def fake_open(version, released_at, title=None):
        seen["version"] = version
        seen["released_at"] = released_at
        return 7

    with patch.object(release_ingest.rn, "trt_date", lambda: date(2026, 8, 3)), \
         patch.object(release_ingest.versions_crud, "month_release_count", lambda y, m: 2), \
         patch.object(release_ingest.versions_crud, "open_release", fake_open), \
         patch.object(release_ingest.versions_crud, "add_release_changes", lambda rid, ch: len(ch)), \
         patch.object(release_ingest.generator, "generate_for_release", lambda rid: {"status": "draft", "body": {}}):
        r = client.post("/internal/platform/releases", json={"commits": _COMMITS}, headers=_hdr())

    assert r.status_code == 201
    assert seen["version"] == "2026.08.3"
    assert seen["released_at"] == "2026-08-03"
    assert r.get_json()["changes_added"] == 2


def test_ingest_parses_conventional_prefixes(client):
    captured = {}

    with patch.object(release_ingest.rn, "trt_date", lambda: date(2026, 8, 3)), \
         patch.object(release_ingest.versions_crud, "month_release_count", lambda y, m: 0), \
         patch.object(release_ingest.versions_crud, "open_release", lambda *a, **k: 7), \
         patch.object(release_ingest.versions_crud, "add_release_changes",
                      lambda rid, ch: captured.setdefault("changes", ch) and 0 or len(ch)), \
         patch.object(release_ingest.generator, "generate_for_release", lambda rid: {"status": "auto", "body": {}}):
        client.post("/internal/platform/releases", json={"commits": _COMMITS}, headers=_hdr())

    first = captured["changes"][0]
    assert first["change_type"] == "feat"
    assert first["summary"] == "yeni rozet"
    assert first["scope"] == "panel"
    assert first["commit_sha"] == "aaaaaaaaaaaa"


def test_ingest_rejects_empty_commit_list(client):
    r = client.post("/internal/platform/releases", json={"commits": []}, headers=_hdr())
    assert r.status_code == 400


def test_ingest_rejects_commits_without_sha(client):
    r = client.post(
        "/internal/platform/releases",
        json={"commits": [{"subject": "feat: x"}]},
        headers=_hdr(),
    )
    assert r.status_code == 400


def test_ingest_honours_explicit_version(client):
    seen = {}
    with patch.object(release_ingest.versions_crud, "open_release",
                      lambda v, d, title=None: seen.setdefault("v", v) and 7 or 7), \
         patch.object(release_ingest.versions_crud, "add_release_changes", lambda rid, ch: 1), \
         patch.object(release_ingest.generator, "generate_for_release", lambda rid: {"status": "auto", "body": {}}):
        client.post(
            "/internal/platform/releases",
            json={"commits": _COMMITS, "version": "2026.08.9"},
            headers=_hdr(),
        )
    assert seen["v"] == "2026.08.9"


def test_confirm_promotes_the_draft(client):
    with patch.object(release_ingest.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(release_ingest.versions_crud, "confirm_draft_note", lambda rid: True):
        r = client.post("/internal/platform/releases/2026.08.1/note/confirm", headers=_hdr())
    assert r.status_code == 200
    assert r.get_json()["confirmed"] is True


def test_confirm_unknown_version_returns_404(client):
    with patch.object(release_ingest.versions_crud, "get_release_by_version", lambda v: None):
        r = client.post("/internal/platform/releases/9999.99.9/note/confirm", headers=_hdr())
    assert r.status_code == 404


def test_reject_clears_the_draft(client):
    with patch.object(release_ingest.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(release_ingest.versions_crud, "reject_draft_note", lambda rid: True):
        r = client.post("/internal/platform/releases/2026.08.1/note/reject", headers=_hdr())
    assert r.get_json()["rejected"] is True


def test_regenerate_returns_a_fresh_note(client):
    with patch.object(release_ingest.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(release_ingest.generator, "generate_for_release",
                      lambda rid: {"status": "draft", "headline": "Yeni", "body": {"added": []}}):
        r = client.post("/internal/platform/releases/2026.08.1/note/regenerate", headers=_hdr())
    assert r.get_json()["note"]["headline"] == "Yeni"


def test_confirm_body_is_ignored(client):
    """Script metin göndermez; gönderse bile sunucu dikkate almaz."""
    with patch.object(release_ingest.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(release_ingest.versions_crud, "confirm_draft_note", lambda rid: True):
        r = client.post(
            "/internal/platform/releases/2026.08.1/note/confirm",
            json={"body": {"added": [{"text": "SAHTE", "shas": ["x"]}]}},
            headers=_hdr(),
        )
    assert r.get_json() == {"confirmed": True}
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `$PY -m pytest tests/test_release_ingest_endpoint.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'src.routes'`.

- [ ] **Step 3: Paketi ve endpoint'leri yaz**

`src/routes/__init__.py`:

```python
"""Dash uygulamasının Flask sunucusuna eklenen düz HTTP yolları."""
```

`src/routes/release_ingest.py`:

```python
"""Release ingest ve not onay endpoint'leri.

Yol öneki `/internal/` — ingress `/api/v1/*` isteklerini başka servislere yönlendirdiği
için bu yollar GUI'nin kendi Flask sunucusunda kalmalı.

Kimlik doğrulama paylaşılan bir token'la yapılır. `RELEASE_INGEST_TOKEN` tanımsız veya
boşsa endpoint 503 döner; hiçbir koşulda açık moda düşmez.

Onaylanan not metni istekle taşınmaz: script yalnızca confirm/reject gönderir, yayına
çıkan metin her zaman sunucunun kendi üretip doğruladığı taslaktır.
"""

from __future__ import annotations

import hmac
import logging
import os

from flask import jsonify, request

from src.auth import versions_crud
from src.services import release_note_generator as generator
from src.services import release_notes as rn

logger = logging.getLogger(__name__)

_TOKEN_ENV = "RELEASE_INGEST_TOKEN"


def _auth_error() -> tuple[dict, int] | None:
    """Yetki sorunu varsa (gövde, status); yoksa None."""
    expected = (os.environ.get(_TOKEN_ENV) or "").strip()
    if not expected:
        logger.warning("%s is not set; release ingest is disabled", _TOKEN_ENV)
        return {"error": "release ingest is not configured"}, 503
    supplied = request.headers.get("X-Release-Token") or ""
    if not hmac.compare_digest(supplied, expected):
        return {"error": "forbidden"}, 403
    return None


def _resolve_release(version: str) -> int | None:
    row = versions_crud.get_release_by_version(str(version))
    return int(row["id"]) if row else None


def register_release_ingest_routes(flask_app) -> None:
    @flask_app.get("/internal/platform/releases/last-sha")
    def release_last_sha():
        err = _auth_error()
        if err:
            return jsonify(err[0]), err[1]
        return jsonify({"last_sha": versions_crud.last_ingested_sha()})

    @flask_app.post("/internal/platform/releases")
    def release_ingest():
        err = _auth_error()
        if err:
            return jsonify(err[0]), err[1]

        payload = request.get_json(silent=True) or {}
        commits = payload.get("commits")
        if not isinstance(commits, list) or not commits:
            return jsonify({"error": "commits required"}), 400

        changes = []
        for c in commits:
            if not isinstance(c, dict):
                continue
            sha = str(c.get("sha") or "")[:12]
            if not sha:
                continue
            change_type, summary, scope = rn.parse_commit_subject(str(c.get("subject") or ""))
            if not summary:
                continue
            changes.append(
                {"change_type": change_type, "summary": summary, "commit_sha": sha, "scope": scope}
            )
        if not changes:
            return jsonify({"error": "no usable commits"}), 400

        day = rn.trt_date()
        version = payload.get("version")
        if not version:
            version = rn.calver(day, versions_crud.month_release_count(day.year, day.month) + 1)

        release_id = versions_crud.open_release(str(version), day.isoformat())
        added = versions_crud.add_release_changes(release_id, changes)
        note = generator.generate_for_release(release_id)
        logger.info("release %s ingested: %s new changes", version, added)
        return (
            jsonify(
                {
                    "version": str(version),
                    "release_id": release_id,
                    "changes_added": added,
                    "note": note,
                }
            ),
            201,
        )

    @flask_app.get("/internal/platform/releases/versions")
    def release_versions():
        err = _auth_error()
        if err:
            return jsonify(err[0]), err[1]
        return jsonify(
            {
                "versions": [
                    str(r.get("version") or "")
                    for r in (versions_crud.list_platform_releases() or [])
                    if r.get("version")
                ]
            }
        )

    @flask_app.post("/internal/platform/releases/<version>/note/confirm")
    def release_note_confirm(version):
        err = _auth_error()
        if err:
            return jsonify(err[0]), err[1]
        release_id = _resolve_release(version)
        if release_id is None:
            return jsonify({"error": "unknown release"}), 404
        return jsonify({"confirmed": bool(versions_crud.confirm_draft_note(release_id))})

    @flask_app.post("/internal/platform/releases/<version>/note/reject")
    def release_note_reject(version):
        err = _auth_error()
        if err:
            return jsonify(err[0]), err[1]
        release_id = _resolve_release(version)
        if release_id is None:
            return jsonify({"error": "unknown release"}), 404
        versions_crud.reject_draft_note(release_id)
        return jsonify({"rejected": True})

    @flask_app.post("/internal/platform/releases/<version>/note/regenerate")
    def release_note_regenerate(version):
        err = _auth_error()
        if err:
            return jsonify(err[0]), err[1]
        release_id = _resolve_release(version)
        if release_id is None:
            return jsonify({"error": "unknown release"}), 404
        return jsonify({"note": generator.generate_for_release(release_id)})
```

- [ ] **Step 4: Uygulamaya bağla**

`src/app.py` — `register_middleware(server)` satırının hemen ardına (`register_faro_routes` ile aynı kalıp):

```python
from src.routes.release_ingest import register_release_ingest_routes

register_release_ingest_routes(server)
```

- [ ] **Step 5: Testlerin geçtiğini gör**

Run: `$PY -m pytest tests/test_release_ingest_endpoint.py -v`
Expected: 15 passed.

- [ ] **Step 6: Commit**

```bash
git add src/routes/ src/app.py tests/test_release_ingest_endpoint.py
git commit -m "feat(task-64): token-gated release ingest and note confirmation endpoints"
```

---

### Task 8: `scripts/new_release.py`

**Files:**
- Create: `scripts/new_release.py`
- Test: `tests/test_new_release_script.py`

**Interfaces:**
- Consumes: Task 7'nin endpoint'leri.
- Produces:
  - `read_commits(last_sha: str | None) -> list[dict]` — `{"sha", "date", "subject"}` sözlükleri
  - `render_note(note: dict) -> str` — terminalde gösterilecek metin
  - `main(argv: list[str] | None = None) -> int`
  - Bayraklar: `--yes`, `--dry-run`, `--base-url` (varsayılan `http://localhost:8050`), `--version`.

**Onay döngüsü:** not gösterilir, `[e = evet / h = hayır / y = yeniden üret]` sorulur. `y` en fazla 3 kez. TTY yoksa (CI, pipe) script taslağı **onaylamadan** çıkar — sessizce onaylamak, insan onayı kuralını delerdi.

- [ ] **Step 1: Başarısız testi yaz**

`tests/test_new_release_script.py`:

```python
"""new_release.py — git ve HTTP mock'lanır."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "new_release.py"
_spec = importlib.util.spec_from_file_location("new_release", _PATH)
nr = importlib.util.module_from_spec(_spec)
sys.modules["new_release"] = nr
_spec.loader.exec_module(nr)


_LOG = "aaaaaaaaaaaa\x1f2026-08-03\x1ffeat(panel): yeni rozet\nbbbbbbbbbbbb\x1f2026-08-03\x1ffix: hiza"


def test_read_commits_parses_unit_separated_log():
    with patch.object(nr, "_git_log", lambda rng: _LOG):
        commits = nr.read_commits("cccccccccccc")
    assert commits[0] == {
        "sha": "aaaaaaaaaaaa",
        "date": "2026-08-03",
        "subject": "feat(panel): yeni rozet",
    }
    assert len(commits) == 2


def test_read_commits_range_starts_from_last_sha():
    seen = {}
    with patch.object(nr, "_git_log", lambda rng: seen.setdefault("rng", rng) or ""):
        nr.read_commits("cccccccccccc")
    assert seen["rng"] == "cccccccccccc..HEAD"


def test_read_commits_without_last_sha_reads_whole_history():
    seen = {}
    with patch.object(nr, "_git_log", lambda rng: seen.setdefault("rng", rng) or ""):
        nr.read_commits(None)
    assert seen["rng"] == "HEAD"


def test_read_commits_skips_malformed_lines():
    with patch.object(nr, "_git_log", lambda rng: "bozuk satır\n" + _LOG):
        assert len(nr.read_commits(None)) == 2


def test_render_note_lists_buckets_in_turkish():
    text = nr.render_note(
        {
            "status": "draft",
            "headline": "Panel yenilendi",
            "body": {
                "added": [{"text": "Yeni rozet", "shas": ["aaaaaaaaaaaa"]}],
                "fixed": [{"text": "Hiza düzeltildi", "shas": ["bbbbbbbbbbbb"]}],
                "improved": [],
            },
        }
    )
    assert "Panel yenilendi" in text
    assert "Yenilikler" in text
    assert "Düzeltmeler" in text
    assert "Yeni rozet" in text
    assert "İyileştirmeler" not in text     # boş kova hiç yazılmaz


def test_render_note_marks_the_automatic_fallback():
    text = nr.render_note({"status": "auto", "headline": None, "body": {"added": [], "fixed": [], "improved": []}})
    assert "otomatik özet" in text.lower()


def test_dry_run_posts_nothing(capsys):
    with patch.object(nr, "_get_last_sha", lambda base, token: None), \
         patch.object(nr, "_git_log", lambda rng: _LOG), \
         patch.object(nr, "_post", lambda *a, **k: pytest_fail_marker()):
        rc = nr.main(["--dry-run", "--base-url", "http://x", "--token", "t"])
    assert rc == 0
    assert "yeni rozet" in capsys.readouterr().out


def pytest_fail_marker():
    raise AssertionError("--dry-run modunda ağa çıkılmamalı")


def test_yes_flag_confirms_without_prompting():
    calls = []

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        if path == "/internal/platform/releases":
            return {"version": "2026.08.1", "note": {"status": "draft", "headline": "H", "body": {}}}
        return {"confirmed": True}

    with patch.object(nr, "_get_last_sha", lambda base, token: None), \
         patch.object(nr, "_git_log", lambda rng: _LOG), \
         patch.object(nr, "_post", fake_post):
        rc = nr.main(["--yes", "--base-url", "http://x", "--token", "t"])

    assert rc == 0
    assert "/internal/platform/releases/2026.08.1/note/confirm" in calls


def test_no_tty_leaves_the_draft_unconfirmed():
    calls = []

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        return {"version": "2026.08.1", "note": {"status": "draft", "headline": "H", "body": {}}}

    with patch.object(nr, "_get_last_sha", lambda base, token: None), \
         patch.object(nr, "_git_log", lambda rng: _LOG), \
         patch.object(nr, "_post", fake_post), \
         patch.object(nr.sys.stdin, "isatty", lambda: False):
        rc = nr.main(["--base-url", "http://x", "--token", "t"])

    assert rc == 0
    assert not any("confirm" in c for c in calls)


def test_regenerate_answer_calls_regenerate_then_confirms():
    calls = []
    answers = iter(["y", "e"])

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        if path.endswith("/regenerate"):
            return {"note": {"status": "draft", "headline": "H2", "body": {}}}
        if path == "/internal/platform/releases":
            return {"version": "2026.08.1", "note": {"status": "draft", "headline": "H", "body": {}}}
        return {"confirmed": True}

    with patch.object(nr, "_get_last_sha", lambda base, token: None), \
         patch.object(nr, "_git_log", lambda rng: _LOG), \
         patch.object(nr, "_post", fake_post), \
         patch.object(nr.sys.stdin, "isatty", lambda: True), \
         patch.object(nr, "_ask", lambda prompt: next(answers)):
        rc = nr.main(["--base-url", "http://x", "--token", "t"])

    assert rc == 0
    assert calls.count("/internal/platform/releases/2026.08.1/note/regenerate") == 1
    assert calls[-1].endswith("/confirm")


def test_no_answer_rejects_the_draft():
    calls = []

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        if path == "/internal/platform/releases":
            return {"version": "2026.08.1", "note": {"status": "draft", "headline": "H", "body": {}}}
        return {"rejected": True}

    with patch.object(nr, "_get_last_sha", lambda base, token: None), \
         patch.object(nr, "_git_log", lambda rng: _LOG), \
         patch.object(nr, "_post", fake_post), \
         patch.object(nr.sys.stdin, "isatty", lambda: True), \
         patch.object(nr, "_ask", lambda prompt: "h"):
        nr.main(["--base-url", "http://x", "--token", "t"])

    assert calls[-1].endswith("/reject")


def test_regenerate_is_capped_at_three_attempts():
    calls = []

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        if path == "/internal/platform/releases":
            return {"version": "2026.08.1", "note": {"status": "draft", "headline": "H", "body": {}}}
        return {"note": {"status": "draft", "headline": "H", "body": {}}, "rejected": True}

    with patch.object(nr, "_get_last_sha", lambda base, token: None), \
         patch.object(nr, "_git_log", lambda rng: _LOG), \
         patch.object(nr, "_post", fake_post), \
         patch.object(nr.sys.stdin, "isatty", lambda: True), \
         patch.object(nr, "_ask", lambda prompt: "y"):
        nr.main(["--base-url", "http://x", "--token", "t"])

    assert calls.count("/internal/platform/releases/2026.08.1/note/regenerate") == 3


def test_no_new_commits_exits_cleanly(capsys):
    with patch.object(nr, "_get_last_sha", lambda base, token: "aaaaaaaaaaaa"), \
         patch.object(nr, "_git_log", lambda rng: ""):
        rc = nr.main(["--base-url", "http://x", "--token", "t"])
    assert rc == 0
    assert "yeni commit yok" in capsys.readouterr().out.lower()
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `$PY -m pytest tests/test_new_release_script.py -v`
Expected: collection error — `FileNotFoundError: scripts/new_release.py`.

- [ ] **Step 3: Script'i yaz**

`scripts/new_release.py`:

```python
#!/usr/bin/env python3
"""Yeni bir release açar ve notunu onaya sunar.

Kullanım:
    python scripts/new_release.py                 # etkileşimli
    python scripts/new_release.py --yes           # soru sormadan onayla
    python scripts/new_release.py --dry-run       # ağa çıkmadan commit'leri göster

Token `RELEASE_INGEST_TOKEN` ortam değişkeninden okunur; `--token` ile geçilebilir.
TTY yoksa taslak ONAYLANMADAN bırakılır — sessiz onay, insan onayı kuralını delerdi.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

import requests

_SEP = "\x1f"
_MAX_REGENERATE = 3
_BUCKET_LABELS = (("added", "Yenilikler"), ("fixed", "Düzeltmeler"), ("improved", "İyileştirmeler"))


def _git_log(rev_range: str) -> str:
    out = subprocess.run(
        ["git", "log", rev_range, "--reverse", "--no-merges", "--date=short",
         f"--pretty=format:%h{_SEP}%ad{_SEP}%s"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout or ""


def read_commits(last_sha: str | None) -> list[dict]:
    rev_range = f"{last_sha}..HEAD" if last_sha else "HEAD"
    commits = []
    for line in _git_log(rev_range).splitlines():
        parts = line.split(_SEP)
        if len(parts) != 3:
            continue
        sha, day, subject = (p.strip() for p in parts)
        if not sha or not subject:
            continue
        commits.append({"sha": sha[:12], "date": day, "subject": subject})
    return commits


def _get_last_sha(base_url: str, token: str) -> str | None:
    resp = requests.get(
        f"{base_url}/internal/platform/releases/last-sha",
        headers={"X-Release-Token": token},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("last_sha")


def _post(base_url: str, path: str, token: str, payload: dict | None = None) -> dict:
    resp = requests.post(
        f"{base_url}{path}",
        json=payload,
        headers={"X-Release-Token": token},
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()


def render_note(note: dict) -> str:
    lines: list[str] = []
    headline = note.get("headline")
    if headline:
        lines.append(str(headline))
        lines.append("")
    body = note.get("body") or {}
    for key, label in _BUCKET_LABELS:
        items = body.get(key) or []
        if not items:
            continue
        lines.append(label)
        for item in items:
            shas = ", ".join(item.get("shas") or [])
            lines.append(f"  • {item.get('text', '')}  [{shas}]")
        lines.append("")
    if note.get("status") == "auto":
        lines.append("(model not üretemedi — bu bir otomatik özet)")
    if not lines:
        lines.append("(bu release için gösterilecek kullanıcıya dönük değişiklik yok)")
    return "\n".join(lines).rstrip()


def _ask(prompt: str) -> str:
    return input(prompt).strip().lower()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Yeni release aç ve notunu onayla.")
    ap.add_argument("--base-url", default=os.environ.get("GUI_BASE_URL", "http://localhost:8050"))
    ap.add_argument("--token", default=os.environ.get("RELEASE_INGEST_TOKEN", ""))
    ap.add_argument("--version", default=None, help="CalVer'i elle ver (varsayılan: otomatik)")
    ap.add_argument("--yes", action="store_true", help="soru sormadan onayla")
    ap.add_argument("--dry-run", action="store_true", help="ağa çıkma, commit'leri göster")
    args = ap.parse_args(argv)

    base = args.base_url.rstrip("/")

    if args.dry_run:
        commits = read_commits(None)
        print(f"{len(commits)} commit bulundu:")
        for c in commits:
            print(f"  {c['sha']}  {c['date']}  {c['subject']}")
        return 0

    if not args.token:
        print("RELEASE_INGEST_TOKEN tanımlı değil.", file=sys.stderr)
        return 2

    last_sha = _get_last_sha(base, args.token)
    commits = read_commits(last_sha)
    if not commits:
        print("Yeni commit yok; yapacak bir şey yok.")
        return 0

    payload: dict = {"commits": commits}
    if args.version:
        payload["version"] = args.version
    result = _post(base, "/internal/platform/releases", args.token, payload)
    version = result.get("version")
    note = result.get("note") or {}

    print(f"\nRelease {version} açıldı — {len(commits)} commit.\n")
    print(render_note(note))
    print()

    confirm_path = f"/internal/platform/releases/{version}/note/confirm"
    reject_path = f"/internal/platform/releases/{version}/note/reject"
    regenerate_path = f"/internal/platform/releases/{version}/note/regenerate"

    if args.yes:
        _post(base, confirm_path, args.token)
        print("Not yayına alındı.")
        return 0

    if not sys.stdin.isatty():
        print("TTY yok; taslak onaylanmadan bırakıldı. Panelde otomatik özet görünüyor.")
        return 0

    regenerated = 0
    while True:
        answer = _ask("Bu notu yayınlayalım mı? [e = evet / h = hayır / y = yeniden üret]: ")
        if answer == "e":
            _post(base, confirm_path, args.token)
            print("Not yayına alındı.")
            return 0
        if answer == "h":
            _post(base, reject_path, args.token)
            print("Taslak silindi; panelde otomatik özet kalıyor.")
            return 0
        if answer == "y":
            if regenerated >= _MAX_REGENERATE:
                _post(base, reject_path, args.token)
                print("Yeniden üretme hakkı bitti; taslak silindi.")
                return 0
            regenerated += 1
            note = (_post(base, regenerate_path, args.token) or {}).get("note") or {}
            print()
            print(render_note(note))
            print()
            continue
        print("e, h veya y yazın.")


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Run: `$PY -m pytest tests/test_new_release_script.py -v`
Expected: 14 passed.

- [ ] **Step 5: `--dry-run` ile gerçek git geçmişinde dene**

Run: `$PY scripts/new_release.py --dry-run`
Expected: son commit'ler `sha  tarih  subject` biçiminde listelenir, ağa çıkılmaz.

- [ ] **Step 6: Commit**

```bash
git add scripts/new_release.py tests/test_new_release_script.py
git commit -m "feat(task-64): new_release CLI with human confirmation loop"
```

---

### Task 9: Panel yenilemesi

**Files:**
- Create: `src/pages/settings/platform/versions_view.py`
- Create: `src/pages/settings/platform/versions_callbacks.py`
- Modify: `src/pages/settings/platform/versions.py` (tamamen yeniden yazılır)
- Modify: `src/app.py` (callback modülü importu)
- Test: `tests/test_platform_versions_page.py` (mevcut kırık test onarılır + genişletilir)

**Interfaces:**
- Consumes: Task 2'nin `list_platform_releases()` çıktısındaki `note` anahtarı; `admin_client.list_platform_releases()`, `admin_client.get_current_versions()`.
- Produces (`versions_view`):
  - `BUCKETS: tuple[tuple[str, str, str, str], ...]` — `(key, Türkçe etiket, renk, ikon)`
  - `group_changes(changes: list[dict]) -> tuple[dict[str, list[dict]], int]`
  - `note_body(rel: dict) -> dict`
  - `note_source(rel: dict) -> str`
  - `bucket_counts(body: dict) -> dict[str, int]`
  - `auto_summary_line(body: dict) -> str`
  - `resolve_live_version(releases: list[dict], current: list[dict]) -> str | None`
  - `is_live(rel: dict, live_version: str | None) -> bool`
  - `matches_search(rel: dict, term: str) -> bool`
  - `month_label(iso_date: str) -> str`
  - `stat_strip(releases: list[dict], live_version: str | None) -> dmc.Paper`
  - `headline_block(rel: dict) -> dmc.Stack`
  - `technical_section(rel: dict) -> dmc.Accordion`
  - `hero_card(rel: dict) -> dmc.Paper`
  - `history_row(rel: dict) -> dmc.AccordionItem`
  - `release_list(releases: list[dict], live_version: str | None) -> html.Div`
- Task 10 `release_list` ve `hero_card`'a "Yeniden üret" düğmesini ekler.

**Panel kuralları:**
- Panel **daima** `body`'yi gösterir, `draft_body`'yi asla. Taslak yalnızca terminalde görünür.
- `source='model'` ise maddeler kartın gövdesinde; `source='auto'` ise kartta yalnızca kodda hesaplanan Türkçe özet satırı + "otomatik özet" rozeti bulunur, commit türevi maddeler katlanmış "Teknik detay" bölümüne iner.
- Bütün rozet sayıları kodda hesaplanır.
- Sabit hex renk kalmaz; hepsi Mantine tema değişkenidir.

**Baseline onarımı:** `test_visible_change_filter_hides_chore` şu an var olmayan `_split_changes`'i çağırıyor. Bu adımda `versions_view.group_changes` üzerinden yeniden yazılıyor.

- [ ] **Step 1: Başarısız testi yaz**

`tests/test_platform_versions_page.py` — dosyayı tamamen bu içerikle değiştir:

```python
"""Platform Versions paneli — saf render kuralları."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

from src.pages.settings.platform import versions as page
from src.pages.settings.platform import versions_view as vv

SHA_A = "aaaaaaaaaaaa"
SHA_B = "bbbbbbbbbbbb"
MARKER = "ZZTOPMARKER"


def _flatten(node) -> list[str]:
    """Bileşen ağacındaki bütün metinleri toplar."""
    out: list[str] = []
    if node is None:
        return out
    if isinstance(node, (str, int, float)):
        return [str(node)]
    if isinstance(node, (list, tuple)):
        for n in node:
            out.extend(_flatten(n))
        return out
    out.extend(_flatten(getattr(node, "children", None)))
    for attr in ("label", "showLabel", "hideLabel", "placeholder"):
        v = getattr(node, attr, None)
        if isinstance(v, str):
            out.append(v)
    return out


def _release(source="model", *, version="2026.08.1", released_at="2026-08-03"):
    return {
        "id": 7,
        "version": version,
        "released_at": released_at,
        "note": {
            "headline": "Panel yenilendi",
            "source": source,
            "body": {
                "added": [{"text": "Yeni rozet eklendi", "shas": [SHA_A]}],
                "fixed": [{"text": "Hiza düzeltildi", "shas": [SHA_B]}],
                "improved": [],
            },
        },
        "changes": [
            {"change_type": "feat", "summary": f"yeni rozet {MARKER}", "commit_sha": SHA_A},
            {"change_type": "fix", "summary": "hiza", "commit_sha": SHA_B},
            {"change_type": "chore", "summary": "bağımlılık", "commit_sha": "cccccccccccc"},
        ],
        "services": [],
    }


# --- group_changes (eski _split_changes testinin yerine) ------------------

def test_visible_change_filter_hides_chore():
    groups, internal = vv.group_changes(_release()["changes"])
    assert [c["summary"] for c in groups["feat"]] == [f"yeni rozet {MARKER}"]
    assert [c["summary"] for c in groups["fix"]] == ["hiza"]
    assert internal == 1


def test_group_changes_tolerates_missing_type():
    groups, internal = vv.group_changes([{"summary": "x"}])
    assert internal == 1
    assert all(not v for v in groups.values())


# --- not okuma ------------------------------------------------------------

def test_panel_never_reads_draft_body():
    rel = _release()
    rel["note"]["draft_body"] = {"added": [{"text": "TASLAK", "shas": [SHA_A]}]}
    text = " ".join(_flatten(vv.hero_card(rel)))
    assert "TASLAK" not in text


def test_model_note_bullets_appear_in_the_card_body():
    text = " ".join(_flatten(vv.headline_block(_release("model"))))
    assert "Yeni rozet eklendi" in text
    assert "Hiza düzeltildi" in text


def test_auto_note_shows_a_code_written_summary_instead_of_bullets():
    block = " ".join(_flatten(vv.headline_block(_release("auto"))))
    assert "otomatik özet" in block.lower()
    assert "Yeni rozet eklendi" not in block


def test_raw_commit_subject_never_reaches_the_card_body():
    for source in ("model", "auto"):
        block = " ".join(_flatten(vv.headline_block(_release(source))))
        assert MARKER not in block, f"{source} kartının gövdesinde ham commit subject'i var"


def test_raw_commit_subject_lives_in_the_technical_section():
    assert MARKER in " ".join(_flatten(vv.technical_section(_release("auto"))))


def test_missing_note_falls_back_to_a_summary_line():
    rel = _release()
    rel["note"] = None
    text = " ".join(_flatten(vv.headline_block(rel)))
    assert MARKER not in text
    assert text.strip() != ""


# --- sayılar kodda hesaplanır --------------------------------------------

def test_bucket_counts_are_computed_from_the_body():
    counts = vv.bucket_counts(_release()["note"]["body"])
    assert counts == {"added": 1, "fixed": 1, "improved": 0}


def test_auto_summary_line_reports_counts_in_turkish():
    line = vv.auto_summary_line(_release()["note"]["body"])
    assert "1 yenilik" in line
    assert "1 düzeltme" in line
    assert "iyileştirme" not in line


def test_auto_summary_line_handles_empty_note():
    assert vv.auto_summary_line({"added": [], "fixed": [], "improved": []}).strip() != ""


# --- "Yayında" rozeti -----------------------------------------------------

def test_live_version_comes_from_the_newest_deployment():
    live = vv.resolve_live_version(
        [{"version": "2026.08.2"}, {"version": "2026.08.1"}],
        [
            {"version": "2026.08.1", "started_at": "2026-08-01T10:00:00"},
            {"version": "2026.08.2", "started_at": "2026-08-03T10:00:00"},
        ],
    )
    assert live == "2026.08.2"


def test_live_version_falls_back_to_the_newest_release():
    assert vv.resolve_live_version([{"version": "2026.08.2"}], []) == "2026.08.2"


def test_is_live_ignores_surrounding_whitespace():
    assert vv.is_live({"version": " 2026.08.2 "}, "2026.08.2") is True


def test_is_live_is_false_when_no_live_version_known():
    assert vv.is_live({"version": "2026.08.2"}, None) is False


# --- arama ve ay ayracı ---------------------------------------------------

def test_search_matches_version_headline_and_bullets():
    rel = _release()
    assert vv.matches_search(rel, "2026.08") is True
    assert vv.matches_search(rel, "panel") is True
    assert vv.matches_search(rel, "hiza") is True
    assert vv.matches_search(rel, "kesinlikle-yok") is False


def test_search_is_case_insensitive_and_empty_term_matches_all():
    assert vv.matches_search(_release(), "PANEL") is True
    assert vv.matches_search(_release(), "") is True


def test_month_label_is_turkish():
    assert vv.month_label("2026-08-03") == "Ağustos 2026"


def test_month_label_tolerates_garbage():
    assert vv.month_label("") == "Tarihsiz"


# --- tema renkleri --------------------------------------------------------

def test_no_hardcoded_hex_colours_remain():
    for module in (vv, page):
        src = Path(module.__file__).read_text(encoding="utf-8")
        assert not re.search(r"#[0-9A-Fa-f]{6}\b", src), f"{module.__name__} içinde sabit hex renk var"


# --- sayfa iskeleti -------------------------------------------------------

def test_build_layout_filters_by_search_query():
    releases = [_release(version="2026.08.2"), _release(version="2026.07.1", released_at="2026-07-01")]
    with patch.object(page.admin_client, "list_platform_releases", lambda: releases), \
         patch.object(page.admin_client, "get_current_versions", lambda: []):
        text = " ".join(_flatten(page.build_layout("?q=2026.07")))
    assert "2026.07.1" in text
    assert "2026.08.2" not in text


def test_build_layout_shows_empty_state_without_releases():
    with patch.object(page.admin_client, "list_platform_releases", lambda: []), \
         patch.object(page.admin_client, "get_current_versions", lambda: []):
        text = " ".join(_flatten(page.build_layout()))
    assert "Henüz sürüm geçmişi yok" in text
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `$PY -m pytest tests/test_platform_versions_page.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'src.pages.settings.platform.versions_view'`.

- [ ] **Step 3: Görünüm katmanını yaz**

`src/pages/settings/platform/versions_view.py`:

```python
"""Platform Versions panelinin saf render yardımcıları.

Burada veri çekilmez; her fonksiyon aldığı sözlükten bileşen üretir. Panelin iki katı
kuralı bu modülde yaşar:
  1. Yalnızca `body` gösterilir; `draft_body` panele hiç girmez.
  2. Ham commit subject'i yalnızca katlanmış "Teknik detay" bölümünde durur.
"""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from src.utils.ui_tokens import ON_SURFACE, relative_time

# (anahtar, Türkçe etiket, renk, ikon)
BUCKETS = (
    ("added", "Yenilikler", "teal", "solar:star-bold-duotone"),
    ("fixed", "Düzeltmeler", "orange", "solar:bug-bold-duotone"),
    ("improved", "İyileştirmeler", "grape", "solar:bolt-bold-duotone"),
)

# Teknik detay bölümünde gösterilen commit tipleri.
_CHANGE_TYPES = (
    ("feat", "Features", "teal"),
    ("fix", "Fixes", "orange"),
    ("perf", "Performance", "grape"),
)

_TR_MONTHS = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)

_ACCENT = "var(--mantine-color-indigo-6)"
_ACCENT_SOFT = "var(--mantine-color-indigo-0)"
_LIVE = "var(--mantine-color-teal-6)"
_RAIL = "var(--mantine-color-gray-3)"
_ON_ACCENT = "var(--mantine-color-white)"


# --- veri yardımcıları ----------------------------------------------------

def group_changes(changes: list[dict]) -> tuple[dict[str, list[dict]], int]:
    groups: dict[str, list[dict]] = {t[0]: [] for t in _CHANGE_TYPES}
    internal = 0
    for c in changes or []:
        t = str(c.get("change_type") or "other")
        if t in groups:
            groups[t].append(c)
        else:
            internal += 1
    return groups, internal


def note_body(rel: dict) -> dict:
    note = rel.get("note") or {}
    body = note.get("body")
    return body if isinstance(body, dict) else {}


def note_source(rel: dict) -> str:
    note = rel.get("note") or {}
    return str(note.get("source") or "auto")


def note_headline(rel: dict) -> str | None:
    note = rel.get("note") or {}
    headline = note.get("headline")
    return str(headline) if headline else None


def bucket_counts(body: dict) -> dict[str, int]:
    return {key: len((body or {}).get(key) or []) for key, _l, _c, _i in BUCKETS}


def auto_summary_line(body: dict) -> str:
    """Kartta gösterilen, tamamen kodda hesaplanan Türkçe özet."""
    counts = bucket_counts(body)
    words = {"added": "yenilik", "fixed": "düzeltme", "improved": "iyileştirme"}
    parts = [f"{counts[k]} {words[k]}" for k in ("added", "fixed", "improved") if counts[k]]
    if not parts:
        return "Bu sürümde kullanıcıya dönük değişiklik yok."
    return "Bu sürümde " + " ve ".join(parts) + " var."


def resolve_live_version(releases: list[dict], current: list[dict]) -> str | None:
    version = None
    if current:
        newest = max(current, key=lambda d: str(d.get("started_at") or ""))
        version = str(newest.get("version") or "").strip() or None
    if not version and releases:
        version = str(releases[0].get("version") or "").strip() or None
    return version


def is_live(rel: dict, live_version: str | None) -> bool:
    if not live_version:
        return False
    return str(rel.get("version") or "").strip() == str(live_version).strip()


def matches_search(rel: dict, term: str) -> bool:
    needle = (term or "").strip().lower()
    if not needle:
        return True
    haystack = [str(rel.get("version") or ""), note_headline(rel) or ""]
    body = note_body(rel)
    for key, _l, _c, _i in BUCKETS:
        for item in body.get(key) or []:
            haystack.append(str((item or {}).get("text") or ""))
    for c in rel.get("changes") or []:
        haystack.append(str(c.get("summary") or ""))
    return needle in " ".join(haystack).lower()


def month_label(iso_date: str) -> str:
    text = str(iso_date or "")[:10]
    try:
        year, month = int(text[:4]), int(text[5:7])
        return f"{_TR_MONTHS[month - 1]} {year}"
    except (ValueError, IndexError):
        return "Tarihsiz"


# --- bileşenler -----------------------------------------------------------

def _bullet_rows(items: list[dict], color: str) -> list:
    return [
        dmc.Group(
            gap=8,
            align="flex-start",
            wrap="nowrap",
            children=[
                html.Div(
                    style={
                        "width": 5, "height": 5, "borderRadius": "50%",
                        "background": f"var(--mantine-color-{color}-5)",
                        "marginTop": 8, "flexShrink": 0,
                    }
                ),
                dmc.Text(str((item or {}).get("text") or ""), size="sm", c=ON_SURFACE),
            ],
        )
        for item in items
    ]


def _count_badges(body: dict) -> dmc.Group | None:
    counts = bucket_counts(body)
    chips = [
        dmc.Badge(f"{counts[key]} {label}", color=color, variant="light", size="sm", radius="sm")
        for key, label, color, _icon in BUCKETS
        if counts[key]
    ]
    return dmc.Group(gap="xs", children=chips) if chips else None


def headline_block(rel: dict) -> dmc.Stack:
    """Kartın gövdesi. Ham commit subject'i buraya asla girmez."""
    body = note_body(rel)
    source = note_source(rel)
    children: list = []

    headline = note_headline(rel)
    if headline:
        children.append(dmc.Text(headline, fw=600, size="md", c=ON_SURFACE))

    badges = _count_badges(body)
    if badges:
        children.append(badges)

    if source == "model":
        for key, label, color, icon in BUCKETS:
            items = body.get(key) or []
            if not items:
                continue
            children.append(
                dmc.Stack(
                    gap=5,
                    children=[
                        dmc.Group(
                            gap=6,
                            align="center",
                            children=[
                                DashIconify(icon=icon, width=14, color=f"var(--mantine-color-{color}-6)"),
                                dmc.Text(
                                    label, size="xs", fw=700, tt="uppercase",
                                    c=f"var(--mantine-color-{color}-7)",
                                ),
                            ],
                        ),
                        *_bullet_rows(items, color),
                    ],
                )
            )
    else:
        children.append(dmc.Text(auto_summary_line(body), size="sm", c=ON_SURFACE))
        children.append(
            dmc.Badge("otomatik özet", variant="light", color="gray", size="xs", radius="sm")
        )

    return dmc.Stack(gap=10, children=children)


def technical_section(rel: dict) -> dmc.Accordion:
    """Ham commit'ler ve service deployment kayıtları — varsayılan olarak kapalı."""
    groups, internal = group_changes(rel.get("changes") or [])
    rows: list = []
    for key, label, color in _CHANGE_TYPES:
        items = groups[key]
        if not items:
            continue
        rows.append(
            dmc.Text(label, size="xs", fw=700, tt="uppercase", c=f"var(--mantine-color-{color}-7)")
        )
        for c in items:
            rows.append(
                dmc.Group(
                    gap="sm",
                    wrap="nowrap",
                    children=[
                        dmc.Text(
                            str(c.get("commit_sha") or "—"), size="xs", c="dimmed", ff="monospace"
                        ),
                        dmc.Text(str(c.get("summary") or ""), size="xs", c="dimmed"),
                    ],
                )
            )
    if internal:
        rows.append(dmc.Text(f"+{internal} internal change", size="xs", c="dimmed"))

    for s in rel.get("services") or []:
        rows.append(
            dmc.Group(
                gap="sm",
                children=[
                    dmc.Badge(str(s.get("service") or "—"), variant="light", color="indigo", size="sm"),
                    dmc.Text(f"sha {s.get('git_sha') or '—'}", size="xs", c="dimmed", ff="monospace"),
                    dmc.Text(str(s.get("started_at") or "")[:19], size="xs", c="dimmed"),
                ],
            )
        )
    if not rows:
        rows.append(dmc.Text("Kayıtlı teknik detay yok.", size="xs", c="dimmed"))

    return dmc.Accordion(
        variant="filled",
        chevronPosition="left",
        styles={"control": {"paddingLeft": 0, "paddingRight": 0}},
        children=[
            dmc.AccordionItem(
                value="tech",
                children=[
                    dmc.AccordionControl(dmc.Text("Teknik detay", size="xs", fw=600, c="dimmed")),
                    dmc.AccordionPanel(dmc.Stack(gap=6, children=rows)),
                ],
            )
        ],
    )


def _version_line(rel: dict, *, live: bool, size: str) -> dmc.Group:
    left = [dmc.Text(str(rel.get("version") or ""), fw=800, size=size, c=ON_SURFACE)]
    if live:
        left.append(dmc.Badge("Yayında", color="teal", variant="filled", size="sm", radius="sm"))
    return dmc.Group(
        justify="space-between",
        align="center",
        wrap="nowrap",
        children=[
            dmc.Group(gap="xs", align="center", children=left),
            dmc.Text(
                f"{str(rel.get('released_at') or '')[:10]} · {relative_time(rel.get('released_at'))}",
                size="xs",
                c="dimmed",
            ),
        ],
    )


def hero_card(rel: dict) -> dmc.Paper:
    """Yayındaki sürüm — büyük, açık, öne çıkan kart."""
    return dmc.Paper(
        withBorder=True,
        radius="md",
        p="lg",
        style={"borderColor": _ACCENT, "background": _ACCENT_SOFT},
        children=dmc.Stack(
            gap=12,
            children=[
                _version_line(rel, live=True, size="xl"),
                headline_block(rel),
                technical_section(rel),
            ],
        ),
    )


def history_row(rel: dict) -> dmc.AccordionItem:
    """Geçmiş sürüm — kapalı satır, açılınca notu gösterir."""
    return dmc.AccordionItem(
        value=str(rel.get("version") or ""),
        children=[
            dmc.AccordionControl(_version_line(rel, live=False, size="md")),
            dmc.AccordionPanel(
                dmc.Stack(gap=12, children=[headline_block(rel), technical_section(rel)])
            ),
        ],
    )


def _stat(value: str, label: str) -> html.Div:
    return html.Div(
        children=[
            dmc.Text(value, fw=800, size="xl", c=_ACCENT, style={"lineHeight": 1.1}),
            dmc.Text(label, size="xs", c="dimmed", tt="uppercase", fw=600),
        ]
    )


def stat_strip(releases: list[dict], live_version: str | None) -> dmc.Paper:
    total_changes = sum(len(r.get("changes") or []) for r in releases)
    with_notes = sum(1 for r in releases if note_source(r) == "model")
    return dmc.Paper(
        withBorder=True,
        radius="md",
        p="md",
        mb="lg",
        children=dmc.Group(
            gap="xl",
            children=[
                _stat(str(len(releases)), "sürüm"),
                _stat(str(total_changes), "değişiklik"),
                _stat(str(with_notes), "yazılmış not"),
                _stat(live_version or "—", "yayındaki sürüm"),
            ],
        ),
    )


def release_list(releases: list[dict], live_version: str | None) -> html.Div:
    """Hero kartı + ay ayraçlarıyla ayrılmış geçmiş satırları."""
    if not releases:
        return html.Div(
            dmc.Text("Aramanla eşleşen sürüm yok.", size="sm", c="dimmed")
        )

    children: list = []
    hero_index = None
    for i, rel in enumerate(releases):
        if is_live(rel, live_version):
            hero_index = i
            break
    if hero_index is None:
        hero_index = 0
    children.append(hero_card(releases[hero_index]))

    rest = [r for i, r in enumerate(releases) if i != hero_index]
    current_month = None
    items: list = []
    for rel in rest:
        label = month_label(rel.get("released_at"))
        if label != current_month:
            if items:
                children.append(dmc.Accordion(variant="separated", chevronPosition="left", children=items))
                items = []
            current_month = label
            children.append(
                dmc.Divider(
                    label=label,
                    labelPosition="left",
                    mt="lg",
                    mb="xs",
                    color=_RAIL,
                )
            )
        items.append(history_row(rel))
    if items:
        children.append(dmc.Accordion(variant="separated", chevronPosition="left", children=items))

    return html.Div(children)
```

- [ ] **Step 4: Sayfayı yeniden yaz**

`src/pages/settings/platform/versions.py` — dosyayı tamamen bu içerikle değiştir:

```python
"""Platform sürüm geçmişi — her release'in okunabilir notuyla birlikte."""

from __future__ import annotations

from urllib.parse import parse_qs

import dash_mantine_components as dmc
from dash import html

from src.pages.settings.platform import versions_view as vv
from src.services import admin_client
from src.utils.ui_tokens import ON_SURFACE, section_header, settings_page_shell

SEARCH_ID = "platform-versions-search"
LIST_ID = "platform-versions-list"


def _search_term(search: str | None) -> str:
    if not search:
        return ""
    values = parse_qs(str(search).lstrip("?")).get("q") or [""]
    return values[0].strip()


def load_releases() -> tuple[list[dict], str | None]:
    releases = admin_client.list_platform_releases() or []
    current = admin_client.get_current_versions() or []
    return releases, vv.resolve_live_version(releases, current)


def render_list(releases: list[dict], live_version: str | None, term: str) -> html.Div:
    visible = [r for r in releases if vv.matches_search(r, term)]
    return vv.release_list(visible, live_version)


def _empty_state() -> dmc.Paper:
    return dmc.Paper(
        withBorder=True,
        radius="md",
        p="xl",
        children=dmc.Stack(
            gap=4,
            children=[
                dmc.Text("Henüz sürüm geçmişi yok.", fw=600, c=ON_SURFACE),
                dmc.Text(
                    "Geçmişi git'ten kurmak için scripts/backfill_platform_versions.py çalıştır.",
                    c="dimmed",
                    size="sm",
                ),
            ],
        ),
    )


def build_layout(search: str | None = None) -> html.Div:
    releases, live_version = load_releases()
    term = _search_term(search)

    if not releases:
        body: list = [_empty_state()]
    else:
        body = [
            vv.stat_strip(releases, live_version),
            dmc.TextInput(
                id=SEARCH_ID,
                placeholder="Sürüm, başlık veya değişiklik ara",
                value=term,
                mb="md",
                size="sm",
                debounce=300,
            ),
            html.Div(render_list(releases, live_version, term), id=LIST_ID),
        ]

    return html.Div(
        settings_page_shell(
            [
                section_header(
                    "Platform sürümleri",
                    "İlk günden bugüne her release ve neyi değiştirdiği.",
                    icon="solar:box-bold-duotone",
                ),
                *body,
            ]
        )
    )
```

- [ ] **Step 5: Arama callback'ini yaz**

`src/pages/settings/platform/versions_callbacks.py`:

```python
"""Platform Versions paneli callback'leri."""

from __future__ import annotations

from dash import Input, Output, callback

from src.pages.settings.platform import versions as page


@callback(
    Output(page.LIST_ID, "children"),
    Input(page.SEARCH_ID, "value"),
    prevent_initial_call=True,
)
def filter_releases(term):
    releases, live_version = page.load_releases()
    return page.render_list(releases, live_version, str(term or ""))
```

`src/app.py` — diğer settings callback importlarının yanına:

```python
from src.pages.settings.platform import versions_callbacks  # noqa: F401
```

- [ ] **Step 6: Testlerin geçtiğini gör**

Run: `$PY -m pytest tests/test_platform_versions_page.py -v`
Expected: 22 passed (baseline'daki kırık test dahil).

- [ ] **Step 7: Bütün paketi çalıştır**

Run: `$PY -m pytest tests/ -q`
Expected: yeni kırık test yok.

- [ ] **Step 8: Commit**

```bash
git add src/pages/settings/platform/ src/app.py tests/test_platform_versions_page.py
git commit -m "feat(task-64): redesign platform versions panel around written release notes"
```

---

### Task 10: "Yeniden üret" düğmesi ve yetkisi

**Files:**
- Modify: `src/auth/permission_catalog.py:505` civarı
- Modify: `src/pages/settings/platform/versions_view.py`
- Modify: `src/pages/settings/platform/versions_callbacks.py`
- Test: `tests/test_platform_versions_regenerate.py`

**Interfaces:**
- Consumes: Task 6'nın `generate_for_release`, Task 9'un `hero_card`/`history_row`, mevcut `src.auth.permission_service.can_edit(user_id, code)`.
- Produces:
  - Yetki kodu `sec:settings_platform_versions:regenerate`
  - Bileşen id kalıbı `{"type": "pv-regen", "version": <version>}`
  - `versions_view.regenerate_button(version: str) -> dmc.Button`
  - Callback `regenerate_note(n_clicks, user_store)`

**Yetki kuralı:** düğme yalnızca yetkisi olana **gösterilmez**, callback içinde de **yeniden kontrol edilir**. Görünürlük tek başına yetki değildir.

- [ ] **Step 1: Başarısız testi yaz**

`tests/test_platform_versions_regenerate.py`:

```python
"""Yeniden üret düğmesi — yetki hem görünürlükte hem callback'te kontrol edilir."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from dash.exceptions import PreventUpdate

from src.auth import permission_catalog
from src.pages.settings.platform import versions_callbacks as cb
from src.pages.settings.platform import versions_view as vv

CODE = "sec:settings_platform_versions:regenerate"


def _codes(node, out=None):
    out = out if out is not None else []
    out.append(node.code)
    for child in node.children or []:
        _codes(child, out)
    return out


def test_permission_code_is_registered_under_the_page():
    codes = []
    for root in permission_catalog.build_default_permission_roots():
        _codes(root, codes)
    assert CODE in codes


def test_permission_code_is_a_child_of_the_versions_page():
    def find(node):
        if node.code == "page:settings_platform_versions":
            return node
        for child in node.children or []:
            hit = find(child)
            if hit:
                return hit
        return None

    page_node = None
    for root in permission_catalog.build_default_permission_roots():
        page_node = page_node or find(root)
    assert page_node is not None
    assert CODE in [c.code for c in page_node.children or []]


def test_button_id_carries_the_version():
    button = vv.regenerate_button("2026.08.1")
    assert button.id == {"type": "pv-regen", "version": "2026.08.1"}


def test_hero_card_shows_the_button_only_with_permission():
    rel = {"version": "2026.08.1", "released_at": "2026-08-03", "note": None, "changes": [], "services": []}
    with_btn = vv.hero_card(rel, can_regenerate=True)
    without = vv.hero_card(rel, can_regenerate=False)
    assert "Yeniden üret" in str(with_btn)
    assert "Yeniden üret" not in str(without)


def test_callback_refuses_without_permission():
    with patch.object(cb, "can_edit", lambda uid, code: False), \
         patch.object(cb.generator, "generate_for_release", lambda rid: pytest.fail("çağrılmamalı")):
        with pytest.raises(PreventUpdate):
            cb.regenerate_note([1], {"id": 5}, [{"type": "pv-regen", "version": "2026.08.1"}])


def test_callback_refuses_without_a_user():
    with patch.object(cb, "can_edit", lambda uid, code: True):
        with pytest.raises(PreventUpdate):
            cb.regenerate_note([1], None, [{"type": "pv-regen", "version": "2026.08.1"}])


def test_callback_regenerates_for_the_clicked_version():
    seen = {}

    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.ctx_helper, "triggered_version", lambda: "2026.08.1"), \
         patch.object(cb.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(cb.generator, "generate_for_release", lambda rid: seen.setdefault("rid", rid)), \
         patch.object(cb.page, "load_releases", lambda: ([], None)), \
         patch.object(cb.page, "render_list", lambda r, l, t: "yeni liste"):
        out = cb.regenerate_note([1], {"id": 5}, [{"type": "pv-regen", "version": "2026.08.1"}])

    assert seen["rid"] == 7
    assert out == "yeni liste"


def test_callback_prevents_update_for_unknown_version():
    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.ctx_helper, "triggered_version", lambda: "9999.99.9"), \
         patch.object(cb.versions_crud, "get_release_by_version", lambda v: None):
        with pytest.raises(PreventUpdate):
            cb.regenerate_note([1], {"id": 5}, [{"type": "pv-regen", "version": "9999.99.9"}])
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `$PY -m pytest tests/test_platform_versions_regenerate.py -v`
Expected: FAIL — yetki kodu yok, `regenerate_button` yok, `regenerate_note` yok.

- [ ] **Step 3: Yetki kodunu ekle**

`src/auth/permission_catalog.py` — `settings_grp`'nin son çocuğu olan Platform Versions düğümüne çocuk ver:

```python
        _n(
            "page:settings_platform_versions",
            "Platform Versions",
            "config",
            route_pattern="/administration/platform/versions",
            sort_order=80,
            children=[
                _n(
                    "sec:settings_platform_versions:regenerate",
                    "Release note yeniden üret",
                    "action",
                    sort_order=10,
                ),
            ],
        ),
```

- [ ] **Step 4: Düğmeyi görünüme ekle**

`src/pages/settings/platform/versions_view.py` — yeni fonksiyon:

```python
def regenerate_button(version: str) -> dmc.Button:
    return dmc.Button(
        "Yeniden üret",
        id={"type": "pv-regen", "version": str(version)},
        variant="subtle",
        size="xs",
        color="indigo",
        leftSection=DashIconify(icon="solar:refresh-bold-duotone", width=14),
    )
```

`hero_card` ve `history_row` imzalarına `can_regenerate: bool = False` ekle; `hero_card` içinde `_version_line(...)` çağrısının ardından, `can_regenerate` doğruysa düğmeyi `dmc.Group(justify="flex-end", children=[regenerate_button(rel.get("version"))])` olarak `children` listesine ekle. Aynısını `history_row`'un `AccordionPanel` yığınının sonuna uygula. `release_list(releases, live_version, can_regenerate: bool = False)` bu bayrağı ikisine de geçirir.

- [ ] **Step 5: Callback'i yaz**

`src/pages/settings/platform/versions_callbacks.py` — dosyayı bu içerikle değiştir:

```python
"""Platform Versions paneli callback'leri.

Yetki iki yerde kontrol edilir: düğmenin görünürlüğünde ve callback'in içinde.
Görünürlük tek başına yetki değildir — istemci tarafı her zaman taklit edilebilir.
"""

from __future__ import annotations

import json

from dash import ALL, Input, Output, State, callback, ctx
from dash.exceptions import PreventUpdate

from src.auth import versions_crud
from src.auth.permission_service import can_edit
from src.pages.settings.platform import versions as page
from src.services import release_note_generator as generator

REGENERATE_CODE = "sec:settings_platform_versions:regenerate"


class ctx_helper:
    """Tetikleyen bileşenin sürümünü verir; testte kolayca değiştirilebilsin diye ayrı."""

    @staticmethod
    def triggered_version() -> str | None:
        triggered = getattr(ctx, "triggered_id", None)
        if isinstance(triggered, dict):
            return str(triggered.get("version") or "") or None
        if isinstance(triggered, str) and triggered.startswith("{"):
            try:
                return str(json.loads(triggered).get("version") or "") or None
            except ValueError:
                return None
        return None


@callback(
    Output(page.LIST_ID, "children"),
    Input(page.SEARCH_ID, "value"),
    State("auth-user-store", "data"),
    prevent_initial_call=True,
)
def filter_releases(term, user_store):
    user_id = (user_store or {}).get("id")
    releases, live_version = page.load_releases()
    return page.render_list(
        releases,
        live_version,
        str(term or ""),
        can_regenerate=bool(user_id) and can_edit(user_id, REGENERATE_CODE),
    )


@callback(
    Output(page.LIST_ID, "children", allow_duplicate=True),
    Input({"type": "pv-regen", "version": ALL}, "n_clicks"),
    State("auth-user-store", "data"),
    State({"type": "pv-regen", "version": ALL}, "id"),
    prevent_initial_call=True,
)
def regenerate_note(n_clicks, user_store, ids):
    if not any(n_clicks or []):
        raise PreventUpdate
    user_id = (user_store or {}).get("id")
    if not user_id or not can_edit(user_id, REGENERATE_CODE):
        raise PreventUpdate

    version = ctx_helper.triggered_version()
    if not version:
        raise PreventUpdate
    row = versions_crud.get_release_by_version(version)
    if not row:
        raise PreventUpdate

    generator.generate_for_release(int(row["id"]))
    releases, live_version = page.load_releases()
    return page.render_list(releases, live_version, "", can_regenerate=True)
```

`src/pages/settings/platform/versions.py` — `render_list` imzasını genişlet:

```python
def render_list(
    releases: list[dict], live_version: str | None, term: str, can_regenerate: bool = False
) -> html.Div:
    visible = [r for r in releases if vv.matches_search(r, term)]
    return vv.release_list(visible, live_version, can_regenerate=can_regenerate)
```

ve `build_layout` içinde ilk render için:

```python
            html.Div(render_list(releases, live_version, term), id=LIST_ID),
```

- [ ] **Step 6: Testlerin geçtiğini gör**

Run: `$PY -m pytest tests/test_platform_versions_regenerate.py tests/test_platform_versions_page.py -v`
Expected: all passed.

- [ ] **Step 7: Commit**

```bash
git add src/auth/permission_catalog.py src/pages/settings/platform/ tests/test_platform_versions_regenerate.py
git commit -m "feat(task-64): permissioned regenerate action on the versions panel"
```

---

### Task 11: `scripts/regenerate_release_notes.py`

**Files:**
- Create: `scripts/regenerate_release_notes.py`
- Test: `tests/test_regenerate_release_notes_script.py`

**Interfaces:**
- Consumes: Task 7'nin `POST /internal/platform/releases/<version>/note/regenerate` ve `confirm`/`reject` yolları; Task 8'in `render_note` kalıbı (aynı biçim tekrar edilir, import edilmez — script'ler birbirine bağlanmaz).
- Produces: `main(argv: list[str] | None = None) -> int`, bayraklar `--version`, `--all`, `--preview`, `--yes`, `--base-url`, `--token`.

**`--preview`:** yalnızca üretir ve gösterir; onaylamaz. Taslak sunucuda kalır, panel değişmez.

- [ ] **Step 1: Başarısız testi yaz**

`tests/test_regenerate_release_notes_script.py`:

```python
"""regenerate_release_notes.py — HTTP mock'lanır."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "regenerate_release_notes.py"
_spec = importlib.util.spec_from_file_location("regenerate_release_notes", _PATH)
rr = importlib.util.module_from_spec(_spec)
sys.modules["regenerate_release_notes"] = rr
_spec.loader.exec_module(rr)

_NOTE = {"status": "draft", "headline": "Panel yenilendi", "body": {"added": [], "fixed": [], "improved": []}}


def test_version_flag_regenerates_and_confirms_with_yes():
    calls = []

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        return {"note": _NOTE, "confirmed": True}

    with patch.object(rr, "_post", fake_post):
        rc = rr.main(["--version", "2026.08.1", "--yes", "--base-url", "http://x", "--token", "t"])

    assert rc == 0
    assert calls == [
        "/internal/platform/releases/2026.08.1/note/regenerate",
        "/internal/platform/releases/2026.08.1/note/confirm",
    ]


def test_preview_never_confirms():
    calls = []

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        return {"note": _NOTE}

    with patch.object(rr, "_post", fake_post):
        rc = rr.main(["--version", "2026.08.1", "--preview", "--base-url", "http://x", "--token", "t"])

    assert rc == 0
    assert calls == ["/internal/platform/releases/2026.08.1/note/regenerate"]


def test_preview_prints_the_note(capsys):
    with patch.object(rr, "_post", lambda base, path, token, payload=None: {"note": _NOTE}):
        rr.main(["--version", "2026.08.1", "--preview", "--base-url", "http://x", "--token", "t"])
    assert "Panel yenilendi" in capsys.readouterr().out


def test_all_flag_walks_every_release():
    calls = []

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        return {"note": _NOTE, "confirmed": True}

    with patch.object(rr, "_list_versions", lambda base, token: ["2026.08.1", "2026.07.1"]), \
         patch.object(rr, "_post", fake_post):
        rc = rr.main(["--all", "--yes", "--base-url", "http://x", "--token", "t"])

    assert rc == 0
    assert calls.count("/internal/platform/releases/2026.08.1/note/regenerate") == 1
    assert calls.count("/internal/platform/releases/2026.07.1/note/regenerate") == 1


def test_requires_version_or_all():
    assert rr.main(["--base-url", "http://x", "--token", "t"]) == 2


def test_requires_a_token():
    assert rr.main(["--version", "2026.08.1", "--base-url", "http://x", "--token", ""]) == 2


def test_interactive_no_answer_rejects():
    calls = []

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        return {"note": _NOTE, "rejected": True}

    with patch.object(rr, "_post", fake_post), \
         patch.object(rr.sys.stdin, "isatty", lambda: True), \
         patch.object(rr, "_ask", lambda prompt: "h"):
        rr.main(["--version", "2026.08.1", "--base-url", "http://x", "--token", "t"])

    assert calls[-1].endswith("/reject")


def test_no_tty_without_yes_leaves_the_draft():
    calls = []

    with patch.object(rr, "_post", lambda base, path, token, payload=None: calls.append(path) or {"note": _NOTE}), \
         patch.object(rr.sys.stdin, "isatty", lambda: False):
        rr.main(["--version", "2026.08.1", "--base-url", "http://x", "--token", "t"])

    assert not any("confirm" in c for c in calls)
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `$PY -m pytest tests/test_regenerate_release_notes_script.py -v`
Expected: collection error — `FileNotFoundError: scripts/regenerate_release_notes.py`.

- [ ] **Step 3: Script'i yaz**

`scripts/regenerate_release_notes.py`:

```python
#!/usr/bin/env python3
"""Var olan release'lerin notunu yeniden üretir.

Kullanım:
    python scripts/regenerate_release_notes.py --version 2026.08.1
    python scripts/regenerate_release_notes.py --version 2026.08.1 --preview
    python scripts/regenerate_release_notes.py --all --yes

--preview yalnızca üretir ve gösterir; taslak sunucuda kalır, panel değişmez.
"""

from __future__ import annotations

import argparse
import os
import sys

import requests

_BUCKET_LABELS = (("added", "Yenilikler"), ("fixed", "Düzeltmeler"), ("improved", "İyileştirmeler"))


def _post(base_url: str, path: str, token: str, payload: dict | None = None) -> dict:
    resp = requests.post(
        f"{base_url}{path}", json=payload, headers={"X-Release-Token": token}, timeout=180
    )
    resp.raise_for_status()
    return resp.json()


def _list_versions(base_url: str, token: str) -> list[str]:
    resp = requests.get(
        f"{base_url}/internal/platform/releases/versions",
        headers={"X-Release-Token": token},
        timeout=30,
    )
    resp.raise_for_status()
    return [str(v) for v in (resp.json().get("versions") or []) if str(v).strip()]


def render_note(note: dict) -> str:
    lines: list[str] = []
    headline = note.get("headline")
    if headline:
        lines.append(str(headline))
        lines.append("")
    body = note.get("body") or {}
    for key, label in _BUCKET_LABELS:
        items = body.get(key) or []
        if not items:
            continue
        lines.append(label)
        for item in items:
            shas = ", ".join(item.get("shas") or [])
            lines.append(f"  • {item.get('text', '')}  [{shas}]")
        lines.append("")
    if note.get("status") == "auto":
        lines.append("(model not üretemedi — bu bir otomatik özet)")
    if not lines:
        lines.append("(gösterilecek kullanıcıya dönük değişiklik yok)")
    return "\n".join(lines).rstrip()


def _ask(prompt: str) -> str:
    return input(prompt).strip().lower()


def _handle_one(base: str, version: str, token: str, *, preview: bool, auto_yes: bool) -> None:
    note = (_post(base, f"/internal/platform/releases/{version}/note/regenerate", token) or {}).get("note") or {}
    print(f"\n--- {version} ---")
    print(render_note(note))
    print()
    if preview:
        print("(önizleme: taslak onaylanmadı)")
        return
    if auto_yes:
        _post(base, f"/internal/platform/releases/{version}/note/confirm", token)
        print("Not yayına alındı.")
        return
    if not sys.stdin.isatty():
        print("TTY yok; taslak onaylanmadan bırakıldı.")
        return
    while True:
        answer = _ask("Yayınlayalım mı? [e = evet / h = hayır]: ")
        if answer == "e":
            _post(base, f"/internal/platform/releases/{version}/note/confirm", token)
            print("Not yayına alındı.")
            return
        if answer == "h":
            _post(base, f"/internal/platform/releases/{version}/note/reject", token)
            print("Taslak silindi.")
            return
        print("e veya h yazın.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Release note'ları yeniden üret.")
    ap.add_argument("--base-url", default=os.environ.get("GUI_BASE_URL", "http://localhost:8050"))
    ap.add_argument("--token", default=os.environ.get("RELEASE_INGEST_TOKEN", ""))
    ap.add_argument("--version", default=None)
    ap.add_argument("--all", action="store_true", help="kayıtlı her sürüm için çalıştır")
    ap.add_argument("--preview", action="store_true", help="üret ve göster, onaylama")
    ap.add_argument("--yes", action="store_true", help="soru sormadan onayla")
    args = ap.parse_args(argv)

    if not args.version and not args.all:
        print("--version veya --all gerekli.", file=sys.stderr)
        return 2
    if not args.token:
        print("RELEASE_INGEST_TOKEN tanımlı değil.", file=sys.stderr)
        return 2

    base = args.base_url.rstrip("/")
    versions = [args.version] if args.version else _list_versions(base, args.token)
    for version in versions:
        _handle_one(base, str(version).strip(), args.token, preview=args.preview, auto_yes=args.yes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Run: `$PY -m pytest tests/test_regenerate_release_notes_script.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/regenerate_release_notes.py tests/test_regenerate_release_notes_script.py
git commit -m "feat(task-64): regenerate release notes for existing versions"
```

---

### Task 12: Token'ın yapılandırılması

**Files:**
- Create: `k8s/frontend/secret-reference.yaml`
- Create: `docs/ops/release-ingest-token.md`
- Modify: `k8s/frontend/deployment.yaml:50` (`envFrom` bloğu)
- Modify: `docker-compose.yml` (`app` servisi)
- Test: `tests/test_release_ingest_secret_hygiene.py`

**Interfaces:**
- Consumes: Task 7'nin `RELEASE_INGEST_TOKEN` ortam değişkeni.
- Produces: yerel ve production'da tanımlı token; repoda yalnızca şablon.

**Kural:** gerçek token repoya girmez. `secret-reference.yaml` mevcut `k8s/chatbot-api/secret-reference.yaml` kalıbını izler ve yalnızca yer tutucu içerir. Secret küme üzerinde elle üretilir.

**Kapsam dışı:** `.github/workflows/*` bu ortamdan push edilemiyor (OAuth `workflow` scope'u yok), bu yüzden CI tarafına dokunulmuyor.

- [ ] **Step 1: Başarısız testi yaz**

`tests/test_release_ingest_secret_hygiene.py`:

```python
"""Repoda gerçek token bulunmadığını ve yapılandırmanın bağlandığını doğrular."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_REF = _ROOT / "k8s" / "frontend" / "secret-reference.yaml"
_DEPLOY = _ROOT / "k8s" / "frontend" / "deployment.yaml"
_COMPOSE = _ROOT / "docker-compose.yml"


def test_secret_reference_holds_only_a_placeholder():
    doc = yaml.safe_load(_REF.read_text(encoding="utf-8"))
    value = doc["stringData"]["RELEASE_INGEST_TOKEN"]
    assert value == "REPLACE_WITH_REAL_TOKEN_OUTSIDE_GIT"


def test_secret_reference_carries_the_do_not_commit_warning():
    text = _REF.read_text(encoding="utf-8")
    assert "REFERENCE ONLY" in text


def test_no_long_random_looking_secret_in_the_reference():
    text = _REF.read_text(encoding="utf-8")
    assert not re.search(r"[A-Za-z0-9+/]{32,}={0,2}", text.replace("REPLACE_WITH_REAL_TOKEN_OUTSIDE_GIT", ""))


def test_frontend_deployment_mounts_the_secret_optionally():
    for doc in yaml.safe_load_all(_DEPLOY.read_text(encoding="utf-8")):
        if not doc or doc.get("kind") != "Deployment":
            continue
        container = doc["spec"]["template"]["spec"]["containers"][0]
        refs = [e.get("secretRef", {}).get("name") for e in container.get("envFrom") or []]
        assert "release-ingest-secret" in refs
        entry = [e for e in container["envFrom"] if e.get("secretRef", {}).get("name") == "release-ingest-secret"][0]
        # Secret yoksa pod başlamalı; endpoint kendi kendini 503'e kapatır.
        assert entry["secretRef"].get("optional") is True
        return
    raise AssertionError("frontend Deployment bulunamadı")


def test_compose_passes_the_token_through():
    doc = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    env = doc["services"]["app"]["environment"]
    if isinstance(env, dict):
        assert "RELEASE_INGEST_TOKEN" in env
    else:
        assert any(str(item).startswith("RELEASE_INGEST_TOKEN") for item in env)
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `$PY -m pytest tests/test_release_ingest_secret_hygiene.py -v`
Expected: FAIL — `FileNotFoundError: k8s/frontend/secret-reference.yaml`.

- [ ] **Step 3: Şablonu yaz**

`k8s/frontend/secret-reference.yaml`:

```yaml
# REFERENCE ONLY — do NOT commit a real token.
#
# Gerçek secret küme üzerinde elle üretilir:
#   TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
#   kubectl create secret generic release-ingest-secret \
#     --from-literal=RELEASE_INGEST_TOKEN="$TOKEN"
#
# Aynı değer, release'i açan makinede RELEASE_INGEST_TOKEN olarak tanımlı olmalı.
apiVersion: v1
kind: Secret
metadata:
  name: release-ingest-secret
type: Opaque
stringData:
  RELEASE_INGEST_TOKEN: "REPLACE_WITH_REAL_TOKEN_OUTSIDE_GIT"
```

- [ ] **Step 4: Deployment ve compose'u bağla**

`k8s/frontend/deployment.yaml` — mevcut `envFrom` listesine ikinci girdi olarak:

```yaml
            - secretRef:
                name: release-ingest-secret
                optional: true
```

`optional: true` bilinçli: secret yoksa pod yine başlar, endpoint kendini 503'e kapatır.

`docker-compose.yml` — `app` servisinin `environment` bloğuna:

```yaml
      RELEASE_INGEST_TOKEN: ${RELEASE_INGEST_TOKEN:-}
```

- [ ] **Step 5: Operasyon notunu yaz**

`docs/ops/release-ingest-token.md`:

```markdown
# Release ingest token

`scripts/new_release.py` GUI'ye paylaşılan bir token'la bağlanır. Token repoda durmaz.

## Üretme

    python3 -c "import secrets; print(secrets.token_urlsafe(32))"

## Yerel

Değeri `.env` dosyasına yaz (`.gitignore` kapsamında):

    RELEASE_INGEST_TOKEN=<üretilen değer>

## Production

    kubectl create secret generic release-ingest-secret \
      --from-literal=RELEASE_INGEST_TOKEN='<üretilen değer>'

`k8s/frontend/deployment.yaml` bu secret'ı `optional: true` ile bağlar. Secret yoksa
pod yine başlar; `/internal/platform/releases*` yolları 503 döner ve panel değişmez.

## Döndürme

Secret'ı güncelle, frontend deployment'ını yeniden başlat, sonra release'i açan
makinedeki değeri değiştir. İki taraf uyuşmazsa endpoint 403 döner.
```

- [ ] **Step 6: Testlerin geçtiğini gör**

Run: `$PY -m pytest tests/test_release_ingest_secret_hygiene.py -v`
Expected: 5 passed.

- [ ] **Step 7: Compose'un çözümlendiğini doğrula**

Run: `docker compose config | grep RELEASE_INGEST_TOKEN`
Expected: değişken görünür (değeri boş olabilir).

- [ ] **Step 8: Bütün paketi çalıştır**

Run: `$PY -m pytest tests/ -q && $PY -m pytest services/chatbot-api/app/tests/ -q`
Expected: hepsi passed.

- [ ] **Step 9: Commit**

```bash
git add k8s/frontend/secret-reference.yaml k8s/frontend/deployment.yaml docker-compose.yml docs/ops/release-ingest-token.md tests/test_release_ingest_secret_hygiene.py
git commit -m "chore(task-64): wire RELEASE_INGEST_TOKEN into compose and k8s"
```

---

## Bitiş kriterleri

- `$PY -m pytest tests/ -q` ve `$PY -m pytest services/chatbot-api/app/tests/ -q` temiz geçer; baseline'daki `test_visible_change_filter_hides_chore` de dahil.
- `scripts/new_release.py --dry-run` commit listesini ağa çıkmadan gösterir.
- Panelde her release'in bir notu vardır; hiçbir kartın gövdesinde ham commit subject'i yoktur.
- `RELEASE_INGEST_TOKEN` tanımsızken `/internal/platform/releases/last-sha` 503 döner.
- Repoda gerçek token yoktur.
- Branch `worktree-task-64-ai-release-notes`, tabanı `origin/development`; merge hedefi `development`.

