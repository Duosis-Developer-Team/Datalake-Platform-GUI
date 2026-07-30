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
    assert "35/47U" in row[9]      # occupancy string
    assert row[10] == "12U"         # free (sellable)
    assert row[11] == "Moderate"    # label (74% -> orange/Moderate)


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


def test_empty_occupancy_dict_is_not_a_cache_hit_for_none_occupancy():
    # occupancy=None (phase 1, not fetched yet) and occupancy={} (phase 2,
    # the bulk endpoint responded but had nothing for these racks -- a
    # documented normal condition, not just an outage) used to fingerprint
    # identically ("" for both, since the cache key built each field with
    # plain truthiness). Same dc_id on both calls on purpose: that is exactly
    # the collision -- a phase-1 figure served back as the phase-2 result,
    # painting the Colocation lens by NetBox *status* under the colocation
    # legend instead of the near-white "unknown" fill _color_by_fill defines
    # for this case.
    racks = _racks()
    fig_none = fm.build_floor_map_figure(racks, dc_id="DC13-fp-collision", occupancy=None)
    fig_empty = fm.build_floor_map_figure(racks, dc_id="DC13-fp-collision", occupancy={})

    assert fig_none is not fig_empty

    fills_none = {s.fillcolor for s in fig_none.layout.shapes if s.fillcolor}
    fills_empty = {s.fillcolor for s in fig_empty.layout.shapes if s.fillcolor}
    assert fills_none != fills_empty

    assert fm.STATUS_FILL["active"] in fills_none        # phase 1: status colour
    assert fm.FILL_PALETTE["unknown"][0] in fills_empty  # phase 2, empty: unknown fill
    assert fm.FILL_PALETTE["unknown"][0] not in fills_none
    assert fm.STATUS_FILL["active"] not in fills_empty
