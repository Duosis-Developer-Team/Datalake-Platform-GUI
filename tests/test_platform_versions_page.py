"""Platform versions page renders for empty and populated history."""

from __future__ import annotations

from unittest.mock import patch

from src.pages.settings.platform import versions as page


def _sample_releases():
    return [{
        "version": "2026.07.2", "released_at": "2026-07-13", "title": None,
        "notes": None, "source": "backfill",
        "changes": [
            {"change_type": "feat", "summary": "Backup tab", "commit_sha": "a1", "scope": "gui"},
            {"change_type": "chore", "summary": "bump deps", "commit_sha": "a2", "scope": None},
        ],
        "services": [
            {"service": "frontend", "version": "2026.07.2", "git_sha": "a1",
             "image_tag": "a1", "environment": "production", "started_at": "2026-07-13T09:00:00"},
        ],
    }]


def test_build_layout_empty_history_renders():
    with patch.object(page.admin_client, "list_platform_releases", return_value=[]), \
         patch.object(page.admin_client, "get_current_versions", return_value=[]):
        out = page.build_layout()
    assert out is not None


def test_build_layout_populated_history_renders():
    with patch.object(page.admin_client, "list_platform_releases", return_value=_sample_releases()), \
         patch.object(page.admin_client, "get_current_versions", return_value=[]):
        out = page.build_layout()
    assert out is not None


def test_visible_change_filter_hides_chore():
    visible, hidden = page._split_changes(_sample_releases()[0]["changes"])
    assert [c["summary"] for c in visible] == ["Backup tab"]
    assert hidden == 1
