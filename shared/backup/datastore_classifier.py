"""Classify VMware datastore names for backup / replication attribution.

Virt KM sellable already excludes names matching NBU / veeam. This helper
attributes eligible pools for replication sellable:

- ``netbackup`` → NetBackup image path (excluded from Veeam and Zerto)
- ``veeam`` → Veeam-named DS (eligible for Veeam; excluded from Zerto)
- ``zerto`` → optional future token (ops-confirmed); unused by default
- ``other`` → classic / non-backup datastores (eligible for Veeam; eligible
  for Zerto when not veeam/netbackup)

Plan rules:
- Veeam may use all VMware datastores except NetBackup
- Zerto may use all VMware datastores except Veeam + NetBackup
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
    if "nbu" in raw or "netbackup" in raw:
        return "netbackup"
    if "veeam" in raw:
        return "veeam"
    if enable_zerto_token and "zerto" in raw:
        return "zerto"
    return "other"


def veeam_storage_eligible(name: str | None) -> bool:
    """True when Veeam replication may use this VMware datastore."""
    return classify_datastore_name(name) != "netbackup"


def zerto_storage_eligible(name: str | None) -> bool:
    """True when Zerto replication may use this VMware datastore."""
    return classify_datastore_name(name) not in ("netbackup", "veeam")
