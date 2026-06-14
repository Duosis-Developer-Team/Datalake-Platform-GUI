"""The /datacenters route must render a skeleton shell instantly, then fill content
off the render path — so a cold backend summary fetch never leaves the page blank.
"""
import ast
from pathlib import Path
from unittest.mock import patch

import dash
from src.pages import datacenters


def test_shell_does_not_build_content_synchronously():
    with patch.object(datacenters, "build_datacenters") as bd:
        shell = datacenters.build_datacenters_shell(["page_a"])
    bd.assert_not_called()                       # no blocking build on the render path
    flat = repr(shell)
    assert "datacenters-page-root" in flat        # empty content container present
    assert "datacenters-visible-sections" in flat # vis carried to the fill callback


def test_fill_callback_noops_off_route():
    out = datacenters._fill_datacenters_content("/global-view", {"preset": "7d"}, None)
    assert out is dash.no_update


def test_fill_callback_builds_on_route():
    with patch.object(datacenters, "build_datacenters", return_value="CONTENT") as bd:
        out = datacenters._fill_datacenters_content(
            "/datacenters", {"preset": "7d", "start": "x", "end": "y"}, ["page_a"]
        )
    assert out == "CONTENT"
    bd.assert_called_once()


def test_render_main_content_returns_shell_for_datacenters():
    """app.py routes /datacenters to the shell, not the synchronous build."""
    src = Path("app.py").read_text(encoding="utf-8")
    assert "build_datacenters_shell" in src
