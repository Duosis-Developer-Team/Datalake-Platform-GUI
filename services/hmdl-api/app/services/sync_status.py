"""Loki sync status aggregation for proxies and datacenters."""

from __future__ import annotations

from typing import Any

SYNC_OK_STATUSES = frozenset({"completed", "completed_with_blocked_removals"})


def proxy_loki_sync_status(
    last_log: dict[str, Any] | None,
    *,
    total_targets: int,
    distributed_targets: int,
) -> str:
    """Return loki_synced or not_synced for a single proxy NiFi node."""
    if not last_log:
        return "not_synced"
    if bool(last_log.get("dry_run")):
        return "not_synced"
    status = str(last_log.get("status") or "").lower()
    if status not in SYNC_OK_STATUSES:
        return "not_synced"
    if total_targets <= 0:
        return "loki_synced"
    if distributed_targets / total_targets >= 0.5:
        return "loki_synced"
    return "not_synced"


def dc_loki_sync_status(proxy_statuses: list[str]) -> str:
    if not proxy_statuses:
        return "not_synced"
    if all(s == "loki_synced" for s in proxy_statuses):
        return "loki_synced"
    return "not_synced"


def count_synced_dcs(dc_statuses: dict[str, str]) -> tuple[int, int]:
    total = len(dc_statuses)
    synced = sum(1 for s in dc_statuses.values() if s == "loki_synced")
    return synced, total
