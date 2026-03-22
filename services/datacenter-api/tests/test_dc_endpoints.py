from unittest.mock import patch


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
        {"start": "2026-03-01", "end": "2026-03-07", "preset": "custom"}
    )


def test_datacenters_summary_without_time_range_uses_default_7d(client, mock_db):
    r = client.get("/api/v1/datacenters/summary")
    assert r.status_code == 200
    call_arg = mock_db.get_all_datacenters_summary.call_args[0][0]
    assert call_arg["preset"] == "7d"
    assert "start" in call_arg
    assert "end" in call_arg


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
        "DC12", {"start": "2026-03-01", "end": "2026-03-07", "preset": "custom"}
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


def test_datacenters_summary_with_preset_7d_passes_7d_range_to_db(client, mock_db):
    r = client.get("/api/v1/datacenters/summary?preset=7d")
    assert r.status_code == 200
    call_arg = mock_db.get_all_datacenters_summary.call_args[0][0]
    assert call_arg["preset"] == "7d"
    assert "start" in call_arg
    assert "end" in call_arg


def test_datacenters_summary_with_preset_30d_passes_30d_range_to_db(client, mock_db):
    r = client.get("/api/v1/datacenters/summary?preset=30d")
    assert r.status_code == 200
    call_arg = mock_db.get_all_datacenters_summary.call_args[0][0]
    assert call_arg["preset"] == "30d"


def test_datacenters_summary_with_preset_1d_passes_1d_range_to_db(client, mock_db):
    r = client.get("/api/v1/datacenters/summary?preset=1d")
    assert r.status_code == 200
    call_arg = mock_db.get_all_datacenters_summary.call_args[0][0]
    assert call_arg["preset"] == "1d"
    assert call_arg["start"] == call_arg["end"]


def test_datacenter_detail_with_preset_7d_passes_range_to_db(client, mock_db):
    r = client.get("/api/v1/datacenters/DC11?preset=7d")
    assert r.status_code == 200
    call_arg = mock_db.get_dc_details.call_args[0][1]
    assert call_arg["preset"] == "7d"


def test_dashboard_overview_with_preset_30d_passes_range_to_db(client, mock_db):
    r = client.get("/api/v1/dashboard/overview?preset=30d")
    assert r.status_code == 200
    call_arg = mock_db.get_global_dashboard.call_args[0][0]
    assert call_arg["preset"] == "30d"


def test_datacenter_detail_summary_stats_has_energy_fields(client):
    r = client.get("/api/v1/datacenters/summary")
    body = r.json()
    stats = body[0]["stats"]
    assert "total_energy_kw" in stats
    assert "ibm_kw" in stats
    assert "vcenter_kw" in stats


def test_datacenter_detail_energy_has_kwh_fields(client):
    r = client.get("/api/v1/datacenters/DC11")
    body = r.json()
    energy = body["energy"]
    assert "total_kwh" in energy
    assert "ibm_kwh" in energy
    assert "vcenter_kwh" in energy


def test_sla_endpoint_returns_by_dc(client):
    with patch(
        "app.routers.datacenters.sla_service.get_sla_data",
        return_value={"DC11": {"availability_pct": 99.9}},
    ):
        r = client.get("/api/v1/sla")
        assert r.status_code == 200
        body = r.json()
        assert body["by_dc"]["DC11"]["availability_pct"] == 99.9


def test_dc_s3_pools_endpoint_delegates_to_db(client, mock_db):
    mock_db.get_dc_s3_pools.return_value = {"pools": ["pool-a"], "latest": {}, "growth": {}}
    r = client.get("/api/v1/datacenters/DC11/s3/pools")
    assert r.status_code == 200
    assert r.json()["pools"] == ["pool-a"]
    mock_db.get_dc_s3_pools.assert_called_once()
