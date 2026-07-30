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


def _find_by_id(node, target_id):
    """Recursively search a Dash component tree's `children` for the first
    component whose `id` prop equals `target_id`. Needed because both
    "Colocation" and "Load" also appear as plain text elsewhere in the
    layout, so string-searching the rendered layout can't tell a correct
    SegmentedControl from a broken one -- we need the actual component."""
    if getattr(node, "id", None) == target_id:
        return node
    children = getattr(node, "children", None)
    if children is None:
        return None
    if isinstance(children, (list, tuple)):
        for child in children:
            found = _find_by_id(child, target_id)
            if found is not None:
                return found
        return None
    return _find_by_id(children, target_id)


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
    # Different dc_id on each call so the two figures are genuinely built
    # independently rather than the second being a cache hit on the first
    # (identical fingerprints would make `before is after` trivially true and
    # this test would only fail if the `lens` default itself changed).
    occ = {"104": 47, "105": 0}
    before = fm.build_floor_map_figure(RACKS, dc_id="DC13-coloc-default", occupancy=occ)
    after = fm.build_floor_map_figure(RACKS, dc_id="DC13-coloc-explicit", occupancy=occ, lens="coloc")
    assert before is not after
    assert _fills(before) == _fills(after)


def test_figure_cache_does_not_serve_one_lens_for_the_other():
    # Same dc_id, same occupancy, same load, passed to BOTH calls -- lens is
    # the only thing that varies. Since production now fetches both payloads
    # regardless of the active lens (fix round 1 / hazard B), this is also
    # the realistic shape of the call: build_recolored_floor_map_figure
    # always supplies both. Without this isolation the test would still pass
    # even if `lens` were dropped from the fingerprint entirely, because the
    # payloads themselves would still differ between calls -- see the
    # mutation check in the report for direct confirmation this version
    # actually depends on `lens` being in the fingerprint.
    occ = {"104": 47, "105": 0}
    load = {"104": {"load_pct": 5.0, "monitored_devices": 1, "total_devices": 1},
            "105": {"load_pct": 5.0, "monitored_devices": 1, "total_devices": 1}}
    coloc_fig = fm.build_floor_map_figure(RACKS, dc_id="DC13-same", occupancy=occ, load=load, lens="coloc")
    load_fig = fm.build_floor_map_figure(RACKS, dc_id="DC13-same", occupancy=occ, load=load, lens="load")
    assert _fills(coloc_fig) != _fills(load_fig)


def test_layout_has_a_lens_switch_with_both_options():
    # build_floor_map_layout never calls _fetch_rack_occupancy -- it calls
    # api.get_dc_racks_occupancy directly (for the colocation summary strip),
    # guarded by its own try/except. Patching _fetch_rack_occupancy was inert
    # and this test previously made a real (silently-swallowed) HTTP attempt.
    with patch("src.services.api_client.get_dc_racks_occupancy",
               return_value={"racks": [], "summary": {}}):
        layout = fm.build_floor_map_layout("DC13", "DC13", RACKS)
    control = _find_by_id(layout, "floor-map-lens")
    assert control is not None
    # Assert on the control's actual options, not the rendered layout string:
    # both "Colocation" and "Load" also appear in the explanatory dmc.Text
    # next to the control, so a string search passes even if `data` were wrong.
    options = {opt["value"]: opt["label"] for opt in control.data}
    assert options == {"coloc": "Colocation", "load": "Load"}


def test_hover_is_complete_in_both_lenses():
    # Fix round 1 (B): the lens must decide colour, not amputate the tooltip.
    # Exercised through build_recolored_floor_map_figure -- the real call
    # site -- with both fetchers mocked, so a regression that reverts to
    # fetching only the active lens's payload would be caught here.
    racks = [{"id": "R1", "name": "104", "status": "active", "u_height": 47, "hall_name": "DH7"}]
    with patch("src.services.api_client.get_dc_racks", return_value={"racks": racks}), \
         patch.object(fm, "_fetch_rack_occupancy", return_value={"104": 10}), \
         patch.object(fm, "_fetch_rack_load",
                      return_value={"104": {"load_pct": 30.0, "monitored_devices": 1,
                                             "total_devices": 1}}):
        load_fig = fm.build_recolored_floor_map_figure("DC13-hover-load", lens="load")
        coloc_fig = fm.build_recolored_floor_map_figure("DC13-hover-coloc", lens="coloc")

    load_cd = load_fig.data[0].customdata[0]
    assert load_cd[9] != "—"    # Occupancy is real even though the Load lens is active

    coloc_cd = coloc_fig.data[0].customdata[0]
    assert coloc_cd[12] != "—"  # Load is real even though the Colocation lens is active


def test_fetch_rack_load_degrades_to_empty_when_the_api_fails():
    with patch("src.services.api_client.get_dc_racks_load", side_effect=RuntimeError):
        assert fm._fetch_rack_load("DC13", RACKS) == {}


def test_fetch_rack_load_keeps_only_requested_racks():
    payload = {"racks": [{"rack_name": "104", "load_pct": 50.0},
                         {"rack_name": "999", "load_pct": 90.0}]}
    with patch("src.services.api_client.get_dc_racks_load", return_value=payload):
        result = fm._fetch_rack_load("DC13", RACKS)
    assert set(result) == {"104"}
