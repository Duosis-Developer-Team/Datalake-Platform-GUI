"""Tests for administration route detection."""

from src.pages.settings.admin_routes import ADMIN_PREFIX, LEGACY_PREFIX, to_administration_path


def is_administration_path(pathname: str | None) -> bool:
    p = str(pathname or "")
    return p.startswith(ADMIN_PREFIX) or p.startswith(LEGACY_PREFIX)


def test_administration_path_detection():
    assert is_administration_path("/administration")
    assert is_administration_path("/administration/integrations/hmdl")
    assert is_administration_path("/settings/iam/users")
    assert not is_administration_path("/")
    assert not is_administration_path("/datacenters")


def test_settings_root_maps_to_administration():
    assert to_administration_path("/settings") == "/administration"
