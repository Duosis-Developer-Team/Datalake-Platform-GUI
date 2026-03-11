import pytest


def test_health_endpoint_returns_200_with_ok_status(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "db_pool" in body


def test_ready_endpoint_returns_200_with_ready_status(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_datacenters_summary_returns_200_and_non_empty_list(client):
    r = client.get("/api/v1/datacenters/summary")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["id"] == "DC11"


def test_datacenters_summary_with_time_range_passes_start_end_to_db(client, mock_db):
    r = client.get("/api/v1/datacenters/summary?start=2026-03-01&end=2026-03-07")
    assert r.status_code == 200
    mock_db.get_all_datacenters_summary.assert_called_once_with(
        {"start": "2026-03-01", "end": "2026-03-07"}
    )


def test_datacenters_summary_without_time_range_passes_none_to_db(client, mock_db):
    r = client.get("/api/v1/datacenters/summary")
    assert r.status_code == 200
    mock_db.get_all_datacenters_summary.assert_called_once_with(None)


def test_datacenter_detail_returns_200_with_meta_and_intel_fields(client):
    r = client.get("/api/v1/datacenters/DC11")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["name"] == "DC11"
    assert body["meta"]["location"] == "Istanbul"
    assert "intel" in body
    assert "power" in body
    assert "energy" in body
    assert "platforms" in body


def test_datacenter_detail_passes_dc_code_and_time_range_to_db(client, mock_db):
    r = client.get("/api/v1/datacenters/DC12?start=2026-03-01&end=2026-03-07")
    assert r.status_code == 200
    mock_db.get_dc_details.assert_called_once_with(
        "DC12", {"start": "2026-03-01", "end": "2026-03-07"}
    )


def test_dashboard_overview_returns_200_with_all_top_level_fields(client):
    r = client.get("/api/v1/dashboard/overview")
    assert r.status_code == 200
    body = r.json()
    assert "overview" in body
    assert "platforms" in body
    assert "energy_breakdown" in body


def test_dashboard_overview_overview_section_contains_dc_count_and_totals(client):
    r = client.get("/api/v1/dashboard/overview")
    body = r.json()
    overview = body["overview"]
    assert overview["dc_count"] == 1
    assert overview["total_hosts"] == 10
    assert overview["total_vms"] == 50


def test_dashboard_overview_platforms_contain_nutanix_vmware_ibm(client):
    r = client.get("/api/v1/dashboard/overview")
    platforms = r.json()["platforms"]
    assert "nutanix" in platforms
    assert "vmware" in platforms
    assert "ibm" in platforms


def test_customers_list_returns_200_and_contains_boyner(client):
    r = client.get("/api/v1/customers")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert "Boyner" in body


def test_customer_resources_returns_200_with_totals_and_assets(client):
    r = client.get("/api/v1/customers/Boyner/resources")
    assert r.status_code == 200
    body = r.json()
    assert "totals" in body
    assert "assets" in body


def test_customer_resources_passes_name_and_time_range_to_db(client, mock_db):
    r = client.get("/api/v1/customers/Boyner/resources?start=2026-02-01&end=2026-03-01")
    assert r.status_code == 200
    mock_db.get_customer_resources.assert_called_once_with(
        "Boyner", {"start": "2026-02-01", "end": "2026-03-01"}
    )


def test_query_endpoint_returns_200_with_result_type_value(client):
    r = client.get("/api/v1/queries/nutanix_host_count?params=DC11")
    assert r.status_code == 200
    body = r.json()
    assert body["result_type"] == "value"
    assert body["value"] == 42


def test_query_endpoint_passes_key_and_params_to_db(client, mock_db):
    r = client.get("/api/v1/queries/some_key?params=some_input")
    assert r.status_code == 200
    mock_db.execute_registered_query.assert_called_once_with("some_key", "some_input")
