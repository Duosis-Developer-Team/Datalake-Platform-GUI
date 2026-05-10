"""Shared virtualization sellable panel fetch + aggregation for DC list and DC detail.

Matches crm-engine ``get_sellable_by_panel`` usage in ``app.py`` callbacks so Potential
Sales on ``/datacenters`` aligns with Virtualization tab totals when cluster scope is
equivalent (see normalize_clusters_if_full_universe).
"""
from __future__ import annotations

from typing import Any

from src.services import api_client as api

VIRT_POWER_FAMILIES: tuple[str, ...] = ("virt_power", "virt_power_hana")

VIRT_SELLABLE_FAMILY_LABELS: tuple[str, ...] = (
    "virt_classic",
    "virt_hyperconverged",
    *VIRT_POWER_FAMILIES,
)


def normalize_clusters_if_full_universe(
    selected: list[str] | None,
    option_data: list[dict[str, Any]] | None,
) -> list[str] | None:
    """When MultiSelect includes every option, return None for API (datacenter-api full-DC path).

    Passing an explicit CSV of all cluster names otherwise selects the filtered SQL path in
    ``get_*_metrics_filtered``, which can diverge from omitting ``clusters`` entirely.
    """
    if not option_data:
        return list(selected) if selected else None
    universe: list[str] = []
    for opt in option_data:
        if not isinstance(opt, dict):
            continue
        v = opt.get("value")
        if v is not None and str(v).strip():
            universe.append(str(v).strip())
    universe_sorted = sorted(set(universe))
    if not universe_sorted:
        return list(selected) if selected else None
    sel_sorted = sorted({str(x).strip() for x in (selected or []) if x is not None and str(x).strip()})
    if sel_sorted == universe_sorted:
        return None
    return list(selected) if selected else None


def collect_virt_sellable_panels(
    dc_id: str,
    classic_clusters: list[str] | None = None,
    hyperconv_clusters: list[str] | None = None,
) -> list[dict]:
    """Fetch virt classic + hyperconv + power panel rows (same order as DC detail callback)."""
    panels: list[dict] = []
    try:
        classic = api.get_sellable_by_panel(
            dc_code=str(dc_id),
            family="virt_classic",
            clusters=classic_clusters,
        ) or []
        if isinstance(classic, list):
            panels.extend(classic)
    except Exception:
        pass
    try:
        hyperconv = api.get_sellable_by_panel(
            dc_code=str(dc_id),
            family="virt_hyperconverged",
            clusters=hyperconv_clusters,
        ) or []
        if isinstance(hyperconv, list):
            panels.extend(hyperconv)
    except Exception:
        pass
    for fam in VIRT_POWER_FAMILIES:
        try:
            chunk = api.get_sellable_by_panel(dc_code=str(dc_id), family=fam) or []
            if isinstance(chunk, list):
                panels.extend(chunk)
        except Exception:
            continue
    return panels


def total_potential_tl(panels: list[dict]) -> float:
    """Sum ``potential_tl`` across panel dicts."""
    total = 0.0
    for p in panels:
        if isinstance(p, dict):
            total += float(p.get("potential_tl") or 0.0)
    return total


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
        tl = float(p.get("potential_tl") or 0.0)
        total_tl += tl
        if kind not in by_kind:
            continue
        by_kind[kind]["constrained"] = float(by_kind[kind]["constrained"]) + float(p.get("sellable_constrained") or 0.0)
        by_kind[kind]["tl"] = float(by_kind[kind]["tl"]) + tl
        unit = p.get("display_unit")
        if unit:
            by_kind[kind]["unit"] = unit
        has_known_kind = True
    return total_tl, by_kind, has_known_kind
