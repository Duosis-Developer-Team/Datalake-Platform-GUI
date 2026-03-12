def test_health_returns_ok(mock_query_service):
    client, _ = mock_query_service
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ready_returns_ready(mock_query_service):
    client, _ = mock_query_service
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_run_query_returns_result(mock_query_service):
    client, _ = mock_query_service
    resp = client.get("/api/v1/queries/nutanix_host_count?params=DC11")
    assert resp.status_code == 200
    data = resp.json()
    assert "result_type" in data or "error" in data


def test_run_query_passes_params(mock_query_service):
    client, svc = mock_query_service
    client.get("/api/v1/queries/nutanix_host_count?params=DC11")
    svc.execute_registered_query.assert_called_with("nutanix_host_count", "DC11")


def test_run_query_with_empty_params(mock_query_service):
    client, svc = mock_query_service
    client.get("/api/v1/queries/nutanix_host_count")
    svc.execute_registered_query.assert_called_with("nutanix_host_count", "")


def test_run_query_value_result(mock_query_service):
    client, svc = mock_query_service
    svc.execute_registered_query.return_value = {"result_type": "value", "value": 42}
    resp = client.get("/api/v1/queries/nutanix_host_count?params=DC11")
    assert resp.status_code == 200
    data = resp.json()
    assert data["result_type"] == "value"
    assert data["value"] == 42


def test_run_query_error_result(mock_query_service):
    client, svc = mock_query_service
    svc.execute_registered_query.return_value = {"error": "Unknown query key: bad_key"}
    resp = client.get("/api/v1/queries/bad_key")
    assert resp.status_code == 200
    assert "error" in resp.json()
