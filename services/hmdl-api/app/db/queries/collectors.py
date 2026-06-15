"""SQL queries for HMDL collector read API."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.db import pool
from app.services import inclusion, sync_status
from app.services.proxy_catalog import find_proxy_entry, load_proxy_catalog, proxies_for_dc

_SCHEMA = settings.hmdl_schema


def _last_prod_run() -> dict[str, Any] | None:
    return pool.fetch_one(
        f"""
        SELECT run_id, MAX(finished_at) AS finished_at, MAX(started_at) AS started_at
        FROM {_SCHEMA}.collector_sync_log
        WHERE dry_run = FALSE
        GROUP BY run_id
        ORDER BY MAX(finished_at) DESC NULLS LAST, run_id DESC
        LIMIT 1
        """
    )


def _latest_logs_by_proxy() -> dict[str, dict[str, Any]]:
    rows = pool.fetch_all(
        f"""
        SELECT DISTINCT ON (proxy_id)
            id, run_id, awx_job_id, proxy_id, collector_id,
            added_count, removed_count, unchanged_count,
            status, dry_run, started_at, finished_at
        FROM {_SCHEMA}.collector_sync_log
        WHERE dry_run = FALSE
        ORDER BY proxy_id, finished_at DESC NULLS LAST, id DESC
        """
    )
    return {str(r["proxy_id"]): dict(r) for r in rows}


def _target_stats_by_proxy() -> dict[str, dict[str, int]]:
    rows = pool.fetch_all(
        f"""
        SELECT
            proxy_id,
            COUNT(*) FILTER (WHERE status = 'active') AS total_targets,
            COUNT(*) FILTER (
                WHERE status = 'active' AND last_distributed_at IS NOT NULL
            ) AS distributed_targets
        FROM {_SCHEMA}.collector_target
        GROUP BY proxy_id
        """
    )
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        pid = str(r["proxy_id"])
        out[pid] = {
            "total": int(r["total_targets"] or 0),
            "distributed": int(r["distributed_targets"] or 0),
        }
    return out


def _proxy_to_dc_map() -> dict[str, str]:
    from app.services.proxy_catalog import proxy_to_dc_map

    return proxy_to_dc_map()


def _enrich_node_environment(
    node: dict[str, Any], counts_by_dc: dict[str, dict[str, int]]
) -> dict[str, Any]:
    from app.services import environment_status as env

    proxy_config = str(node.get("proxy_config_status") or "")
    dc_code = node.get("dc_code")
    if proxy_config == "no_configured_proxy" or not dc_code:
        return {
            **node,
            "environment_status": "no_configured_proxy",
            "connectivity_issue_count": 0,
        }
    counts = counts_by_dc.get(str(dc_code).upper(), {})
    status = env.resolve_environment_status(proxy_config, counts)
    return {
        **node,
        "environment_status": status,
        "connectivity_issue_count": int(counts.get("connectivity_issue") or 0),
    }


def _enrich_topology_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from app.services import environment_status as env

    run_id = payload.get("last_prod_run_id")
    # Compute category counts for ALL DCs in a single bulk pass. Calling
    # _category_counts_for_dc per node issued ~4 queries each (one targets
    # fetch + three identical run-level lookups), so ~80 DCs meant ~320
    # queries per topology build and exhausted the connection pool under
    # concurrent load. See _category_counts_by_dc.
    counts_by_dc = _category_counts_by_dc(run_id)
    nodes = [_enrich_node_environment(n, counts_by_dc) for n in payload.get("nodes") or []]
    payload["nodes"] = nodes
    connected, connectivity, _no_proxy = env.count_environments(nodes)
    payload["connected_environment_count"] = connected
    payload["connectivity_issue_environment_count"] = connectivity
    return payload


def build_topology(hub_dc: str) -> dict[str, Any]:
    from app.services import topology_builder

    last_run = _last_prod_run()
    logs = _latest_logs_by_proxy()
    stats = _target_stats_by_proxy()
    payload = topology_builder.build_topology_payload(
        hub_dc,
        last_run=last_run,
        logs=logs,
        stats=stats,
    )
    return _enrich_topology_payload(payload)


def build_sync_summary() -> dict[str, Any]:
    from datetime import datetime, timezone

    topo = build_topology(settings.hub_dc_code)
    proxy_statuses: list[str] = []
    for node in topo["nodes"]:
        for p in node.get("proxies") or []:
            proxy_statuses.append(p["loki_sync_status"])

    return {
        "generated_at": datetime.now(timezone.utc),
        "last_prod_run_id": topo.get("last_prod_run_id"),
        "last_prod_run_at": topo.get("last_prod_run_at"),
        "synced_dc_count": topo["synced_dc_count"],
        "total_dc_count": topo["total_dc_count"],
        "configured_location_count": topo.get("configured_location_count", 0),
        "no_configured_proxy_count": topo.get("no_configured_proxy_count", 0),
        "connected_environment_count": topo.get("connected_environment_count", 0),
        "connectivity_issue_environment_count": topo.get("connectivity_issue_environment_count", 0),
        "synced_proxy_count": sum(1 for s in proxy_statuses if s == "loki_synced"),
        "total_proxy_count": len(proxy_statuses),
        "dc_statuses": topo.get("dc_statuses") or {},
    }


def get_proxy_detail(proxy_id: str) -> dict[str, Any] | None:
    dc_code, proxy_entry = find_proxy_entry(proxy_id)
    host = proxy_entry.get("proxy_nifi_host") if proxy_entry else None

    stats = _target_stats_by_proxy().get(proxy_id, {"total": 0, "distributed": 0})
    logs = pool.fetch_all(
        f"""
        SELECT id, run_id, awx_job_id, proxy_id, collector_id,
               added_count, removed_count, unchanged_count,
               status, dry_run, started_at, finished_at
        FROM {_SCHEMA}.collector_sync_log
        WHERE proxy_id = %s AND dry_run = FALSE
        ORDER BY finished_at DESC NULLS LAST, id DESC
        LIMIT 10
        """,
        (proxy_id,),
    )
    last = logs[0] if logs else None
    pstatus = sync_status.proxy_loki_sync_status(
        last,
        total_targets=stats["total"],
        distributed_targets=stats["distributed"],
    )
    return {
        "proxy_id": proxy_id,
        "dc_code": dc_code,
        "proxy_nifi_host": host,
        "loki_sync_status": pstatus,
        "target_count": stats["total"],
        "distributed_count": stats["distributed"],
        "last_sync": last,
        "recent_syncs": logs,
    }


def get_dc_summary(dc_code: str) -> dict[str, Any] | None:
    dc_code = dc_code.upper()
    topo = build_topology(settings.hub_dc_code)
    node = next(
        (n for n in topo["nodes"] if str(n.get("dc_code") or "").upper() == dc_code),
        None,
    )
    if not node:
        return None

    if node.get("proxy_config_status") == "no_configured_proxy":
        return {
            "dc_code": dc_code,
            "location_name": node.get("location_name"),
            "proxy_config_status": "no_configured_proxy",
            "environment_status": "no_configured_proxy",
            "connectivity_issue_count": 0,
            "loki_sync_status": "not_synced",
            "proxy_count": 0,
            "target_count": 0,
            "last_prod_run_id": topo.get("last_prod_run_id"),
            "last_prod_run_at": topo.get("last_prod_run_at"),
            "recent_diffs": [],
            "category_counts": {},
        }

    proxy_ids = [p["proxy_id"] for p in node.get("proxies") or []]
    if not proxy_ids:
        return {
            "dc_code": dc_code,
            "loki_sync_status": node["loki_sync_status"],
            "proxy_count": 0,
            "target_count": 0,
            "last_prod_run_id": topo.get("last_prod_run_id"),
            "last_prod_run_at": topo.get("last_prod_run_at"),
            "recent_diffs": [],
            "category_counts": {},
        }

    placeholders = ",".join(["%s"] * len(proxy_ids))
    target_count_row = pool.fetch_one(
        f"""
        SELECT COUNT(*) AS cnt
        FROM {_SCHEMA}.collector_target
        WHERE dc_code = %s AND status = 'active'
        """,
        (dc_code,),
    )
    diffs = pool.fetch_all(
        f"""
        SELECT run_id, proxy_id, conf_key, action, host(ip)::text AS ip, reason, created_at
        FROM {_SCHEMA}.collector_diff_log
        WHERE proxy_id IN ({placeholders})
        ORDER BY created_at DESC
        LIMIT 25
        """,
        tuple(proxy_ids),
    )

    last_run = _last_prod_run()
    run_id = last_run.get("run_id") if last_run else None
    category_counts = _category_counts_for_dc(dc_code, run_id)

    return {
        "dc_code": dc_code,
        "location_name": node.get("location_name"),
        "proxy_config_status": "configured",
        "environment_status": node.get("environment_status"),
        "connectivity_issue_count": node.get("connectivity_issue_count", 0),
        "loki_sync_status": node["loki_sync_status"],
        "proxy_count": len(proxy_ids),
        "target_count": int(target_count_row["cnt"] or 0) if target_count_row else 0,
        "last_prod_run_id": topo.get("last_prod_run_id"),
        "last_prod_run_at": topo.get("last_prod_run_at"),
        "recent_diffs": diffs,
        "category_counts": category_counts,
    }


def _removed_ip_keys(last_run_id: str | None) -> set[str]:
    """`ip|proxy_id` keys removed in the given run (run-scoped, not per-DC)."""
    if not last_run_id:
        return set()
    removed = pool.fetch_all(
        f"""
        SELECT DISTINCT host(ip)::text AS ip, proxy_id
        FROM {_SCHEMA}.collector_diff_log
        WHERE run_id = %s AND action = 'removed'
        """,
        (last_run_id,),
    )
    return {f"{r['ip']}|{r['proxy_id']}" for r in removed}


def _connectivity_fail_keys(last_run_id: str | None) -> set[str]:
    """`ip|proxy_id` keys that failed post-reconcile checks (run-scoped)."""
    if not last_run_id:
        return set()
    fails = pool.fetch_all(
        f"""
        SELECT DISTINCT host(ip)::text AS ip, proxy_id
        FROM {_SCHEMA}.collector_check_log
        WHERE run_id = %s
          AND check_phase = 'post_reconcile'
          AND status NOT IN ('ok', 'success', 'passed')
        """,
        (last_run_id,),
    )
    return {f"{r['ip']}|{r['proxy_id']}" for r in fails}


def _last_run_finished_at(last_run_id: str | None) -> Any:
    """Finish time of the given run (run-scoped); None if unknown."""
    if not last_run_id:
        return None
    lr = pool.fetch_one(
        f"""
        SELECT MAX(finished_at) AS finished_at
        FROM {_SCHEMA}.collector_sync_log
        WHERE run_id = %s AND dry_run = FALSE
        """,
        (last_run_id,),
    )
    return lr.get("finished_at") if lr else None


def _classify_row(
    row: dict[str, Any],
    *,
    removed_ips: set[str],
    conn_fails: set[str],
    last_run_finished: Any,
) -> str:
    key = f"{row['ip']}|{row['proxy_id']}"
    pending = row.get("last_distributed_at") is None and last_run_finished is not None
    return inclusion.classify_target(
        extra=row.get("extra"),
        has_connectivity_fail=key in conn_fails,
        removed_in_last_run=key in removed_ips,
        pending_distribution=pending,
    )


def _category_counts_for_dc(dc_code: str, last_run_id: str | None) -> dict[str, int]:
    targets = _fetch_dc_targets(dc_code, last_run_id, category_filter=None)
    counts: dict[str, int] = {c: 0 for c in inclusion.INCLUSION_CATEGORIES}
    for t in targets:
        cat = t["inclusion_category"]
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def _category_counts_by_dc(last_run_id: str | None) -> dict[str, dict[str, int]]:
    """Category counts keyed by upper-cased dc_code for ALL DCs in one pass.

    Replaces per-node _category_counts_for_dc calls during topology
    enrichment: the run-level lookups (removed / connectivity-fail / run
    finish time) are computed once, and every active target is fetched in a
    single query, so the query count is constant regardless of DC count.
    """
    removed_ips = _removed_ip_keys(last_run_id)
    conn_fails = _connectivity_fail_keys(last_run_id)
    last_run_finished = _last_run_finished_at(last_run_id)

    rows = pool.fetch_all(
        f"""
        SELECT
            t.dc_code,
            host(t.ip)::text AS ip,
            t.proxy_id,
            t.extra,
            t.last_distributed_at
        FROM {_SCHEMA}.collector_target t
        WHERE t.status = 'active'
        """
    )

    counts_by_dc: dict[str, dict[str, int]] = {}
    for r in rows:
        dc = str(r.get("dc_code") or "").upper()
        if not dc:
            continue
        cat = _classify_row(
            r,
            removed_ips=removed_ips,
            conn_fails=conn_fails,
            last_run_finished=last_run_finished,
        )
        bucket = counts_by_dc.get(dc)
        if bucket is None:
            bucket = {c: 0 for c in inclusion.INCLUSION_CATEGORIES}
            counts_by_dc[dc] = bucket
        bucket[cat] = bucket.get(cat, 0) + 1
    return counts_by_dc


def _fetch_dc_targets(
    dc_code: str,
    last_run_id: str | None,
    *,
    category_filter: str | None,
    entity_name: str | None = None,
    ip: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = [dc_code.upper()]
    clauses = ["t.dc_code = %s", "t.status = 'active'"]

    if entity_name:
        clauses.append("t.entity_name ILIKE %s")
        params.append(f"%{entity_name}%")
    if ip:
        clauses.append("host(t.ip)::text ILIKE %s")
        params.append(f"%{ip}%")

    where = " AND ".join(clauses)
    rows = pool.fetch_all(
        f"""
        SELECT
            t.entity_name,
            host(t.ip)::text AS ip,
            t.proxy_id,
            t.extra,
            t.last_distributed_at,
            t.last_check_status,
            t.tenant_name,
            t.manufacturer,
            cd.conf_key
        FROM {_SCHEMA}.collector_target t
        LEFT JOIN {_SCHEMA}.collector_definition cd ON cd.id = t.collector_id
        WHERE {where}
        ORDER BY t.entity_name NULLS LAST, t.ip
        """,
        tuple(params),
    )

    removed_ips = _removed_ip_keys(last_run_id)
    conn_fails = _connectivity_fail_keys(last_run_id)
    last_run_finished = _last_run_finished_at(last_run_id)

    out: list[dict[str, Any]] = []
    for r in rows:
        ip_s = str(r["ip"])
        pid = str(r["proxy_id"])
        cat = _classify_row(
            {"ip": ip_s, "proxy_id": pid, "extra": r.get("extra"),
             "last_distributed_at": r.get("last_distributed_at")},
            removed_ips=removed_ips,
            conn_fails=conn_fails,
            last_run_finished=last_run_finished,
        )
        if category_filter and cat != category_filter:
            continue
        ps = inclusion.normalize_platform_status(r.get("extra"))
        out.append(
            {
                "entity_name": r.get("entity_name"),
                "ip": ip_s,
                "proxy_id": pid,
                "conf_key": r.get("conf_key"),
                "inclusion_category": cat,
                "platform_status": ps,
                "last_distributed_at": r.get("last_distributed_at"),
                "last_check_status": r.get("last_check_status"),
                "tenant_name": r.get("tenant_name"),
                "manufacturer": r.get("manufacturer"),
                "extra": r.get("extra") if isinstance(r.get("extra"), dict) else None,
            }
        )
    return out


def get_dc_targets(
    dc_code: str,
    *,
    category: str | None = None,
    entity_name: str | None = None,
    ip: str | None = None,
) -> dict[str, Any] | None:
    dc_code = dc_code.upper()
    topo = build_topology(settings.hub_dc_code)
    node = next(
        (n for n in topo["nodes"] if str(n.get("dc_code") or "").upper() == dc_code),
        None,
    )
    if not node:
        return None
    if node.get("proxy_config_status") == "no_configured_proxy":
        return {
            "dc_code": dc_code,
            "total": 0,
            "items": [],
            "category_filter": category,
        }
    if dc_code not in load_proxy_catalog():
        return None
    last_run = _last_prod_run()
    run_id = last_run.get("run_id") if last_run else None
    items = _fetch_dc_targets(
        dc_code,
        run_id,
        category_filter=category,
        entity_name=entity_name,
        ip=ip,
    )
    return {
        "dc_code": dc_code,
        "total": len(items),
        "items": items,
        "category_filter": category,
    }


def list_root_locations() -> list[dict[str, Any]]:
    topo = build_topology(settings.hub_dc_code)
    return [
        {
            "location_id": n.get("location_id"),
            "location_name": n.get("location_name"),
            "dc_code": n.get("dc_code"),
            "site_name": n.get("site_name"),
            "description": n.get("description"),
            "proxy_config_status": n.get("proxy_config_status"),
            "loki_sync_status": n.get("loki_sync_status"),
            "environment_status": n.get("environment_status"),
            "connectivity_issue_count": n.get("connectivity_issue_count", 0),
            "proxy_count": len(n.get("proxies") or []),
        }
        for n in topo.get("nodes") or []
    ]


def list_recent_runs(limit: int = 20) -> list[dict[str, Any]]:
    return pool.fetch_all(
        f"""
        SELECT DISTINCT ON (run_id, proxy_id)
            id, run_id, awx_job_id, proxy_id, collector_id,
            added_count, removed_count, unchanged_count,
            status, dry_run, started_at, finished_at
        FROM {_SCHEMA}.collector_sync_log
        WHERE dry_run = FALSE
        ORDER BY run_id DESC, proxy_id, finished_at DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (limit,),
    )
