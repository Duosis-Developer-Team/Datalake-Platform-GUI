"""Classify VMware datastore names for backup / replication attribution.

Virt KM sellable already excludes names matching NBU / veeam. This helper
attributes those excluded pools so capacity is not left unsold:

- ``veeam`` → Veeam replication storage (``backup_veeam_replication_storage``)
- ``netbackup`` → NetBackup image path (not Veeam/Zerto replication)
- ``other`` → classic / non-backup datastores

Zerto has no confirmed dedicated datastore naming convention; keep Zerto
storage on site/VPG metrics. Optional ``zerto`` token is reserved for a future
ops-confirmed pattern and is unused by default.
"""
from __future__ import annotations

from typing import Literal

DatastoreBucket = Literal["veeam", "netbackup", "zerto", "other"]


def classify_datastore_name(
    name: str | None,
    *,
    enable_zerto_token: bool = False,
) -> DatastoreBucket:
    """Return the sellable bucket for a datastore name (case-insensitive)."""
    raw = (name or "").strip().lower()
    if not raw:
        return "other"
    # NetBackup before Veeam when both tokens appear (ops NBU* naming).
    if "nbu" in raw:
        return "netbackup"
    if "veeam" in raw:
        return "veeam"
    if enable_zerto_token and "zerto" in raw:
        return "zerto"
    return "other"
