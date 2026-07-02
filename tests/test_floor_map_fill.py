"""Floor map rack fill-coloring pure functions (sub-part 1.1).

Color by U-occupancy: blue = empty (0 devices) OR inactive/planned/closed;
active -> <50% green, 50-80% orange, >80% red; unknown occupancy -> gray.
_rack_fill_info gives occupied/total/free/pct + a Turkish status label.
"""
from src.pages import floor_map as fm


def test_color_by_fill_blue_for_non_active_status():
    assert fm._color_by_fill("inactive", 20, 47) == fm.FILL_PALETTE["blue"]
    assert fm._color_by_fill("planned", 20, 47) == fm.FILL_PALETTE["blue"]
    assert fm._color_by_fill("closed", 20, 47) == fm.FILL_PALETTE["blue"]


def test_color_by_fill_blue_for_empty_active_rack():
    assert fm._color_by_fill("active", 0, 47) == fm.FILL_PALETTE["blue"]


def test_color_by_fill_gray_when_occupancy_unknown():
    assert fm._color_by_fill("active", None, 47) == fm.FILL_PALETTE["unknown"]


def test_color_by_fill_gradient():
    assert fm._color_by_fill("active", 10, 47) == fm.FILL_PALETTE["green"]   # ~21%
    assert fm._color_by_fill("active", 30, 47) == fm.FILL_PALETTE["orange"]  # ~64%
    assert fm._color_by_fill("active", 45, 47) == fm.FILL_PALETTE["red"]     # ~96%


def test_color_by_fill_threshold_boundaries():
    # exactly 50% -> orange (>=50), exactly 80% -> orange (<=80), just over 80 -> red
    assert fm._color_by_fill("active", 24, 48) == fm.FILL_PALETTE["orange"]  # 50%
    assert fm._color_by_fill("active", 40, 50) == fm.FILL_PALETTE["orange"]  # 80%
    assert fm._color_by_fill("active", 41, 50) == fm.FILL_PALETTE["red"]     # 82%


def test_rack_fill_info_labels():
    assert fm._rack_fill_info(0, 47)["label"] == "Boş"
    assert fm._rack_fill_info(10, 47)["label"] == "Satılabilir alan var"
    assert fm._rack_fill_info(30, 47)["label"] == "Orta"
    assert fm._rack_fill_info(45, 47)["label"] == "Çok dolu"
    assert fm._rack_fill_info(None, 47)["label"] == "Bilinmiyor"


def test_rack_fill_info_free_and_pct():
    info = fm._rack_fill_info(35, 47)
    assert info["occupied"] == 35
    assert info["total"] == 47
    assert info["free"] == 12
    assert info["pct"] == 74
