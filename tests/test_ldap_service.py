"""LDAP service import (no live LDAP)."""

import pytest

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


def test_search_directory_users_short_query_raises():
    with pytest.raises(ValueError, match="2 characters"):
        ldap_service.search_directory_users("x")
