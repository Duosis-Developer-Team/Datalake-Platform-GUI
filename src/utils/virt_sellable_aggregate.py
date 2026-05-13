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
    configured_family_workers = int(os.getenv("VIRT_SELLABLE_FAMILY_WORKERS", "1") or "1")
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
