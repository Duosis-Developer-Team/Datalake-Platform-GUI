"""Global CRM inventory overview — merges sellable infra panels with CRM entitled sales."""
from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.db.queries import crm_sales as sq
from app.db.queries import sellable as sellable_sq
from app.db.queries import service_mapping as smq
from app.services.crm_config_service import CrmConfigService
from app.services.sales_service import SalesService
from app.services.sellable_service import SellableService
from app.services.webui_db import WebuiPool
from app.utils.licensed_os_inventory import LICENCE_OS_PANEL_FAMILIES
from app.utils.usage_comparison import (
    aggregate_entitled_by_panel_key,
    merge_entitled_for_inventory_panel,
    panel_inventory_status,
    panel_inventory_status_virt,
)
from shared.sellable.computation import (
    apply_utilization_gate,
    compute_potential_tl,
)
from shared.sellable.models import PanelResult, ResourceRatio

logger = logging.getLogger(__name__)

_INVENTORY_CACHE_TTL_SEC = float(os.getenv("INVENTORY_OVERVIEW_CACHE_TTL", "600") or "600")
_INVENTORY_REDIS_PREFIX = "crm:inventory_overview:"
_INVENTORY_DC_PARALLELISM = max(1, int(os.getenv("INVENTORY_DC_PARALLELISM", "4") or "4"))

# Dual-track sellable profile (allocation / max util / avg util) for inventory UI.
_HOST_DUAL_PROFILE_FAMILIES: frozenset[str] = frozenset({
    "virt_classic",
    "virt_hyperconverged",
    "backup_veeam_replication_classic",
    "backup_zerto_replication_classic",
    "backup_veeam_replication_hyperconverged",
    "backup_zerto_replication_hyperconverged",
    "backup_veeam_replication",
    "backup_zerto_replication",
})
# Global inventory: recompute these via host-based multi-DC path (not Σ DC aggregates).
_HOST_DUAL_FAMILIES: frozenset[str] = frozenset({
    "virt_classic",
    "virt_hyperconverged",
    "backup_veeam_replication_classic",
    "backup_zerto_replication_classic",
    "backup_veeam_replication_hyperconverged",
    "backup_zerto_replication_hyperconverged",
})
_ALLOC_ONLY_FAMILIES: frozenset[str] = frozenset({"virt_power", "virt_power_hana"})
_REPLICATION_ALLOCATION_FAMILIES: frozenset[str] = frozenset({
    "backup_veeam_replication",
    "backup_zerto_replication",
    "backup_veeam_replication_classic",
    "backup_zerto_replication_classic",
    "backup_veeam_replication_hyperconverged",
    "backup_zerto_replication_hyperconverged",
})
# Inventory surfaces Resource Ratios + Compute/Storage coupling for Classic/HC.
_REPLICATION_RATIO_SURFACE_FAMILIES: frozenset[str] = frozenset({
    "backup_veeam_replication_classic",
    "backup_zerto_replication_classic",
    "backup_veeam_replication_hyperconverged",
    "backup_zerto_replication_hyperconverged",
})
_REPLICATION_RATIO_SHORT_LABELS: dict[str, str] = {
    "backup_veeam_replication_classic": "Veeam Classic",
    "backup_zerto_replication_classic": "Zerto Classic",
    "backup_veeam_replication_hyperconverged": "Veeam HC",
    "backup_zerto_replication_hyperconverged": "Zerto HC",
}
_INVENTORY_VIRT_FAMILIES: frozenset[str] = frozenset({
    "virt_classic",
    "virt_hyperconverged",
    "virt_power",
    "virt_power_hana",
})

# CRM sub-buckets merged into canonical inventory rows (KM → Klasik Mimari).
_INVENTORY_MERGED_CRM_SUB: dict[str, tuple[str, str]] = {
    "virt_classic_cpu": ("virt_km_cpu", "km"),
    "virt_classic_ram": ("virt_km_ram", "km"),
    "virt_classic_storage": ("virt_km_storage", "km"),
}

_VIRT_FAMILY_LABELS: dict[str, str] = {
    "virt_classic": "Klasik Mimari",
    "virt_hyperconverged": "Hyperconverged",
    "virt_power": "Power",
    "virt_power_hana": "Power HANA",
    "virt_intel_hana": "Intel HANA",
}

_RESOURCE_SUFFIXES = ("_cpu", "_ram", "_storage")

_S3_MERGE_TARGET = "storage_s3"
_S3_SITE_PANEL_KEYS: tuple[str, ...] = ("storage_s3_ankara", "storage_s3_istanbul")
_TB_BYTES = 1024.0 ** 4
_PHYSICAL_FREE_FAMILIES: frozenset[str] = frozenset({"storage_s3", "backup_netbackup"})

# Families shown in grouped accordion even when infra binding is CRM-only (when CRM entitled).
_INVENTORY_CRM_VISIBLE_FAMILIES: frozenset[str] = frozenset({
    _S3_MERGE_TARGET,
    *_INVENTORY_VIRT_FAMILIES,
    "backup_netbackup",
    "backup_veeam_replication",
    "backup_zerto_replication",
    "backup_veeam_replication_classic",
    "backup_zerto_replication_classic",
    "backup_veeam_replication_hyperconverged",
    "backup_zerto_replication_hyperconverged",
    "backup_image",
    "backup_remote",
    "backup_offsite",
    "backup_replication",
})

_NETBACKUP_INVENTORY_PANEL_KEYS: frozenset[str] = frozenset({
    "backup_netbackup_image",
    "backup_netbackup_application",
    "backup_netbackup_storage",
})

# Top-level CRM Inventory accordion groups (ADR-0025 / backup IA).
_INVENTORY_GROUP_IMAGE = "image_backup"
_INVENTORY_GROUP_APPLICATION = "application_backup"
_INVENTORY_GROUP_REPLICATION = "replication"
_INVENTORY_GROUP_LABELS: dict[str, str] = {
    _INVENTORY_GROUP_IMAGE: "Image Backup",
    _INVENTORY_GROUP_APPLICATION: "Application Backup",
    _INVENTORY_GROUP_REPLICATION: "Replication",
}
_INVENTORY_GROUP_ORDER: tuple[str, ...] = (
    _INVENTORY_GROUP_IMAGE,
    _INVENTORY_GROUP_APPLICATION,
    _INVENTORY_GROUP_REPLICATION,
)

# Panel / family → inventory accordion group (backup & replication only).
_PANEL_INVENTORY_GROUP: dict[str, str] = {
    "backup_netbackup_image": _INVENTORY_GROUP_IMAGE,
    "backup_image_hyperconverged": _INVENTORY_GROUP_IMAGE,
    "backup_remote_nutanix": _INVENTORY_GROUP_IMAGE,
    "backup_offsite_veeam": _INVENTORY_GROUP_IMAGE,
    "backup_offsite_s3": _INVENTORY_GROUP_IMAGE,
    "backup_veeam_image": _INVENTORY_GROUP_IMAGE,
    "backup_netbackup_application": _INVENTORY_GROUP_APPLICATION,
    "backup_netbackup_storage": _INVENTORY_GROUP_IMAGE,
}
_FAMILY_INVENTORY_GROUP: dict[str, str] = {
    "backup_image": _INVENTORY_GROUP_IMAGE,
    "backup_nutanix": _INVENTORY_GROUP_IMAGE,
    "backup_remote": _INVENTORY_GROUP_IMAGE,
    "backup_offsite": _INVENTORY_GROUP_IMAGE,
    "backup_veeam": _INVENTORY_GROUP_IMAGE,
    "backup_netbackup": _INVENTORY_GROUP_IMAGE,  # overridden per panel for application
    "backup_veeam_replication": _INVENTORY_GROUP_REPLICATION,
    "backup_zerto_replication": _INVENTORY_GROUP_REPLICATION,
    "backup_veeam_replication_classic": _INVENTORY_GROUP_REPLICATION,
    "backup_zerto_replication_classic": _INVENTORY_GROUP_REPLICATION,
    "backup_veeam_replication_hyperconverged": _INVENTORY_GROUP_REPLICATION,
    "backup_zerto_replication_hyperconverged": _INVENTORY_GROUP_REPLICATION,
    "backup_replication": _INVENTORY_GROUP_REPLICATION,
}

# Nutanix snapshots: sold↔used comparison only (no sellable / Potential Sales).
_COMPARISON_ONLY_FAMILIES: frozenset[str] = frozenset({
    "backup_image",
    "backup_nutanix",
})
_COMPARISON_ONLY_PANELS: frozenset[str] = frozenset({
    "backup_image_hyperconverged",
    "backup_remote_nutanix",
})


def _inventory_group_for_row(row: dict[str, Any]) -> str | None:
    """Return Image/Application/Replication group key, or None for non-backup rows."""
    panel_key = str(row.get("panel_key") or "")
    if panel_key in _PANEL_INVENTORY_GROUP:
        return _PANEL_INVENTORY_GROUP[panel_key]
    family = str(row.get("family") or "")
    if family == "backup_netbackup":
        if panel_key == "backup_netbackup_application":
            return _INVENTORY_GROUP_APPLICATION
        return _INVENTORY_GROUP_IMAGE
    if family in _FAMILY_INVENTORY_GROUP:
        return _FAMILY_INVENTORY_GROUP[family]
    if family.startswith("backup_veeam_replication") or family.startswith("backup_zerto"):
        return _INVENTORY_GROUP_REPLICATION
    if "DR" in str(row.get("service_label") or "") or panel_key.startswith("virt_") and "dr" in panel_key:
        return None
    return None


def _is_comparison_only_row(row: dict[str, Any]) -> bool:
    pk = str(row.get("panel_key") or "")
    fam = str(row.get("family") or "")
    return pk in _COMPARISON_ONLY_PANELS or fam in _COMPARISON_ONLY_FAMILIES


def _apply_comparison_only_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Nutanix image: hide sellable framing; keep CRM sold vs used."""
    if not _is_comparison_only_row(row):
        return row
    row = dict(row)
    row["sellable_profile"] = "comparison_only"
    row["sellable_qty"] = None
    row["sellable_alloc_qty"] = None
    row["sellable_max_qty"] = None
    row["sellable_avg_qty"] = None
    row["potential_tl"] = 0.0
    row["potential_tl_alloc"] = None
    row["potential_tl_max"] = None
    row["potential_tl_avg"] = None
    row["free_qty"] = None
    row["free_tl"] = None
    row["inventory_free_mode"] = "comparison"
    notes = list(row.get("notes") or [])
    note = "comparison_only: Nutanix snapshots are sold↔used (no sellable headroom)"
    if note not in notes:
        notes.append(note)
    row["notes"] = notes
    return row


def _format_resource_ratio(ratio: ResourceRatio) -> str:
    def _n(v: float) -> str:
        if abs(v - round(v)) < 1e-9:
            return str(int(round(v)))
        return f"{v:g}"

    return (
        f"{_n(float(ratio.cpu_per_unit))} : "
        f"{_n(float(ratio.ram_gb_per_unit))} : "
        f"{_n(float(ratio.storage_gb_per_unit))}"
    )


def _replication_config_fields(
    family_key: str,
    *,
    dc_code: str,
    ratio_lookup: dict[tuple[str, str], ResourceRatio],
    coupling_mode: str | None,
) -> dict[str, Any]:
    """Attach active Resource Ratio + storage coupling for Classic/HC replication."""
    if family_key not in _REPLICATION_RATIO_SURFACE_FAMILIES:
        return {}
    ratio = ratio_lookup.get((family_key, dc_code)) or ratio_lookup.get((family_key, "*"))
    if ratio is None:
        ratio = ResourceRatio(family=family_key)
    mode = coupling_mode if coupling_mode in ("auto", "merged", "separate") else "auto"
    return {
        "resource_ratio": {
            "cpu_per_unit": float(ratio.cpu_per_unit),
            "ram_gb_per_unit": float(ratio.ram_gb_per_unit),
            "storage_gb_per_unit": float(ratio.storage_gb_per_unit),
        },
        "resource_ratio_fmt": _format_resource_ratio(ratio),
        "storage_coupling_mode": mode,
        "resource_ratio_label": _REPLICATION_RATIO_SHORT_LABELS.get(family_key, family_key),
    }


def _summarize_replication_ratios(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One chip per Classic/HC family present in the Replication accordion."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        fam = str(row.get("family") or "")
        if fam not in _REPLICATION_RATIO_SURFACE_FAMILIES or fam in seen:
            continue
        if not row.get("resource_ratio_fmt"):
            continue
        seen.add(fam)
        out.append({
            "family": fam,
            "label": row.get("resource_ratio_label") or _REPLICATION_RATIO_SHORT_LABELS.get(fam, fam),
            "resource_ratio_fmt": row.get("resource_ratio_fmt"),
            "storage_coupling_mode": row.get("storage_coupling_mode") or "auto",
        })
    return out


def _regroup_backup_families(families_out: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse backup panel families into Image | Application | Replication."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    passthrough: list[dict[str, Any]] = []
    for fam in families_out:
        panels = fam.get("panels") or []
        if not panels:
            continue
        # If any panel maps to a backup inventory group, regroup those panels.
        backup_panels = []
        other_panels = []
        for row in panels:
            g = _inventory_group_for_row(row)
            if g:
                backup_panels.append((g, row))
            else:
                other_panels.append(row)
        for g, row in backup_panels:
            grouped[g].append(row)
        if other_panels:
            passthrough.append({
                **fam,
                "panels": other_panels,
                "panel_count": len(other_panels),
            })
        elif not backup_panels:
            passthrough.append(fam)

    rebuilt: list[dict[str, Any]] = []
    for gkey in _INVENTORY_GROUP_ORDER:
        rows = grouped.get(gkey) or []
        # Hide empty Offsite/Remote when no sold and no infra
        rows = [
            r for r in rows
            if not (
                str(r.get("panel_key") or "") in (
                    "backup_remote_nutanix",
                    "backup_offsite_veeam",
                    "backup_offsite_s3",
                )
                and float(r.get("crm_sold_qty") or 0) <= 0
                and not r.get("has_infra_source")
            )
        ]
        if not rows:
            continue
        label = _INVENTORY_GROUP_LABELS[gkey]
        rows_sorted = sorted(rows, key=lambda r: r.get("service_label") or "")
        entry: dict[str, Any] = {
            "family": gkey,
            "label": label,
            "family_label": label,
            "dc_code": rows_sorted[0].get("dc_code") or "*",
            "panels": rows_sorted,
            "panel_count": len(rows_sorted),
            "has_infra": any(r.get("has_infra_source") for r in rows_sorted),
            "sellable_profile": (
                "comparison_only"
                if gkey == _INVENTORY_GROUP_IMAGE
                and all(_is_comparison_only_row(r) for r in rows_sorted)
                else "standard"
            ),
        }
        if gkey == _INVENTORY_GROUP_REPLICATION:
            entry["resource_ratio_summary"] = _summarize_replication_ratios(rows_sorted)
        rebuilt.append(entry)
    # Keep non-backup families (virt, S3, …) after backup groups
    passthrough.sort(key=lambda f: (f.get("family_label") or f.get("family") or "").lower())
    return rebuilt + passthrough

# Families rendered nowhere on /crm/inventory-overview. virt_power shares the
# same IBM Power infrastructure as virt_power_hana (see sellable_service:261),
# so showing both reads the underlying capacity twice. Filtered from the panel
# list before families AND summary are built, so the table and the KPI cards
# can never disagree about what is on the page.
_INVENTORY_HIDDEN_FAMILIES: frozenset[str] = frozenset({"virt_power"})


def _drop_hidden_families(panel_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        r for r in panel_rows
        if str(r.get("family") or "") not in _INVENTORY_HIDDEN_FAMILIES
    ]


def _humanize_token(value: str) -> str:
    return (value or "").replace("_", " ").replace(".", " ").strip().title()


def _infer_family_key(panel_key: str, panel_defs: dict[str, dict[str, Any]]) -> str:
    if panel_key in panel_defs:
        return str(panel_defs[panel_key].get("family") or panel_key)
    for suffix in _RESOURCE_SUFFIXES:
        if panel_key.endswith(suffix):
            return panel_key[: -len(suffix)]
    return panel_key


def _family_label(
    family_key: str,
    *,
    service_label: str,
    gui_tab_binding: str | None,
) -> str:
    if family_key in _VIRT_FAMILY_LABELS:
        return _VIRT_FAMILY_LABELS[family_key]
    if " — " in service_label:
        return service_label.split(" — ", 1)[0].strip()
    if gui_tab_binding:
        parts = [p for p in gui_tab_binding.split(".") if p]
        if len(parts) >= 2:
            return _humanize_token(parts[-1])
        if parts:
            return _humanize_token(parts[0])
    return _humanize_token(family_key)


def _coerce_bool(value: Any, *, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "t", "yes", "y")


def _bytes_to_tb(value: float) -> float:
    return float(value or 0.0) / _TB_BYTES


def _value_tl_from_catalog_price(
    qty: float | None,
    *,
    unit_price_tl: float | None,
    has_price: bool,
) -> float | None:
    """Monetary value for a physical qty using CRM catalog / override unit price."""
    if qty is None or not has_price or unit_price_tl is None:
        return None
    try:
        price = float(unit_price_tl)
    except (TypeError, ValueError):
        return None
    if price <= 0.0:
        return None
    return compute_potential_tl(float(qty), price)


def _netbackup_job_metrics_for_panel(
    metrics: dict[str, Any],
    panel_key: str,
) -> dict[str, float]:
    """Pick Image/Application job slice; Total/Free stay on shared pool fields."""
    by_cat = metrics.get("by_category") if isinstance(metrics, dict) else None
    category: str | None = None
    if panel_key == "backup_netbackup_image":
        category = "image"
    elif panel_key == "backup_netbackup_application":
        category = "application"
    slice_m: dict[str, Any] = {}
    if category and isinstance(by_cat, dict):
        raw = by_cat.get(category)
        if isinstance(raw, dict):
            slice_m = raw
    return {
        "pre_dedup_bytes": float(
            slice_m.get("pre_dedup_bytes", metrics.get("pre_dedup_bytes", 0.0)) or 0.0
        ),
        "used_post_dedup_bytes": float(
            slice_m.get(
                "used_post_dedup_bytes",
                metrics.get("used_post_dedup_bytes", 0.0),
            )
            or 0.0
        ),
        "dedup_savings_bytes": float(
            slice_m.get(
                "dedup_savings_bytes",
                metrics.get("dedup_savings_bytes", 0.0),
            )
            or 0.0
        ),
        "dedup_savings_pct": float(
            slice_m.get(
                "dedup_savings_pct",
                metrics.get("dedup_savings_pct", 0.0),
            )
            or 0.0
        ),
        "dedup_factor": float(
            slice_m.get("dedup_factor", metrics.get("dedup_factor", 0.0)) or 0.0
        ),
    }


def _apply_netbackup_inventory_fields(
    row: dict[str, Any],
    metrics: dict[str, Any],
    *,
    under_pct: float = 80.0,
    over_pct: float = 110.0,
) -> dict[str, Any]:
    """Enrich NetBackup row with dual-basis used (PreDedup) and PostDedup cost.

    K-01: customer billable ``used_qty`` = PreDedup; PostDedup is cost-only.
    Total/Free/pool used = shared disk pool; Transfer/Post = Image or App jobs.
    """
    if not row.get("has_infra_source"):
        return row
    row = dict(row)
    has_price = bool(row.get("has_price"))
    unit_price = row.get("unit_price_tl")
    panel_key = str(row.get("panel_key") or "")
    job_m = _netbackup_job_metrics_for_panel(metrics, panel_key)
    pre = _bytes_to_tb(job_m.get("pre_dedup_bytes", 0.0))
    post = _bytes_to_tb(job_m.get("used_post_dedup_bytes", 0.0))
    if post <= 0.0 and row.get("used_qty") is not None:
        try:
            post = float(row.get("used_qty") or 0.0)
        except (TypeError, ValueError):
            post = 0.0

    pool_used = _bytes_to_tb(metrics.get("used_pool_bytes", 0.0))
    total_qty = row.get("total")
    try:
        total_f = float(total_qty) if total_qty is not None else None
    except (TypeError, ValueError):
        total_f = None
    crm_sold = float(row.get("crm_sold_qty") or 0.0)
    row["inventory_free_mode"] = "physical"
    row["free_qty"] = _bytes_to_tb(metrics.get("available_bytes", 0.0))
    row["unsold_qty"] = (
        max(total_f - crm_sold, 0.0) if total_f is not None else None
    )
    row["pool_used_qty"] = pool_used
    row["pre_dedup_qty"] = pre
    row["post_dedup_qty"] = post
    row["dedup_savings_qty"] = _bytes_to_tb(job_m.get("dedup_savings_bytes", 0.0))
    row["dedup_savings_pct"] = float(job_m.get("dedup_savings_pct") or 0.0)
    row["dedup_factor"] = float(job_m.get("dedup_factor") or 0.0)
    cat_label = (
        "image" if panel_key == "backup_netbackup_image"
        else "app" if panel_key == "backup_netbackup_application"
        else "jobs"
    )
    # Pool used + category PostDedup live under Used (not Total).
    row["used_compare_note"] = (
        f"Pool used: {pool_used:,.1f} TB · {cat_label} PostDedup: {post:,.1f} TB"
    )
    row["free_tl"] = _value_tl_from_catalog_price(
        row.get("free_qty"),
        unit_price_tl=unit_price,
        has_price=has_price,
    )
    row["unsold_tl"] = _value_tl_from_catalog_price(
        row.get("unsold_qty"),
        unit_price_tl=unit_price,
        has_price=has_price,
    )
    row["post_dedup_tl"] = _value_tl_from_catalog_price(
        post,
        unit_price_tl=unit_price,
        has_price=has_price,
    )
    margin_qty = max(pre - post, 0.0)
    row["dedup_margin_tl"] = _value_tl_from_catalog_price(
        margin_qty,
        unit_price_tl=unit_price,
        has_price=has_price,
    )

    # Billable inventory used = PreDedup when jobs transfer data is present.
    if pre > 0.0:
        row["used_qty"] = pre
        row["used_tl"] = _value_tl_from_catalog_price(
            pre,
            unit_price_tl=unit_price,
            has_price=has_price,
        )
        crm_sold = float(row.get("crm_sold_qty") or 0.0)
        row["delta_used_vs_crm"] = pre - crm_sold
        row["overage_qty"] = max(0.0, pre - crm_sold)
        row["efficiency_pct"] = (
            round((pre / crm_sold) * 100.0, 2) if crm_sold > 0 else None
        )
        row["status"] = panel_inventory_status(
            crm_sold_qty=crm_sold,
            used_qty=pre,
            has_infra_source=True,
            under_pct=under_pct,
            over_pct=over_pct,
        )

    # PreDedup enrichment overwrites used via bytes→TB helpers; clear stale
    # KiB→TB conversion false positives from sellable metadata mismatch.
    notes = [
        n for n in (row.get("notes") or [])
        if "unit_conversion_missing" not in (n or "")
    ]
    row["notes"] = notes
    if row.get("suspect_reason") == "unit_conversion_missing":
        row["suspect_reason"] = None
        if row.get("data_quality") == "suspect":
            row["data_quality"] = None
    return row


def _inventory_panel_hidden(
    panel_key: str,
    panel_defs: dict[str, dict[str, Any]],
) -> bool:
    """Return True when panel registry marks the row hidden from inventory."""
    meta = panel_defs.get(panel_key)
    if meta is None:
        return False
    if not _coerce_bool(meta.get("inventory_visible"), default=True):
        return True
    merge_target = str(meta.get("inventory_merge_target") or "").strip()
    if merge_target and merge_target != panel_key:
        return True
    return False


def _merge_source_keys_for_target(
    target_key: str,
    panel_defs: dict[str, dict[str, Any]],
) -> list[str]:
    return sorted(
        pk
        for pk, meta in panel_defs.items()
        if str(meta.get("inventory_merge_target") or "").strip() == target_key
    )


def _merge_entitled_for_target(
    target_key: str,
    entitled_by_panel: dict[str, dict[str, Any]],
    panel_defs: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Merge CRM buckets from source panels into one inventory target row."""
    source_keys = _merge_source_keys_for_target(target_key, panel_defs)
    if target_key == _S3_MERGE_TARGET:
        source_keys = sorted(set(source_keys) | set(_S3_SITE_PANEL_KEYS))
    buckets = [
        entitled_by_panel.get(key)
        for key in source_keys
        if entitled_by_panel.get(key)
    ]
    legacy_bucket = entitled_by_panel.get(target_key)
    if not buckets:
        return legacy_bucket

    entitled_qty = sum(float(b.get("entitled_qty") or 0.0) for b in buckets)
    entitled_tl = sum(float(b.get("entitled_amount_tl") or 0.0) for b in buckets)
    product_ids: set[str] = set()
    product_names: set[str] = set()
    for bucket in buckets:
        product_ids.update(str(pid) for pid in (bucket.get("product_ids") or []) if pid)
        product_names.update(str(name) for name in (bucket.get("product_names") or []) if name)

    base = dict(buckets[0])
    base["panel_key"] = target_key
    base["entitled_qty"] = entitled_qty
    base["entitled_amount_tl"] = entitled_tl
    base["product_ids"] = sorted(product_ids)
    base["product_names"] = sorted(product_names)
    if legacy_bucket:
        base["entitled_qty"] += float(legacy_bucket.get("entitled_qty") or 0.0)
        base["entitled_amount_tl"] += float(legacy_bucket.get("entitled_amount_tl") or 0.0)
        product_ids.update(str(pid) for pid in (legacy_bucket.get("product_ids") or []) if pid)
        product_names.update(
            str(name) for name in (legacy_bucket.get("product_names") or []) if name
        )
        base["product_ids"] = sorted(product_ids)
        base["product_names"] = sorted(product_names)
    return base


def _include_row_in_families(row: dict[str, Any]) -> bool:
    """Whether a panel row belongs in the grouped family accordion."""
    if row.get("infra_binding") != "crm_only":
        return True
    family_key = str(row.get("family") or "other")
    if family_key not in _INVENTORY_CRM_VISIBLE_FAMILIES:
        return False
    return float(row.get("crm_sold_tl") or 0) > 0 or bool(row.get("has_infra_source"))


def _upsert_inventory_row(
    panel_rows: list[dict[str, Any]],
    crm_only_panels: list[dict[str, Any]],
    row: dict[str, Any],
) -> None:
    """Replace any prior row for the same panel_key (e.g. CRM-only before infra merge)."""
    panel_key = str(row.get("panel_key") or "")
    panel_rows[:] = [r for r in panel_rows if str(r.get("panel_key") or "") != panel_key]
    crm_only_panels[:] = [r for r in crm_only_panels if str(r.get("panel_key") or "") != panel_key]
    panel_rows.append(row)
    if row.get("infra_binding") == "crm_only":
        crm_only_panels.append(row)


def _build_merged_infra_panel(
    target_key: str,
    candidates: list[PanelResult],
    panel_defs: dict[str, dict[str, Any]],
) -> PanelResult | None:
    """Collapse site-scoped source panels into one inventory row (max node metrics)."""
    found = list(candidates)
    if not found:
        return None

    template = max(found, key=lambda p: float(p.allocated or 0.0))
    total = max(float(p.total or 0.0) for p in found)
    allocated = max(float(p.allocated or 0.0) for p in found)
    sellable_raw = apply_utilization_gate(
        total,
        allocated,
        None,
        float(template.threshold_pct or 80.0),
    )
    sellable_constrained = sellable_raw
    unit_price = float(template.unit_price_tl or 0.0)
    potential_tl = (
        compute_potential_tl(sellable_constrained, unit_price)
        if template.has_price
        else 0.0
    )
    meta = panel_defs.get(target_key) or {}
    label = str(meta.get("label") or template.label or target_key)
    family = str(meta.get("family") or template.family or target_key)
    notes = list(template.notes or [])
    merge_note = f"merged from {len(found)} source panel(s)"
    if merge_note not in notes:
        notes.append(merge_note)

    return PanelResult(
        panel_key=target_key,
        label=label,
        family=family,
        resource_kind=template.resource_kind,
        display_unit=template.display_unit,
        dc_code="*",
        total=total,
        allocated=allocated,
        threshold_pct=template.threshold_pct,
        sellable_raw=sellable_raw,
        sellable_constrained=sellable_constrained,
        unit_price_tl=unit_price,
        potential_tl=potential_tl,
        ratio_bound=False,
        gate_blocked=sellable_raw <= 0.0 and total > 0.0,
        has_infra_source=True,
        has_price=template.has_price,
        notes=notes,
        computation_mode="aggregated",
        constraint_reason="none",
    )


def _build_merged_infra_panels(
    panels: list[PanelResult],
    panel_defs: dict[str, dict[str, Any]],
) -> list[PanelResult]:
    """Build synthetic inventory panels for merge targets declared in panel registry."""
    targets: dict[str, list[PanelResult]] = defaultdict(list)
    for panel in panels:
        target = str((panel_defs.get(panel.panel_key) or {}).get("inventory_merge_target") or "").strip()
        if target:
            targets[target].append(panel)

    merged: list[PanelResult] = []
    for target_key in sorted(targets):
        built = _build_merged_infra_panel(target_key, targets[target_key], panel_defs)
        if built is not None:
            merged.append(built)
    return merged


def _merge_s3_site_entitled(
    entitled_by_panel: dict[str, dict[str, Any]],
    panel_defs: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Backward-compatible wrapper for storage_s3 entitled merge."""
    return _merge_entitled_for_target("storage_s3", entitled_by_panel, panel_defs)


def _build_merged_s3_panel(
    candidates: list[PanelResult],
    panel_defs: dict[str, dict[str, Any]] | None = None,
) -> PanelResult | None:
    """Backward-compatible wrapper for storage_s3 infra merge."""
    panel_defs = panel_defs or {}
    source_keys = _merge_source_keys_for_target("storage_s3", panel_defs)
    if not source_keys:
        source_keys = ["storage_s3_ankara", "storage_s3_istanbul"]
    found = [p for p in candidates if p.panel_key in source_keys]
    return _build_merged_infra_panel("storage_s3", found, panel_defs)


def _crm_product_names_summary(names: list[str] | None, limit: int = 3) -> str:
    items = [n for n in (names or []) if n]
    if not items:
        return ""
    if len(items) <= limit:
        return ", ".join(items)
    rest = len(items) - limit
    return f"{', '.join(items[:limit])} (+{rest} more)"


def _merge_panel_results(existing: PanelResult | None, incoming: PanelResult) -> PanelResult:
    """Sum total/allocated across DC-scoped PanelResult rows; sellable is recomputed later."""
    if existing is None:
        mode = incoming.computation_mode
        if incoming.has_infra_source and not mode:
            mode = "aggregated"
        return PanelResult(
            panel_key=incoming.panel_key,
            label=incoming.label,
            family=incoming.family,
            resource_kind=incoming.resource_kind,
            display_unit=incoming.display_unit,
            dc_code="*",
            total=float(incoming.total or 0.0),
            allocated=float(incoming.allocated or 0.0),
            threshold_pct=incoming.threshold_pct,
            sellable_raw=0.0,
            sellable_constrained=0.0,
            unit_price_tl=incoming.unit_price_tl,
            potential_tl=0.0,
            ratio_bound=False,
            gate_blocked=False,
            has_infra_source=incoming.has_infra_source,
            has_price=incoming.has_price,
            notes=list(incoming.notes or []),
            computation_mode=mode,
            constraint_reason=incoming.constraint_reason,
        )

    notes = list(existing.notes or [])
    for note in incoming.notes or []:
        if note and note not in notes:
            notes.append(note)

    mode = "aggregated"
    if existing.computation_mode == "host_based" or incoming.computation_mode == "host_based":
        mode = "host_based"

    return PanelResult(
        panel_key=existing.panel_key,
        label=existing.label,
        family=existing.family,
        resource_kind=existing.resource_kind,
        display_unit=existing.display_unit,
        dc_code="*",
        total=float(existing.total or 0.0) + float(incoming.total or 0.0),
        allocated=float(existing.allocated or 0.0) + float(incoming.allocated or 0.0),
        threshold_pct=existing.threshold_pct,
        sellable_raw=0.0,
        sellable_constrained=0.0,
        unit_price_tl=existing.unit_price_tl or incoming.unit_price_tl,
        potential_tl=0.0,
        ratio_bound=False,
        gate_blocked=False,
        has_infra_source=existing.has_infra_source or incoming.has_infra_source,
        has_price=existing.has_price or incoming.has_price,
        notes=notes,
        computation_mode=mode,
        constraint_reason="none",
    )


def _assess_data_quality(
    panel: PanelResult,
    *,
    crm_sold: float,
) -> tuple[str | None, str | None]:
    """Return (data_quality flag, suspect_reason) for inventory rows."""
    if not panel.has_infra_source:
        return None, None
    if any("unit_conversion_missing" in (note or "") for note in (panel.notes or [])):
        return "suspect", "unit_conversion_missing"
    total = float(panel.total or 0.0)
    allocated = float(panel.allocated or 0.0)
    crm = float(crm_sold or 0.0)
    # Licence panels compare a sold quantity with a detected guest count. Selling
    # more licences than there are guests is over-licensing — a real commercial
    # position, not a unit mismatch — so the "check units" suspicion does not
    # apply. total == allocated there by construction, so neither does the other.
    if panel.panel_key in LICENCE_OS_PANEL_FAMILIES:
        return None, None
    if panel.family not in _INVENTORY_VIRT_FAMILIES and allocated > total > 0:
        if panel.family in _REPLICATION_ALLOCATION_FAMILIES:
            return "suspect", "allocation_exceeds_total"
        return "suspect", "used_exceeds_total"
    if crm > total > 0 and panel.family not in _INVENTORY_VIRT_FAMILIES:
        return "suspect", "crm_exceeds_total"
    if total > 1e9:
        return "suspect", "total_scale_anomaly"
    if (
        allocated <= 0.0
        and total > 0.0
        and (panel.computation_mode or "") in ("aggregated", "cluster_fallback")
        and panel.family not in _INVENTORY_VIRT_FAMILIES
        and panel.panel_key != "backup_netbackup_storage"
    ):
        return "suspect", "zero_used_with_capacity"
    return None, None


def _family_sellable_profile(family_key: str) -> str:
    """Column profile for inventory report sellable tracks."""
    if family_key in _HOST_DUAL_PROFILE_FAMILIES:
        return "dual_track"
    if family_key in _ALLOC_ONLY_FAMILIES:
        return "allocation_only"
    return "standard"


def _sellable_track_fields(
    panel: PanelResult,
    *,
    has_infra: bool,
    hide_used: bool = False,
) -> dict[str, Any]:
    """Dual-track sellable quantities and TL for virtualization / replication families."""
    if not has_infra:
        return {
            "unit_price_tl": None,
            "used_tl": None,
            "sellable_profile": _family_sellable_profile(panel.family),
            "sellable_alloc_qty": None,
            "sellable_max_qty": None,
            "sellable_avg_qty": None,
            "potential_tl_alloc": None,
            "potential_tl_max": None,
            "potential_tl_avg": None,
            "sellable_tl_min": None,
            "sellable_tl_max": None,
        }
    unit_price = float(panel.unit_price_tl or 0.0)
    used = float(panel.allocated or 0.0)
    alloc_qty = panel.sellable_allocation
    max_qty = panel.sellable_max_util
    if alloc_qty is None and panel.sellable_effective is not None:
        alloc_qty = panel.sellable_effective
    if max_qty is None and panel.resource_kind == "ram" and panel.sellable_effective is not None:
        max_qty = panel.sellable_effective
    avg_qty = panel.sellable_avg_util
    # Replication storage has no host dual tracks — surface constrained as the triad
    # (including 0.0 so the UI shows 0, not em-dash).
    if (
        panel.family in _REPLICATION_ALLOCATION_FAMILIES
        and (panel.resource_kind or "").lower() == "storage"
    ):
        constrained = panel.sellable_constrained
        if constrained is None and panel.sellable_effective is not None:
            constrained = panel.sellable_effective
        if constrained is not None:
            constrained_f = float(constrained)
            if alloc_qty is None:
                alloc_qty = constrained_f
            if max_qty is None:
                max_qty = constrained_f
            if avg_qty is None:
                avg_qty = constrained_f
    # Replication: triad TL = qty × price (not IBM alternate min/max from Potential Sales).
    if panel.family in _REPLICATION_ALLOCATION_FAMILIES and panel.has_price:
        potential_tl_alloc = (
            compute_potential_tl(alloc_qty, unit_price) if alloc_qty is not None else None
        )
        potential_tl_max = (
            compute_potential_tl(max_qty, unit_price) if max_qty is not None else None
        )
    else:
        potential_tl_alloc = panel.potential_tl_min
        if potential_tl_alloc is None and panel.potential_tl is not None:
            potential_tl_alloc = panel.potential_tl
        potential_tl_max = panel.potential_tl_max
    potential_tl_avg = (
        compute_potential_tl(avg_qty, unit_price)
        if avg_qty is not None and panel.has_price
        else None
    )
    used_tl = None
    if not hide_used and panel.has_price:
        used_tl = compute_potential_tl(used, unit_price)
    # Row-level sellable TL bounds for inventory header interval aggregation.
    track_tls = [
        v for v in (potential_tl_alloc, potential_tl_max, potential_tl_avg) if v is not None
    ]
    sellable_tl_min = min(track_tls) if track_tls else None
    sellable_tl_max = max(track_tls) if track_tls else None
    return {
        "unit_price_tl": unit_price if panel.has_price else None,
        "used_tl": used_tl,
        "sellable_profile": _family_sellable_profile(panel.family),
        "sellable_alloc_qty": alloc_qty,
        "sellable_max_qty": max_qty,
        "sellable_avg_qty": avg_qty,
        "potential_tl_alloc": potential_tl_alloc,
        "potential_tl_max": potential_tl_max,
        "potential_tl_avg": potential_tl_avg,
        "sellable_tl_min": sellable_tl_min,
        "sellable_tl_max": sellable_tl_max,
    }


class InventoryOverviewService:
    """Build global capacity vs CRM sold vs infra used overview."""

    def __init__(
        self,
        *,
        sellable: SellableService,
        sales: SalesService,
        webui: WebuiPool,
        config: CrmConfigService | None = None,
        crm_redis=None,
    ):
        self._sellable = sellable
        self._sales = sales
        self._webui = webui
        self._config = config or CrmConfigService(webui)
        self._crm_redis = crm_redis
        self._mapping_cache: tuple[float, dict[str, dict[str, Any]]] | None = None
        self._pages_cache: tuple[float, dict[str, dict[str, Any]]] | None = None
        self._panel_defs_cache: tuple[float, dict[str, dict[str, Any]]] | None = None

    def is_available(self) -> bool:
        return self._sellable.is_available

    def _load_product_mapping(self) -> dict[str, dict[str, Any]]:
        now = time.perf_counter()
        if self._mapping_cache and (now - self._mapping_cache[0]) < 120.0:
            return self._mapping_cache[1]
        if not self._webui or not self._webui.is_available:
            return {}
        rows = self._webui.run_rows(smq.LIST_SERVICE_MAPPINGS_WEBUI)
        mapping = {str(r["productid"]): r for r in rows if r.get("productid")}
        self._mapping_cache = (now, mapping)
        return mapping

    def _load_service_pages(self) -> dict[str, dict[str, Any]]:
        now = time.perf_counter()
        if self._pages_cache and (now - self._pages_cache[0]) < 120.0:
            return self._pages_cache[1]
        if not self._webui or not self._webui.is_available:
            return {}
        rows = self._webui.run_rows(smq.LIST_SERVICE_PAGES)
        pages = {str(r["page_key"]): r for r in rows if r.get("page_key")}
        self._pages_cache = (now, pages)
        return pages

    def _load_panel_defs(self) -> dict[str, dict[str, Any]]:
        now = time.perf_counter()
        if self._panel_defs_cache and (now - self._panel_defs_cache[0]) < 120.0:
            return self._panel_defs_cache[1]
        if not self._webui or not self._webui.is_available:
            return {}
        rows = self._webui.run_rows(sellable_sq.LIST_PANEL_DEFS)
        defs = {str(r["panel_key"]): r for r in rows if r.get("panel_key")}
        self._panel_defs_cache = (now, defs)
        return defs

    def _mapped_product_ids(self, mapping: dict[str, dict[str, Any]]) -> list[str]:
        return [
            pid
            for pid, row in mapping.items()
            if (row.get("source") or "") != "unmatched" and row.get("category_code")
        ]

    def _panel_unit_index(self, panels: list[PanelResult]) -> dict[str, str]:
        return {p.panel_key: p.display_unit for p in panels if p.panel_key}

    def _list_infra_dc_codes(self) -> list[str]:
        """Return DC codes for global inventory per-DC aggregation.

        Prefer explicit per-DC rows in ``gui_panel_infra_source``. When all bindings
        are wildcard-only (``dc_code='*'`` with ``filter_clause``), fall back to
        active datacenter codes from datacenter-api / Redis so panels are computed
        once per DC instead of a single global SQL SUM.
        """
        codes: list[str] = []
        if self._webui and self._webui.is_available:
            rows = self._webui.run_rows(sellable_sq.LIST_INFRA_DC_CODES)
            codes = [
                str(r["dc_code"]).strip()
                for r in rows
                if r.get("dc_code") and str(r["dc_code"]).strip() not in ("", "*")
            ]
        if codes:
            return codes
        fallback = self._sellable._fetch_datacenter_codes()
        if not isinstance(fallback, list):
            fallback = []
        if fallback:
            logger.info(
                "inventory overview: wildcard-only infra bindings; aggregating across "
                "%d datacenter code(s) from platform",
                len(fallback),
            )
        return fallback

    def _load_global_only_panel_keys(self) -> frozenset[str]:
        """Panels with wildcard-only infra bindings and no per-DC filter."""
        if not self._webui or not self._webui.is_available:
            return frozenset()
        rows = self._webui.run_rows(sellable_sq.LIST_GLOBAL_ONLY_PANEL_KEYS)
        return frozenset(
            str(r["panel_key"]).strip()
            for r in rows
            if r.get("panel_key")
        )

    def _load_site_scoped_panel_keys(self) -> frozenset[str]:
        """Panels tied to a fixed site (e.g. storage_s3_ankara) — never SUM-merged per infra DC."""
        keys: set[str] = set()
        if self._webui and self._webui.is_available:
            rows = self._webui.run_rows(sellable_sq.LIST_SITE_SCOPED_PANEL_KEYS)
            keys.update(
                str(r["panel_key"]).strip()
                for r in rows
                if r.get("panel_key")
            )
        if not keys:
            keys.update(_S3_SITE_PANEL_KEYS)
            logger.info(
                "inventory overview: site-scoped panel SQL empty; using S3 fallback keys %s",
                list(_S3_SITE_PANEL_KEYS),
            )
        return frozenset(keys)

    def _ensure_s3_site_panels(
        self,
        panels: list[PanelResult],
        *,
        force_recompute: bool = False,
    ) -> list[PanelResult]:
        """Ensure S3 site nodes are present for merge (not dropped by per-DC aggregation)."""
        present = {p.panel_key for p in panels}
        missing = [key for key in _S3_SITE_PANEL_KEYS if key not in present]
        if not missing:
            return panels
        site_panels = self._sellable.compute_site_scoped_panels(
            panel_keys=missing,
            force_recompute=force_recompute,
        )
        if not site_panels:
            logger.warning(
                "inventory overview: S3 site-scoped compute returned no panels for %s",
                missing,
            )
            return panels
        merged = {p.panel_key: p for p in panels}
        for panel in site_panels:
            merged[panel.panel_key] = panel
        logger.info(
            "inventory overview: injected %d S3 site-scoped panel(s): %s",
            len(site_panels),
            [p.panel_key for p in site_panels],
        )
        return list(merged.values())

    def _load_sellable_panels(
        self,
        dc_code: str,
        *,
        force_recompute: bool = False,
    ) -> list[PanelResult]:
        """Load sellable panels; global '*' aggregates per-DC infra across all bound DCs."""
        norm = (dc_code or "*").strip() or "*"
        if norm != "*":
            return self._sellable.compute_all_panels(
                dc_code=norm,
                force_recompute=force_recompute,
            )

        dc_codes = self._list_infra_dc_codes()
        global_only_keys = self._load_global_only_panel_keys()
        site_scoped_keys = self._load_site_scoped_panel_keys()
        if not dc_codes:
            return self._sellable.compute_all_panels(
                dc_code="*",
                force_recompute=force_recompute,
            )

        merged: dict[str, PanelResult] = {}

        def _ingest_dc_panels(panels: list[PanelResult]) -> None:
            for panel in panels:
                if panel.family in _HOST_DUAL_FAMILIES:
                    continue
                if not panel.has_infra_source:
                    if panel.panel_key not in merged:
                        merged[panel.panel_key] = panel
                    continue
                if panel.panel_key in global_only_keys:
                    continue
                if panel.panel_key in site_scoped_keys:
                    continue
                merged[panel.panel_key] = _merge_panel_results(
                    merged.get(panel.panel_key),
                    panel,
                )

        worker_count = min(_INVENTORY_DC_PARALLELISM, len(dc_codes))
        if worker_count <= 1:
            for code in dc_codes:
                _ingest_dc_panels(
                    self._sellable.compute_all_panels(
                        dc_code=code,
                        force_recompute=force_recompute,
                    )
                )
        else:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = {
                    executor.submit(
                        self._sellable.compute_all_panels,
                        dc_code=code,
                        force_recompute=force_recompute,
                    ): code
                    for code in dc_codes
                }
                for future in as_completed(futures):
                    code = futures[future]
                    try:
                        _ingest_dc_panels(future.result())
                    except Exception:
                        logger.exception(
                            "inventory overview: per-DC sellable compute failed dc=%s",
                            code,
                        )

        for fam in sorted(_HOST_DUAL_FAMILIES):
            for panel in self._sellable.compute_all_panels(
                dc_code="*",
                family=fam,
                force_recompute=force_recompute,
                infra_dc_codes=dc_codes,
            ):
                if panel.has_infra_source:
                    merged[panel.panel_key] = panel
                elif panel.panel_key not in merged:
                    merged[panel.panel_key] = panel

        if global_only_keys:
            wildcard_panels = [
                panel
                for panel in self._sellable.compute_all_panels(
                    dc_code="*",
                    force_recompute=force_recompute,
                )
                if panel.panel_key in global_only_keys
            ]
        else:
            wildcard_panels = []
        for panel in wildcard_panels:
            key = panel.panel_key
            if key in global_only_keys:
                if panel.has_infra_source:
                    merged[key] = panel
                elif key not in merged:
                    merged[key] = panel
                continue
            if key in site_scoped_keys:
                continue
            if key not in merged:
                merged[key] = panel
            elif panel.has_infra_source and not merged[key].has_infra_source:
                merged[key] = _merge_panel_results(merged.get(key), panel)

        for panel in self._sellable.compute_site_scoped_panels(
            panel_keys=sorted(site_scoped_keys),
            force_recompute=force_recompute,
        ):
            merged[panel.panel_key] = panel

        merged_list = list(merged.values())
        recomputed = self._sellable.recompute_family_constraints(
            merged_list,
            dc_code="*",
            infra_dc_codes=dc_codes,
        )
        logger.info(
            "inventory overview: aggregated sellable panels from %d DC(s), %d panel keys",
            len(dc_codes),
            len(recomputed),
        )
        return recomputed

    def _resolve_labels(
        self,
        panel_key: str,
        *,
        panel: PanelResult | None,
        entitled: dict[str, Any] | None,
        panel_defs: dict[str, dict[str, Any]],
        service_pages: dict[str, dict[str, Any]],
    ) -> tuple[str, str, str, str | None]:
        page = service_pages.get(panel_key) or {}
        pdef = panel_defs.get(panel_key) or {}
        service_label = (
            page.get("category_label")
            or (entitled or {}).get("category_label")
            or (panel.label if panel else None)
            or pdef.get("label")
            or panel_key
        )
        family_key = (
            (panel.family if panel else None)
            or pdef.get("family")
            or _infer_family_key(panel_key, panel_defs)
        )
        family_key = str(family_key or panel_key)
        gui_tab = page.get("gui_tab_binding")
        family_label = _family_label(
            family_key,
            service_label=str(service_label),
            gui_tab_binding=str(gui_tab) if gui_tab else None,
        )
        display_unit = (
            (panel.display_unit if panel else None)
            or pdef.get("display_unit")
            or page.get("resource_unit")
            or (entitled or {}).get("resource_unit")
            or "Adet"
        )
        return str(service_label), family_key, family_label, str(display_unit)

    def _enrich_row(
        self,
        base: dict[str, Any],
        *,
        service_label: str,
        family_key: str,
        family_label: str,
        entitled: dict[str, Any] | None,
        panel: PanelResult | None,
    ) -> dict[str, Any]:
        product_names = list((entitled or {}).get("product_names") or [])
        has_infra = bool(base.get("has_infra_source"))
        infra_binding = "bound" if has_infra else "crm_only"
        row = {
            **base,
            "service_label": service_label,
            "family": family_key,
            "family_label": family_label,
            "label": service_label,
            "crm_product_names": product_names,
            "crm_products_summary": _crm_product_names_summary(product_names),
            "infra_binding": infra_binding,
            "computation_mode": panel.computation_mode if panel else None,
        }
        return row

    def _build_panel_row(
        self,
        panel: PanelResult,
        entitled: dict[str, Any] | None,
        *,
        panel_defs: dict[str, dict[str, Any]],
        service_pages: dict[str, dict[str, Any]],
        under_pct: float,
        over_pct: float,
        dc_code: str = "*",
        ratio_lookup: dict[tuple[str, str], ResourceRatio] | None = None,
        coupling_lookup: dict[tuple[str, str, str, str], str] | None = None,
    ) -> dict[str, Any]:
        crm_sold = float((entitled or {}).get("entitled_qty") or 0.0)
        crm_sold_tl = float((entitled or {}).get("entitled_amount_tl") or 0.0)
        used = float(panel.allocated or 0.0)
        sellable = float(panel.sellable_constrained or 0.0)
        total = float(panel.total or 0.0) if panel.has_infra_source else None
        service_label, family_key, family_label, display_unit = self._resolve_labels(
            panel.panel_key,
            panel=panel,
            entitled=entitled,
            panel_defs=panel_defs,
            service_pages=service_pages,
        )
        hide_used = family_key in _INVENTORY_VIRT_FAMILIES
        used_is_allocation = family_key in _REPLICATION_ALLOCATION_FAMILIES
        # Free = infra empty (Total − allocated). Unsold = Total − CRM Sold.
        infra_used = used if panel.has_infra_source else None
        free_out = (
            max(float(total or 0) - float(infra_used or 0), 0.0)
            if panel.has_infra_source and total is not None
            else None
        )
        unsold_out = (
            max(float(total or 0) - crm_sold, 0.0)
            if panel.has_infra_source and total is not None
            else None
        )
        if hide_used:
            used_out = None
            status = panel_inventory_status_virt(
                crm_sold_qty=crm_sold,
                total_qty=total,
                has_infra_source=panel.has_infra_source,
                under_pct=under_pct,
                over_pct=over_pct,
            )
            delta = (crm_sold - float(total or 0)) if panel.has_infra_source and total is not None else None
            overage = max(0.0, crm_sold - float(total or 0)) if panel.has_infra_source and total is not None else 0.0
            efficiency = (
                round((crm_sold / float(total)) * 100.0, 2)
                if total and total > 0 and panel.has_infra_source
                else None
            )
        else:
            used_out = used if panel.has_infra_source else None
            status = panel_inventory_status(
                crm_sold_qty=crm_sold,
                used_qty=used if panel.has_infra_source else 0.0,
                has_infra_source=panel.has_infra_source,
                under_pct=under_pct,
                over_pct=over_pct,
            )
            delta = (used - crm_sold) if panel.has_infra_source else None
            overage = max(0.0, used - crm_sold) if panel.has_infra_source else 0.0
            efficiency = (
                round((used / crm_sold) * 100.0, 2)
                if crm_sold > 0 and panel.has_infra_source
                else None
            )
        sellable_out = sellable if panel.has_infra_source else None
        crm_fields: dict[str, Any] = {}
        if entitled:
            for key in (
                "crm_sold_qty_general",
                "crm_sold_qty_km",
                "crm_sold_qty_hana",
                "crm_sold_tl_general",
                "crm_sold_tl_km",
                "crm_sold_tl_hana",
                "crm_sub_bucket",
            ):
                if key in entitled:
                    crm_fields[key] = entitled[key]
        data_quality, suspect_reason = _assess_data_quality(panel, crm_sold=crm_sold)
        # Free is always infra empty; Unsold is commercial residual.
        inventory_free_mode = (
            "physical" if family_key in _PHYSICAL_FREE_FAMILIES else "infra"
        )
        track_fields = _sellable_track_fields(
            panel, has_infra=panel.has_infra_source, hide_used=hide_used,
        )
        free_tl_out = None
        unsold_tl_out = None
        if panel.has_infra_source and panel.has_price:
            if inventory_free_mode == "physical":
                free_tl_out = _value_tl_from_catalog_price(
                    free_out,
                    unit_price_tl=panel.unit_price_tl,
                    has_price=panel.has_price,
                )
            else:
                free_tl_out = compute_potential_tl(free_out, panel.unit_price_tl)
            unsold_tl_out = compute_potential_tl(unsold_out, panel.unit_price_tl)
        # Surface IBM-style alternate min/max on replication rows.
        sellable_min = panel.sellable_min if used_is_allocation else None
        sellable_max = panel.sellable_max if used_is_allocation else None
        base = {
            "panel_key": panel.panel_key,
            "label": service_label,
            "family": family_key,
            "resource_kind": panel.resource_kind,
            "display_unit": display_unit,
            "total": total,
            "crm_sold_qty": crm_sold,
            "crm_sold_tl": crm_sold_tl,
            "used_qty": used_out,
            "used_is_allocation": used_is_allocation,
            "sellable_qty": sellable_out,
            "sellable_min_qty": sellable_min,
            "sellable_max_qty": sellable_max,
            "free_qty": free_out,
            "free_tl": free_tl_out,
            "unsold_qty": unsold_out,
            "unsold_tl": unsold_tl_out,
            "potential_tl": panel.potential_tl,
            "has_infra_source": panel.has_infra_source,
            "has_price": panel.has_price,
            "status": status,
            "delta_used_vs_crm": delta,
            "overage_qty": overage if panel.has_infra_source else 0.0,
            "efficiency_pct": efficiency,
            "inventory_hide_used": hide_used,
            "inventory_free_mode": inventory_free_mode,
            "data_quality": data_quality,
            "suspect_reason": suspect_reason,
            # Why a virt row's sellable is 0 (RAM/ratio bound, gate, etc.) — surfaced as a
            # hint in the report so a legitimate 0 is not mistaken for a bug.
            "sellable_constraint_reason": panel.constraint_reason,
            **track_fields,
            **crm_fields,
        }
        if family_key in _REPLICATION_RATIO_SURFACE_FAMILIES:
            mode = self._sellable.resolve_storage_coupling(
                family_key, dc_code or "*", coupling_lookup,
            )
            base.update(
                _replication_config_fields(
                    family_key,
                    dc_code=dc_code or "*",
                    ratio_lookup=ratio_lookup or {},
                    coupling_mode=mode,
                )
            )
        return self._enrich_row(
            base,
            service_label=service_label,
            family_key=family_key,
            family_label=family_label,
            entitled=entitled,
            panel=panel,
        )

    def _build_entitled_only_row(
        self,
        panel_key: str,
        bucket: dict[str, Any],
        *,
        panel_defs: dict[str, dict[str, Any]],
        service_pages: dict[str, dict[str, Any]],
        dc_code: str = "*",
        ratio_lookup: dict[tuple[str, str], ResourceRatio] | None = None,
        coupling_lookup: dict[tuple[str, str, str, str], str] | None = None,
    ) -> dict[str, Any]:
        service_label, family_key, family_label, display_unit = self._resolve_labels(
            panel_key,
            panel=None,
            entitled=bucket,
            panel_defs=panel_defs,
            service_pages=service_pages,
        )
        base = {
            "panel_key": panel_key,
            "label": service_label,
            "family": family_key,
            "resource_kind": (panel_defs.get(panel_key) or {}).get("resource_kind") or "other",
            "display_unit": display_unit,
            "total": None,
            "crm_sold_qty": float(bucket.get("entitled_qty") or 0.0),
            "crm_sold_tl": float(bucket.get("entitled_amount_tl") or 0.0),
            "used_qty": None,
            "sellable_qty": None,
            "free_qty": None,
            "unsold_qty": None,
            "unsold_tl": None,
            "potential_tl": 0.0,
            "has_infra_source": False,
            "has_price": False,
            "status": "crm_only",
            "delta_used_vs_crm": None,
            "overage_qty": 0.0,
            "efficiency_pct": None,
            "data_quality": None,
            "unit_price_tl": None,
            "used_tl": None,
            "sellable_profile": _family_sellable_profile(family_key),
            "sellable_alloc_qty": None,
            "sellable_max_qty": None,
            "sellable_avg_qty": None,
            "potential_tl_alloc": None,
            "potential_tl_max": None,
            "potential_tl_avg": None,
            "sellable_tl_min": None,
            "sellable_tl_max": None,
        }
        if family_key in _REPLICATION_RATIO_SURFACE_FAMILIES:
            mode = self._sellable.resolve_storage_coupling(
                family_key, dc_code or "*", coupling_lookup,
            )
            base.update(
                _replication_config_fields(
                    family_key,
                    dc_code=dc_code or "*",
                    ratio_lookup=ratio_lookup or {},
                    coupling_mode=mode,
                )
            )
        return self._enrich_row(
            base,
            service_label=service_label,
            family_key=family_key,
            family_label=family_label,
            entitled=bucket,
            panel=None,
        )

    def compute_inventory_overview(
        self,
        dc_code: str = "*",
        *,
        force_recompute: bool = False,
    ) -> dict[str, Any]:
        cache_key = f"{_INVENTORY_REDIS_PREFIX}{dc_code or '*'}"
        if not force_recompute and self._crm_redis is not None:
            try:
                raw = self._crm_redis.get(cache_key)
                if raw:
                    return json.loads(raw)
            except Exception:  # noqa: BLE001
                logger.debug("inventory overview cache read failed", exc_info=True)

        calc = self._config.get_calc_dict() if self._config else {}
        under_pct = float(calc.get("efficiency.under_pct", 80.0))
        over_pct = float(calc.get("efficiency.over_pct", 110.0))

        panel_defs = self._load_panel_defs()
        service_pages = self._load_service_pages()
        panels = self._load_sellable_panels(dc_code or "*", force_recompute=force_recompute)
        panels = self._ensure_s3_site_panels(panels, force_recompute=force_recompute)
        panels = [
            panel
            for panel in panels
            if panel.panel_key != _S3_MERGE_TARGET or panel.has_infra_source
        ]
        mapping = self._load_product_mapping()
        panel_units = self._panel_unit_index(panels)
        overview_dc = dc_code or "*"
        try:
            ratio_rows = list(self._sellable.list_ratios() or [])
        except Exception:  # noqa: BLE001
            ratio_rows = []
        ratio_lookup: dict[tuple[str, str], ResourceRatio] = {
            (r.family, r.dc_code): r
            for r in ratio_rows
            if getattr(r, "family", None)
        }
        try:
            coupling_lookup = self._sellable._build_coupling_lookup()
        except Exception:  # noqa: BLE001
            coupling_lookup = {}

        entitled_raw = self._sales._run_query(sq.SALES_ENTITLED_RAW_GLOBAL, ())
        entitled_by_panel = aggregate_entitled_by_panel_key(
            entitled_raw, mapping, panel_units=panel_units
        )

        panel_rows: list[dict[str, Any]] = []
        crm_only_panels: list[dict[str, Any]] = []
        seen_panels: set[str] = set()

        merged_infra = _build_merged_infra_panels(panels, panel_defs)
        merged_keys = {p.panel_key for p in merged_infra}
        netbackup_metrics = self._sellable.get_netbackup_inventory_metrics()

        for panel in panels:
            if _inventory_panel_hidden(panel.panel_key, panel_defs):
                continue
            seen_panels.add(panel.panel_key)
            merge_cfg = _INVENTORY_MERGED_CRM_SUB.get(panel.panel_key)
            if merge_cfg:
                sub_key, sub_name = merge_cfg
                entitled = merge_entitled_for_inventory_panel(
                    panel.panel_key,
                    entitled_by_panel,
                    sub_panel_key=sub_key,
                    sub_bucket_name=sub_name,
                )
            else:
                entitled = entitled_by_panel.get(panel.panel_key)
            row = self._build_panel_row(
                panel,
                entitled,
                panel_defs=panel_defs,
                service_pages=service_pages,
                under_pct=under_pct,
                over_pct=over_pct,
                dc_code=overview_dc,
                ratio_lookup=ratio_lookup,
                coupling_lookup=coupling_lookup,
            )
            if row.get("panel_key") in _NETBACKUP_INVENTORY_PANEL_KEYS:
                row = _apply_netbackup_inventory_fields(
                    row,
                    netbackup_metrics,
                    under_pct=under_pct,
                    over_pct=over_pct,
                )
            panel_rows.append(row)
            if row.get("infra_binding") == "crm_only":
                crm_only_panels.append(row)

        for merged_panel in merged_infra:
            if merged_panel.panel_key in seen_panels:
                continue
            seen_panels.add(merged_panel.panel_key)
            merged_entitled = _merge_entitled_for_target(
                merged_panel.panel_key,
                entitled_by_panel,
                panel_defs,
            )
            row = self._build_panel_row(
                merged_panel,
                merged_entitled,
                panel_defs=panel_defs,
                service_pages=service_pages,
                under_pct=under_pct,
                over_pct=over_pct,
                dc_code=overview_dc,
                ratio_lookup=ratio_lookup,
                coupling_lookup=coupling_lookup,
            )
            if row.get("panel_key") in _NETBACKUP_INVENTORY_PANEL_KEYS:
                row = _apply_netbackup_inventory_fields(
                    row,
                    netbackup_metrics,
                    under_pct=under_pct,
                    over_pct=over_pct,
                )
            _upsert_inventory_row(panel_rows, crm_only_panels, row)

        for panel_key, bucket in entitled_by_panel.items():
            if panel_key in seen_panels:
                continue
            family_key = str(
                bucket.get("family")
                or panel_defs.get(panel_key, {}).get("family")
                or _infer_family_key(panel_key, panel_defs)
            )
            if _inventory_panel_hidden(panel_key, panel_defs):
                continue
            if panel_key in merged_keys:
                continue
            if panel_key in {pair[0] for pair in _INVENTORY_MERGED_CRM_SUB.values()}:
                continue
            row = self._build_entitled_only_row(
                panel_key,
                bucket,
                panel_defs=panel_defs,
                service_pages=service_pages,
                dc_code=overview_dc,
                ratio_lookup=ratio_lookup,
                coupling_lookup=coupling_lookup,
            )
            panel_rows.append(row)
            crm_only_panels.append(row)

        panel_rows = _drop_hidden_families(panel_rows)
        crm_only_panels = _drop_hidden_families(crm_only_panels)
        panel_rows = [_apply_comparison_only_fields(r) for r in panel_rows]
        crm_only_panels = [_apply_comparison_only_fields(r) for r in crm_only_panels]
        panel_rows.sort(key=lambda r: (-float(r.get("crm_sold_tl") or 0), r.get("service_label") or ""))

        families_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in panel_rows:
            if not _include_row_in_families(row):
                continue
            family_key = str(row.get("family") or "other")
            families_map[family_key].append(row)

        families_out: list[dict[str, Any]] = []
        for family_key, rows in families_map.items():
            family_label = rows[0].get("family_label") or family_key if rows else family_key
            rows_sorted = sorted(rows, key=lambda r: r.get("service_label") or "")
            families_out.append({
                "family": family_key,
                "label": family_label,
                "family_label": family_label,
                "dc_code": dc_code or "*",
                "panels": rows_sorted,
                "panel_count": len(rows_sorted),
                "has_infra": any(r.get("has_infra_source") for r in rows_sorted),
            })
        families_out.sort(key=lambda f: (f.get("family_label") or f.get("family") or "").lower())
        families_out = _regroup_backup_families(families_out)

        mapped_ids = self._mapped_product_ids(mapping)
        bind_ids = mapped_ids if mapped_ids else ["__none__"]
        unmapped_products = self._sales._run_query(sq.UNMAPPED_ENTITLED_PRODUCTS, (bind_ids,))

        infra_panels = [r for r in panel_rows if r.get("has_infra_source")]
        overage_count = sum(1 for r in infra_panels if r.get("status") == "over")
        unsold_count = sum(1 for r in infra_panels if r.get("status") == "unsold_usage")
        crm_entitled_tl = sum(float(r.get("crm_sold_tl") or 0) for r in panel_rows)
        unmapped_count = self._sellable._count_unmapped_products()

        summary = {
            "dc_code": dc_code or "*",
            "infra_panel_count": len(infra_panels),
            "panel_count": len(panel_rows),
            "crm_only_count": len(crm_only_panels),
            "crm_entitled_tl": crm_entitled_tl,
            "unmapped_product_count": unmapped_count,
            "unmapped_entitled_count": len(unmapped_products),
            "overage_panel_count": overage_count,
            "unsold_usage_count": unsold_count,
            "total_potential_tl": sum(float(r.get("potential_tl") or 0) for r in panel_rows),
            "note": (
                "Capacity units are heterogeneous across panels; compare quantities in the service list."
                + (
                    " Global view sums DC-scoped infra totals across bound DCs, then "
                    "recomputes sellable per family; global-only panels (e.g. NetBackup) "
                    "are counted once."
                    if (dc_code or "*") == "*"
                    else ""
                )
            ),
        }

        payload = {
            "dc_code": dc_code or "*",
            "summary": summary,
            "families": families_out,
            "panels": panel_rows,
            "crm_only_panels": sorted(
                crm_only_panels,
                key=lambda r: r.get("service_label") or r.get("panel_key") or "",
            ),
            "unmapped_products": unmapped_products,
        }

        if self._crm_redis is not None:
            try:
                self._crm_redis.setex(
                    cache_key,
                    int(_INVENTORY_CACHE_TTL_SEC),
                    json.dumps(payload, default=str),
                )
            except Exception:  # noqa: BLE001
                logger.debug("inventory overview cache write failed", exc_info=True)

        return payload

    def warm_inventory_cache(self, dc_code: str = "*") -> dict[str, Any]:
        """Prewarm Redis inventory overview cache (scheduler / admin refresh)."""
        logger.info("inventory overview: warming cache dc=%s", dc_code or "*")
        return self.compute_inventory_overview(dc_code=dc_code, force_recompute=True)
