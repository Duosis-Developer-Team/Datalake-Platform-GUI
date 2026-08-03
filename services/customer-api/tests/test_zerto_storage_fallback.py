"""Zerto storage must never fall back to raw_zerto_site_metrics history SUM."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.sellable_service import SellableService
from shared.sellable.models import InfraSource, PanelDefinition


def _build_service() -> SellableService:
    svc = SellableService(
        customer_service=MagicMock(),
        webui=MagicMock(is_available=True),
        config_service=MagicMock(),
        currency_service=MagicMock(),
        tagging_service=MagicMock(),
    )
    svc._dc_api_url = "http://dc-api"
    svc._resolve_threshold = MagicMock(return_value=80.0)
    svc._resolve_unit_price_tl = MagicMock(return_value=(2.37, True))
    svc._query_total_allocated = MagicMock(return_value=(1e15, 1e14))
    svc.list_unit_conversions = MagicMock(return_value=[])
    return svc


def test_zerto_storage_skips_site_metrics_when_compute_fails():
    svc = _build_service()
    infra = InfraSource(
        "backup_zerto_replication_storage",
        "DC13",
        "raw_zerto_site_metrics",
        "provisioned_storage_mb",
        "MB",
        "raw_zerto_site_metrics",
        "used_storage_mb",
        "MB",
    )
    panel = PanelDefinition(
        "backup_zerto_replication_storage",
        "Zerto Storage",
        "backup_zerto_replication",
        "storage",
        "GB",
    )
    with patch.object(svc, "_fetch_zerto_datastore_storage", return_value=None):
        with patch.object(svc, "get_infra_source", return_value=infra):
            result = svc.compute_panel(panel, dc_code="DC13")

    notes = " ".join(result.notes or [])
    assert (
        "raw_zerto_site_metrics fallback disabled" in notes
        or "backup-zerto-storage unavailable" in notes
    )
    assert float(result.total or 0) == 0.0
    assert float(result.allocated or 0) == 0.0
    svc._query_total_allocated.assert_not_called()


def test_merge_compute_capacity_sums_classic_and_hc():
    a = {
        "cpu_cap": 10.0,
        "cpu_alloc_ghz_sales": 1.0,
        "mem_cap": 100.0,
        "mem_alloc_gb_vm": 10.0,
    }
    b = {
        "cpu_cap": 5.0,
        "cpu_alloc_ghz_sales": 2.0,
        "mem_cap": 50.0,
        "mem_alloc_gb_vm": 5.0,
    }
    merged = SellableService._merge_compute_capacity(a, b)
    assert merged["cpu_cap"] == 15.0
    assert merged["mem_cap"] == 150.0
    assert merged["architecture"] == "unified"
