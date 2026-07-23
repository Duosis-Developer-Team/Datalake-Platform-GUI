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
