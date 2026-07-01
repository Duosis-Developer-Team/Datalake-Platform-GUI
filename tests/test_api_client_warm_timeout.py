"""Background warm must use a long timeout so genuinely-slow cold queries
(e.g. the >60s overview) actually COMPLETE and populate the shared cache —
otherwise they time out at the interactive limit, never cache, and warm==cold
forever. Interactive requests keep the short (fail-fast) timeout.
"""
from src.services import api_client as api


def test_interactive_client_uses_interactive_timeout():
    c = api._get_client_dc()
    assert c.timeout.read == api._INTERACTIVE_READ_TIMEOUT


def test_warm_mode_client_uses_inventory_timeout():
    with api.warm_mode():
        c = api._get_client_dc()
    assert c.timeout.read == api._INVENTORY_READ_TIMEOUT


def test_warm_mode_customer_client_uses_inventory_timeout():
    with api.warm_mode():
        c = api._get_client_cust()
    assert c.timeout.read == api._INVENTORY_READ_TIMEOUT


def test_warm_mode_resets_after_context():
    with api.warm_mode():
        pass
    c = api._get_client_dc()
    assert c.timeout.read == api._INTERACTIVE_READ_TIMEOUT
