"""Delegation test for GET /api/v1/crm/colocation/{dc_code}: the router just
constructs ColocationMatchingService from app.state and returns its payload."""
from unittest.mock import MagicMock, patch


def test_get_colocation_delegates_to_service(mock_customer_service):
    client, _mock_svc = mock_customer_service
    canned = {
        "aggregate": {"total_u": 94, "used_u": 62, "free_u": 32, "rack_count": 2},
        "customers": [
            {"tenant": "Boyner", "crm_accountid": "A-1", "match_status": "matched"},
        ],
        "racks": [{"rack_name": "116", "dc": "DC13"}],
    }
    mock_instance = MagicMock()
    mock_instance.get_colocation.return_value = canned

    with patch("app.routers.colocation.ColocationMatchingService", return_value=mock_instance):
        r = client.get("/api/v1/crm/colocation/DC13")

    assert r.status_code == 200
    assert r.json() == canned
    mock_instance.get_colocation.assert_called_once_with("DC13")
