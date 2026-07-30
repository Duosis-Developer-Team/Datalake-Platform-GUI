"""Pure VM name classification for DR / replica vs billable pools.

No database access. Defaults mirror ``replica_patterns.yaml`` (Platform Backup
Mapping seed). Callers may pass an explicit ``patterns`` dict for tests or a
future DB override export.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Literal

VmBucket = Literal["silinecek", "replica", "billable"]

_PATTERNS_PATH = Path(__file__).resolve().parent / "replica_patterns.yaml"

# Built-in defaults (keep in sync with replica_patterns.yaml).
_SILINECEK_RE = re.compile(r"silinecek", re.IGNORECASE)
_SUFFIX_RE = re.compile(r"(_dr|_drc|_replica|_replika)$", re.IGNORECASE)
_EMBEDDED_DR_RE = re.compile(r"[_-]dr[_-]", re.IGNORECASE)
_CONTAINS_REPLICA_RE = re.compile(r"replica|replika", re.IGNORECASE)


def classify_vm_name(
    name: str | None,
    patterns: dict[str, Any] | None = None,
) -> VmBucket:
    """Return ``silinecek``, ``replica``, or ``billable`` for a VM name.

    Order: silinecek exclude first, then DR/replica patterns, else billable.
    Empty / None names are ``billable`` (nothing to classify as replica).
    """
    raw = (name or "").strip()
    if not raw:
        return "billable"

    if patterns is None:
        if _SILINECEK_RE.search(raw):
            return "silinecek"
        if _is_replica_name(raw):
            return "replica"
        return "billable"

    if _matches_silinecek(raw, patterns):
        return "silinecek"
    if _matches_replica(raw, patterns):
        return "replica"
    return "billable"


def filter_replica_names(
    names: Iterable[str | None],
    patterns: dict[str, Any] | None = None,
) -> list[str]:
    """Return names classified as ``replica`` (order preserved, empties dropped)."""
    out: list[str] = []
    for name in names:
        if name is None:
            continue
        text = str(name).strip()
        if not text:
            continue
        if classify_vm_name(text, patterns=patterns) == "replica":
            out.append(text)
    return out


def reconcile_vendor_counts(
    replica_vm_count: int | float | None,
    veeam_objects: int | float | None,
    zerto_vms: int | float | None,
) -> dict[str, Any]:
    """Compare name-based replica pool size to Veeam + Zerto vendor counters.

    ``gap`` = replica pool − (veeam objects + zerto VMs). Non-zero gap means
    leakage or double-count; status is ``ok`` only when gap is zero.
    """
    replica = int(replica_vm_count or 0)
    veeam = int(veeam_objects or 0)
    zerto = int(zerto_vms or 0)
    vendor_total = veeam + zerto
    gap = replica - vendor_total
    return {
        "replica_vm_count": replica,
        "veeam_objects": veeam,
        "zerto_vms": zerto,
        "vendor_total": vendor_total,
        "gap": gap,
        "status": "ok" if gap == 0 else "mismatch",
    }


def _is_replica_name(name: str) -> bool:
    return bool(
        _SUFFIX_RE.search(name)
        or _EMBEDDED_DR_RE.search(name)
        or _CONTAINS_REPLICA_RE.search(name)
    )


def _matches_silinecek(name: str, patterns: dict[str, Any]) -> bool:
    for rule in patterns.get("silinecek") or []:
        if _rule_matches(name, rule):
            return True
    # Fallback when override omits silinecek block
    return bool(_SILINECEK_RE.search(name))


def _matches_replica(name: str, patterns: dict[str, Any]) -> bool:
    rules = patterns.get("replica_patterns") or []
    if not rules:
        return _is_replica_name(name)
    for rule in rules:
        if _rule_matches(name, rule):
            return True
    return False


def _rule_matches(name: str, rule: dict[str, Any]) -> bool:
    value = str(rule.get("value") or "")
    if not value:
        return False
    method = str(rule.get("match") or "contains").lower()
    case_insensitive = bool(rule.get("case_insensitive", True))
    hay = name.casefold() if case_insensitive else name
    needle = value.casefold() if case_insensitive else value
    if method == "suffix":
        return hay.endswith(needle)
    if method == "prefix":
        return hay.startswith(needle)
    if method == "exact":
        return hay == needle
    # contains (default)
    return needle in hay


@lru_cache(maxsize=8)
def load_replica_patterns(path: str | None = None) -> dict[str, Any]:
    """Load replica pattern seed YAML (optional path for override / tests)."""
    mapping_path = Path(path) if path else _PATTERNS_PATH
    default: dict[str, Any] = {
        "version": 1,
        "silinecek": [
            {
                "id": "silinecek_contains",
                "match": "contains",
                "value": "silinecek",
                "case_insensitive": True,
            }
        ],
        "replica_patterns": [],
    }
    try:
        import yaml
    except ImportError:
        return default

    if not mapping_path.is_file():
        return default

    try:
        raw = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
    except OSError:
        return default

    if not isinstance(raw, dict):
        return default
    return raw


def clear_replica_patterns_cache() -> None:
    """Clear LRU cache for tests / hot-reload."""
    load_replica_patterns.cache_clear()
