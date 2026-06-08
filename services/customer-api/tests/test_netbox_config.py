#!/usr/bin/env python3
"""Tests for NetBox visualization exclusion config service."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.netbox_config_service import NetboxConfigService


def _webui(rows=None, rowcount=1):
    pool = MagicMock()
    pool.is_available = True
    pool.run_rows.return_value = rows or []
    pool.execute.return_value = rowcount
    return pool


def test_list_exclusions_empty_when_webui_unavailable():
    pool = MagicMock()
    pool.is_available = False
    svc = NetboxConfigService(pool)
    assert svc.list_exclusions() == []


def test_list_exclusions_returns_rows():
    pool = _webui(
        [
            {
                "id": 1,
                "view_scope": "datacenter",
                "dimension": "device_role",
                "dimension_value": "Patch Panel",
                "notes": None,
                "updated_by": "api",
                "updated_at": None,
            }
        ]
    )
    svc = NetboxConfigService(pool)
    rows = svc.list_exclusions()
    assert len(rows) == 1
    assert rows[0]["dimension_value"] == "Patch Panel"


def test_upsert_exclusion_validates_scope():
    svc = NetboxConfigService(_webui())
    with pytest.raises(ValueError, match="view_scope"):
        svc.upsert_exclusion(
            view_scope="invalid",
            dimension="device_role",
            dimension_value="Patch Panel",
            notes=None,
            updated_by="test",
        )


def test_upsert_exclusion_requires_value():
    svc = NetboxConfigService(_webui())
    with pytest.raises(ValueError, match="dimension_value"):
        svc.upsert_exclusion(
            view_scope="datacenter",
            dimension="device_role",
            dimension_value="  ",
            notes=None,
            updated_by="test",
        )


def test_upsert_exclusion_executes_sql():
    pool = _webui()
    svc = NetboxConfigService(pool)
    out = svc.upsert_exclusion(
        view_scope="Datacenter",
        dimension="device_role",
        dimension_value="Patch Panel",
        notes="noise",
        updated_by="tester",
    )
    assert out["view_scope"] == "datacenter"
    assert out["dimension_value"] == "Patch Panel"
    pool.execute.assert_called_once()


def test_delete_exclusion():
    pool = _webui(rowcount=1)
    svc = NetboxConfigService(pool)
    assert svc.delete_exclusion(7) == 1
    pool.execute.assert_called_once()
