"""Permission catalog flattening."""

from src.auth.registry import _flatten_nodes
from src.auth.permission_catalog import build_default_permission_roots


def test_flatten_non_empty():
    roots = build_default_permission_roots()
    flat = _flatten_nodes(roots, None)
    assert len(flat) > 10
    codes = {r["code"] for r in flat}
    assert "grp:settings" in codes
    assert "page:settings_users" in codes
