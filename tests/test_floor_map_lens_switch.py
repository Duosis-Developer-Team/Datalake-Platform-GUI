# tests/test_floor_map_lens_switch.py
from unittest.mock import patch

from src.pages import floor_map as fm

RACKS = [
    {"id": "R1", "name": "104", "status": "active", "u_height": 47, "hall_name": "DH7"},
    {"id": "R2", "name": "105", "status": "active", "u_height": 47, "hall_name": "DH7"},
]


def _fills(fig):
    # fig.layout.shapes holds plotly.graph_objs.layout.Shape objects, not dicts:
    # they support item access (s["fillcolor"]) but not .get(), so use attribute
    # access here, matching the existing tests/test_floor_map_figure_fill.py.
    return {s.fillcolor for s in fig.layout.shapes if s.fillcolor}


def test_load_lens_paints_racks_with_the_load_palette():
    load = {"104": {"load_pct": 92.0, "monitored_devices": 2, "total_devices": 3},
            "105": {"load_pct": 12.0, "monitored_devices": 1, "total_devices": 4}}
    fig = fm.build_floor_map_figure(RACKS, dc_id="DC13", load=load, lens="load")
    fills = _fills(fig)
    assert fm.LOAD_PALETTE["red"][0] in fills
    assert fm.LOAD_PALETTE["green"][0] in fills


def test_load_lens_renders_unmonitored_racks_as_unmonitored_not_green():
    load = {"104": {"load_pct": None, "monitored_devices": 0, "total_devices": 5}}
    fig = fm.build_floor_map_figure(RACKS[:1], dc_id="DC13", load=load, lens="load")
    assert fm.LOAD_PALETTE["unmonitored"][0] in _fills(fig)
    assert fm.LOAD_PALETTE["green"][0] not in _fills(fig)


def test_colocation_lens_is_unchanged_by_the_lens_parameter():
    occ = {"104": 47, "105": 0}
    before = fm.build_floor_map_figure(RACKS, dc_id="DC13", occupancy=occ)
    after = fm.build_floor_map_figure(RACKS, dc_id="DC13", occupancy=occ, lens="coloc")
    assert _fills(before) == _fills(after)


def test_figure_cache_does_not_serve_one_lens_for_the_other():
    occ = {"104": 47, "105": 0}
    load = {"104": {"load_pct": 5.0, "monitored_devices": 1, "total_devices": 1},
            "105": {"load_pct": 5.0, "monitored_devices": 1, "total_devices": 1}}
    coloc_fig = fm.build_floor_map_figure(RACKS, dc_id="DC13", occupancy=occ, lens="coloc")
    load_fig = fm.build_floor_map_figure(RACKS, dc_id="DC13", load=load, lens="load")
    assert _fills(coloc_fig) != _fills(load_fig)


def test_layout_has_a_lens_switch_with_both_options():
    with patch.object(fm, "_fetch_rack_occupancy", return_value={}):
        layout = str(fm.build_floor_map_layout("DC13", "DC13", RACKS))
    assert "floor-map-lens" in layout
    assert "Colocation" in layout
    assert "Load" in layout


def test_fetch_rack_load_degrades_to_empty_when_the_api_fails():
    with patch("src.services.api_client.get_dc_racks_load", side_effect=RuntimeError):
        assert fm._fetch_rack_load("DC13", RACKS) == {}


def test_fetch_rack_load_keeps_only_requested_racks():
    payload = {"racks": [{"rack_name": "104", "load_pct": 50.0},
                         {"rack_name": "999", "load_pct": 90.0}]}
    with patch("src.services.api_client.get_dc_racks_load", return_value=payload):
        result = fm._fetch_rack_load("DC13", RACKS)
    assert set(result) == {"104"}
