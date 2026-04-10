"""Unit tests for permission path resolution (no DB)."""

from src.auth.permission_service import resolve_pathname_to_page_code


def test_resolve_overview():
    assert resolve_pathname_to_page_code("/") == "page:overview"
    assert resolve_pathname_to_page_code("") == "page:overview"


def test_resolve_dc_view():
    assert resolve_pathname_to_page_code("/datacenter/DC11") == "page:dc_view"


def test_resolve_admin():
    assert resolve_pathname_to_page_code("/admin/users") == "page:admin_users"


def test_resolve_login_none():
    assert resolve_pathname_to_page_code("/login") is None
