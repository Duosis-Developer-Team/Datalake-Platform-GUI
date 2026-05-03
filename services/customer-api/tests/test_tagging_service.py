"""TaggingService — metric_key namespacing, in-memory cache, snapshot writes."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.services.tagging_service import (
    TaggingService,
    build_metric_key,
    family_namespace,
)
from shared.sellable.models import MetricValue, PanelResult


# ------------------------------------------------------------ namespace map


def test_family_namespace_known_family():
    assert family_namespace("virt_hyperconverged") == "virtualization.hyperconverged"
    assert family_namespace("backup_veeam_replication") == "backup.veeam_replication"
    assert family_namespace("storage_s3") == "storage.s3"


def test_family_namespace_unknown_family_falls_back_to_dotting():
    """An unmapped family becomes a dotted name so we never crash."""
    assert family_namespace("custom_brand_thing") == "custom.brand.thing"


def test_build_metric_key_canonical_format():
    key = build_metric_key("virt_hyperconverged", "ram", "total")
    assert key == "virtualization.hyperconverged.ram.total"


# ------------------------------------------------------------ runtime cache


def _ts() -> TaggingService:
    return TaggingService(webui=MagicMock(is_available=False))


def test_cache_set_and_get_round_trip():
    svc = _ts()
    mv = MetricValue("a.b.cpu.total", 16.0, "vCPU")
    svc.set(mv)
    assert svc.get("a.b.cpu.total") is mv


def test_cache_scope_isolation():
    svc = _ts()
    g = MetricValue("k", 1.0, "TL")
    d = MetricValue("k", 2.0, "TL", scope_type="dc", scope_id="ANK")
    svc.set(g)
    svc.set(d)
    assert svc.get("k").value == 1.0
    assert svc.get("k", scope_type="dc", scope_id="ANK").value == 2.0


def test_all_with_prefix_filters_correctly():
    svc = _ts()
    svc.set(MetricValue("virtualization.hyperconverged.ram.total", 100.0, "GB"))
    svc.set(MetricValue("virtualization.hyperconverged.cpu.total", 16.0, "vCPU"))
    svc.set(MetricValue("storage.s3.storage.total", 5000.0, "TB"))

    virt = svc.all_with_prefix("virtualization.")
    assert set(virt.keys()) == {
        "virtualization.hyperconverged.ram.total",
        "virtualization.hyperconverged.cpu.total",
    }
    s3 = svc.all_with_prefix("storage.")
    assert set(s3.keys()) == {"storage.s3.storage.total"}


# ------------------------------------------------------------ snapshot writer


def test_snapshot_writes_one_row_per_metric():
    pool = MagicMock()
    pool.is_available = True
    svc = TaggingService(webui=pool)

    metrics = [
        MetricValue("a.cpu.total", 10.0, "vCPU"),
        MetricValue("a.cpu.allocated", 4.0, "vCPU"),
    ]
    written = svc.snapshot(metrics)
    assert written == 2
    assert pool.execute.call_count == 2


def test_snapshot_skipped_when_pool_unavailable():
    pool = MagicMock()
    pool.is_available = False
    svc = TaggingService(webui=pool)
    written = svc.snapshot([MetricValue("a", 1.0, "TL")])
    assert written == 0
    pool.execute.assert_not_called()


def test_snapshot_continues_after_single_row_failure():
    pool = MagicMock()
    pool.is_available = True
    pool.execute.side_effect = [None, RuntimeError("disk full"), None]
    svc = TaggingService(webui=pool)
    written = svc.snapshot([
        MetricValue("a", 1.0, "TL"),
        MetricValue("b", 2.0, "TL"),
        MetricValue("c", 3.0, "TL"),
    ])
    # Only the two successful rows count.
    assert written == 2
    assert pool.execute.call_count == 3


# ------------------------------------------------------------ measures helper


def test_measures_from_panel_returns_six_canonical_measures():
    panel = PanelResult(
        panel_key="virt_hyperconverged_cpu",
        label="HC CPU",
        family="virt_hyperconverged",
        resource_kind="cpu",
        display_unit="vCPU",
        total=100.0,
        allocated=40.0,
        sellable_raw=40.0,
        sellable_constrained=30.0,
        unit_price_tl=1500.0,
        potential_tl=45000.0,
    )
    measures = TaggingService.measures_from_panel(panel)
    names = [m[0] for m in measures]
    assert names == [
        "total",
        "allocated",
        "sellable_raw",
        "sellable_constrained",
        "unit_price_tl",
        "potential_tl",
    ]
    # TL units stay TL even though display_unit=vCPU
    assert dict((n, u) for n, _, u in measures)["unit_price_tl"] == "TL"
    assert dict((n, u) for n, _, u in measures)["total"] == "vCPU"
