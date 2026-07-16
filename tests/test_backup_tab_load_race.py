"""Regression: Backup tab load must preserve active tab and bump ready store."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import dash


def test_load_dc_view_data_prefers_tabs_value_over_stale_store():
    """Tabs UI is source of truth — avoids Summary bounce while Backup is open."""
    from src.pages import dc_view_callbacks as mod

    fake_ctx = MagicMock()
    fake_ctx.triggered_id = "app-time-range"
    fake_page = MagicMock(name="page")
    with patch.object(mod, "ctx", fake_ctx), \
         patch.object(mod, "build_dc_view", return_value=fake_page) as p_build, \
         patch.object(mod, "_dc_context", return_value={"dc": "DC13"}):
        wrapper, loaded, _ctx, ready = mod.load_dc_view_data(
            pathname="/datacenter/DC13",
            time_range={"preset": "7d"},
            visible_sections=None,
            loaded_tabs=["summary", "backup"],
            active_tab="summary",  # stale store
            tabs_value="backup",  # real UI tab
            prev_dc_id="DC13",
            panels_ready=2,
        )

    assert "backup" in loaded
    assert p_build.call_args.kwargs["active_outer_tab"] == "backup"
    assert ready == 3
    assert wrapper is not None


def test_load_dc_view_data_dc_change_resets_to_summary():
    from src.pages import dc_view_callbacks as mod

    fake_ctx = MagicMock()
    fake_ctx.triggered_id = "url"
    with patch.object(mod, "ctx", fake_ctx), \
         patch.object(mod, "build_dc_view", return_value=MagicMock()) as p_build, \
         patch.object(mod, "_dc_context", return_value={"dc": "DC14"}):
        _wrapper, loaded, _ctx, ready = mod.load_dc_view_data(
            pathname="/datacenter/DC14",
            time_range={"preset": "7d"},
            visible_sections=None,
            loaded_tabs=["summary", "backup"],
            active_tab="backup",
            tabs_value="backup",
            prev_dc_id="DC13",
            panels_ready=5,
        )

    assert p_build.call_args.kwargs["active_outer_tab"] == "summary"
    assert loaded == sorted(mod._SUMMARY_EAGER_TABS)
    assert ready is dash.no_update
