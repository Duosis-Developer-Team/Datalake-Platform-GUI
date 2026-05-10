"""Shared virtualization sellable panel fetch + aggregation for DC list and DC detail.

Matches crm-engine ``get_sellable_by_panel`` usage in ``app.py`` callbacks so Potential
Sales on ``/datacenters`` can align with Virtualization tab totals when the same cluster
scope is passed (including explicit full cluster lists for compute-backed panels).
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
