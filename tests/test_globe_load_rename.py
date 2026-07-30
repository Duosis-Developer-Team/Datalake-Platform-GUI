import inspect

from src.pages import global_view as gv

SUMMARIES = [{"id": "DC13", "site_name": "ISTANBUL", "name": "DC13",
              "stats": {"used_cpu_pct": 60.0, "used_ram_pct": 80.0},
              "vm_count": 100, "host_count": 10}]


def test_globe_points_carry_load_not_health():
    point = gv._build_globe_data(SUMMARIES)[0]
    assert point["load"] == 70.0
    assert "health" not in point


def test_dead_plotly_globe_and_its_fabricated_ping_are_gone():
    # _create_map_figure has been unreachable since the MapLibre migration
    # (3eb55fe8) and generated random "Ping: N ms" values for a hover popup.
    assert not hasattr(gv, "_create_map_figure")
    assert not hasattr(gv, "_health_colors")
    source = inspect.getsource(gv)
    assert "random" not in source
    assert "Ping" not in source


def test_badges_say_load_not_health():
    source = inspect.getsource(gv)
    assert "% Health" not in source
    assert "% Load" in source


def test_globe_free_u_label_is_english():
    source = inspect.getsource(gv)
    assert "U boş" not in source
    assert "U free" in source
