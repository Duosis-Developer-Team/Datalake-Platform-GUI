# tests/test_floor_map_load_lens.py
from src.pages import floor_map as fm


def test_unmonitored_rack_is_not_coloured_as_idle():
    # A rack with no metrics must never read as prime free capacity.
    assert fm._color_by_load("active", None) == fm.LOAD_PALETTE["unmonitored"]


def test_load_thresholds_match_the_colocation_lens_steps():
    assert fm._color_by_load("active", 10.0) == fm.LOAD_PALETTE["green"]
    assert fm._color_by_load("active", 49.9) == fm.LOAD_PALETTE["green"]
    assert fm._color_by_load("active", 50.0) == fm.LOAD_PALETTE["orange"]
    assert fm._color_by_load("active", 80.0) == fm.LOAD_PALETTE["orange"]
    assert fm._color_by_load("active", 80.1) == fm.LOAD_PALETTE["red"]


def test_closed_beats_load():
    # Mirrors _color_by_fill's closed-before-empty ordering.
    for status in ("inactive", "planned", "closed"):
        assert fm._color_by_load(status, 95.0) == fm.LOAD_PALETTE["closed"]


def test_load_palette_has_no_turquoise_idle_step():
    # A 0% reading is far more often a silent collector than idle hardware.
    assert "empty" not in fm.LOAD_PALETTE
    assert fm._color_by_load("active", 0.0) == fm.LOAD_PALETTE["green"]


def test_legends_are_english_and_lens_specific():
    coloc = str(fm.build_lens_legend("coloc"))
    load = str(fm.build_lens_legend("load"))
    assert "Fully free (sellable)" in coloc
    assert "Closed / inactive" in coloc
    assert "Not monitored" in load
    assert "Heavy load" in load
    assert "Fully free (sellable)" not in load
    for text in (coloc, load):
        for turkish in ("Tamamen boş", "Çok dolu", "Bilinmiyor", "Kapalı"):
            assert turkish not in text
