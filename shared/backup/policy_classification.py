"""NetBackup policytype → Image / Application panel classification.

Config-driven: mapping lives in ``policy_panel_mapping.yaml`` (and can later
be overridden by a webui settings table). Helper signatures accept an explicit
``mapping`` so callers and tests do not depend on file I/O.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

BackupCategory = Literal["image", "application"]

DEFAULT_NETBACKUP_IMAGE_POLICYTYPES: frozenset[str] = frozenset({"VMWARE"})

_MAPPING_PATH = Path(__file__).resolve().parent / "policy_panel_mapping.yaml"


def _normalize_policytype(policytype: str | None) -> str:
    if policytype is None:
        return ""
    return str(policytype).strip().upper()


def classify_netbackup_policy(
    policytype: str | None,
    mapping: dict[str, Any] | None = None,
) -> BackupCategory:
    """Return ``image`` or ``application`` for a NetBackup policytype.

    When ``mapping`` is omitted, :func:`load_policy_panel_mapping` is used.
    Policy types in ``image_policy_types`` (case-insensitive) map to image;
    everything else (including empty / Unknown) maps to application.
    """
    cfg = mapping if mapping is not None else load_policy_panel_mapping()
    image_types = {
        _normalize_policytype(t)
        for t in (cfg.get("image_policy_types") or DEFAULT_NETBACKUP_IMAGE_POLICYTYPES)
        if _normalize_policytype(t)
    }
    if not image_types:
        image_types = set(DEFAULT_NETBACKUP_IMAGE_POLICYTYPES)
    normalized = _normalize_policytype(policytype)
    if normalized and normalized in image_types:
        return "image"
    return "application"


def policy_types_for_category(
    category: BackupCategory,
    available: list[str] | set[str] | frozenset[str],
    mapping: dict[str, Any] | None = None,
) -> list[str]:
    """Filter ``available`` policy types that belong to ``category`` (sorted)."""
    out: list[str] = []
    for pt in available:
        if not pt:
            continue
        if classify_netbackup_policy(pt, mapping=mapping) == category:
            out.append(str(pt))
    return sorted(set(out), key=lambda s: s.upper())


@lru_cache(maxsize=1)
def load_policy_panel_mapping() -> dict[str, Any]:
    """Load policytype → panel mapping from YAML (cached).

    Falls back to the default ``VMWARE`` → image mapping when the file is
    missing or unreadable. Structure::

        {
          "image_policy_types": ["VMWARE", ...],
          "application_policy_types": ["SAP", ...],  # optional / documentary
        }
    """
    default: dict[str, Any] = {
        "image_policy_types": sorted(DEFAULT_NETBACKUP_IMAGE_POLICYTYPES),
        "application_policy_types": [],
    }
    try:
        import yaml
    except ImportError:
        return default

    if not _MAPPING_PATH.is_file():
        return default

    try:
        raw = yaml.safe_load(_MAPPING_PATH.read_text(encoding="utf-8")) or {}
    except OSError:
        return default

    if not isinstance(raw, dict):
        return default

    image = [
        str(t).strip()
        for t in (raw.get("image_policy_types") or default["image_policy_types"])
        if str(t).strip()
    ]
    application = [
        str(t).strip()
        for t in (raw.get("application_policy_types") or [])
        if str(t).strip()
    ]
    if not image:
        image = sorted(DEFAULT_NETBACKUP_IMAGE_POLICYTYPES)
    return {
        "image_policy_types": image,
        "application_policy_types": application,
    }


def clear_policy_panel_mapping_cache() -> None:
    """Clear the LRU cache (tests / future hot-reload of config)."""
    load_policy_panel_mapping.cache_clear()
