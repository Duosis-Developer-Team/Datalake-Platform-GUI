"""The home/overview route must render a skeleton shell instantly, then fill content
off the render path — so a cold /dashboard/overview fetch (~80s) never blanks the page.
"""
from pathlib import Path
from unittest.mock import patch

import dash
from src.pages import home


def test_shell_does_not_build_content_synchronously():
    with patch.object(home, "build_overview") as bo:
        shell = home.build_overview_shell(["page_a"])
    bo.assert_not_called()
    flat = repr(shell)
    assert "overview-page-root" in flat
    assert "overview-visible-sections" in flat


def test_fill_callback_noops_off_route():
    assert home._fill_overview_content("/datacenters", {"preset": "7d"}, None) is dash.no_update


def test_fill_callback_builds_on_home_route():
    for path in ("/", ""):
        with patch.object(home, "build_overview", return_value="CONTENT") as bo:
            out = home._fill_overview_content(path, {"preset": "7d", "start": "x", "end": "y"}, ["p"])
        assert out == "CONTENT"
        bo.assert_called_once()


def test_app_routes_home_to_shell():
    src = Path("app.py").read_text(encoding="utf-8")
    assert "build_overview_shell" in src
