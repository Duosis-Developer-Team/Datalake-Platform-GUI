#!/usr/bin/env python3
"""Tests for NetBox visualization exclusion helpers."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.services.netbox_viz_filter import (
    filter_devices_by_role_exclusion,
    invalidate_exclusion_cache,
    is_role_excluded,
    load_excluded_roles,
)


def test_is_role_excluded_case_insensitive():
    excluded = {"patch panel", "cabling"}
    assert is_role_excluded("Patch Panel", excluded)
    assert is_role_excluded("HOST", {"host"})
    assert not is_role_excluded("Switch", excluded)


def test_load_excluded_roles_uses_webui():
    invalidate_exclusion_cache()
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.return_value = [
        {"dimension_value": "Patch Panel"},
        {"dimension_value": "Cabling"},
    ]
    roles = load_excluded_roles(webui, "datacenter")
    assert roles == {"patch panel", "cabling"}


def test_load_excluded_roles_invalid_scope():
    assert load_excluded_roles(MagicMock(), "overview") == set()


def test_filter_devices_by_role_exclusion():
    devices = [
        {"name": "a", "device_role_name": "HOST"},
        {"name": "b", "device_role_name": "Patch Panel"},
    ]
    out = filter_devices_by_role_exclusion(devices, {"patch panel"})
    assert len(out) == 1
    assert out[0]["name"] == "a"
