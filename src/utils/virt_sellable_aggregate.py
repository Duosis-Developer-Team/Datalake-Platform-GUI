"""Shared virtualization sellable panel fetch + aggregation for DC list and DC detail.

Matches crm-engine ``get_sellable_by_panel`` usage in ``app.py`` callbacks so Potential
Sales on ``/datacenters`` can align with Virtualization tab totals when the same cluster
scope is passed (including explicit full cluster lists for compute-backed panels).
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.services import api_client as api

VIRT_POWER_FAMILIES: tuple[str, ...] = ("virt_power", "virt_power_hana")

VIRT_SELLABLE_FAMILY_LABELS: tuple[str, ...] = (
    "virt_classic",
    "virt_hyperconverged",
    *VIRT_POWER_FAMILIES,
)

_CONSTRAINT_REASON_PRIORITY: tuple[str, ...] = (
    "compute_bottleneck",
    "gate_blocked",
    "ratio_bound",
    "none",
)


def _merge_constraint_reason(group: list[dict]) -> str:
    reasons = {(p.get("constraint_reason") or "none").lower() for p in group}
    for reason in _CONSTRAINT_REASON_PRIORITY:
        if reason in reasons:
            return reason
    return "none"


def _bottleneck_panel(group: list[dict]) -> dict | None:
    """Pick panel with smallest bottleneck_units (tightest compute cap)."""
    candidates = [
        p for p in group
        if p.get("bottleneck_units") is not None
    ]
    if not candidates:
        return group[0] if group else None
    return min(candidates, key=lambda p: float(p.get("bottleneck_units") or 0.0))


def virt_tab_cluster_scope(
    classic_clusters: list[str] | None,
    hyperconv_clusters: list[str] | None,
) -> tuple[list[str] | None, list[str] | None]:
    """Mirror Virt tab cluster selector defaults: explicit full lists when known.

    Empty lists are treated as ``None`` (DC-wide datalake path), matching
    ``selected_clusters or None`` in Dash callbacks.
    """
    classic = list(classic_clusters) if classic_clusters else None
    hyperconv = list(hyperconv_clusters) if hyperconv_clusters else None
    return classic, hyperconv


def collect_virt_sellable_panels(
    dc_id: str,
    classic_clusters: list[str] | None = None,
    hyperconv_clusters: list[str] | None = None,
    max_family_workers: int | None = None,
) -> list[dict]:
    """Fetch virt classic + hyperconv + power panel rows.

    Run family fetches in parallel so cold-cache page loads don't serialize
    multiple CRM calls per DC.
    """
    panels: list[dict] = []

    def _fetch_family(family: str) -> list[dict]:
        kwargs: dict[str, Any] = {"dc_code": str(dc_id), "family": family}
        if family == "virt_classic":
            kwargs["clusters"] = classic_clusters
        elif family == "virt_hyperconverged":
            kwargs["clusters"] = hyperconv_clusters
        chunk = api.get_sellable_by_panel(**kwargs) or []
        return chunk if isinstance(chunk, list) else []

    families: tuple[str, ...] = ("virt_classic", "virt_hyperconverged", *VIRT_POWER_FAMILIES)
    configured_family_workers = int(os.getenv("VIRT_SELLABLE_FAMILY_WORKERS", "4") or "4")
    workers = max_family_workers if max_family_workers is not None else configured_family_workers
    workers = min(max(1, workers), len(families))
    if workers == 1:
        for fam in families:
            try:
                panels.extend(_fetch_family(fam))
            except Exception:
                continue
        return panels
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_fetch_family, fam) for fam in families]
        for fut in as_completed(futures):
            try:
                panels.extend(fut.result())
            except Exception:
                continue
    return panels


def virt_tl_from_sellable_summary(summary: dict | None) -> float:
    """Sum virt family rollups from lightweight CRM summary (rollup_only=true)."""
    if not summary or not isinstance(summary, dict):
        return 0.0
    virt_fams = set(VIRT_SELLABLE_FAMILY_LABELS)
    total = 0.0
    for fam in summary.get("families") or []:
        if not isinstance(fam, dict):
            continue
        if fam.get("family") in virt_fams:
            total += float(fam.get("total_potential_tl") or 0.0)
    return total


def total_potential_tl(panels: list[dict]) -> float:
    """Sum ``potential_tl`` across panel dicts."""
    total = 0.0
    for p in panels:
        if isinstance(p, dict):
            total += float(p.get("potential_tl") or 0.0)
    return total


def merge_power_panels_for_summary(panels: list[dict]) -> list[dict]:
    """Collapse virt_power + virt_power_hana into a single virt_power family for Summary UI."""
    from collections import defaultdict

    out: list[dict] = []
    power_by_kind: dict[str, list[dict]] = defaultdict(list)
    sum_fields = (
        "sellable_constrained",
        "sellable_raw",
        "sellable_physical",
        "sellable_effective",
        "potential_tl",
        "potential_tl_physical",
        "potential_tl_effective",
        "potential_tl_min",
        "potential_tl_max",
        "sellable_min",
        "sellable_max",
    )
    # Shared IBM Power infra: total/allocated must not double-count when HANA aliases virt_power.
    infra_fields = ("total", "allocated")
    for p in panels:
        if not isinstance(p, dict):
            continue
        fam = p.get("family") or ""
        if fam in VIRT_POWER_FAMILIES:
            kind = (p.get("resource_kind") or "other").lower()
            power_by_kind[kind].append(p)
        else:
            out.append(p)
    for kind, group in power_by_kind.items():
        if not group:
            continue
        if len(group) == 1:
            single = dict(group[0])
            single["family"] = "virt_power"
            out.append(single)
            continue
        merged = dict(group[0])
        merged["family"] = "virt_power"
        for field in sum_fields:
            merged[field] = sum(float(g.get(field) or 0.0) for g in group)
        for field in infra_fields:
            merged[field] = max(float(g.get(field) or 0.0) for g in group)
        merged["ratio_bound"] = any(bool(g.get("ratio_bound")) for g in group)
        merged["gate_blocked"] = any(bool(g.get("gate_blocked")) for g in group)
        merged["constraint_reason"] = _merge_constraint_reason(group)
        bottleneck_src = _bottleneck_panel(group)
        if bottleneck_src is not None:
            merged["bottleneck_kind"] = bottleneck_src.get("bottleneck_kind")
            merged["bottleneck_units"] = bottleneck_src.get("bottleneck_units")
        out.append(merged)
    return out


def virt_total_potential_range(panels: list[dict]) -> tuple[float, float, float]:
    """Return (total_tl, min_tl, max_tl) across virt panel dicts."""
    total = 0.0
    lo = 0.0
    hi = 0.0
    for p in panels:
        if not isinstance(p, dict):
            continue
        tl = float(p.get("potential_tl") or 0.0)
        total += tl
        lo += float(
            p.get("potential_tl_min") if p.get("potential_tl_min") is not None else tl
        )
        hi += float(
            p.get("potential_tl_max") if p.get("potential_tl_max") is not None else tl
        )
    return total, lo, hi


def virt_constrained_loss_tl(panels: list[dict]) -> float:
    """Ratio-bound TL loss across virt panels (raw potential minus constrained)."""
    loss = 0.0
    for p in panels:
        if not isinstance(p, dict):
            continue
        price = float(p.get("unit_price_tl") or 0.0)
        if price <= 0:
            continue
        raw = float(p.get("sellable_raw") or 0.0)
        constrained = float(p.get("sellable_constrained") or 0.0)
        loss += max((raw - constrained) * price, 0.0)
    return loss


def aggregate_virt_sellable_panels(
    panels: list[dict],
) -> tuple[float, dict[str, dict[str, float | str]], bool]:
    """Match ``app.py`` sellable-virt-total-card aggregation (CPU/RAM/Storage + total TL)."""
    by_kind: dict[str, dict[str, float | str]] = {
        "cpu":     {"constrained": 0.0, "tl": 0.0, "unit": "vCPU"},
        "ram":     {"constrained": 0.0, "tl": 0.0, "unit": "GB"},
        "storage": {"constrained": 0.0, "tl": 0.0, "unit": "GB"},
    }
    total_tl = 0.0
    has_known_kind = False
    for p in panels:
        if not isinstance(p, dict):
            continue
        kind = (p.get("resource_kind") or "other").lower()
        constrained = float(p.get("sellable_constrained") or 0.0)
        tl = float(p.get("potential_tl") or 0.0)
        if constrained <= 1e-9:
            tl = 0.0
        total_tl += tl
        if kind not in by_kind:
            continue
        by_kind[kind]["constrained"] = float(by_kind[kind]["constrained"]) + constrained
        by_kind[kind]["tl"] = float(by_kind[kind]["tl"]) + tl
        unit = p.get("display_unit")
        if unit:
            by_kind[kind]["unit"] = unit
        has_known_kind = True
    return total_tl, by_kind, has_known_kind
