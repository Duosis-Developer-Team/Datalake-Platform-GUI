"""Wire customer backup usage + CRM sold license SKUs into license_compliance rows.

Pure helpers (no DB). SalesService / CustomerService supply totals and sold qtys.
Surfaces: Summary + Backup (K-03) — not Billing.
"""
from __future__ import annotations

from typing import Any

from shared.backup.license_compliance import (
    LICENSE_SKUS,
    evaluate_backup_licenses,
)

# Flat list of productnumbers used for sold-license SQL filters.
BACKUP_LICENSE_PRODUCTNUMBERS: tuple[str, ...] = tuple(
    sku for skus in LICENSE_SKUS.values() for sku in skus
)


def usage_signals_from_backup(
    backup_totals: dict[str, Any] | None,
    backup_assets: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Map adapter backup totals/assets to license category usage quantities.

    Veeam Cloud Connect jobs/sessions drive both backup and replication license
    categories (matching registry). Zerto uses protected VMs, falling back to VPG count.
    """
    totals = backup_totals or {}
    assets = backup_assets or {}

    veeam_sessions = float(totals.get("veeam_defined_sessions") or 0.0)
    if veeam_sessions <= 0:
        veeam_block = assets.get("veeam") if isinstance(assets, dict) else None
        if isinstance(veeam_block, dict):
            veeam_sessions = float(veeam_block.get("defined_sessions") or 0.0)

    zerto_vms = float(totals.get("zerto_protected_vms") or 0.0)
    zerto_block = assets.get("zerto") if isinstance(assets, dict) else None
    if isinstance(zerto_block, dict):
        if zerto_vms <= 0:
            zerto_vms = float(zerto_block.get("protected_total_vms") or 0.0)
        vpgs = zerto_block.get("vpgs")
        if isinstance(vpgs, list) and zerto_vms <= 0:
            zerto_vms = float(len(vpgs))

    return {
        "veeam_backup": veeam_sessions,
        "veeam_replication": veeam_sessions,
        "zerto": zerto_vms,
    }


def sold_qty_by_sku_from_rows(
    rows: list[dict[str, Any]] | None,
) -> dict[str, float]:
    """Sum sold quantities keyed by productnumber from active sales order lines."""
    sold: dict[str, float] = {}
    for row in rows or []:
        sku = str(
            row.get("productnumber")
            or row.get("product_number")
            or ""
        ).strip()
        if not sku:
            continue
        try:
            qty = float(row.get("sold_qty") if "sold_qty" in row else row.get("quantity") or 0.0)
        except (TypeError, ValueError):
            qty = 0.0
        sold[sku] = sold.get(sku, 0.0) + qty
    return sold


def build_backup_license_compliance(
    *,
    backup_totals: dict[str, Any] | None = None,
    backup_assets: dict[str, Any] | None = None,
    sold_by_sku: dict[str, Any] | None = None,
    sold_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return ``evaluate_backup_licenses`` rows for the customer backup bundle."""
    usage = usage_signals_from_backup(backup_totals, backup_assets)
    sold = dict(sold_by_sku or {})
    if sold_rows:
        for sku, qty in sold_qty_by_sku_from_rows(sold_rows).items():
            sold[sku] = sold.get(sku, 0.0) + qty
    return evaluate_backup_licenses(usage, sold)


def attach_license_compliance_to_bundle(
    bundle: dict[str, Any],
    compliance: list[dict[str, Any]],
) -> dict[str, Any]:
    """Mutate/return customer resources bundle with assets.backup.license_compliance."""
    if not isinstance(bundle, dict):
        return bundle
    assets = bundle.setdefault("assets", {})
    if not isinstance(assets, dict):
        return bundle
    backup = assets.setdefault("backup", {})
    if not isinstance(backup, dict):
        return bundle
    backup["license_compliance"] = list(compliance or [])
    return bundle
