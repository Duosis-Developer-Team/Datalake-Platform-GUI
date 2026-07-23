"""Tests for Settings → Administration URL helpers."""

from src.pages.settings.admin_routes import to_administration_path


def test_settings_root_maps_to_administration():
    assert to_administration_path("/settings") == "/administration"


def test_settings_nested_path_maps_to_administration():
    assert to_administration_path("/settings/integrations/hmdl") == "/administration/integrations/hmdl"


def test_administration_path_unchanged():
    assert to_administration_path("/administration/iam/users") == "/administration/iam/users"


def test_non_settings_path_unchanged():
    assert to_administration_path("/datacenters") == "/datacenters"


def test_platform_versions_route_normalizes():
    from src.pages.settings.shell import _normalize_path
    assert _normalize_path("/administration/platform/versions") == "/administration/platform/versions"
    assert _normalize_path("/administration/platform/versions/") == "/administration/platform/versions"


def test_platform_versions_page_builder_registered():
    from src.pages.settings.shell import _PAGE_BUILDERS
    assert "/administration/platform/versions" in _PAGE_BUILDERS
    code, builder = _PAGE_BUILDERS["/administration/platform/versions"]
    assert code == "page:settings_platform_versions"
    assert callable(builder)
