"""Floor map 1.5: the legend reflects the fill-based coloring, not raw status."""
from src.pages import floor_map as fm


def test_legend_uses_fill_based_labels():
    racks = [{"id": "R1", "name": "104", "status": "active", "u_height": 47, "hall_name": "DH7"}]
    layout = fm.build_floor_map_layout("DC13", "DC13", racks)
    txt = str(layout)
    assert "Satılabilir alan var" in txt   # green
    assert "Orta" in txt                    # orange
    assert "Çok dolu" in txt                # red
    assert "Boş / Kapalı" in txt            # blue
    assert "Bilinmiyor" in txt              # gray
