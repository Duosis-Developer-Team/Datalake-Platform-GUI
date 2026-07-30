"""Pure Veeam / Zerto license compliance helpers (no DB).

Status model (Summary + Backup surfaces; not Billing):

- usage > 0 and sold > 0 → ``ok``
- usage > 0 and sold = 0 → ``unsold_usage`` (license NO)
- usage = 0 and sold > 0 → ``crm_only``
- usage = 0 and sold = 0 → ``no_usage``
"""
from __future__ import annotations

from typing import Any, Literal

LicenseStatus = Literal["ok", "unsold_usage", "crm_only", "no_usage"]

# CRM productnumbers (000BLT-*) grouped by license category.
LICENSE_SKUS: dict[str, tuple[str, ...]] = {
    "veeam_backup": ("000BLT-144", "000BLT-145"),
    "veeam_replication": ("000BLT-147", "000BLT-148"),
    "zerto": ("000BLT-169",),
}


def evaluate_license(
    usage_qty: float | int | None,
    sold_qty: float | int | None,
) -> LicenseStatus:
    """Derive license compliance status from usage vs sold quantities."""
    usage = float(usage_qty or 0.0)
    sold = float(sold_qty or 0.0)
    has_usage = usage > 0
    has_sold = sold > 0
    if has_usage and has_sold:
        return "ok"
    if has_usage and not has_sold:
        return "unsold_usage"
    if not has_usage and has_sold:
        return "crm_only"
    return "no_usage"


def evaluate_backup_licenses(
    usage: dict[str, Any] | None,
    sold: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Evaluate compliance for each known license category.

    ``usage`` / ``sold`` may be keyed by category (``veeam_backup``, …) and/or
    by productnumber (``000BLT-144``, …). Category keys take precedence; SKU
    keys are summed when the category key is absent.
    """
    usage = usage or {}
    sold = sold or {}
    rows: list[dict[str, Any]] = []
    for category, skus in LICENSE_SKUS.items():
        usage_qty = _resolve_qty(usage, category, skus)
        sold_qty = _resolve_qty(sold, category, skus)
        status = evaluate_license(usage_qty, sold_qty)
        rows.append(
            {
                "category": category,
                "skus": list(skus),
                "usage_qty": usage_qty,
                "sold_qty": sold_qty,
                "status": status,
            }
        )
    return rows


def _resolve_qty(
    data: dict[str, Any],
    category: str,
    skus: tuple[str, ...],
) -> float:
    if category in data and data[category] is not None:
        try:
            return float(data[category])
        except (TypeError, ValueError):
            return 0.0
    total = 0.0
    for sku in skus:
        if sku not in data or data[sku] is None:
            continue
        try:
            total += float(data[sku])
        except (TypeError, ValueError):
            continue
    return total
