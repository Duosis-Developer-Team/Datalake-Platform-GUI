#!/usr/bin/env python3
"""Tests for customer-scoped physical inventory filtering."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.services.dc_service import DatabaseService


def _device(name: str, tenant_id: int, tenant_name: str = "") -> dict:
    return {
        "id": 1,
        "name": name,
        "device_type_name": "server",
        "manufacturer_name": "Dell",
        "device_role_name": "compute",
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "site_name": "DC11",
        "location_name": "",
    }


def test_physical_inventory_customer_matches_tenant_id_mapping(monkeypatch):
    svc = DatabaseService.__new__(DatabaseService)
    monkeypatch.setattr(svc, "_get_physical_inventory_raw", lambda force=False: [_device("d1", 5, "Boyner")])
    monkeypatch.setattr(svc, "_get_location_dc_map", lambda: {})
    monkeypatch.setattr("app.services.dc_service.cache.get", lambda key: None)
    monkeypatch.setattr("app.services.dc_service.cache.set", lambda key, val: None)

    webui = MagicMock()
    webui.is_available = True
    webui.run_one.return_value = {"crm_accountid": "boyner-id", "crm_account_name": "Boyner CRM"}
    webui.run_rows.return_value = [
        {"match_method": "id_exact", "match_value": "5", "enabled": True, "priority": 10},
    ]

    rows = svc.get_physical_inventory_customer("Boyner CRM", webui=webui)
    assert len(rows) == 1
    assert rows[0]["name"] == "d1"


def test_physical_inventory_customer_boyner_fallback_without_mappings(monkeypatch):
    svc = DatabaseService.__new__(DatabaseService)
    monkeypatch.setattr(
        svc,
        "_get_physical_inventory_raw",
        lambda force=False: [_device("d1", 5, "Boyner"), _device("d2", 9, "Other")],
    )
    monkeypatch.setattr(svc, "_get_location_dc_map", lambda: {})
    monkeypatch.setattr("app.services.dc_service.cache.get", lambda key: None)
    monkeypatch.setattr("app.services.dc_service.cache.set", lambda key, val: None)

    rows = svc.get_physical_inventory_customer("BOYNER BUYUK MAGAZACILIK A.S.", webui=None)
    assert len(rows) == 1
    assert rows[0]["name"] == "d1"
