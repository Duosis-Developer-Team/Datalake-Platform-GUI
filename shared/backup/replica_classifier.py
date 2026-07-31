"""Pure VM name classification for DR / replica vs billable pools.

No database access. Defaults mirror ``replica_patterns.yaml`` (Platform Backup
Mapping seed). Callers may pass an explicit ``patterns`` dict for tests or a
future DB override export.

Buckets (v2)::

    silinecek → excluded
    veeam_dr → Veeam DR / replication name patterns
    altra_replica → external Altra / Cloud Connect style replicas
    custom → operator non-standard patterns
    billable → remainder

Legacy ``replica`` is not returned; use ``is_replica_like`` / ``filter_replica_names``.
Zerto VMs are identified from vendor tables, not name patterns.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Literal

VmBucket = Literal["silinecek", "veeam_dr", "altra_replica", "custom", "billable"]

_REPLICA_LIKE: frozenset[str] = frozenset({"veeam_dr", "altra_replica", "custom"})

_PATTERNS_PATH = Path(__file__).resolve().parent / "replica_patterns.yaml"

# Built-in defaults (keep in sync with replica_patterns.yaml when YAML missing).
_SILINECEK_RE = re.compile(r"silinecek", re.IGNORECASE)
_VEEAM_DR_SUFFIX_RE = re.compile(r"(_dr|_drc)$", re.IGNORECASE)
_VEEAM_DR_EMBEDDED_RE = re.compile(r"[_-]dr[_-]", re.IGNORECASE)
_ALTRA_SUFFIX_RE = re.compile(r"(_replica|_replika)$", re.IGNORECASE)
_ALTRA_CONTAINS_RE = re.compile(r"replica|replika", re.IGNORECASE)


def is_replica_like(bucket: str | None) -> bool:
    """True for veeam_dr / altra_replica / custom (name-based replica pools)."""
    return (bucket or "") in _REPLICA_LIKE


def classify_vm_name(
    name: str | None,
    patterns: dict[str, Any] | None = None,
) -> VmBucket:
    """Return silinecek, veeam_dr, altra_replica, custom, or billable.

    Order: silinecek → veeam_dr → altra_replica → custom → billable.
    Empty / None names are ``billable``.
    """
    raw = (name or "").strip()
    if not raw:
        return "billable"

    if patterns is None:
        return _classify_builtin(raw)

    if _matches_silinecek(raw, patterns):
        return "silinecek"
    if _matches_bucket(raw, patterns, "veeam_dr_patterns"):
        return "veeam_dr"
    if _matches_bucket(raw, patterns, "altra_replica_patterns"):
        return "altra_replica"
    if _matches_bucket(raw, patterns, "custom_patterns"):
        return "custom"
    # Legacy flat replica_patterns (v1 seed) → treat as veeam_dr first-match
    # then altra via value heuristics is too fragile; map all to veeam_dr for
    # backward compat only when no v2 keys present.
    if _legacy_flat_replica(patterns) and _matches_bucket(raw, patterns, "replica_patterns"):
        return _legacy_bucket_for_name(raw)
    return "billable"


def filter_replica_names(
    names: Iterable[str | None],
    patterns: dict[str, Any] | None = None,
    *,
    buckets: Iterable[str] | None = None,
) -> list[str]:
    """Return names classified into replica-like buckets (order preserved)."""
    allowed = set(buckets) if buckets is not None else set(_REPLICA_LIKE)
    out: list[str] = []
    for name in names:
        if name is None:
            continue
        text = str(name).strip()
        if not text:
            continue
        if classify_vm_name(text, patterns=patterns) in allowed:
            out.append(text)
    return out


def reconcile_vendor_counts(
    replica_vm_count: int | float | None = None,
    veeam_objects: int | float | None = None,
    zerto_vms: int | float | None = None,
    *,
    veeam_dr_count: int | float | None = None,
    altra_count: int | float | None = None,
) -> dict[str, Any]:
    """Compare name-based pools to Veeam + Zerto vendor counters.

    Prefer ``veeam_dr_count`` + ``altra_count``. When only ``replica_vm_count``
    is passed (legacy), it is treated as the combined name-based pool.

    ``gap`` = name_pool − (veeam objects + zerto VMs). Altra names are included
    in the name pool but have no vendor counter yet (expected gap contribution).
    """
    veeam = int(veeam_objects or 0)
    zerto = int(zerto_vms or 0)
    veeam_dr = int(veeam_dr_count) if veeam_dr_count is not None else None
    altra = int(altra_count) if altra_count is not None else None

    if veeam_dr is not None or altra is not None:
        name_pool = int(veeam_dr or 0) + int(altra or 0)
    else:
        name_pool = int(replica_vm_count or 0)

    vendor_total = veeam + zerto
    gap = name_pool - vendor_total
    return {
        "replica_vm_count": name_pool,
        "veeam_dr_count": int(veeam_dr or 0) if veeam_dr is not None else None,
        "altra_count": int(altra or 0) if altra is not None else None,
        "veeam_objects": veeam,
        "zerto_vms": zerto,
        "vendor_total": vendor_total,
        "gap": gap,
        "status": "ok" if gap == 0 else "mismatch",
    }


def classify_veeam_session_or_job_type(
    value: str | None,
    mapping: dict[str, Any] | None = None,
) -> Literal["replica", "backup", "other"]:
    """Map Veeam session_type or jobs.type to replica / backup / other.

    When ``mapping`` (or loaded YAML) lists exact type strings under
    ``veeam_replication_session_types`` / ``veeam_backup_session_types``, those
    win. Otherwise builtin contains heuristics apply.
    """
    raw = (value or "").strip()
    if not raw:
        return "other"

    cfg = mapping if mapping is not None else load_veeam_session_mapping()
    rep = {
        str(t).strip().casefold()
        for t in (cfg.get("veeam_replication_session_types") or [])
        if str(t).strip()
    }
    bak = {
        str(t).strip().casefold()
        for t in (cfg.get("veeam_backup_session_types") or [])
        if str(t).strip()
    }
    key = raw.casefold()
    if key in rep:
        return "replica"
    if key in bak:
        return "backup"
    # Builtin fallback for unlisted types
    if "replica" in key:
        return "replica"
    if "backup" in key:
        return "backup"
    return "other"


@lru_cache(maxsize=8)
def load_veeam_session_mapping(path: str | None = None) -> dict[str, Any]:
    """Load Veeam session_type → replication/backup seed YAML."""
    mapping_path = Path(path) if path else (
        Path(__file__).resolve().parent / "veeam_session_mapping.yaml"
    )
    default: dict[str, Any] = {
        "version": 1,
        "veeam_replication_session_types": ["ReplicaJob", "VSphereReplica", "Replica"],
        "veeam_backup_session_types": ["BackupJob", "Backup", "BackupCopyJob"],
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


def clear_veeam_session_mapping_cache() -> None:
    load_veeam_session_mapping.cache_clear()


def _classify_builtin(name: str) -> VmBucket:
    if _SILINECEK_RE.search(name):
        return "silinecek"
    if _VEEAM_DR_SUFFIX_RE.search(name) or _VEEAM_DR_EMBEDDED_RE.search(name):
        return "veeam_dr"
    if _ALTRA_SUFFIX_RE.search(name) or _ALTRA_CONTAINS_RE.search(name):
        return "altra_replica"
    return "billable"


def _legacy_flat_replica(patterns: dict[str, Any]) -> bool:
    has_v2 = bool(
        patterns.get("veeam_dr_patterns")
        or patterns.get("altra_replica_patterns")
        or patterns.get("custom_patterns")
    )
    return (not has_v2) and bool(patterns.get("replica_patterns"))


def _legacy_bucket_for_name(name: str) -> VmBucket:
    """When only v1 replica_patterns matched, split by builtin heuristics."""
    builtin = _classify_builtin(name)
    if builtin in ("veeam_dr", "altra_replica"):
        return builtin
    return "veeam_dr"


def _matches_silinecek(name: str, patterns: dict[str, Any]) -> bool:
    for rule in patterns.get("silinecek") or []:
        if _rule_matches(name, rule):
            return True
    return bool(_SILINECEK_RE.search(name))


def _matches_bucket(name: str, patterns: dict[str, Any], key: str) -> bool:
    for rule in patterns.get(key) or []:
        if isinstance(rule, dict) and _rule_matches(name, rule):
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
        "version": 2,
        "silinecek": [
            {
                "id": "silinecek_contains",
                "match": "contains",
                "value": "silinecek",
                "case_insensitive": True,
            }
        ],
        "veeam_dr_patterns": [],
        "altra_replica_patterns": [],
        "custom_patterns": [],
        "replica_patterns": [],  # legacy
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
