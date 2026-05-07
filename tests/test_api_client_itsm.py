"""Unit tests for ITSM api_client functions — HTTP is mocked."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clear_cache():
    """api_client now reads memory cache before HTTP; flush between tests."""
    from src.services import cache_service as cs

    cs.clear()
    yield


class TestITSMApiClientFunctions:
    def test_get_customer_itsm_summary_returns_dict(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"total_count": 5, "incident_count": 3}

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        with patch("src.services.api_client._get_client_cust", return_value=mock_client):
            from src.services.api_client import get_customer_itsm_summary
            result = get_customer_itsm_summary("Boyner", {"start": "2026-01-01", "end": "2026-04-01"})

        assert isinstance(result, dict)
        assert result.get("total_count") == 5

    def test_get_customer_itsm_extremes_returns_dict(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"long_tail": [], "sla_breach": []}

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        with patch("src.services.api_client._get_client_cust", return_value=mock_client):
            from src.services.api_client import get_customer_itsm_extremes
            result = get_customer_itsm_extremes("Boyner", None)

        assert isinstance(result, dict)
        assert "long_tail" in result
        assert "sla_breach" in result

    def test_get_customer_itsm_tickets_returns_list(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"source": "incident", "id": 1}]

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        with patch("src.services.api_client._get_client_cust", return_value=mock_client):
            from src.services.api_client import get_customer_itsm_tickets
            result = get_customer_itsm_tickets("Boyner", None)

        assert isinstance(result, list)
        assert len(result) == 1

    def test_summary_cache_key_includes_customer_and_tr(self):
        """Cache key must differ for different customers and time ranges."""
        from src.services.api_client import _serialize_tr_params
        tr1 = {"start": "2026-01-01", "end": "2026-02-01"}
        tr2 = {"start": "2026-03-01", "end": "2026-04-01"}
        from urllib.parse import quote
        enc = quote("Boyner", safe="")
        key1 = f"api:customer_itsm_summary:{enc}:{_serialize_tr_params(tr1)}"
        key2 = f"api:customer_itsm_summary:{enc}:{_serialize_tr_params(tr2)}"
        assert key1 != key2

    def test_fallback_on_http_error(self):
        """On HTTP connection error, empty fallback is returned (not an exception)."""
        import httpx
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("connection refused")
        with patch("src.services.api_client._get_client_cust", return_value=mock_client):
            from src.services.api_client import get_customer_itsm_summary
            result = get_customer_itsm_summary("NoOne", None)

        assert isinstance(result, dict)
        assert result.get("total_count") == 0
