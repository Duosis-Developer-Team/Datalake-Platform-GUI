"""Platform-wide Potential Sales: virt + colo + backup + replication.

Extends virt sellable collection with IBM-style shared-pool TL dedupe for
NetBackup Image/App and virt↔replication, plus colocation free-U TL.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from shared.sellable.computation import dedupe_shared_pool_tl

from src.services import api_client as api
from src.utils.virt_sellable_aggregate import (
    VIRT_POWER_FAMILIES,
    VIRT_SELLABLE_FAMILY_LABELS,
    _ibm_shared_storage_dedup_tl,
    _panel_tl_bounds,
    collect_virt_sellable_panels,
    prepare_virt_sellable_panels,
    virt_tab_cluster_scope,
    virt_total_potential_range,
)

# English info tooltip service groups for Potential Sales.
POTENTIAL_SALES_SERVICE_GROUPS: tuple[str, ...] = (
    "Virtualization (Classic, Hyperconverged, Power)",
    "Backup (NetBackup Image / Application — sold↔used for Nutanix snapshots)",
    "Replication (Veeam / Zerto — unified families; architecture is filter only)",
    "Colocation / Physical (rack-U)",
)

# Potential Sales / sellable cards: one family per product line (no Classic/HC
# duplicate cards, no Nutanix image sellable — snapshots are comparison-only).
BACKUP_SELLABLE_FAMILIES: tuple[str, ...] = (
    "backup_netbackup",
    "backup_veeam_replication",
    "backup_zerto_replication",
)

_NETBACKUP_PANEL_KEYS = frozenset({
    "backup_netbackup_image",
    "backup_netbackup_application",
})

_REPLICATION_FAMILIES = frozenset({
    "backup_veeam_replication",
    "backup_zerto_replication",
    # Legacy classic/HC keys may still appear in cached panel rows
    "backup_veeam_replication_classic",
    "backup_zerto_replication_classic",
    "backup_veeam_replication_hyperconverged",
    "backup_zerto_replication_hyperconverged",
})

_VIRT_COMPUTE_FAMILIES = frozenset({
    "virt_classic",
    "virt_hyperconverged",
})

_REPLICATION_CLASSIC_FAMILIES = frozenset({
    "backup_veeam_replication_classic",
    "backup_zerto_replication_classic",
})

_REPLICATION_HC_FAMILIES = frozenset({
    "backup_veeam_replication_hyperconverged",
    "backup_zerto_replication_hyperconverged",
})

_REPLICATION_UNIFIED_FAMILIES = frozenset({
    "backup_veeam_replication",
    "backup_zerto_replication",
})


def collect_backup_sellable_panels(
    dc_id: str,
    classic_clusters: list[str] | None = None,
    hyperconv_clusters: list[str] | None = None,
    max_family_workers: int | None = None,
) -> list[dict]:
    """Fetch backup / replication sellable panel rows for one DC."""
    panels: list[dict] = []

    def _fetch(family: str) -> list[dict]:
        kwargs: dict[str, Any] = {"dc_code": str(dc_id), "family": family}
        if family in _REPLICATION_UNIFIED_FAMILIES:
            # Unified family: pass both scopes when available (API may ignore).
            merged = list(classic_clusters or []) + list(hyperconv_clusters or [])
            if merged:
                kwargs["clusters"] = merged
        elif family in _REPLICATION_CLASSIC_FAMILIES:
            kwargs["clusters"] = classic_clusters
        elif family in _REPLICATION_HC_FAMILIES:
            kwargs["clusters"] = hyperconv_clusters
        chunk = api.get_sellable_by_panel(**kwargs) or []
        return chunk if isinstance(chunk, list) else []

    workers_cfg = int(os.getenv("BACKUP_SELLABLE_FAMILY_WORKERS", "4") or "4")
    workers = max_family_workers if max_family_workers is not None else workers_cfg
    workers = min(max(1, workers), len(BACKUP_SELLABLE_FAMILIES))
    if workers == 1:
        for fam in BACKUP_SELLABLE_FAMILIES:
            try:
                panels.extend(_fetch(fam))
            except Exception:
                continue
        return prepare_virt_sellable_panels(panels)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_fetch, fam) for fam in BACKUP_SELLABLE_FAMILIES]
        for fut in as_completed(futures):
            try:
                panels.extend(fut.result())
            except Exception:
                continue
    return prepare_virt_sellable_panels(panels)


def _dedupe_netbackup_tl(panels: list[dict]) -> tuple[float | None, float | None]:
    image = next((p for p in panels if p.get("panel_key") == "backup_netbackup_image"), None)
    app = next((p for p in panels if p.get("panel_key") == "backup_netbackup_application"), None)
    if not image or not app:
        return None, None
    _, lo_i, hi_i = _panel_tl_bounds(image)
    _, lo_a, hi_a = _panel_tl_bounds(app)
    return dedupe_shared_pool_tl(lo_i, hi_i, lo_a, hi_a)


def _dedupe_virt_replication_tl(panels: list[dict]) -> list[tuple[str, float, float]]:
    """Per resource_kind: virt primary + replication alternate TL bands."""
    out: list[tuple[str, float, float]] = []
    kinds = sorted({
        (p.get("resource_kind") or "").lower()
        for p in panels
        if (p.get("family") in _VIRT_COMPUTE_FAMILIES or p.get("family") in _REPLICATION_FAMILIES)
        and (p.get("resource_kind") or "").lower() in ("cpu", "ram")
    })
    for kind in kinds:
        virt = [
            p for p in panels
            if p.get("family") in _VIRT_COMPUTE_FAMILIES
            and (p.get("resource_kind") or "").lower() == kind
        ]
        repl = [
            p for p in panels
            if p.get("family") in _REPLICATION_FAMILIES
            and (p.get("resource_kind") or "").lower() == kind
        ]
        if not virt or not repl:
            continue
        # Sum virt kind TL bounds, then dedupe against sum of replication bounds.
        v_lo = v_hi = 0.0
        for p in virt:
            _, lo, hi = _panel_tl_bounds(p)
            v_lo += lo
            v_hi += hi
        r_lo = r_hi = 0.0
        for p in repl:
            _, lo, hi = _panel_tl_bounds(p)
            r_lo += lo
            r_hi += hi
        out.append((kind, *dedupe_shared_pool_tl(v_lo, v_hi, r_lo, r_hi)))
    return out


def platform_total_potential_range(
    panels: list[dict],
    *,
    colocation_tl: float | None = None,
) -> tuple[float, float, float]:
    """Return (total_tl, min_tl, max_tl) across platform sellable panels + colo.

    Applies IBM storage dedupe, NetBackup Image/App dedupe, and virt↔replication
    per-kind dedupe so shared pools are not double-counted at max.
    """
    skip_keys: set[str] = set()
    skip_fam_kind: set[tuple[str, str]] = set()

    # 1) Classic/Power IBM storage (existing)
    ibm_lo, ibm_hi = _ibm_shared_storage_dedup_tl(panels)
    has_ibm = ibm_lo is not None and ibm_hi is not None
    if has_ibm:
        for fam in ("virt_classic", "virt_power"):
            skip_fam_kind.add((fam, "storage"))

    # 2) NetBackup Image/App
    nb_lo, nb_hi = _dedupe_netbackup_tl(panels)
    has_nb = nb_lo is not None and nb_hi is not None
    if has_nb:
        skip_keys |= set(_NETBACKUP_PANEL_KEYS)

    # 3) Virt ↔ replication competing kinds
    vr_bands = _dedupe_virt_replication_tl(panels)
    vr_kinds = {k for k, _, _ in vr_bands}
    if vr_kinds:
        for p in panels:
            fam = p.get("family") or ""
            kind = (p.get("resource_kind") or "").lower()
            if kind in vr_kinds and (
                fam in _VIRT_COMPUTE_FAMILIES or fam in _REPLICATION_FAMILIES
            ):
                skip_fam_kind.add((fam, kind))

    total = lo = hi = 0.0
    for p in panels:
        if not isinstance(p, dict):
            continue
        key = p.get("panel_key") or ""
        fam = p.get("family") or ""
        kind = (p.get("resource_kind") or "other").lower()
        if key in skip_keys:
            continue
        if (fam, kind) in skip_fam_kind:
            continue
        tl, p_lo, p_hi = _panel_tl_bounds(p)
        total += tl
        lo += p_lo
        hi += p_hi

    if has_ibm:
        lo += float(ibm_lo)
        hi += float(ibm_hi)
        total += float(ibm_lo)
    if has_nb:
        lo += float(nb_lo)
        hi += float(nb_hi)
        total += float(nb_lo)
    for _, band_lo, band_hi in vr_bands:
        lo += float(band_lo)
        hi += float(band_hi)
        total += float(band_lo)

    colo = float(colocation_tl or 0.0)
    if colo > 0:
        total += colo
        lo += colo
        hi += colo

    return total, lo, hi


def collect_platform_sellable_panels(
    dc_id: str,
    classic_clusters: list[str] | None = None,
    hyperconv_clusters: list[str] | None = None,
    *,
    max_family_workers: int | None = None,
) -> list[dict]:
    """Virt + backup/replication panels for one DC."""
    classic, hyper = virt_tab_cluster_scope(classic_clusters, hyperconv_clusters)
    virt = collect_virt_sellable_panels(
        dc_id, classic, hyper, max_family_workers=max_family_workers,
    )
    backup = collect_backup_sellable_panels(
        dc_id, classic, hyper, max_family_workers=max_family_workers,
    )
    return list(virt) + list(backup)


def potential_sales_info_text() -> str:
    """English tooltip body explaining Potential Sales calculation rules."""
    lines = [
        "Potential Sales includes sellable headroom across:",
    ]
    for group in POTENTIAL_SALES_SERVICE_GROUPS:
        lines.append(f"• {group}")
    lines.extend(
        [
            "",
            "How capacity is calculated:",
            "• Virtualization CPU/RAM is primary on the host pool; "
            "Veeam/Zerto replication CPU/RAM is an alternate claimant "
            "(min=0 if virt sells all free, max=full free if replication sells all).",
            "• NetBackup Image and Application share one disk pool "
            "(IBM-style min=half free, max=full free).",
            "• Veeam replication storage uses all VMware datastores except NetBackup "
            "(dedicated; not shared with virt). On hyperconverged, Nutanix disks "
            "are included when VMware-managed HC VMs use Veeam.",
            "• Zerto replication storage uses VMware datastores except Veeam and "
            "NetBackup (dedicated compute path only — never raw site-metrics history).",
            "• Classic vs Hyperconverged is a filter/breakdown only; sellable cards "
            "use one Veeam Replication and one Zerto Replication family.",
            "• Nutanix image snapshots are sold↔used comparison only (not sellable).",
            "• Colocation free rack-U is included.",
            "• License headroom is not included yet (external data source planned).",
        ]
    )
    return "\n".join(lines)


# Re-export helpers used by datacenters / summary
__all__ = [
    "BACKUP_SELLABLE_FAMILIES",
    "POTENTIAL_SALES_SERVICE_GROUPS",
    "VIRT_POWER_FAMILIES",
    "VIRT_SELLABLE_FAMILY_LABELS",
    "collect_backup_sellable_panels",
    "collect_platform_sellable_panels",
    "collect_virt_sellable_panels",
    "platform_total_potential_range",
    "potential_sales_info_text",
    "virt_tab_cluster_scope",
    "virt_total_potential_range",
]
