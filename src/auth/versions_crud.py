"""Local (direct-DB) platform versioning reads/writes.

Mirrors the shapes returned by admin-api's versions router so
src/services/admin_client.py can fall back to this without ADMIN_API_URL.
"""

from __future__ import annotations

import json
from typing import Any

from src.auth import db

_NOTE_COLS = (
    "release_id, headline, body, source, draft_headline, draft_body, "
    "model, input_fingerprint, generated_at"
)


def list_platform_releases() -> list[dict[str, Any]]:
    releases = db.fetch_all(
        """
        SELECT id, version, released_at::text AS released_at, title, notes, source
        FROM platform_releases
        ORDER BY released_at DESC, version DESC
        """
    )
    changes = db.fetch_all(
        "SELECT release_id, change_type, summary, commit_sha, scope FROM release_changes ORDER BY id"
    )
    deps = db.fetch_all(
        """
        SELECT service, version, git_sha, image_tag, environment, started_at::text AS started_at
        FROM service_deployments ORDER BY started_at DESC
        """
    )
    changes_by_release: dict[Any, list[dict]] = {}
    for c in changes:
        changes_by_release.setdefault(c["release_id"], []).append(c)
    deps_by_version: dict[str, list[dict]] = {}
    for d in deps:
        deps_by_version.setdefault(d["version"], []).append(d)
    notes = {
        int(n["release_id"]): dict(n)
        for n in db.fetch_all(f"SELECT {_NOTE_COLS} FROM release_notes")
    }
    out = []
    for r in releases:
        r = dict(r)
        r["changes"] = changes_by_release.get(r["id"], [])
        r["services"] = deps_by_version.get(r["version"], [])
        r["note"] = notes.get(int(r["id"]))
        out.append(r)
    return out


def get_current_versions() -> list[dict[str, Any]]:
    return db.fetch_all(
        """
        SELECT DISTINCT ON (service)
               service, version, git_sha, image_tag, environment, started_at::text AS started_at
        FROM service_deployments
        ORDER BY service, started_at DESC
        """
    )


def register_deployment(
    service: str,
    version: str,
    git_sha: str | None = None,
    image_tag: str | None = None,
    environment: str = "production",
) -> None:
    db.execute(
        """
        INSERT INTO service_deployments (service, version, git_sha, image_tag, environment)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (service, version, git_sha, image_tag, environment),
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
        (
            release_id,
            headline,
            json.dumps(body, ensure_ascii=False),
            source,
            model,
            input_fingerprint,
        ),
    )


def set_draft_note(
    release_id: int, *, draft_headline: str | None, draft_body: dict, model: str
) -> None:
    db.execute(
        "UPDATE release_notes SET draft_headline = %s, draft_body = %s, model = %s "
        "WHERE release_id = %s",
        (draft_headline, json.dumps(draft_body, ensure_ascii=False), model, release_id),
    )


def pending_draft_notes() -> dict[str, dict]:
    """Onay bekleyen taslakları sürüm numarasına göre döndürür.

    Anahtar `id` değil `version`: admin-api'nin `ReleaseOut` modelinde `id` alanı
    yok (taslak alanları da bilerek yok), yani panel iki taşıma yolunda da ancak
    sürüm numarası üzerinden eşleştirebiliyor.

    Taslak metni buradan okunur, release listesinden değil. Böylece onaylanmamış
    metin yalnızca yetkili kullanıcı için, tek ve açıkça kapılanmış bir yoldan
    panele giriyor.
    """
    rows = db.fetch_all(
        "SELECT pr.version, rn.release_id, rn.draft_headline, rn.draft_body, rn.model "
        "FROM release_notes rn "
        "JOIN platform_releases pr ON pr.id = rn.release_id "
        "WHERE rn.draft_body IS NOT NULL"
    )
    return {str(r["version"]): dict(r) for r in rows}


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
