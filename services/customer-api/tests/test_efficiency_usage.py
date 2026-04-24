"""efficiency_usage helpers — sold vs used mapping."""
from __future__ import annotations

from app.utils.efficiency_usage import efficiency_status, resolve_used_quantity


def test_resolve_virt_classic_cpu():
    assets = {"classic": {"cpu_total": 10.0, "memory_gb": 0, "disk_gb": 0, "vm_count": 2}}
    totals = {"backup": {}}
    used, note = resolve_used_quantity(
        category_code="virt_classic",
        resource_unit="vCPU",
        assets=assets,
        totals=totals,
    )
    assert used == 10.0
    assert note is None


def test_storage_s3_note():
    used, note = resolve_used_quantity(
        category_code="storage_s3",
        resource_unit="GB",
        assets={},
        totals={},
    )
    assert used == 0.0
    assert note is not None


def test_efficiency_status():
    assert efficiency_status(50.0, 10.0) == "under"
    assert efficiency_status(90.0, 10.0) == "optimal"
    assert efficiency_status(120.0, 10.0) == "over"
    assert efficiency_status(None, 0.0) == "no_sales"
