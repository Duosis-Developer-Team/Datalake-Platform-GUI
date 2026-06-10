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
