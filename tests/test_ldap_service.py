"""LDAP service import (no live LDAP)."""

from src.auth import ldap_service


def test_servers_empty_config():
    cfg = {
        "server_primary": "127.0.0.1",
        "server_secondary": None,
        "port": 389,
        "use_ssl": False,
    }
    srvs = ldap_service._servers(cfg)
    assert len(srvs) >= 1
