#!/usr/bin/env python3
"""API tests for CRM alias source mapping endpoints."""
from __future__ import annotations

from unittest.mock import MagicMock


def test_list_aliases_returns_mappings(mock_customer_service):
    client, _svc = mock_customer_service
    sales = MagicMock()
    sales.get_all_aliases.return_value = [
        {
            "crm_accountid": "acc-1",
            "crm_account_name": "Acme Corp",
            "canonical_customer_key": None,
            "netbox_musteri_value": None,
            "notes": None,
            "source": "auto",
            "source_mappings": [],
        }
    ]
    client.app.state.sales = sales
    resp = client.get("/api/v1/crm/aliases")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["crm_accountid"] == "acc-1"
    assert "source_mappings" in body[0]


def test_save_source_mappings_endpoint(mock_customer_service):
    client, _svc = mock_customer_service
    sales = MagicMock()
    sales.save_source_mappings.return_value = [{"match_value": "Boyner"}]
    client.app.state.sales = sales
    resp = client.put(
        "/api/v1/crm/aliases/acc-1/source-mappings",
        json={
            "crm_account_name": "Boyner",
            "mappings": [
                {
                    "data_source": "virtualization",
                    "match_method": "contains",
                    "match_value": "Boyner",
                    "enabled": True,
                }
            ],
        },
    )
    assert resp.status_code == 200
    sales.save_source_mappings.assert_called_once()


def test_seed_boyner_endpoint(mock_customer_service):
    client, _svc = mock_customer_service
    sales = MagicMock()
    sales.seed_boyner_source_mappings.return_value = {
        "status": "ok",
        "crm_accountid": "boyner-id",
        "rows_upserted": 12,
    }
    client.app.state.sales = sales
    resp = client.post("/api/v1/crm/aliases/seed-boyner")
    assert resp.status_code == 200
    assert resp.json()["rows_upserted"] == 12
