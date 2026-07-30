import inspect

from src.pages import global_view as gv

SUMMARIES = [{"id": "DC13", "site_name": "ISTANBUL", "name": "DC13",
              "stats": {"used_cpu_pct": 60.0, "used_ram_pct": 80.0},
              "vm_count": 100, "host_count": 10}]


def test_globe_points_carry_load_not_health():
    point = gv._build_globe_data(SUMMARIES)[0]
    assert point["load"] == 70.0
    # `health` is a deliberate, temporary alias — NOT an oversight. The
    # committed dash_globe_component.min.js bundle still reads `.health`
    # (the source DashGlobe.react.js was updated to read `.load`, but the
    # pre-built bundle was not rebuilt). Do not delete this alias, and do
    # not "clean up" the duplicate, until the bundle has been rebuilt and
    # committed. See the matching comment in _build_globe_data.
    assert point["health"] == point["load"]


def test_dead_plotly_globe_and_its_fabricated_ping_are_gone():
    # _create_map_figure has been unreachable since the MapLibre migration
    # (3eb55fe8) and generated random "Ping: N ms" values for a hover popup,
    # presenting fabricated latency as if it were real telemetry.
    assert not hasattr(gv, "_create_map_figure")
    assert not hasattr(gv, "_health_colors")
    source = inspect.getsource(gv)
    # Bans the specific RNG call that manufactured the fake latency numbers.
    # A bare "random" substring ban is too broad — it would false-positive on
    # any legitimate future identifier/docstring containing that substring
    # (e.g. "randomize", "randomised"), inviting someone to just delete the
    # assertion instead of fixing their code.
    assert "random.randint" not in source
    # Bans the fabricated hover row's literal text, case-insensitively. A
    # case-sensitive "Ping" ban gives false confidence: a reintroduced fake
    # value written as lowercase "ping" would sail straight through while
    # this test stayed green — exactly the regression this guards against.
    lowered_source = source.lower()
    assert "ping:" not in lowered_source
    assert "active route" not in lowered_source


def test_badges_say_load_not_health():
    source = inspect.getsource(gv)
    assert "% Health" not in source
    assert "% Load" in source


def test_globe_free_u_label_is_english():
    source = inspect.getsource(gv)
    assert "U boş" not in source
    assert "U free" in source
