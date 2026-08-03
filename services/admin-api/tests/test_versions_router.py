"""Versions router: list, current, register — DB mocked."""

from __future__ import annotations

from unittest.mock import patch

from app.models import RegisterDeploymentRequest
from app.routers import versions


def test_list_releases_groups_changes_and_services():
    releases = [{"id": 1, "version": "2026.07.1", "released_at": "2026-07-06",
                 "title": None, "notes": None, "source": "backfill"}]
    changes = [{"release_id": 1, "change_type": "feat", "summary": "Add X",
                "commit_sha": "abc1234", "scope": "gui"}]
    deps = [{"service": "frontend", "version": "2026.07.1", "git_sha": "abc1234",
             "image_tag": "abc1234", "environment": "production", "started_at": "2026-07-06T10:00:00"}]

    def fake_fetch_all(sql, params=None):
        s = sql.lower()
        if "from platform_releases" in s:
            return releases
        if "from release_changes" in s:
            return changes
        if "from service_deployments" in s:
            return deps
        return []

    with patch.object(versions.db, "fetch_all", side_effect=fake_fetch_all):
        out = versions.list_releases()
    assert out[0].version == "2026.07.1"
    assert out[0].changes[0].change_type == "feat"
    assert out[0].services[0].service == "frontend"


def test_list_releases_attaches_the_published_note():
    """Panel notu buradan okur; router doldurmazsa ekran boş görünür.

    Modelde `note` alanının bulunması yetmez — bu test alanın gerçekten
    doldurulduğunu ister, çünkü eksik olan tam olarak oydu.
    """
    releases = [{"id": 7, "version": "2026.07.3", "released_at": "2026-07-23",
                 "title": None, "notes": None, "source": "backfill"}]
    notes = [{"release_id": 7, "headline": "Üç yenilik",
              "body": {"added": [{"shas": ["abc1234"], "text": "X eklendi"}]},
              "source": "auto", "model": None, "generated_at": None}]

    def fake_fetch_all(sql, params=None):
        s = sql.lower()
        if "from platform_releases" in s:
            return releases
        if "from release_notes" in s:
            return notes
        return []

    with patch.object(versions.db, "fetch_all", side_effect=fake_fetch_all):
        out = versions.list_releases()
    assert out[0].note is not None, "note doldurulmadı"
    assert out[0].note.headline == "Üç yenilik"
    assert out[0].note.body["added"][0]["text"] == "X eklendi"
    assert out[0].note.source == "auto"


def test_release_without_a_note_stays_none():
    """Notu olmayan release boş sözlük değil, None döner — panel ikisini ayırıyor."""
    releases = [{"id": 8, "version": "2026.06.1", "released_at": "2026-06-01",
                 "title": None, "notes": None, "source": "backfill"}]

    def fake_fetch_all(sql, params=None):
        return releases if "from platform_releases" in sql.lower() else []

    with patch.object(versions.db, "fetch_all", side_effect=fake_fetch_all):
        out = versions.list_releases()
    assert out[0].note is None


def test_draft_fields_never_leave_the_service():
    """Onaylanmamış taslak metin API'den dışarı sızmamalı."""
    releases = [{"id": 9, "version": "2026.07.4", "released_at": "2026-07-30",
                 "title": None, "notes": None, "source": "deploy"}]
    notes = [{"release_id": 9, "headline": "Yayın", "body": {}, "source": "model",
              "model": "gpt", "generated_at": None,
              "draft_headline": "GİZLİ TASLAK", "draft_body": {"added": ["gizli"]}}]

    def fake_fetch_all(sql, params=None):
        s = sql.lower()
        if "from platform_releases" in s:
            return releases
        if "from release_notes" in s:
            return notes
        return []

    with patch.object(versions.db, "fetch_all", side_effect=fake_fetch_all):
        out = versions.list_releases()
    blob = out[0].model_dump_json()
    assert "GİZLİ TASLAK" not in blob
    assert "gizli" not in blob


def test_register_deployment_inserts_and_echoes():
    req = RegisterDeploymentRequest(service="query-api", version="2026.07.2", git_sha="def5678")
    with patch.object(versions.db, "execute", return_value=1) as ex:
        out = versions.register_deployment(req)
    assert ex.called
    assert out.service == "query-api"
    assert out.version == "2026.07.2"


def test_current_versions_returns_latest_per_service():
    rows = [{"service": "frontend", "version": "2026.07.2", "git_sha": "x",
             "image_tag": "x", "environment": "production", "started_at": "2026-07-13T00:00:00"}]
    with patch.object(versions.db, "fetch_all", return_value=rows):
        out = versions.current_versions()
    assert out[0].service == "frontend"
    assert out[0].version == "2026.07.2"
