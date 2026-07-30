# tests/test_floor_map_english_copy.py
"""No Turkish copy leaks into the floor map's user-facing surfaces.

Split into two tests because the copy is produced by two independent
surfaces:

  - build_floor_map_layout (src/pages/floor_map.py) renders the map, the
    legend, and (when show_colocation=True) the customer/potential panel.
  - show_rack_detail (app.py) renders the rack-click side panel, including
    the "Dedicated:" external-tenant badge, entirely separately from the
    layout above.

"Dedike" is only ever rendered by show_rack_detail. Asserting its absence
from build_floor_map_layout's output would pass unconditionally -- the word
can never appear there regardless of whether app.py's badge is translated --
so that assertion would prove nothing about the thing it claims to guard.
Each word below is checked against the surface that can actually render it.
"""
from unittest.mock import patch

from src.pages import floor_map as fm

# Words the map layout (figure hover labels, legend, customer panel) could
# render if _rack_fill_info or the legend/panel copy reverted to Turkish.
# Each contains a Turkish-only character (ç/ş/ı) or is checked case-sensitive
# against multi-word phrases, so none of these can match an English string
# that legitimately appears (component ids, CSS classes, hex colours, icon
# names are all plain ASCII identifiers).
LAYOUT_TURKISH = ("Tamamen boş", "Satılabilir alan var", "Çok dolu",
                   "Kapalı / Pasif", "Bilinmiyor", "Doluluk", "boş", "Orta")


def test_rack_fill_info_labels_are_english():
    assert fm._rack_fill_info(None, 47)["label"] == "Unknown"
    assert fm._rack_fill_info(0, 47)["label"] == "Fully free"
    assert fm._rack_fill_info(46, 47)["label"] == "Nearly full"
    assert fm._rack_fill_info(30, 47)["label"] == "Moderate"
    assert fm._rack_fill_info(5, 47)["label"] == "Space available"


def test_floor_map_layout_carries_no_turkish_copy():
    # show_colocation=True so the customer panel (the other place copy could
    # hide) is actually rendered into the string being searched, not skipped.
    racks = [{"id": "R1", "name": "104", "status": "active",
              "u_height": 47, "hall_name": "DH7"}]
    coloc = {"allocation": [{"customer": "BOYNER", "rack_count": 1,
                              "allocated_u": 47, "used_u": 10,
                              "racks": ["104"]}]}
    with patch("src.services.api_client.get_dc_racks_occupancy",
               return_value={"racks": [], "summary": {}}), \
         patch("src.services.api_client.get_colocation", return_value=coloc):
        layout = str(fm.build_floor_map_layout("DC13", "DC13", racks,
                                                show_colocation=True))
    for word in LAYOUT_TURKISH:
        assert word not in layout


def test_rack_detail_panel_carries_no_turkish_copy():
    # "Dedike" lives in app.py's show_rack_detail, a surface
    # build_floor_map_layout never touches -- exercise it directly instead of
    # asserting its absence somewhere it could never appear.
    import app as app_module

    customdata = ["R1", "104", "active", 47, "220V", "DH7", "Cabinet", "SN1"]
    click_data = {"points": [{"customdata": customdata}]}
    with patch.object(app_module, "api") as mock_api, \
         patch.object(app_module, "_resolve_show_colocation", return_value=True):
        mock_api.get_rack_devices.return_value = {"devices": []}
        mock_api.get_dc_racks_occupancy.return_value = {
            "racks": [{"rack_name": "104", "tenants": ["BOYNER"]}]
        }
        result = app_module.show_rack_detail(click_data, {"dc_id": "DC13"})

    txt = str(result)
    # Positive control: the badge itself did render (with its English label),
    # so the absence check below is meaningful rather than the panel simply
    # never reaching the tenant-badge code path at all.
    assert "Dedicated:" in txt
    assert "Dedike" not in txt
