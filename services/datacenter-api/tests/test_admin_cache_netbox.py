#!/usr/bin/env python3
"""Tests for targeted NetBox viz cache invalidation endpoint."""
from __future__ import annotations

from unittest.mock import patch

from app.routers.admin_cache import invalidate_netbox_viz_cache


def test_invalidate_netbox_viz_cache_clears_prefixes():
    with patch("app.routers.admin_cache.invalidate_exclusion_cache") as p_inv, \
         patch("app.routers.admin_cache.cache.delete_prefix") as p_prefix, \
         patch("app.routers.admin_cache.cache.delete") as p_delete:
        out = invalidate_netbox_viz_cache()

    assert out == {"status": "ok"}
    p_inv.assert_called_once()
    assert p_prefix.call_count == 3
    p_delete.assert_called_once_with("netbox:device_roles")
