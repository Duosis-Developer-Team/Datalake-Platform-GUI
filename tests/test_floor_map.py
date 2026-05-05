"""Tests for floor_map figure cache and batch-build correctness."""

import importlib

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rack(name, status="active", hall="Hall A", facility_id=None):
    return {
        "id": name,
        "name": name,
        "status": status,
        "u_height": 42,
        "hall_name": hall,
        "facility_id": facility_id or name,
        "last_observed": "2026-04-30",
        "kabin_enerji": "5kW",
        "rack_type": "Standard",
        "serial": "SN-001",
    }


def _reload_floor_map():
    """Reload module so the TTLCache starts empty for each test."""
    import src.pages.floor_map as fm
    importlib.reload(fm)
    return fm


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------

def test_figure_cache_hit_on_same_racks():
    fm = _reload_floor_map()
    racks = [_make_rack(f"R{i:02d}") for i in range(5)]
    fig1 = fm.build_floor_map_figure(racks, dc_id="DC11")
    fig2 = fm.build_floor_map_figure(racks, dc_id="DC11")
    assert fig1 is fig2, "Second call with identical racks must return cached figure object"


def test_figure_cache_miss_on_different_dc_id():
    fm = _reload_floor_map()
    racks = [_make_rack(f"R{i:02d}") for i in range(3)]
    fig1 = fm.build_floor_map_figure(racks, dc_id="DC11")
    fig2 = fm.build_floor_map_figure(racks, dc_id="DC13")
    assert fig1 is not fig2, "Different dc_id must produce distinct figures"


def test_figure_cache_miss_on_status_change():
    fm = _reload_floor_map()
    racks_a = [_make_rack("R01", status="active")]
    racks_b = [_make_rack("R01", status="inactive")]
    fig_a = fm.build_floor_map_figure(racks_a, dc_id="DC11")
    fig_b = fm.build_floor_map_figure(racks_b, dc_id="DC11")
    assert fig_a is not fig_b, "Status change must bust the cache"


def test_figure_cache_miss_on_rack_count_change():
    fm = _reload_floor_map()
    racks_3 = [_make_rack(f"R{i:02d}") for i in range(3)]
    racks_4 = [_make_rack(f"R{i:02d}") for i in range(4)]
    fig3 = fm.build_floor_map_figure(racks_3, dc_id="DC11")
    fig4 = fm.build_floor_map_figure(racks_4, dc_id="DC11")
    assert fig3 is not fig4, "Adding a rack must bust the cache"


# ---------------------------------------------------------------------------
# Figure correctness tests
# ---------------------------------------------------------------------------

def test_figure_has_single_hover_trace():
    fm = _reload_floor_map()
    racks = [_make_rack(f"R{i:02d}") for i in range(5)]
    fig = fm.build_floor_map_figure(racks, dc_id="DC11")
    assert len(fig.data) == 1, "All rack hover points must be in a single Scatter trace"


def test_hover_trace_has_correct_point_count():
    fm = _reload_floor_map()
    n = 7
    racks = [_make_rack(f"R{i:02d}") for i in range(n)]
    fig = fm.build_floor_map_figure(racks, dc_id="DC11")
    trace = fig.data[0]
    assert len(trace.x) == n
    assert len(trace.y) == n
    assert len(trace.customdata) == n


def test_customdata_fields_match_click_handler_expectations():
    """customdata row must be [rid, name, status, u, pwr, hall, type, serial, dc_id]."""
    fm = _reload_floor_map()
    rack = _make_rack("RACK-01", status="active", hall="Hall B")
    fig = fm.build_floor_map_figure([rack], dc_id="DC11")
    cd = list(fig.data[0].customdata[0])
    # Indices expected by show_rack_detail: 0=id, 1=name, 2=status, 3=u, 4=pwr, 5=hall, 6=type, 7=serial
    assert cd[0] == "RACK-01"   # rid
    assert cd[1] == "RACK-01"   # name
    assert cd[2] == "active"    # status
    assert cd[3] == 42          # u_height
    assert cd[5] == "Hall B"    # hall


def test_shapes_count_is_proportional_to_rack_count():
    fm = _reload_floor_map()
    n = 6
    racks = [_make_rack(f"R{i:02d}") for i in range(n)]
    fig = fm.build_floor_map_figure(racks, dc_id="DC11")
    # 5 shapes per rack + 2 floor shapes + 3 hall shapes + optional aisle = at least 5*n + 5
    assert len(fig.layout.shapes) >= 5 * n + 5


def test_empty_racks_returns_figure_without_traces():
    fm = _reload_floor_map()
    fig = fm.build_floor_map_figure([], dc_id="DC11")
    assert len(fig.data) == 0
    # Annotation "No rack data available" should be present
    assert any("No rack data" in (a.text or "") for a in fig.layout.annotations)


def test_multi_hall_figure_has_one_trace_still():
    fm = _reload_floor_map()
    racks = (
        [_make_rack(f"A{i:02d}", hall="Hall A") for i in range(4)] +
        [_make_rack(f"B{i:02d}", hall="Hall B") for i in range(4)]
    )
    fig = fm.build_floor_map_figure(racks, dc_id="DC11")
    assert len(fig.data) == 1, "Multi-hall must still produce a single hover trace"
    assert len(fig.data[0].x) == 8
