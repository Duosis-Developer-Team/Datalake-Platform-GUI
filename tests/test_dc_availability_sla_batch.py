"""Tests for batch DC availability SLA fetch in api_client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from src.services import api_client as api
from src.services import cache_service as cache


def setup_function():
    cache.clear()


def test_get_dc_availability_sla_items_for_dcs_ok_match():
    rows = [{"id": "AZ11", "name": "AZ11", "description": "AzinTelecom DC"}]
    tr = {"start": "2026-01-01", "end": "2026-12-31", "preset": "year_2026"}

    with patch.object(api, "_get_json") as mock_get:
        mock_get.return_value = {
            "items": [
                {
                    "group_name": "AzinTelecom - AZ11",
                    "availability_pct": 99.95,
                }
            ]
        }
        result = api.get_dc_availability_sla_items_for_dcs(rows, tr)

    assert result["status"] == "ok"
    assert result["raw_count"] == 1
    assert result["items_map"]["AZ11"]["availability_pct"] == 99.95


def test_get_dc_availability_sla_items_for_dcs_uses_stale_cache_on_http_error():
    rows = [{"id": "DC11", "name": "DC11", "description": "Premier DC"}]
    tr = {"start": "2026-01-01", "end": "2026-12-31", "preset": "year_2026"}
    ck = f"api:dc_svc_sla_items:{api._serialize_tr_params(tr)}"
    cache.set(ck, [{"group_name": "Premier - DC11", "availability_pct": 99.9}])

    with patch.object(api, "_get_json", side_effect=httpx.ConnectError("refused")):
        result = api.get_dc_availability_sla_items_for_dcs(rows, tr, force_refresh=True)

    assert result["status"] == "ok"
    assert result["raw_count"] == 1
    assert result["items_map"]["DC11"] is not None


def test_get_dc_availability_sla_items_for_dcs_error_without_cache():
    rows = [{"id": "DC11", "name": "DC11", "description": "Premier DC"}]
    tr = {"start": "2026-01-01", "end": "2026-12-31", "preset": "year_2026"}

    with patch.object(api, "_get_json", side_effect=httpx.ConnectError("refused")):
        result = api.get_dc_availability_sla_items_for_dcs(rows, tr)

    assert result["status"] == "error"
    assert result["raw_count"] == 0
    assert result["items_map"]["DC11"] is None


def test_gui_sla_fetch_uses_end_of_day():
    from src.services import sla_service

    tr = {"start": "2026-01-01", "end": "2026-12-31"}
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"items": []}

    with patch.object(sla_service, "SLA_API_KEY", "test-key"):
        with patch("src.services.sla_service.requests.get", return_value=mock_resp) as mock_get:
            sla_service._fetch_sla_raw(tr)

    _args, kwargs = mock_get.call_args
    assert kwargs["params"]["start_date"] == "2026-01-01T00:00:00"
    assert kwargs["params"]["end_date"] == "2026-12-31T23:59:59"
