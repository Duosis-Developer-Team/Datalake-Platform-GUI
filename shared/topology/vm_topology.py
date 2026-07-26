"""Deduped DC->Cluster->Host->VM topology from the live NetBox VM snapshot.

Pure tree-builder + the dedup SQL. Source: discovery_netbox_virtualization_vm.
One row per VM via a dedup key (instanceUUID, else name|cluster). vCLS/system
VMs are excluded; site/cluster/host gaps surface as explicit unmapped buckets.
"""
from __future__ import annotations

from typing import Any, Iterable

from shared.licensing.os_classifier import classify

_UNMAPPED_DC = "(DC atanmamış)"
_UNMAPPED_CLUSTER = "(cluster yok)"
_UNMAPPED_HOST = "(host yok)"

VM_OS_DEDUP_KEY_SQL = (
    "COALESCE(NULLIF(btrim(custom_fields_config_instance_uuid), ''), "
    "lower(name) || '|' || coalesce(cluster_name, ''))"
)

VM_TOPOLOGY_SQL = f"""
SELECT DISTINCT ON ({VM_OS_DEDUP_KEY_SQL})
    COALESCE(NULLIF(btrim(site_name), ''), '{_UNMAPPED_DC}')         AS dc,
    COALESCE(NULLIF(btrim(cluster_name), ''), '{_UNMAPPED_CLUSTER}') AS cluster,
    COALESCE(NULLIF(btrim(device_name), ''), '{_UNMAPPED_HOST}')     AS host,
    name                        AS vm_name,
    custom_fields_guest_os      AS guest_os,
    status_value                AS power_state
FROM public.discovery_netbox_virtualization_vm
ORDER BY {VM_OS_DEDUP_KEY_SQL}, (status_value = 'poweredOn') DESC
"""


def is_system_vm(name: str | None) -> bool:
    """vCLS-* are vSphere Cluster Services agent VMs — not licensable guests."""
    return (name or "").strip().lower().startswith("vcls")


def _empty_os() -> dict:
    return {"rhel": 0, "suse": 0, "windows": 0, "free": 0, "unknown": 0}


def build_tree(rows: Iterable[tuple], *, with_os: bool = False, with_vms: bool = False) -> dict[str, Any]:
    """Nest deduped VM rows into DC->cluster->host with per-node counts.

    rows: iterable of (dc, cluster, host, vm_name, guest_os, power_state).
    vCLS/system VMs are excluded. When with_os, each node also carries an OS tally.
    When with_vms, host nodes also carry the leaf VM list — OFF by default because
    ~20k VM leaves at once freeze the browser DOM (VM detail is loaded lazily
    per host instead).
    """
    dcs: dict[str, dict] = {}
    for dc, cluster, host, vm_name, guest_os, power_state in rows or []:
        if is_system_vm(vm_name):
            continue
        # Coalesce gaps to explicit unmapped buckets (defense-in-depth; the SQL
        # does the same, but a stray empty must never silently vanish).
        dc = (dc or "").strip() or _UNMAPPED_DC
        cluster = (cluster or "").strip() or _UNMAPPED_CLUSTER
        host = (host or "").strip() or _UNMAPPED_HOST
        d = dcs.setdefault(dc, {"clusters": {}})
        cl = d["clusters"].setdefault(cluster, {"hosts": {}})
        h = cl["hosts"].setdefault(host, {"vms": []})
        fam = classify(guest_os).family
        h["vms"].append({"name": vm_name, "os_family": fam, "power_state": power_state})

    def _os_tally(vms):
        t = _empty_os()
        for v in vms:
            t[v["os_family"]] = t.get(v["os_family"], 0) + 1
        return t

    def _counts(vms, **extra):
        running = sum(1 for v in vms if v["power_state"] == "poweredOn")
        return {**extra, "vms": len(vms), "running": running}

    out_dcs: list[dict] = []
    tot = {"dcs": 0, "clusters": 0, "hosts": 0, "vms": 0, "running": 0}
    for dc in sorted(dcs):
        out_clusters, dc_vms = [], []
        for cl in sorted(dcs[dc]["clusters"]):
            out_hosts, cl_vms = [], []
            for hn in sorted(dcs[dc]["clusters"][cl]["hosts"]):
                hvms = dcs[dc]["clusters"][cl]["hosts"][hn]["vms"]
                cl_vms.extend(hvms)
                node = {"name": hn, "counts": _counts(hvms)}
                if with_vms:
                    node["vms"] = hvms
                if with_os:
                    node["os"] = _os_tally(hvms)
                out_hosts.append(node)
            dc_vms.extend(cl_vms)
            cnode = {"name": cl, "counts": _counts(cl_vms, hosts=len(out_hosts)), "hosts": out_hosts}
            if with_os:
                cnode["os"] = _os_tally(cl_vms)
            out_clusters.append(cnode)
        dnode = {
            "name": dc,
            "counts": _counts(dc_vms, clusters=len(out_clusters),
                              hosts=sum(len(c["hosts"]) for c in out_clusters)),
            "clusters": out_clusters,
        }
        if with_os:
            dnode["os"] = _os_tally(dc_vms)
        out_dcs.append(dnode)
        tot["dcs"] += 1
        tot["clusters"] += dnode["counts"]["clusters"]
        tot["hosts"] += dnode["counts"]["hosts"]
        tot["vms"] += dnode["counts"]["vms"]
        tot["running"] += dnode["counts"]["running"]
    return {"dcs": out_dcs, "totals": tot}
