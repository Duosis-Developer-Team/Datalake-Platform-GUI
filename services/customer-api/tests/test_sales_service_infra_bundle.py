"""Tests for SalesService infra bundle resolution (Redis + on-demand fallback)."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.services import sales_service as sales_module
from app.services.sales_service import SalesService


def test_customer_infra_bundle_reads_redis_hit(monkeypatch):
    monkeypatch.setattr(
        sales_module.cache,
        "get",
        lambda key: {"assets": {"hyperconv": {"cpu_total": 42}}, "totals": {}},
    )
    svc = SalesService(None, None, None, get_customer_assets=MagicMock())
    bundle = svc._customer_infra_bundle("Acme", {"start": "2026-06-01", "end": "2026-06-08"})
    assert bundle["assets"]["hyperconv"]["cpu_total"] == 42
    svc._get_customer_assets.assert_not_called()


def test_customer_infra_bundle_falls_back_on_miss(monkeypatch):
    monkeypatch.setattr(sales_module.cache, "get", lambda key: None)
    loader = MagicMock(
        return_value={"assets": {"classic": {"cpu_total": 7}}, "totals": {}},
    )
    svc = SalesService(None, None, None, get_customer_assets=loader)
    tr = {"start": "2026-06-02", "end": "2026-06-08", "preset": "7d"}
    bundle = svc._customer_infra_bundle("Acme", tr)
    assert bundle["assets"]["classic"]["cpu_total"] == 7
    loader.assert_called_once_with("Acme", tr)
