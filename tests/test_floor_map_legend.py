# tests/test_floor_map_legend.py
from unittest.mock import patch

from src.pages import floor_map as fm


def test_legend_uses_fill_based_labels():
    racks = [{"id": "R1", "name": "104", "status": "active",
              "u_height": 47, "hall_name": "DH7"}]
    with patch.object(fm, "_fetch_rack_occupancy", return_value={}):
        layout = str(fm.build_floor_map_layout("DC13", "DC13", racks))
    for label in ("Fully free (sellable)", "Space available", "Moderate",
                  "Nearly full", "Closed / inactive", "Unknown"):
        assert label in layout
