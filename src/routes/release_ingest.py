"""Release ingest ve not onay endpoint'leri.

Yol öneki `/internal/` — ingress `/api/v1/*` isteklerini başka servislere yönlendirdiği
için bu yollar GUI'nin kendi Flask sunucusunda kalmalı.

Kimlik doğrulama paylaşılan bir token'la yapılır. `RELEASE_INGEST_TOKEN` tanımsız veya
boşsa endpoint 503 döner; hiçbir koşulda açık moda düşmez ve varsayılan token yoktur.
Karşılaştırma `hmac.compare_digest` ile yapılır. Kapı blueprint'in `before_request`'i
olarak kurulur; böylece buraya sonradan eklenen bir yol da kapının dışında kalamaz.

Onaylanan not metni istekle taşınmaz: script yalnızca confirm/reject gönderir, yayına
çıkan metin her zaman sunucunun kendi üretip doğruladığı taslaktır. İstek gövdesindeki
serbest metin hiçbir yolda okunmaz.
"""

from __future__ import annotations

import hmac
import logging
import os

from flask import Blueprint, jsonify, request

from src.auth import versions_crud
from src.services import release_note_generator as generator
from src.services import release_notes as rn

logger = logging.getLogger(__name__)

_TOKEN_ENV = "RELEASE_INGEST_TOKEN"
_URL_PREFIX = "/internal/platform"


def _auth_error():
    """Yetki sorunu varsa `(gövde, status)`; yoksa None."""
    expected = (os.environ.get(_TOKEN_ENV) or "").strip()
    if not expected:
        logger.warning("%s is not set; release ingest is disabled", _TOKEN_ENV)
        return {"error": "release ingest is not configured"}, 503
    supplied = request.headers.get("X-Release-Token") or ""
    if not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        return {"error": "forbidden"}, 403
    return None


def _resolve_release(version: str) -> int | None:
    row = versions_crud.get_release_by_version(str(version))
    return int(row["id"]) if row else None


def _parse_commits(commits) -> list[dict]:
    """Ham commit listesini `release_changes` satırlarına çevirir. Kullanılamayanı atar."""
    changes: list[dict] = []
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
    return changes


def register_release_ingest_routes(flask_app) -> None:
    """Release ingest yollarını verilen Flask sunucusuna bağlar."""
    bp = Blueprint("release_ingest", __name__, url_prefix=_URL_PREFIX)

    @bp.before_request
    def _require_token():
        err = _auth_error()
        if err:
            return jsonify(err[0]), err[1]
        return None

    @bp.get("/releases/last-sha")
    def release_last_sha():
        return jsonify({"last_sha": versions_crud.last_ingested_sha()})

    @bp.get("/releases/versions")
    def release_versions():
        return jsonify(
            {
                "versions": [
                    str(r.get("version") or "")
                    for r in (versions_crud.list_platform_releases() or [])
                    if r.get("version")
                ]
            }
        )

    @bp.post("/releases")
    def release_ingest():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"error": "object body required"}), 400
        commits = payload.get("commits")
        if not isinstance(commits, list) or not commits:
            return jsonify({"error": "commits required"}), 400

        changes = _parse_commits(commits)
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

    @bp.post("/releases/<version>/note/confirm")
    def release_note_confirm(version):
        release_id = _resolve_release(version)
        if release_id is None:
            return jsonify({"error": "unknown release"}), 404
        # Gövde okunmaz: yayına yalnızca sunucunun ürettiği taslak çıkar.
        return jsonify({"confirmed": bool(versions_crud.confirm_draft_note(release_id))})

    @bp.post("/releases/<version>/note/reject")
    def release_note_reject(version):
        release_id = _resolve_release(version)
        if release_id is None:
            return jsonify({"error": "unknown release"}), 404
        versions_crud.reject_draft_note(release_id)
        return jsonify({"rejected": True})

    @bp.post("/releases/<version>/note/regenerate")
    def release_note_regenerate(version):
        release_id = _resolve_release(version)
        if release_id is None:
            return jsonify({"error": "unknown release"}), 404
        return jsonify({"note": generator.generate_for_release(release_id)})

    flask_app.register_blueprint(bp)
