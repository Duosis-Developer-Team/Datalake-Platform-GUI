"""Tests for teams router schema detection (no live DB)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.routers import teams


@pytest.fixture(autouse=True)
def reset_teams_schema_cache():
    teams._reset_teams_schema_cache_for_tests()
    yield
    teams._reset_teams_schema_cache_for_tests()


def test_teams_extended_schema_probe_true():
    with patch.object(teams.db, "fetch_one", return_value={"ok": True}) as m:
        teams._reset_teams_schema_cache_for_tests()
        assert teams._teams_extended_schema_ready() is True
        assert teams._teams_extended_schema_ready() is True  # cached
        assert m.call_count == 1


def test_teams_extended_schema_probe_false():
    with patch.object(teams.db, "fetch_one", return_value={"ok": False}):
        teams._reset_teams_schema_cache_for_tests()
        assert teams._teams_extended_schema_ready() is False


def test_teams_extended_schema_probe_exception_falls_back():
    with patch.object(teams.db, "fetch_one", side_effect=RuntimeError("db down")):
        teams._reset_teams_schema_cache_for_tests()
        assert teams._teams_extended_schema_ready() is False
