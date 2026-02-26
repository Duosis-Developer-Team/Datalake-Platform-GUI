"""
gui-service/tests/test_api_client.py — api_client birim testleri

Test kapsamı:
  get_summary()        → başarı, Timeout, ConnectionError
  get_dc_detail()      → başarı, HTTPError (500)
  get_overview_trends() → başarı, Timeout

Strateji:
  - unittest.mock.patch ile services.api_client.requests.get mock'lanır.
  - Gerçek HTTP isteği ATILMAZ.
  - caplog fixture ile logger.error çağrısı doğrulanır.
  - pytest.raises ile exception propagation (re-raise) doğrulanır.

Kapsam: log-and-rethrow pattern'inin her hata türü için çalışması.
"""

import logging

import pytest
import requests
import requests.exceptions

from services.api_client import get_dc_detail, get_overview_trends, get_summary


# ── Sabit örnek yanıtlar ──────────────────────────────────────────────────────

SUMMARY_RESPONSE = [
    {
        "dc_code": "DC11",
        "name": "DC11",
        "provider": "vmware",
        "status": "Healthy",
        "stats": {
            "total_cpu": "100 / 500 GHz",
            "used_cpu_pct": 20.0,
            "total_ram": "200 / 1000 GB",
            "used_ram_pct": 25.0,
            "total_storage": "50 / 200 TB",
            "used_storage_pct": 30.0,
            "last_updated": "Live",
            "total_energy_kw": 18.0,
        },
    }
]

DC_DETAIL_RESPONSE = {
    "dc_code": "DC11",
    "name": "DC11",
    "provider": "vmware",
    "status": "Healthy",
    "stats": {
        "total_cpu": "100 / 500 GHz",
        "used_cpu_pct": 20.0,
        "total_ram": "200 / 1000 GB",
        "used_ram_pct": 25.0,
        "total_storage": "50 / 200 TB",
        "used_storage_pct": 30.0,
        "last_updated": "Live",
        "total_energy_kw": 18.0,
    },
    "clusters": [],
    "hosts": [],
    "vms": [],
    "energy": {"total_kw": 18.0, "sources": {}},
}

TRENDS_RESPONSE = {
    "cpu_pct": {"labels": ["2026-02-25T12:00:00+00:00"], "values": [23.5]},
    "ram_pct": {"labels": ["2026-02-25T12:00:00+00:00"], "values": [28.2]},
    "energy_kw": {"labels": ["2026-02-25T12:00:00+00:00"], "values": [2473479.0]},
}


# ── Yardımcı: Mock yanıt nesnesi ──────────────────────────────────────────────

def _mock_response(status_code: int, json_data):
    """requests.Response benzeri mock nesnesi döndürür."""
    mock = requests.models.Response()
    mock.status_code = status_code
    mock._content = None
    mock.json = lambda: json_data  # type: ignore[assignment]
    mock.raise_for_status = lambda: None
    return mock


def _mock_http_error_response(status_code: int):
    """raise_for_status → HTTPError fırlatan mock yanıt."""
    mock = requests.models.Response()
    mock.status_code = status_code
    mock.json = lambda: {"detail": "Internal Server Error"}  # type: ignore[assignment]

    def _raise():
        raise requests.exceptions.HTTPError(
            f"HTTP {status_code}", response=mock
        )

    mock.raise_for_status = _raise
    return mock


# ── get_summary() testleri ────────────────────────────────────────────────────

class TestGetSummary:
    def test_success_returns_list(self, mocker):
        """Başarılı yanıtta get_summary() liste döndürmeli."""
        mocker.patch(
            "services.api_client.requests.get",
            return_value=_mock_response(200, SUMMARY_RESPONSE),
        )
        result = get_summary()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["dc_code"] == "DC11"

    def test_success_calls_correct_url(self, mocker):
        """requests.get doğru URL ile çağrılmalı."""
        mock_get = mocker.patch(
            "services.api_client.requests.get",
            return_value=_mock_response(200, SUMMARY_RESPONSE),
        )
        get_summary()
        call_url = mock_get.call_args[0][0]
        assert "/datacenters/summary" in call_url

    def test_timeout_raises_and_logs(self, mocker, caplog):
        """Timeout: exception fırlatılmalı + logger.error çağrılmalı."""
        mocker.patch(
            "services.api_client.requests.get",
            side_effect=requests.exceptions.Timeout("zaman aşımı"),
        )
        with caplog.at_level(logging.ERROR, logger="services.api_client"):
            with pytest.raises(requests.exceptions.Timeout):
                get_summary()
        assert len(caplog.records) >= 1
        assert any("summary" in r.message.lower() or "zaman" in r.message.lower()
                   for r in caplog.records)

    def test_connection_error_raises_and_logs(self, mocker, caplog):
        """ConnectionError: exception fırlatılmalı + logger.error çağrılmalı."""
        mocker.patch(
            "services.api_client.requests.get",
            side_effect=requests.exceptions.ConnectionError("bağlantı hatası"),
        )
        with caplog.at_level(logging.ERROR, logger="services.api_client"):
            with pytest.raises(requests.exceptions.ConnectionError):
                get_summary()
        assert len(caplog.records) >= 1


# ── get_dc_detail() testleri ──────────────────────────────────────────────────

class TestGetDcDetail:
    def test_success_returns_dict(self, mocker):
        """Başarılı yanıtta get_dc_detail() dict döndürmeli."""
        mocker.patch(
            "services.api_client.requests.get",
            return_value=_mock_response(200, DC_DETAIL_RESPONSE),
        )
        result = get_dc_detail("DC11")
        assert isinstance(result, dict)
        assert result["dc_code"] == "DC11"

    def test_success_calls_correct_url(self, mocker):
        """requests.get URL'i dc_code içermeli."""
        mock_get = mocker.patch(
            "services.api_client.requests.get",
            return_value=_mock_response(200, DC_DETAIL_RESPONSE),
        )
        get_dc_detail("DC11")
        call_url = mock_get.call_args[0][0]
        assert "DC11" in call_url

    def test_http_error_raises_and_logs(self, mocker, caplog):
        """HTTP 500: HTTPError fırlatılmalı + logger.error çağrılmalı."""
        mocker.patch(
            "services.api_client.requests.get",
            return_value=_mock_http_error_response(500),
        )
        with caplog.at_level(logging.ERROR, logger="services.api_client"):
            with pytest.raises(requests.exceptions.HTTPError):
                get_dc_detail("DC11")
        assert len(caplog.records) >= 1
        assert any("DC11" in r.message for r in caplog.records)


# ── get_overview_trends() testleri ───────────────────────────────────────────

class TestGetOverviewTrends:
    def test_success_returns_dict_with_keys(self, mocker):
        """Başarılı yanıtta 3 trend anahtarı gelmeli."""
        mocker.patch(
            "services.api_client.requests.get",
            return_value=_mock_response(200, TRENDS_RESPONSE),
        )
        result = get_overview_trends()
        assert isinstance(result, dict)
        assert "cpu_pct" in result
        assert "ram_pct" in result
        assert "energy_kw" in result

    def test_success_values_correct(self, mocker):
        """cpu_pct.values[0] == 23.5 (mock verisiyle)."""
        mocker.patch(
            "services.api_client.requests.get",
            return_value=_mock_response(200, TRENDS_RESPONSE),
        )
        result = get_overview_trends()
        assert result["cpu_pct"]["values"][0] == pytest.approx(23.5)

    def test_timeout_raises_and_logs(self, mocker, caplog):
        """Timeout: exception fırlatılmalı + logger.error çağrılmalı."""
        mocker.patch(
            "services.api_client.requests.get",
            side_effect=requests.exceptions.Timeout("zaman aşımı"),
        )
        with caplog.at_level(logging.ERROR, logger="services.api_client"):
            with pytest.raises(requests.exceptions.Timeout):
                get_overview_trends()
        assert len(caplog.records) >= 1
        assert any("trends" in r.message.lower() or "zaman" in r.message.lower()
                   for r in caplog.records)
