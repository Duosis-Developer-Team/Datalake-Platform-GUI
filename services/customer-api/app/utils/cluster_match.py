"""Cluster name normalization for VMware vs Nutanix cross-platform matching."""

from __future__ import annotations

import re

_CLUSTER_SUFFIXES = re.compile(
    r"[-_]?(?:Cluster|CLS|SSD|NVME|HYBRID|NEW|OLD|VEEAM|VYS)(?=[-_]|$)",
    re.IGNORECASE,
)


def normalize_cluster_key(name: str) -> str:
    """Strip known storage/type suffixes to get a canonical base key for matching."""
    if not name or not str(name).strip():
        return ""
    key = str(name).strip()
    changed = True
    while changed:
        changed = False
        new_key = _CLUSTER_SUFFIXES.sub("", key)
        if new_key != key:
            key = new_key.rstrip("-_")
            changed = True
    return key.upper()


def build_cluster_arch_map(
    vmware_nonkm_clusters: list[str],
    nutanix_clusters: list[str],
) -> dict[str, list[str]]:
    """
    Classify Nutanix clusters as VMware-managed (normalize key matches a VMware non-KM cluster)
    or Pure Nutanix (AHV-only — no VMware non-KM cluster with the same normalized key).

    Returns JSON-serializable lists (for cache).
    """
    vmware_keys = {normalize_cluster_key(c) for c in vmware_nonkm_clusters if c}
    managed: list[str] = []
    pure: list[str] = []
    for n in nutanix_clusters:
        if not n:
            continue
        if normalize_cluster_key(n) in vmware_keys:
            managed.append(n)
        else:
            pure.append(n)
    return {"managed_nutanix": managed, "pure_nutanix": pure}
