def test_licensed_os_summary_endpoint(client, mock_db):
    mock_db.get_licensed_os_summary.return_value = {
        "families": {"rhel": 3, "suse": 1, "windows": 5, "free": 10, "unknown": 2},
        "total": 21, "unknown_samples": ["Other Linux (64-bit)"],
    }
    r = client.get("/api/v1/licensed-os/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["families"]["windows"] == 5
    assert body["total"] == 21
    mock_db.get_licensed_os_summary.assert_called_once()


def test_licensed_os_summary_customer_routes_to_customer_method(client, mock_db):
    mock_db.get_licensed_os_for_customer.return_value = {
        "families": {"rhel": 2, "suse": 0, "windows": 1, "free": 4, "unknown": 0},
        "total": 7, "unknown_samples": [],
    }
    r = client.get("/api/v1/licensed-os/summary?customer=Boyner")
    assert r.status_code == 200
    assert r.json()["families"]["rhel"] == 2
    mock_db.get_licensed_os_for_customer.assert_called_once()
