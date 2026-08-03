"""Coverage topology graph — same React Flow canvas as the ETL hub view.

Builds the `graphData` payload for `dash_hmdl_flow.HmdlFlow`: a product hub with
DC spokes that expand into parents (vCenter / Prism / HMC) and then into their
children (clusters / IBM hosts).
"""

from __future__ import annotations

from collections import defaultdict

import dash_hmdl_flow
from dash import html

_PROBLEM_STATUSES = frozenset({"missing", "partial", "stale"})
_STATUS_RANK = ["missing", "partial", "stale", "extra", "unknown", "live"]
_COVERAGE_FLOW_ID = "hmdl-coverage-flow"
# Hub-spoke is for matched topology only. Parentless clusters stay in the expand
# table ("Parent eşleşmeyen"); drawing them as UNKNOWN / synthetic parents was noise.


def worst_status(statuses: list[str]) -> str:
    rank = {s: i for i, s in enumerate(_STATUS_RANK)}
    worst = "unknown"
    worst_i = len(_STATUS_RANK)
    for s in statuses:
        i = rank.get(str(s or "unknown"), rank["unknown"])
        if i < worst_i:
            worst_i = i
            worst = str(s or "unknown")
    return worst if statuses else "unknown"


def rollup_group_status(statuses: list[str]) -> str:
    """Mixed live + problem children → partial (DC / hub badge)."""
    norms = [str(s or "unknown") for s in statuses]
    if not norms:
        return "unknown"
    uniq = set(norms)
    if uniq == {"live"}:
        return "live"
    problems = {"missing", "stale", "partial", "extra", "offline", "unknown"}
    if "live" in uniq and (uniq & problems):
        return "partial"
    return worst_status(norms)


def parent_display_name(row: dict) -> str:
    """Operators know parents by collector entity name; parent_name is the fallback."""
    return (
        str(row.get("endpoint_name") or "").strip()
        or str(row.get("parent_name") or "").strip()
        or "—"
    )


def _parent_key(row: dict) -> str:
    """Join key the API resolved between a cluster and its collector endpoint."""
    return str(row.get("parent_key") or row.get("parent_name") or "").strip()


def _is_source(row: dict, product: str) -> bool:
    return str(row.get("source") or "").lower() == product


def _cluster_node(cluster: dict, prefix: str) -> dict:
    name = str(cluster.get("cluster_name") or "—")
    return {
        "id": f"{prefix}::cl::{name}",
        "label": name,
        "sublabel": str(cluster.get("expected_source") or ""),
        "status": str(cluster.get("status") or "unknown"),
        "kind": "child",
    }


def _host_node(host: dict, prefix: str) -> dict:
    name = str(host.get("servername") or "—")
    return {
        "id": f"{prefix}::host::{name}",
        "label": name,
        "sublabel": str(host.get("expected_source") or ""),
        "status": str(host.get("status") or "unknown"),
        "kind": "child",
    }


def _virtualization_parent_nodes(vcenters: list[dict], clusters: list[dict], prefix: str) -> list[dict]:
    by_parent: dict[str, list[dict]] = defaultdict(list)
    parent_keys = {_parent_key(v) for v in vcenters if _parent_key(v)}
    for c in clusters:
        key = _parent_key(c)
        if key and key in parent_keys:
            by_parent[key].append(c)

    nodes: list[dict] = []
    for v in vcenters:
        key = _parent_key(v)
        kids = by_parent.get(key, [])
        node_id = f"{prefix}::p::{key or parent_display_name(v)}"
        nodes.append(
            {
                "id": node_id,
                "label": parent_display_name(v),
                "sublabel": str(v.get("endpoint_ip") or "IP eşleşmedi"),
                "status": str(v.get("status") or "unknown"),
                "kind": "parent",
                "children": [_cluster_node(c, node_id) for c in kids],
            }
        )
    return nodes


def _ibm_parent_nodes(hmcs: list[dict], hosts: list[dict], prefix: str) -> list[dict]:
    by_hmc: dict[str, list[dict]] = defaultdict(list)
    for h in hosts:
        name = str(h.get("parent_name") or "").strip()
        if name and name != "HMC eşleşmedi":
            by_hmc[name].append(h)

    nodes: list[dict] = []
    for m in hmcs:
        name = str(m.get("hmc_name") or "—")
        if name == "HMC eşleşmedi":
            continue
        kids = by_hmc.get(name, [])
        node_id = f"{prefix}::hmc::{name}"
        nodes.append(
            {
                "id": node_id,
                "label": name,
                "sublabel": str(m.get("endpoint_ip") or "IP yok"),
                "status": str(m.get("status") or "unknown"),
                "kind": "parent",
                "children": [_host_node(h, node_id) for h in kids],
            }
        )
    return nodes


def build_coverage_graph(
    data: dict,
    *,
    product: str,
    product_label: str,
    selected_dc: str | None = None,
) -> dict:
    """`graphData` for HmdlFlow: hub → DC → parent → cluster/host."""
    data = data or {}
    product = (product or "vmware").lower()
    selected = (selected_dc or "").strip().upper() or None

    if product == "ibm":
        hmcs = data.get("ibm_hmcs") or []
        hosts = data.get("ibm_hosts") or []
        leaf_word = "host"

        def parent_builder(dc: str) -> list[dict]:
            return _ibm_parent_nodes(
                [m for m in hmcs if str(m.get("dc") or "").upper() == dc],
                [h for h in hosts if str(h.get("dc") or "").upper() == dc],
                dc,
            )

        dcs = sorted(
            {str(m.get("dc") or "").upper() for m in hmcs}
            | {str(h.get("dc") or "").upper() for h in hosts}
        )
        leaf_counts = {
            dc: sum(1 for h in hosts if str(h.get("dc") or "").upper() == dc) for dc in dcs
        }
    else:
        vcenters = [v for v in (data.get("vcenters") or []) if _is_source(v, product)]
        clusters = [c for c in (data.get("clusters") or []) if _is_source(c, product)]
        leaf_word = "cluster"

        def parent_builder(dc: str) -> list[dict]:
            return _virtualization_parent_nodes(
                [v for v in vcenters if str(v.get("dc") or "").upper() == dc],
                [c for c in clusters if str(c.get("dc") or "").upper() == dc],
                dc,
            )

        # Graph spokes are matched parents only — orphan / UNKNOWN-only clusters
        # stay in the table panel, not as a fake DC hub child.
        matched_clusters = [c for c in clusters if _parent_key(c)]
        dcs = sorted(
            {str(v.get("dc") or "").upper() for v in vcenters}
            | {str(c.get("dc") or "").upper() for c in matched_clusters}
        )
        leaf_counts = {
            dc: sum(1 for c in matched_clusters if str(c.get("dc") or "").upper() == dc)
            for dc in dcs
        }

    dcs = [dc for dc in dcs if dc and dc not in {"UNKNOWN", "DİĞER", "DIGER"}]
    if selected:
        parents = parent_builder(selected)
        return {
            "hub": {"label": selected, "sublabel": product_label},
            "nodes": parents,
        }

    nodes: list[dict] = []
    for dc in dcs:
        parents = parent_builder(dc)
        if not parents:
            continue
        statuses = [str(p.get("status") or "") for p in parents]
        bad = sum(1 for s in statuses if s in _PROBLEM_STATUSES)
        nodes.append(
            {
                "id": f"dc::{dc}",
                "label": dc,
                "sublabel": f"{len(parents)} parent · {leaf_counts.get(dc, 0)} {leaf_word}"
                + (f" · {bad} sorun" if bad else ""),
                "status": worst_status(statuses),
                "kind": "dc",
                "buttonLabel": "Bu DC'ye in",
                "selectValue": dc,
                "children": parents,
            }
        )
    return {"hub": {"label": product_label, "sublabel": "Tüm lokasyonlar"}, "nodes": nodes}


def build_backup_coverage_graph(
    data: dict,
    *,
    product: str,
    product_label: str,
    selected_dc: str | None = None,
) -> dict:
    """`graphData` for Backup: hub → DC → endpoint (IP is the join key)."""
    data = data or {}
    product = (product or "netbackup").lower()
    selected = (selected_dc or "").strip().upper() or None
    rows = [
        r
        for r in (data.get("backup_endpoints") or [])
        if str(r.get("source") or "").lower() == product
    ]

    def endpoint_nodes(dc: str) -> list[dict]:
        nodes: list[dict] = []
        for r in sorted(
            [x for x in rows if str(x.get("dc") or "").upper() == dc],
            key=lambda x: str(x.get("endpoint_name") or x.get("endpoint_ip") or ""),
        ):
            ip = str(r.get("endpoint_ip") or "").strip()
            name = str(r.get("endpoint_name") or "").strip() or ip or "—"
            nodes.append(
                {
                    "id": f"{dc}::ep::{ip or name}",
                    "label": name,
                    "sublabel": ip or "IP yok",
                    "status": str(r.get("status") or "unknown"),
                    "kind": "parent",
                    "children": [],
                }
            )
        return nodes

    dcs = sorted(
        {
            str(r.get("dc") or "").upper()
            for r in rows
            if str(r.get("dc") or "").strip()
            and str(r.get("dc") or "").upper() not in {"UNKNOWN", "DİĞER", "DIGER"}
        }
    )

    if selected:
        return {
            "hub": {"label": selected, "sublabel": product_label},
            "nodes": endpoint_nodes(selected),
        }

    nodes: list[dict] = []
    for dc in dcs:
        endpoints = endpoint_nodes(dc)
        if not endpoints:
            continue
        statuses = [str(e.get("status") or "") for e in endpoints]
        bad = sum(1 for s in statuses if s in _PROBLEM_STATUSES)
        nodes.append(
            {
                "id": f"dc::{dc}",
                "label": dc,
                "sublabel": f"{len(endpoints)} endpoint"
                + (f" · {bad} sorun" if bad else ""),
                "status": rollup_group_status(statuses),
                "kind": "dc",
                "buttonLabel": "Bu DC'ye in",
                "selectValue": dc,
                "children": endpoints,
            }
        )
    return {"hub": {"label": product_label, "sublabel": "Tüm lokasyonlar"}, "nodes": nodes}


def build_coverage_flow(
    graph: dict,
    *,
    height: int = 560,
    flow_id: str = _COVERAGE_FLOW_ID,
) -> html.Div:
    return html.Div(
        dash_hmdl_flow.HmdlFlow(
            id=flow_id,
            graphData=graph,
            height=height,
        )
    )
