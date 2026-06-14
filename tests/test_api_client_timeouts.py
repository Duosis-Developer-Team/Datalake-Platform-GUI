"""Interactive httpx client timeouts.

Sprint 4 re-tuning: the read timeout must be LONG enough for genuinely-slow cold
queries (filtered compute is 15-39s over the remote VPN DB) to COMPLETE and populate
the cache — an 8s timeout fired before completion, returned empty, never cached, and
left the UI showing zeros (warm==cold). Connect stays SHORT so a truly-unreachable
backend still fails fast.
"""
import httpx
from src.services import api_client as api


def test_interactive_clients_read_timeout_allows_slow_cold_queries():
    for getter in (api._get_client_dc, api._get_client_cust, api._get_client_query,
                   api._get_client_hmdl, api._get_client_crm):
        client = getter()
        assert isinstance(client.timeout, httpx.Timeout)
        # Long enough to let a moderately-slow query finish and cache, but not a
        # multi-minute freeze on a degraded backend (~15-30s window).
        assert client.timeout.read is not None and 15.0 <= client.timeout.read <= 30.0
        # Still fail fast when the host is unreachable.
        assert client.timeout.connect is not None and client.timeout.connect <= 5.0


def test_interactive_read_timeout_is_env_tunable(monkeypatch):
    # The ceiling is configurable so ops can tune it per environment.
    assert hasattr(api, "_INTERACTIVE_READ_TIMEOUT")
    assert api._INTERACTIVE_READ_TIMEOUT >= 15.0
