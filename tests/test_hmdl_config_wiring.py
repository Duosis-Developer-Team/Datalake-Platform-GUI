"""Wiring tests: shell registration, resolver, permission catalog node."""

from src.pages.settings import shell
from src.auth.permission_service import resolve_pathname_to_page_code


def test_shell_registers_hmdl_config_route():
    assert "/administration/integrations/hmdl/config" in shell._PAGE_BUILDERS
    code, builder = shell._PAGE_BUILDERS["/administration/integrations/hmdl/config"]
    assert code == "page:settings_hmdl_config"
    assert callable(builder)


def test_hmdl_tabs_include_configuration():
    hrefs = [h for h, _l, _c in shell.HMDL_TABS]
    assert "/administration/integrations/hmdl/config" in hrefs


def test_resolver_maps_config_path():
    assert resolve_pathname_to_page_code(
        "/administration/integrations/hmdl/config"
    ) == "page:settings_hmdl_config"


def test_resolver_still_maps_hmdl_overview():
    assert resolve_pathname_to_page_code(
        "/administration/integrations/hmdl"
    ) == "page:settings_hmdl_overview"


def test_permission_catalog_has_config_node():
    from src.auth.permission_catalog import build_default_permission_roots

    roots = build_default_permission_roots()

    # NOTE: build_default_permission_roots() returns PermissionNode pydantic
    # models (src/auth/models.py), not dicts — the `_n(...)` helper in
    # permission_catalog.py constructs PermissionNode instances. Traverse via
    # attribute access (`n.code`, `n.children`) rather than `n.get(...)`.
    def _codes(nodes):
        for n in nodes:
            yield n.code
            yield from _codes(n.children or [])

    all_codes = set(_codes(roots))
    assert "page:settings_hmdl_config" in all_codes
