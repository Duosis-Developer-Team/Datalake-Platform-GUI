"""Floor map 1.2: occupancy threaded into build_floor_map_figure. With an
occupancy map the racks are colored by fill and the hover carries occupancy
fields; without it (phase 1) racks keep the status color and hover shows "—".
"""
from src.pages import floor_map as fm


def _racks():
    return [{"id": "R1", "name": "104", "status": "active", "u_height": 47, "hall_name": "DH7"}]


def test_figure_hover_has_occupancy_fields_when_occupancy_given():
    fig = fm.build_floor_map_figure(_racks(), dc_id="DC13-a", occupancy={"104": 35})
    row = fig.data[0].customdata[0]
    assert len(row) >= 12
    assert "35/47U" in row[9]      # doluluk string
    assert row[10] == "12U"         # free (sellable)
    assert row[11] == "Orta"        # label (74% -> orange/Orta)


def test_figure_uses_fill_color_for_full_active_rack():
    fig = fm.build_floor_map_figure(_racks(), dc_id="DC13-b", occupancy={"104": 45})  # ~96% -> red
    fills = [s.fillcolor for s in fig.layout.shapes]
    assert fm.FILL_PALETTE["red"][0] in fills


def test_figure_phase1_keeps_status_color_and_dash_hover():
    fig = fm.build_floor_map_figure(_racks(), dc_id="DC13-c")  # occupancy=None (phase 1)
    fills = [s.fillcolor for s in fig.layout.shapes]
    assert fm.STATUS_FILL["active"] in fills   # active status color, not fill-red
    assert fm.FILL_PALETTE["red"][0] not in fills
    assert fig.data[0].customdata[0][9] == "—"  # occupancy unknown in phase 1
