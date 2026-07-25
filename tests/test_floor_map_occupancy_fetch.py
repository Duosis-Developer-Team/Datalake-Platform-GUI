"""Floor map 2.0: _fetch_rack_occupancy now sources occupancy from the bulk
colocation occupancy endpoint (real used-U, one call) instead of fanning out
get_rack_devices per rack and counting devices (1-U each). Racks absent from
the bulk response are omitted (unknown -> rendered gray).
"""
from unittest.mock import patch

from src.pages import floor_map as fm


def test_fetch_rack_occupancy_returns_real_used_u():
    racks = [{"name": "104"}, {"name": "105"}]
    bulk = {"racks": [
        {"rack_name": "104", "used_u": 12, "capacity_u": 47},
        {"rack_name": "105", "used_u": 0, "capacity_u": 47},
    ], "summary": {}}

    with patch("src.services.api_client.get_dc_racks_occupancy", return_value=bulk) as m:
        occ = fm._fetch_rack_occupancy("DC13", racks)

    m.assert_called_once_with("DC13")
    assert occ["104"] == 12
    assert occ["105"] == 0


def test_fetch_rack_occupancy_omits_rack_missing_from_bulk_response():
    racks = [{"name": "104"}]

    with patch("src.services.api_client.get_dc_racks_occupancy", return_value={"racks": [], "summary": {}}):
        occ = fm._fetch_rack_occupancy("DC13", racks)

    assert "104" not in occ  # missing -> omitted so it renders as unknown (gray)


def test_fetch_rack_occupancy_skips_nameless_racks():
    with patch("src.services.api_client.get_dc_racks_occupancy") as m:
        occ = fm._fetch_rack_occupancy("DC13", [{"name": ""}, {"id": "x"}])
    assert occ == {}
    m.assert_not_called()


def test_floor_map_layout_has_colocation_summary_strip():
    bulk = {"racks": [], "summary": {
        "total_u": 100, "used_u": 60, "free_u": 40, "rack_count": 3,
        "external_u": 20, "internal_u": 25, "untagged_u": 15, "external_customer_count": 2,
    }}
    with patch("src.services.api_client.get_dc_racks_occupancy", return_value=bulk):
        layout = fm.build_floor_map_layout("DC13", "DC13", racks=[])
    text = str(layout)
    assert "External 20U (2 customers)" in text
    assert "Used U" in text
