"""Global inventory replication storage multi-DC aggregate."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.services.sellable_service import SellableService
from shared.sellable.models import PanelResult, UnitConversion


def test_aggregate_replication_storage_multi_sums_dcs():
    svc = SellableService.__new__(SellableService)
    svc._dc_api_url = "http://dc-api"  # type: ignore[attr-defined]
    svc._fetch_veeam_datastore_storage = MagicMock(  # type: ignore[method-assign]
        side_effect=[
            {"stor_cap": 1000.0, "stor_provisioned_gb": 200.0 * 1024, "stor_used_pct": 20.0},
            {"stor_cap": 500.0, "stor_provisioned_gb": 100.0 * 1024, "stor_used_pct": 30.0},
        ]
    )
    out = svc._aggregate_replication_storage_multi(
        "backup_veeam_replication_classic",
        ["DC13", "DC14"],
    )
    assert out is not None
    total, alloc, util = out
    assert total == 1500.0
    # stor_provisioned_gb is converted GB→TB in _extract_compute_metrics then summed
    assert alloc == 300.0
    _ = util  # optional util when stor_pct absent


def test_apply_replication_storage_multi_sets_has_infra():
    sto = PanelResult(
        panel_key="backup_veeam_replication_classic_storage",
        label="Storage",
        family="backup_veeam_replication_classic",
        resource_kind="storage",
        display_unit="GB",
        dc_code="*",
        total=0.0,
        allocated=0.0,
        threshold_pct=85.0,
        sellable_raw=0.0,
        sellable_constrained=0.0,
        has_infra_source=False,
        has_price=True,
        unit_price_tl=1.0,
        potential_tl=0.0,
    )
    svc = SellableService.__new__(SellableService)
    svc._aggregate_replication_storage_multi = MagicMock(  # type: ignore[method-assign]
        return_value=(2000.0, 400.0, 25.0),
    )
    svc._lookup_conversion = MagicMock(  # type: ignore[method-assign]
        return_value=UnitConversion("TB", "GB", 1024.0, "multiply", False),
    )
    out = svc._apply_replication_storage_multi(
        [sto],
        "backup_veeam_replication_classic",
        ["DC13"],
        {},
    )
    assert out[0].has_infra_source is True
    assert out[0].total == 2000.0 * 1024.0
    assert out[0].allocated == 400.0 * 1024.0
