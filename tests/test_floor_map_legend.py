# tests/test_floor_map_legend.py
from unittest.mock import patch

from src.pages import floor_map as fm


def test_legend_uses_fill_based_labels():
    # build_floor_map_layout never calls _fetch_rack_occupancy -- it calls
    # api.get_dc_racks_occupancy directly (for the colocation summary strip),
    # guarded by its own try/except. Patching _fetch_rack_occupancy was inert
    # and this test previously made a real (silently-swallowed) HTTP attempt.
    # See tests/test_floor_map_lens_switch.py::test_layout_has_a_lens_switch_with_both_options.
    racks = [{"id": "R1", "name": "104", "status": "active",
              "u_height": 47, "hall_name": "DH7"}]
    with patch("src.services.api_client.get_dc_racks_occupancy",
               return_value={"racks": [], "summary": {}}):
        layout = str(fm.build_floor_map_layout("DC13", "DC13", racks))
    for label in ("Fully free (sellable)", "Space available", "Moderate",
                  "Nearly full", "Closed / inactive", "Unknown"):
        assert label in layout
