# tests/test_floor_map_highlight.py
from unittest.mock import patch

import dash

from src.pages import floor_map as fm

ALLOCATION = [
    {"customer": "BOYNER", "rack_count": 2, "allocated_u": 94,
     "used_u": 60, "racks": ["104", "105"]},
    {"customer": "AKSIGORTA", "rack_count": 1, "allocated_u": 47,
     "used_u": 12, "racks": ["210"]},
]


def test_selecting_a_customer_returns_exactly_their_racks():
    result = fm.resolve_customer_highlight("BOYNER", ALLOCATION, current=None)
    assert result == {"customer": "BOYNER", "racks": ["104", "105"]}


def test_reselecting_the_same_customer_clears_the_highlight():
    current = {"customer": "BOYNER", "racks": ["104", "105"]}
    assert fm.resolve_customer_highlight("BOYNER", ALLOCATION, current=current) is None


def test_switching_customers_replaces_rather_than_merges():
    current = {"customer": "BOYNER", "racks": ["104", "105"]}
    result = fm.resolve_customer_highlight("AKSIGORTA", ALLOCATION, current=current)
    assert result == {"customer": "AKSIGORTA", "racks": ["210"]}


def test_unknown_customer_clears_rather_than_highlighting_everything():
    assert fm.resolve_customer_highlight("NOBODY", ALLOCATION, current=None) is None


def test_customer_with_no_racks_clears():
    alloc = [{"customer": "GHOST", "rack_count": 0, "allocated_u": 0,
              "used_u": 0, "racks": []}]
    assert fm.resolve_customer_highlight("GHOST", alloc, current=None) is None


def test_highlighted_racks_get_an_outline_on_the_figure():
    # fig.layout.shapes holds plotly.graph_objs.layout.Shape objects, not
    # dicts: they support attribute access (s.line.color) but not .get(),
    # matching the existing tests/test_floor_map_figure_fill.py and
    # tests/test_floor_map_lens_switch.py.
    racks = [{"id": "R1", "name": "104", "status": "active",
              "u_height": 47, "hall_name": "DH7"}]
    fig = fm.build_floor_map_figure(racks, dc_id="DC13", occupancy={"104": 20},
                                    highlight={"104"})
    outlines = [s for s in fig.layout.shapes
                if s.line and s.line.color == "#4318FF"]
    assert len(outlines) == 1


# ── app.py: select_colocation_customer callback ─────────────────────────────
#
# Fires on a pattern-matching Input over every customer row. Dash delivers
# which id triggered via callback_context.triggered_id; fake that context the
# same way tests/test_hmdl_env_card_click.py does for hmdl_callbacks.ctx.

class _FakeCtx:
    def __init__(self, triggered_id):
        self.triggered_id = triggered_id


def _click_row(customer):
    return _FakeCtx({"type": "fm-coloc-customer-row", "index": customer})


def test_select_colocation_customer_highlights_the_clicked_rows_racks():
    import app as app_module

    with patch.object(app_module, "api") as mock_api, \
         patch.object(app_module, "_resolve_show_colocation", return_value=True), \
         patch.object(dash, "callback_context", _click_row("BOYNER")):
        mock_api.get_colocation.return_value = {"allocation": ALLOCATION}
        result = app_module.select_colocation_customer(
            [1], None, {"dc_id": "DC13"})

    assert result == {"customer": "BOYNER", "racks": ["104", "105"]}
    mock_api.get_colocation.assert_called_once_with("DC13")


def test_select_colocation_customer_no_clicks_yields_no_update():
    import app as app_module

    with patch.object(app_module, "api") as mock_api, \
         patch.object(app_module, "_resolve_show_colocation", return_value=True):
        result = app_module.select_colocation_customer(
            [0, 0], None, {"dc_id": "DC13"})

    assert result is dash.no_update
    mock_api.get_colocation.assert_not_called()


# ── Permission gating: select_colocation_customer ───────────────────────────
#
# This callback is reachable via a pattern-matching Input regardless of
# whether the row was ever rendered for this user -- a crafted request can
# fire it directly. It must re-check _resolve_show_colocation() itself rather
# than trusting that an unentitled user was never shown the row.

def test_select_colocation_customer_denied_user_gets_no_update_and_no_fetch():
    import app as app_module

    with patch.object(app_module, "api") as mock_api, \
         patch.object(app_module, "_resolve_show_colocation", return_value=False), \
         patch.object(dash, "callback_context", _click_row("BOYNER")):
        result = app_module.select_colocation_customer(
            [1], None, {"dc_id": "DC13"})

    assert result is dash.no_update
    mock_api.get_colocation.assert_not_called()


# ── app.py: show_rack_detail's "Back to customers" button ───────────────────
#
# The button must only render for entitled callers -- otherwise an
# unentitled user could click it and reach back_to_colocation_panel, which
# renders the very panel Task 6 hid.

def _rack_click_data(rack_name="104"):
    customdata = ["R1", rack_name, "active", 47, "220V", "DH7", "Cabinet", "SN1"]
    return {"points": [{"customdata": customdata}]}


def test_show_rack_detail_omits_back_button_when_resolver_denies():
    import app as app_module

    with patch.object(app_module, "api") as mock_api, \
         patch.object(app_module, "_resolve_show_colocation", return_value=False):
        mock_api.get_rack_devices.return_value = {"devices": []}
        mock_api.get_dc_racks_occupancy.return_value = {"racks": []}
        result = app_module.show_rack_detail(_rack_click_data(), {"dc_id": "DC13"})

    assert "fm-back-to-customers" not in str(result)


def test_show_rack_detail_includes_back_button_when_resolver_allows():
    import app as app_module

    with patch.object(app_module, "api") as mock_api, \
         patch.object(app_module, "_resolve_show_colocation", return_value=True):
        mock_api.get_rack_devices.return_value = {"devices": []}
        mock_api.get_dc_racks_occupancy.return_value = {"racks": []}
        result = app_module.show_rack_detail(_rack_click_data(), {"dc_id": "DC13"})

    assert "fm-back-to-customers" in str(result)


# ── Permission gating: back_to_colocation_panel ─────────────────────────────
#
# Even if a denied user's browser never rendered the button, a crafted
# n_clicks event on "fm-back-to-customers" would still reach this callback.
# It must re-check the resolver itself before building the customer panel.

def test_back_to_colocation_panel_denied_user_gets_no_update_and_no_fetch():
    import app as app_module

    with patch.object(app_module, "api") as mock_api, \
         patch.object(app_module, "_resolve_show_colocation", return_value=False):
        result = app_module.back_to_colocation_panel(1, {"dc_id": "DC13"})

    assert result is dash.no_update
    mock_api.get_colocation.assert_not_called()


def test_back_to_colocation_panel_allowed_user_gets_the_panel():
    import app as app_module

    with patch.object(app_module, "api") as mock_api, \
         patch.object(app_module, "_resolve_show_colocation", return_value=True):
        mock_api.get_colocation.return_value = {"allocation": ALLOCATION}
        result = app_module.back_to_colocation_panel(1, {"dc_id": "DC13"})

    assert "fm-coloc-panel" in str(result)
    mock_api.get_colocation.assert_called_once_with("DC13")
