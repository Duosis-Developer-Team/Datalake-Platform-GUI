#!/usr/bin/env python3
"""Tests for datacenter network/storage exclusion integration."""
from __future__ import annotations

from unittest.mock import patch

from psycopg2 import OperationalError

from app.services.dc_service import DatabaseService


def _make_service():
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        return DatabaseService()


def test_get_network_filters_omits_excluded_roles():
    svc = _make_service()
    filtered_devices = [
        {"manufacturer_name": "Cisco", "device_role_name": "Switch", "device_name": "sw1", "host": "h1"},
    ]

    with patch.object(svc, "_resolve_zabbix_dc_devices", return_value={"devices": filtered_devices}):
        out = svc.get_network_filters("DC11", {"preset": "last_7d"})

    roles = out.get("roles_by_manufacturer", {})
    assert "Patch Panel" not in str(roles)
    assert "Switch" in str(roles)


def test_resolve_zabbix_dc_devices_excludes_roles():
    svc = _make_service()
    rows = [
        ("1", "host1", "dev1", "Cisco", "Switch", None, None, 10, 5, 0.0, None),
        ("2", "host2", "dev2", "Generic", "Patch Panel", None, None, 4, 2, 0.0, None),
    ]

    with patch.object(svc, "_excluded_roles_for_scope", return_value={"patch panel"}), \
         patch("app.services.dc_service.cache.get", return_value=None), \
         patch("app.services.dc_service.cache.set"), \
         patch.object(svc, "_get_connection"), \
         patch.object(svc, "_run_rows", return_value=rows):
        out = svc._resolve_zabbix_dc_devices("DC11", {"preset": "last_7d"})

    assert len(out["devices"]) == 1
    assert out["devices"][0]["device_role_name"] == "Switch"


def test_get_zabbix_storage_capacity_excludes_roles():
    svc = _make_service()
    rows = [
        ("1", "host1", "stor1", "IBM", "Storage", None, None, 1000, 500, 500, "ok", None),
        ("2", "host2", "stor2", "IBM", "Patch Panel", None, None, 2000, 1000, 1000, "ok", None),
    ]

    with patch.object(svc, "_excluded_roles_for_scope", return_value={"patch panel"}), \
         patch("app.services.dc_service.cache.get", return_value=None), \
         patch("app.services.dc_service.cache.set"), \
         patch.object(svc, "_get_connection"), \
         patch.object(svc, "_run_rows", return_value=rows):
        out = svc.get_zabbix_storage_capacity("DC11", {"preset": "last_7d"})

    assert out.get("storage_device_count") == 1
    assert out.get("total_capacity_bytes") == 1000
