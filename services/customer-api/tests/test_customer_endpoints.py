def test_health_returns_ok(mock_customer_service):
    client, _ = mock_customer_service
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ready_returns_ready(mock_customer_service):
    client, _ = mock_customer_service
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_list_customers_returns_list(mock_customer_service):
    client, _ = mock_customer_service
    resp = client.get("/api/v1/customers")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert "Boyner" in resp.json()


def test_customer_resources_returns_totals(mock_customer_service):
    client, _ = mock_customer_service
    resp = client.get("/api/v1/customers/Boyner/resources?preset=7d")
    assert resp.status_code == 200
    data = resp.json()
    assert "totals" in data
    assert "assets" in data


def test_customer_resources_has_vms_total(mock_customer_service):
    client, _ = mock_customer_service
    resp = client.get("/api/v1/customers/Boyner/resources?preset=7d")
    assert resp.status_code == 200
    assert resp.json()["totals"]["vms_total"] == 10


def test_customer_resources_has_intel_and_power(mock_customer_service):
    client, _ = mock_customer_service
    resp = client.get("/api/v1/customers/Boyner/resources")
    assert resp.status_code == 200
    assets = resp.json()["assets"]
    assert "intel" in assets
    assert "power" in assets


def test_customer_resources_has_backup_section(mock_customer_service):
    client, _ = mock_customer_service
    resp = client.get("/api/v1/customers/Boyner/resources")
    assert resp.status_code == 200
    assets = resp.json()["assets"]
    assert "backup" in assets
    assert "veeam" in assets["backup"]
    assert "zerto" in assets["backup"]


def test_customer_resources_with_preset_30d(mock_customer_service):
    client, svc = mock_customer_service
    resp = client.get("/api/v1/customers/Boyner/resources?preset=30d")
    assert resp.status_code == 200
    svc.get_customer_resources.assert_called()


def test_customer_resources_with_custom_range(mock_customer_service):
    client, _ = mock_customer_service
    resp = client.get("/api/v1/customers/Boyner/resources?start=2026-01-01&end=2026-01-31")
    assert resp.status_code == 200
    data = resp.json()
    assert "totals" in data
