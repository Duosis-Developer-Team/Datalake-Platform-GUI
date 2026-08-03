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
