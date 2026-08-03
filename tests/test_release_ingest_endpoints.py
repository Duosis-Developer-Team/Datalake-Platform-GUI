"""Ingest ve onay endpoint'leri — token, TRT günü, dedupe, onay.

DB'ye ve chatbot-api'ye hiç çıkılmaz; `versions_crud` ve `release_note_generator`
modül seviyesinde patch'lenir. Buradaki token sahtedir, gerçek bir sır değildir.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import flask
import pytest

from src.routes import release_ingest

TOKEN = "test-token-123"


def _make_app():
    app = flask.Flask(__name__)
    release_ingest.register_release_ingest_routes(app)
    return app


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("RELEASE_INGEST_TOKEN", TOKEN)
    return _make_app()


@pytest.fixture()
def client(app):
    return app.test_client()


def _hdr(token=TOKEN):
    return {"X-Release-Token": token}


_COMMITS = [
    {"sha": "aaaaaaaaaaaa", "date": "2026-08-03", "subject": "feat(panel): yeni rozet"},
    {"sha": "bbbbbbbbbbbb", "date": "2026-08-03", "subject": "fix: rozet hizası"},
]


# --- token kapısı ---------------------------------------------------------


def test_missing_token_env_returns_503(monkeypatch):
    monkeypatch.delenv("RELEASE_INGEST_TOKEN", raising=False)
    r = _make_app().test_client().get("/internal/platform/releases/last-sha", headers=_hdr())
    assert r.status_code == 503


def test_empty_token_env_returns_503(monkeypatch):
    monkeypatch.setenv("RELEASE_INGEST_TOKEN", "   ")
    r = _make_app().test_client().get("/internal/platform/releases/last-sha", headers=_hdr())
    assert r.status_code == 503


def test_missing_token_env_closes_the_write_path_too(monkeypatch):
    """503 yalnızca okuma yolunda değil; ingest de kapanır."""
    monkeypatch.delenv("RELEASE_INGEST_TOKEN", raising=False)
    r = _make_app().test_client().post(
        "/internal/platform/releases", json={"commits": _COMMITS}, headers=_hdr()
    )
    assert r.status_code == 503


def test_wrong_token_returns_403(client):
    assert client.get("/internal/platform/releases/last-sha", headers=_hdr("nope")).status_code == 403


def test_missing_header_returns_403(client):
    assert client.get("/internal/platform/releases/last-sha").status_code == 403


def test_token_prefix_is_not_accepted(client):
    """Doğru token'ın ön eki de reddedilir."""
    assert client.get(
        "/internal/platform/releases/last-sha", headers=_hdr(TOKEN[:-1])
    ).status_code == 403


def test_non_ascii_token_does_not_crash_the_comparison(monkeypatch):
    """hmac.compare_digest str ile ASCII dışı değerde TypeError verir; karşılaştırma byte üstünden."""
    monkeypatch.setenv("RELEASE_INGEST_TOKEN", "şifre-çğüöı")
    client = _make_app().test_client()
    assert client.get("/internal/platform/releases/last-sha", headers=_hdr("başka")).status_code == 403
    with patch.object(release_ingest.versions_crud, "last_ingested_sha", lambda: None):
        ok = client.get("/internal/platform/releases/last-sha", headers=_hdr("şifre-çğüöı"))
    assert ok.status_code == 200


def test_every_registered_route_is_token_gated(app):
    """Kapıdan kaçan tek bir yol bile kalmamalı."""
    checked = 0
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/internal/"):
            continue
        method = "POST" if "POST" in rule.methods else "GET"
        path = rule.rule.replace("<version>", "2026.08.1")
        resp = app.test_client().open(path, method=method, headers=_hdr("nope"))
        assert resp.status_code == 403, f"{method} {path} kapıdan kaçtı"
        checked += 1
    assert checked >= 6


def test_every_registered_route_lives_under_internal(app):
    """ingress /api/v1/* isteklerini başka servise yönlendiriyor; oraya taşınmamalı."""
    rules = [r.rule for r in app.url_map.iter_rules() if r.endpoint != "static"]
    assert rules
    assert all(r.startswith("/internal/platform/releases") for r in rules), rules


# --- okuma yolları --------------------------------------------------------


def test_last_sha_returns_stored_value(client):
    with patch.object(release_ingest.versions_crud, "last_ingested_sha", lambda: "aaaaaaaaaaaa"):
        r = client.get("/internal/platform/releases/last-sha", headers=_hdr())
    assert r.status_code == 200
    assert r.get_json()["last_sha"] == "aaaaaaaaaaaa"


def test_last_sha_is_null_when_nothing_ingested(client):
    with patch.object(release_ingest.versions_crud, "last_ingested_sha", lambda: None):
        r = client.get("/internal/platform/releases/last-sha", headers=_hdr())
    assert r.get_json() == {"last_sha": None}


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


# --- ingest ---------------------------------------------------------------


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
         patch.object(release_ingest.generator, "generate_for_release",
                      lambda rid: {"status": "draft", "body": {}}):
        r = client.post("/internal/platform/releases", json={"commits": _COMMITS}, headers=_hdr())

    assert r.status_code == 201
    assert seen["version"] == "2026.08.3"
    assert seen["released_at"] == "2026-08-03"
    payload = r.get_json()
    assert payload["changes_added"] == 2
    assert payload["release_id"] == 7
    assert payload["note"] == {"status": "draft", "body": {}}


def test_ingest_parses_conventional_prefixes(client):
    captured = {}

    def fake_add(release_id, changes):
        captured["changes"] = changes
        return len(changes)

    with patch.object(release_ingest.rn, "trt_date", lambda: date(2026, 8, 3)), \
         patch.object(release_ingest.versions_crud, "month_release_count", lambda y, m: 0), \
         patch.object(release_ingest.versions_crud, "open_release", lambda *a, **k: 7), \
         patch.object(release_ingest.versions_crud, "add_release_changes", fake_add), \
         patch.object(release_ingest.generator, "generate_for_release",
                      lambda rid: {"status": "auto", "body": {}}):
        client.post("/internal/platform/releases", json={"commits": _COMMITS}, headers=_hdr())

    first = captured["changes"][0]
    assert first["change_type"] == "feat"
    assert first["summary"] == "yeni rozet"
    assert first["scope"] == "panel"
    assert first["commit_sha"] == "aaaaaaaaaaaa"
    second = captured["changes"][1]
    assert second["change_type"] == "fix"
    assert second["scope"] is None


def test_ingest_truncates_long_sha_to_twelve(client):
    captured = {}

    def fake_add(release_id, changes):
        captured["changes"] = changes
        return len(changes)

    with patch.object(release_ingest.versions_crud, "open_release", lambda *a, **k: 7), \
         patch.object(release_ingest.versions_crud, "month_release_count", lambda y, m: 0), \
         patch.object(release_ingest.versions_crud, "add_release_changes", fake_add), \
         patch.object(release_ingest.generator, "generate_for_release",
                      lambda rid: {"status": "auto", "body": {}}):
        client.post(
            "/internal/platform/releases",
            json={"commits": [{"sha": "a" * 40, "subject": "feat: uzun sha"}]},
            headers=_hdr(),
        )

    assert captured["changes"][0]["commit_sha"] == "a" * 12


def test_ingest_rejects_empty_commit_list(client):
    r = client.post("/internal/platform/releases", json={"commits": []}, headers=_hdr())
    assert r.status_code == 400


def test_ingest_rejects_missing_commits_key(client):
    r = client.post("/internal/platform/releases", json={}, headers=_hdr())
    assert r.status_code == 400


def test_ingest_rejects_commits_without_sha(client):
    r = client.post(
        "/internal/platform/releases",
        json={"commits": [{"subject": "feat: x"}]},
        headers=_hdr(),
    )
    assert r.status_code == 400


def test_ingest_rejects_garbage_body_without_touching_the_db(client):
    """Gövde JSON bile değilse DB'ye hiç gidilmemeli."""
    def _boom(*a, **k):  # pragma: no cover - çağrılırsa test düşer
        raise AssertionError("DB'ye dokunuldu")

    with patch.object(release_ingest.versions_crud, "open_release", _boom):
        r = client.post(
            "/internal/platform/releases",
            data="düz metin",
            content_type="text/plain",
            headers=_hdr(),
        )
    assert r.status_code == 400


def test_ingest_honours_explicit_version(client):
    seen = {}

    def fake_open(version, released_at, title=None):
        seen["v"] = version
        return 7

    def _no_calver(*a, **k):  # pragma: no cover - çağrılırsa test düşer
        raise AssertionError("açık version verilmişken CalVer sayacı çalıştı")

    with patch.object(release_ingest.versions_crud, "open_release", fake_open), \
         patch.object(release_ingest.versions_crud, "month_release_count", _no_calver), \
         patch.object(release_ingest.versions_crud, "add_release_changes", lambda rid, ch: 1), \
         patch.object(release_ingest.generator, "generate_for_release",
                      lambda rid: {"status": "auto", "body": {}}):
        client.post(
            "/internal/platform/releases",
            json={"commits": _COMMITS, "version": "2026.08.9"},
            headers=_hdr(),
        )
    assert seen["v"] == "2026.08.9"


# --- onay / red / yeniden üretim -----------------------------------------


def test_confirm_promotes_the_draft(client):
    with patch.object(release_ingest.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(release_ingest.versions_crud, "confirm_draft_note", lambda rid: True):
        r = client.post("/internal/platform/releases/2026.08.1/note/confirm", headers=_hdr())
    assert r.status_code == 200
    assert r.get_json()["confirmed"] is True


def test_confirm_reports_false_when_there_is_no_draft(client):
    with patch.object(release_ingest.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(release_ingest.versions_crud, "confirm_draft_note", lambda rid: False):
        r = client.post("/internal/platform/releases/2026.08.1/note/confirm", headers=_hdr())
    assert r.get_json()["confirmed"] is False


def test_confirm_unknown_version_returns_404(client):
    with patch.object(release_ingest.versions_crud, "get_release_by_version", lambda v: None):
        r = client.post("/internal/platform/releases/9999.99.9/note/confirm", headers=_hdr())
    assert r.status_code == 404


def test_reject_clears_the_draft(client):
    with patch.object(release_ingest.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(release_ingest.versions_crud, "reject_draft_note", lambda rid: True):
        r = client.post("/internal/platform/releases/2026.08.1/note/reject", headers=_hdr())
    assert r.get_json()["rejected"] is True


def test_reject_unknown_version_returns_404(client):
    with patch.object(release_ingest.versions_crud, "get_release_by_version", lambda v: None):
        r = client.post("/internal/platform/releases/9999.99.9/note/reject", headers=_hdr())
    assert r.status_code == 404


def test_regenerate_returns_a_fresh_note(client):
    with patch.object(release_ingest.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(release_ingest.generator, "generate_for_release",
                      lambda rid: {"status": "draft", "headline": "Yeni", "body": {"added": []}}):
        r = client.post("/internal/platform/releases/2026.08.1/note/regenerate", headers=_hdr())
    assert r.get_json()["note"]["headline"] == "Yeni"


def test_regenerate_unknown_version_returns_404(client):
    with patch.object(release_ingest.versions_crud, "get_release_by_version", lambda v: None):
        r = client.post("/internal/platform/releases/9999.99.9/note/regenerate", headers=_hdr())
    assert r.status_code == 404


# --- serbest metin kabul edilmez -----------------------------------------


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


def test_confirm_takes_no_argument_beyond_the_release_id(client):
    """confirm_draft_note yalnızca release_id alır; dışarıdan metin sızamaz."""
    seen = {}

    def fake_confirm(release_id, *args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return True

    with patch.object(release_ingest.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(release_ingest.versions_crud, "confirm_draft_note", fake_confirm):
        client.post(
            "/internal/platform/releases/2026.08.1/note/confirm",
            json={"headline": "SAHTE", "body": {"added": []}},
            headers=_hdr(),
        )
    assert seen["args"] == ()
    assert seen["kwargs"] == {}


def test_reject_body_is_ignored(client):
    with patch.object(release_ingest.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(release_ingest.versions_crud, "reject_draft_note", lambda rid: True):
        r = client.post(
            "/internal/platform/releases/2026.08.1/note/reject",
            json={"body": {"added": [{"text": "SAHTE", "shas": ["x"]}]}},
            headers=_hdr(),
        )
    assert r.get_json() == {"rejected": True}


# --- app.py bağlantısı ----------------------------------------------------


def test_app_module_registers_the_routes():
    """app.py'nin gerçekten kaydı yaptığını kaynaktan doğrula (import etmeden)."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert "from src.routes.release_ingest import register_release_ingest_routes" in source
    assert "register_release_ingest_routes(server)" in source
