"""Local versions CRUD reads/writes via src.auth.db (mocked)."""

from __future__ import annotations

from unittest.mock import patch

from src.auth import versions_crud


def test_list_platform_releases_shapes_rows():
    releases = [{"id": 1, "version": "2026.07.1", "released_at": "2026-07-06",
                 "title": None, "notes": None, "source": "backfill"}]
    changes = [{"release_id": 1, "change_type": "feat", "summary": "Add X",
                "commit_sha": "abc", "scope": "gui"}]
    deps = [{"service": "frontend", "version": "2026.07.1", "git_sha": "abc",
             "image_tag": "abc", "environment": "production", "started_at": "2026-07-06T10:00:00"}]

    def fake_fetch_all(sql, params=None):
        s = sql.lower()
        if "from platform_releases" in s:
            return releases
        if "from release_changes" in s:
            return changes
        if "from service_deployments" in s:
            return deps
        return []

    with patch.object(versions_crud.db, "fetch_all", side_effect=fake_fetch_all):
        out = versions_crud.list_platform_releases()
    assert out[0]["version"] == "2026.07.1"
    assert out[0]["changes"][0]["change_type"] == "feat"
    assert out[0]["services"][0]["service"] == "frontend"


def test_register_deployment_executes_insert():
    with patch.object(versions_crud.db, "execute", return_value=1) as ex:
        versions_crud.register_deployment("query-api", "2026.07.2", "def", None, "local")
    assert ex.called
