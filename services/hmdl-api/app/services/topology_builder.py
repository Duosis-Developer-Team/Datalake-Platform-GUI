"""Build HMDL collector topology from Loki root locations and proxy catalog."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.db.queries import loki_locations as loki_q
from app.services import sync_status
from app.services.dc_code import extract_dc_code
from app.services.proxy_catalog import load_proxy_catalog, proxies_for_dc

LOKI_SOURCE_ID = "LOKI"


def _resolve_catalog_dc(location_name: str, catalog: dict[str, dict[str, Any]]) -> str | None:
    """Map a root location name to a proxy_assignment catalog key."""
    dc_code = extract_dc_code(location_name)
    if dc_code and dc_code in catalog:
        return dc_code
    upper_name = location_name.strip().upper()
    if upper_name in catalog:
        return upper_name
    return None


def _build_proxy_nodes(
    dc_code: str,
    *,
    logs: dict[str, dict[str, Any]],
    stats: dict[str, dict[str, int]],
) -> tuple[list[dict[str, Any]], list[str]]:
    proxy_nodes: list[dict[str, Any]] = []
    proxy_statuses: list[str] = []
    for proxy in proxies_for_dc(dc_code):
        pid = str(proxy["id"])
        st = stats.get(pid, {"total": 0, "distributed": 0})
        pstatus = sync_status.proxy_loki_sync_status(
            logs.get(pid),
            total_targets=st["total"],
            distributed_targets=st["distributed"],
        )
        proxy_statuses.append(pstatus)
        log = logs.get(pid)
        proxy_nodes.append(
            {
                "proxy_id": pid,
                "proxy_nifi_host": proxy.get("proxy_nifi_host", ""),
                "loki_sync_status": pstatus,
                "target_count": st["total"],
                "distributed_count": st["distributed"],
                "last_sync_at": log.get("finished_at") if log else None,
                "last_sync_status": log.get("status") if log else None,
                "last_run_id": log.get("run_id") if log else None,
            }
        )
    return proxy_nodes, proxy_statuses


def build_location_nodes(
    *,
    hub_dc: str,
    logs: dict[str, dict[str, Any]],
    stats: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    catalog = load_proxy_catalog()
    nodes: list[dict[str, Any]] = []

    for loc in loki_q.fetch_root_locations():
        location_id = loc.get("id")
        location_name = str(loc.get("name") or "").strip()
        if not location_name:
            continue

        dc_code = extract_dc_code(location_name) or None
        catalog_dc = _resolve_catalog_dc(location_name, catalog)
        proxy_nodes: list[dict[str, Any]] = []
        loki_sync: str | None = None

        if catalog_dc:
            proxy_nodes, proxy_statuses = _build_proxy_nodes(
                catalog_dc,
                logs=logs,
                stats=stats,
            )
            loki_sync = sync_status.dc_loki_sync_status(proxy_statuses)
            proxy_config_status = "configured"
            effective_dc = catalog_dc
        else:
            proxy_config_status = "no_configured_proxy"
            effective_dc = dc_code

        is_hub = bool(
            effective_dc
            and effective_dc.upper() == hub_dc.upper()
        )
        nodes.append(
            {
                "location_id": int(location_id) if location_id is not None else None,
                "location_name": location_name,
                "dc_code": effective_dc,
                "description": loc.get("description"),
                "site_name": loc.get("site_name"),
                "role": "hub" if is_hub else "spoke",
                "proxy_config_status": proxy_config_status,
                "loki_sync_status": loki_sync,
                "proxies": proxy_nodes,
            }
        )

    return nodes


def build_flow_edges(nodes: list[dict[str, Any]], hub_dc: str) -> list[dict[str, Any]]:
    """Spoke locations ingest toward hub DC; proxy nodes distribute to parent location."""
    edges: list[dict[str, Any]] = []
    hub = hub_dc.upper()
    for node in nodes:
        parent = node.get("dc_code") or node.get("location_name") or ""
        for proxy in node.get("proxies") or []:
            pid = str(proxy.get("proxy_id") or "")
            if pid and parent:
                edges.append(
                    {
                        "from_dc": pid,
                        "to_dc": parent,
                        "edge_type": "distribution",
                    }
                )
        if node.get("role") == "hub":
            continue
        spoke = parent
        if not spoke:
            continue
        edges.append(
            {
                "from_dc": spoke,
                "to_dc": hub,
                "edge_type": "ingestion",
            }
        )
    return edges


def build_topology_payload(
    hub_dc: str,
    *,
    last_run: dict[str, Any] | None,
    logs: dict[str, dict[str, Any]],
    stats: dict[str, dict[str, int]],
) -> dict[str, Any]:
    hub_dc = hub_dc.upper()
    nodes = build_location_nodes(hub_dc=hub_dc, logs=logs, stats=stats)
    dc_statuses = sync_status.dc_statuses_from_nodes(nodes)
    synced, total = sync_status.count_synced_locations(nodes)
    configured, no_proxy = sync_status.count_proxy_config_status(nodes)

    return {
        "hub_dc": hub_dc,
        "source_node": {
            "id": LOKI_SOURCE_ID,
            "label": "Loki Inventory",
            "role": "source",
        },
        "generated_at": datetime.now(timezone.utc),
        "last_prod_run_id": last_run.get("run_id") if last_run else None,
        "last_prod_run_at": last_run.get("finished_at") if last_run else None,
        "nodes": nodes,
        "edges": build_flow_edges(nodes, hub_dc),
        "synced_dc_count": synced,
        "total_dc_count": total,
        "configured_location_count": configured,
        "no_configured_proxy_count": no_proxy,
        "dc_statuses": dc_statuses,
    }


def build_locations_payload(
    *,
    logs: dict[str, dict[str, Any]],
    stats: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    hub_dc = settings.hub_dc_code
    nodes = build_location_nodes(hub_dc=hub_dc, logs=logs, stats=stats)
    return [
        {
            "location_id": n.get("location_id"),
            "location_name": n.get("location_name"),
            "dc_code": n.get("dc_code"),
            "site_name": n.get("site_name"),
            "description": n.get("description"),
            "proxy_config_status": n.get("proxy_config_status"),
            "loki_sync_status": n.get("loki_sync_status"),
            "proxy_count": len(n.get("proxies") or []),
        }
        for n in nodes
    ]
