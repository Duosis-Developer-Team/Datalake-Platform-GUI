"""P4b: interactive httpx clients use a tight read timeout (fail-fast), not 30s."""
import httpx
from src.services import api_client as api


def test_interactive_clients_have_tight_read_timeout():
    for getter in (api._get_client_dc, api._get_client_cust, api._get_client_query,
                   api._get_client_hmdl, api._get_client_crm):
        client = getter()
        assert isinstance(client.timeout, httpx.Timeout)
        assert client.timeout.read is not None and client.timeout.read <= 8.0
        assert client.timeout.connect is not None and client.timeout.connect <= 3.0
