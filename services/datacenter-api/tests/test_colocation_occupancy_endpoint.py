"""Bulk occupancy endpoint delegates to DatabaseService.get_dc_racks_occupancy."""


def test_occupancy_endpoint_delegates(client, mock_db):
    payload = {
        "racks": [{"rack_name": "116", "capacity_u": 47, "used_u": 35, "free_u": 12, "tenants": ["Boyner"]}],
        "summary": {"total_u": 47, "used_u": 35, "free_u": 12, "rack_count": 1},
    }
    mock_db.get_dc_racks_occupancy.return_value = payload
    r = client.get("/api/v1/datacenters/DC13/racks/occupancy")
    assert r.status_code == 200
    assert r.json() == payload
    mock_db.get_dc_racks_occupancy.assert_called_once_with("DC13")
