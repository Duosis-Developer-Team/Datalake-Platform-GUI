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
