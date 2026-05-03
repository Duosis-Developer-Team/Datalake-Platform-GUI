"""
Map CRM product category + resource unit to observed customer usage (from CustomerAdapter bundle).

Used by SalesService for /sales/efficiency-by-category. Naming and docstrings in English per project rules.
"""
from __future__ import annotations

from typing import Any, Optional, Tuple


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _resource_kind(resource_unit: str | None) -> str:
    """Coarse bucket: cpu | memory | disk | count | other."""
    u = _norm(resource_unit)
    if "vcpu" in u or u in ("core", "cpu", "vcore"):
        return "cpu"
    if "user" in u or "seat" in u or "license" in u:
        return "count"
    if "vm" in u or u in ("adet", "piece", "unit", "ea"):
        return "count"
    if "tb" in u:
        return "memory"  # treat TB lines like capacity; caller may scale
    if "gb" in u or "gib" in u or "ram" in u or "memory" in u:
        return "memory"
    if "disk" in u or "storage" in u:
        return "disk"
    return "other"


def _virt_bucket(category_code: str | None) -> Optional[str]:
    cc = _norm(category_code)
    if cc.startswith("virt_classic"):
        return "classic"
    if cc.startswith("virt_hyper"):
        return "hyperconv"
    if cc.startswith("virt_nutanix"):
        return "pure_nutanix"
    if cc.startswith("virt_power"):
        return "power"
    return None


def resolve_used_quantity(
    *,
    category_code: str | None,
    resource_unit: str | None,
    assets: dict[str, Any],
    totals: dict[str, Any],
) -> Tuple[float, Optional[str]]:
    """
    Return (used_qty, usage_note). usage_note set when usage cannot be derived (e.g. S3 telemetry).
    """
    cc = category_code or "other"
    rk = _resource_kind(resource_unit)
    backup_totals = (totals.get("backup") or {}) if isinstance(totals, dict) else {}
    bassets = (assets.get("backup") or {}) if isinstance(assets, dict) else {}

    if _norm(cc).startswith("storage_s3"):
        return 0.0, "Usage telemetry pending for object storage (S3)."

    vb = _virt_bucket(cc)
    if vb:
        block = (assets.get(vb) or {}) if isinstance(assets, dict) else {}
        if rk == "cpu":
            return float(block.get("cpu_total", 0) or 0), None
        if rk == "memory":
            mem = block.get("memory_gb")
            if mem is None and vb == "power":
                mem = block.get("memory_total_gb")
            return float(mem or 0), None
        if rk == "disk":
            return float(block.get("disk_gb", 0) or 0), None
        if rk == "count":
            if vb == "power":
                return float(block.get("lpar_count", 0) or 0), None
            return float(block.get("vm_count", 0) or 0), None
        return 0.0, None

    if _norm(cc).startswith("backup_veeam"):
        v = float(backup_totals.get("veeam_defined_sessions", 0) or 0)
        return v, None

    if _norm(cc).startswith("backup_zerto"):
        if rk == "cpu":
            return float(backup_totals.get("zerto_protected_vms", 0) or 0) * 2.0, None
        return float(backup_totals.get("zerto_protected_vms", 0) or 0), None

    if _norm(cc).startswith("backup_netbackup"):
        return float(backup_totals.get("netbackup_post_dedup_gib", 0) or 0), None

    if _norm(cc).startswith("backup_"):
        vol = bassets.get("storage") or {}
        return float(vol.get("total_volume_capacity_gb", 0) or backup_totals.get("storage_volume_gb", 0) or 0), None

    # No usage signal for firewalls, licensing, generic SKUs
    return 0.0, None


def efficiency_status(
    efficiency_pct: float | None,
    sold_qty: float,
    *,
    under_pct: float = 80.0,
    over_pct: float = 110.0,
) -> str:
    """Classify a sold/used ratio. Bands come from gui_crm_calc_config when caller supplies them."""
    if sold_qty <= 0:
        return "no_sales"
    if efficiency_pct is None:
        return "unknown"
    if efficiency_pct < under_pct:
        return "under"
    if efficiency_pct <= over_pct:
        return "optimal"
    return "over"
