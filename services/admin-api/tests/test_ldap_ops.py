"""Unit tests for LDAP filter helpers (no live directory)."""

from __future__ import annotations

import pytest

from app.ldap_ops import _escape_ldap_filter_value, _sanitize_query


def test_escape_wildcard_and_paren():
    assert _escape_ldap_filter_value("a*b") == "a\\2ab"
    assert "\\28" in _escape_ldap_filter_value("a(b")


def test_sanitize_query_truncates():
    long_q = "a" * 300
    assert len(_sanitize_query(long_q)) <= 200


def test_sanitize_query_strips():
    assert _sanitize_query("  hello   world  ") == "hello world"


def test_search_directory_users_short_query_raises():
    from app.ldap_ops import search_directory_users

    cfg = {
        "server_primary": "127.0.0.1",
        "server_secondary": None,
        "use_ssl": False,
        "port": 389,
        "bind_dn": "cn=admin",
        "bind_password": "x",
        "search_base_dn": "dc=example,dc=com",
    }
    with pytest.raises(ValueError, match="2 characters"):
        search_directory_users(cfg, "a")
