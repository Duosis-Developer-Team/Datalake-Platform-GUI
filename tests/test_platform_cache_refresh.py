"""The operator "refresh caches" button must not make the UI worse.

refresh_platform_redis_caches() calls three backends and then drops the GUI's own
HTTP response cache so the next render picks up the newly warmed values. Two
properties matter and neither was pinned:

1. The drop happens *after* the backends are warm. Doing it first would refill
   the GUI from services that have not finished warming, caching pre-refresh
   values under a fresh timestamp — the refresh would appear to do nothing. This
   ordering only became load-bearing once the backends stopped flushing up front
   (see services/datacenter-api/app/routers/admin_cache.py); while they went cold
   at t=0 the order was a wash.

2. If every backend failed, there is nothing new to pick up. Dropping the cache
   then buys a cold window for no benefit: the operator presses refresh, every
   backend is unreachable, and the only observable effect is that the pages that
   were still rendering from cache go blank.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.services import api_client


@pytest.fixture
def clients():
    """Patch the three service clients; each yields a MagicMock httpx.Client."""
    dc, cust, crm = MagicMock(), MagicMock(), MagicMock()
    for mock in (dc, cust, crm):
        response = MagicMock()
        response.content = b'{"status": "ok"}'
        response.json.return_value = {"status": "ok"}
        response.raise_for_status.return_value = None
        mock.post.return_value = response
    with patch.object(api_client, "_get_client_dc", return_value=dc), patch.object(
        api_client, "_get_client_cust", return_value=cust
    ), patch.object(api_client, "_get_client_crm", return_value=crm):
        yield dc, cust, crm


def test_all_three_services_are_refreshed(clients):
    with patch.object(api_client._api_response_cache, "clear"):
        out = api_client.refresh_platform_redis_caches()

    for mock in clients:
        mock.post.assert_called_once()
    assert set(out["services"]) == {"datacenter_api", "customer_api", "crm_engine"}
    assert all(entry["ok"] for entry in out["services"].values())


def test_gui_cache_is_cleared_after_the_backends_are_warm(clients):
    """Order matters: clearing first would cache pre-refresh values as fresh."""
    calls: list[str] = []
    for name, mock in zip(("dc", "cust", "crm"), clients):
        mock.post.side_effect = lambda *a, _n=name, **k: (
            calls.append(_n) or _ok_response()
        )

    with patch.object(api_client._api_response_cache, "clear") as clear:
        clear.side_effect = lambda: calls.append("clear")
        out = api_client.refresh_platform_redis_caches()

    assert calls[-1] == "clear", f"GUI cache cleared too early: {calls}"
    assert out["gui_cache_cleared"] is True


def test_gui_cache_survives_when_every_backend_fails(clients):
    """Nothing new to show, so a cold window is pure loss."""
    for mock in clients:
        mock.post.side_effect = httpx.ConnectError("connection refused")

    with patch.object(api_client._api_response_cache, "clear") as clear:
        out = api_client.refresh_platform_redis_caches()

    clear.assert_not_called()
    assert out["gui_cache_cleared"] is False
    assert all(not entry["ok"] for entry in out["services"].values())


def test_gui_cache_is_cleared_when_one_backend_succeeds(clients):
    """A partial refresh still produced new data somewhere; pick it up."""
    dc, cust, crm = clients
    cust.post.side_effect = httpx.ConnectError("connection refused")
    crm.post.side_effect = httpx.ConnectError("connection refused")

    with patch.object(api_client._api_response_cache, "clear") as clear:
        out = api_client.refresh_platform_redis_caches()

    clear.assert_called_once()
    assert out["gui_cache_cleared"] is True


def test_a_failing_service_does_not_stop_the_others(clients):
    dc, cust, crm = clients
    dc.post.side_effect = httpx.ConnectError("connection refused")

    with patch.object(api_client._api_response_cache, "clear"):
        out = api_client.refresh_platform_redis_caches()

    cust.post.assert_called_once()
    crm.post.assert_called_once()
    assert out["services"]["datacenter_api"]["ok"] is False
    assert out["services"]["customer_api"]["ok"] is True


def _ok_response() -> MagicMock:
    response = MagicMock()
    response.content = b'{"status": "ok"}'
    response.json.return_value = {"status": "ok"}
    response.raise_for_status.return_value = None
    return response
