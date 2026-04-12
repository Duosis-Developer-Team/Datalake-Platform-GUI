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


def test_test_ldap_connection_ok_when_search_succeeds(monkeypatch):
    def _fake_search(_cfg, _q, size_limit=None):
        assert size_limit == 3
        return [
            {
                "username": "jdoe",
                "display_name": "Jane",
                "email": None,
                "distinguished_name": "CN=jdoe,DC=example,DC=com",
            }
        ]

    monkeypatch.setattr(ldap_service, "_search_directory_users_with_cfg", _fake_search)
    out = ldap_service.test_ldap_connection(
        "127.0.0.1",
        None,
        389,
        False,
        "cn=admin,dc=example,dc=com",
        "secret",
        "dc=example,dc=com",
        "(sAMAccountName={username})",
        None,
        "test",
    )
    assert out["ok"] is True
    assert out["search_count"] == 1


def test_test_ldap_connection_error_dict_on_runtime_error(monkeypatch):
    def _fail(_cfg, _q, size_limit=None):
        raise RuntimeError("all servers down")

    monkeypatch.setattr(ldap_service, "_search_directory_users_with_cfg", _fail)
    out = ldap_service.test_ldap_connection(
        "127.0.0.1",
        None,
        389,
        False,
        "cn=admin,dc=example,dc=com",
        "x",
        "dc=example,dc=com",
        "(sAMAccountName={username})",
        None,
        "test",
    )
    assert out["ok"] is False
    assert "all servers down" in (out.get("error") or "")
