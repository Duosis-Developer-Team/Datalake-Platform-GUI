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


def test_resolve_hyperconverged_ram_uses_memory_metric():
    """Granular ``virt_hyperconverged_ram`` reads memory_gb even though resource_unit=GB collides with disk."""
    assets = {"hyperconv": {"cpu_total": 4.0, "memory_gb": 256.0, "disk_gb": 1024.0, "vm_count": 5}}
    used, note = resolve_used_quantity(
        category_code="virt_hyperconverged_ram",
        resource_unit="GB",
        assets=assets,
        totals={},
    )
    assert used == 256.0
    assert note is None


def test_resolve_hyperconverged_storage_uses_disk_metric():
    """Granular ``_storage`` suffix routes to disk_gb even when unit is GB."""
    assets = {"hyperconv": {"cpu_total": 4.0, "memory_gb": 256.0, "disk_gb": 1024.0, "vm_count": 5}}
    used, _ = resolve_used_quantity(
        category_code="virt_hyperconverged_storage",
        resource_unit="GB",
        assets=assets,
        totals={},
    )
    assert used == 1024.0


def test_resolve_classic_cpu_via_suffix():
    """Suffix takes precedence over the broad bucket default."""
    assets = {"classic": {"cpu_total": 12.0, "memory_gb": 64.0, "disk_gb": 500.0}}
    used, _ = resolve_used_quantity(
        category_code="virt_classic_cpu",
        resource_unit="vCPU",
        assets=assets,
        totals={},
    )
    assert used == 12.0


def test_resolve_zerto_storage_uses_protected_gb():
    totals = {"backup": {"zerto_protected_gb": 4096.0, "zerto_protected_vms": 8}}
    assets = {"backup": {}}
    used, _ = resolve_used_quantity(
        category_code="backup_zerto_storage",
        resource_unit="GB",
        assets=assets,
        totals=totals,
    )
    assert used == 4096.0


def test_resolve_unmatched_returns_zero():
    """Products with NULL category_code surface as zero usage (no panel)."""
    used, note = resolve_used_quantity(
        category_code=None,
        resource_unit="Adet",
        assets={},
        totals={},
    )
    assert used == 0.0
    assert note is None


def test_resolve_power_ram_falls_back_to_memory_total_gb():
    """IBM Power LPAR exposes memory under ``memory_total_gb``."""
    assets = {"power": {"cpu_total": 8.0, "memory_total_gb": 1024.0}}
    used, _ = resolve_used_quantity(
        category_code="virt_power_ram",
        resource_unit="GB",
        assets=assets,
        totals={},
    )
    assert used == 1024.0
