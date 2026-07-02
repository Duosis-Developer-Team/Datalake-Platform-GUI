"""Floor map 1.4: phase-2 recolor. build_recolored_floor_map_figure(dc_id)
fetches racks + per-rack occupancy and returns the fill-colored figure that the
phase-2 callback swaps into the graph after the fast status-colored first paint.
"""
from unittest.mock import patch

from src.pages import floor_map as fm


def test_build_recolored_figure_colors_by_fill():
    racks = [{"id": "R1", "name": "104", "status": "active", "u_height": 47, "hall_name": "DH7"}]
    with patch("src.services.api_client.get_dc_racks", return_value={"racks": racks}), \
         patch.object(fm, "_fetch_rack_occupancy", return_value={"104": 45}):  # ~96% -> red
        fig = fm.build_recolored_floor_map_figure("DC13-r")
    fills = [s.fillcolor for s in fig.layout.shapes]
    assert fm.FILL_PALETTE["red"][0] in fills


def test_build_recolored_figure_none_when_no_racks():
    with patch("src.services.api_client.get_dc_racks", return_value={"racks": []}):
        assert fm.build_recolored_floor_map_figure("DC13-empty") is None
