"""Load CRM product ↔ infrastructure matching registry (ADR-0024)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_REGISTRY_PATH = Path(__file__).resolve().parent / "product_matching_registry.yaml"

VALID_STATUSES = frozenset({
    "capacity",
    "documented",
    "sold_noted_customer_phase",
    "crm_only",
})


@lru_cache(maxsize=1)
def load_product_matching_registry() -> dict[str, dict[str, Any]]:
    """Return productnumber → matching metadata."""
    raw = yaml.safe_load(_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    products = raw.get("products") or {}
    out: dict[str, dict[str, Any]] = {}
    for key, entry in products.items():
        pn = str(key).strip()
        if not pn or not isinstance(entry, dict):
            continue
        status = str(entry.get("match_status") or "documented").strip()
        if status not in VALID_STATUSES:
            status = "documented"
        out[pn] = {
            "productnumber": pn,
            "name": str(entry.get("name") or pn),
            "usage_source": str(entry.get("usage_source") or ""),
            "matching_rule": str(entry.get("matching_rule") or ""),
            "match_status": status,
            "panel_key": (str(entry["panel_key"]).strip() if entry.get("panel_key") else None),
            "family": str(entry.get("family") or ""),
            "infra_tables": [str(t) for t in (entry.get("infra_tables") or [])],
            "notes": str(entry.get("notes") or ""),
        }
    return out


def clear_registry_cache() -> None:
    load_product_matching_registry.cache_clear()
