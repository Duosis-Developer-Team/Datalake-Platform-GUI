"""Floor map occupancy now comes from the bulk /racks/occupancy endpoint (real
used-U), one call, instead of per-rack device-count fan-out."""
from unittest.mock import patch

from src.pages import floor_map as fm


def test_fetch_rack_occupancy_uses_bulk_endpoint():
    racks = [{"name": "116"}, {"name": "209"}]
    bulk = {"racks": [
        {"rack_name": "116", "used_u": 35, "capacity_u": 47, "free_u": 12},
        {"rack_name": "209", "used_u": 27, "capacity_u": 47, "free_u": 20},
    ], "summary": {}}
    with patch("src.services.api_client.get_dc_racks_occupancy", return_value=bulk) as m:
        occ = fm._fetch_rack_occupancy("DC13", racks)
    m.assert_called_once_with("DC13")
    assert occ["116"] == 35
    assert occ["209"] == 27


def test_fetch_rack_occupancy_omits_missing_racks():
    racks = [{"name": "116"}, {"name": "999"}]
    bulk = {"racks": [{"rack_name": "116", "used_u": 35, "capacity_u": 47}], "summary": {}}
    with patch("src.services.api_client.get_dc_racks_occupancy", return_value=bulk):
        occ = fm._fetch_rack_occupancy("DC13", racks)
    assert occ["116"] == 35
    assert "999" not in occ  # unknown -> rendered gray


def test_fetch_rack_occupancy_empty_on_backend_failure():
    with patch("src.services.api_client.get_dc_racks_occupancy", return_value={"racks": [], "summary": {}}):
        occ = fm._fetch_rack_occupancy("DC13", [{"name": "116"}])
    assert occ == {}
