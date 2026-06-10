"""Environment-level connectivity status for HMDL Sync Health overview."""

from __future__ import annotations

from typing import Any

EnvironmentStatus = str  # connected | connectivity_issue | no_configured_proxy


def resolve_environment_status(
    proxy_config_status: str,
    category_counts: dict[str, int] | None,
) -> str:
    """Derive per-location environment badge from proxy config and check logs."""
    if proxy_config_status == "no_configured_proxy":
        return "no_configured_proxy"
    counts = category_counts or {}
    if int(counts.get("connectivity_issue") or 0) > 0:
        return "connectivity_issue"
    return "connected"


def count_environments(nodes: list[dict[str, Any]]) -> tuple[int, int, int]:
    """Return (connected, connectivity_issue, no_configured_proxy) counts."""
    connected = connectivity = no_proxy = 0
    for node in nodes:
        status = str(node.get("environment_status") or "")
        if status == "connected":
            connected += 1
        elif status == "connectivity_issue":
            connectivity += 1
        elif status == "no_configured_proxy":
            no_proxy += 1
    return connected, connectivity, no_proxy
