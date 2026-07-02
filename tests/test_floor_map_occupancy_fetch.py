"""Floor map 1.3: _fetch_rack_occupancy fetches each rack's device list (in
parallel, shared-cached via get_rack_devices) and returns {rack_name ->
occupied_u} = count of devices with a position. Racks whose fetch fails are
omitted (unknown -> rendered gray).
"""
from unittest.mock import patch

from src.pages import floor_map as fm


def test_fetch_rack_occupancy_counts_positions():
    racks = [{"name": "104"}, {"name": "105"}]

    def fake(dc, name):
        if name == "104":
            return {"devices": [{"position": 38}, {"position": 40}, {"position": None}]}
        return {"devices": []}

    with patch("src.services.api_client.get_rack_devices", side_effect=fake):
        occ = fm._fetch_rack_occupancy("DC13", racks)

    assert occ["104"] == 2  # two devices with a position
    assert occ["105"] == 0


def test_fetch_rack_occupancy_omits_failed_rack():
    racks = [{"name": "104"}]

    def boom(dc, name):
        raise RuntimeError("backend down")

    with patch("src.services.api_client.get_rack_devices", side_effect=boom):
        occ = fm._fetch_rack_occupancy("DC13", racks)

    assert "104" not in occ  # failed -> omitted so it renders as unknown (gray)


def test_fetch_rack_occupancy_skips_nameless_racks():
    with patch("src.services.api_client.get_rack_devices", return_value={"devices": []}) as m:
        occ = fm._fetch_rack_occupancy("DC13", [{"name": ""}, {"id": "x"}])
    assert occ == {}
    m.assert_not_called()
