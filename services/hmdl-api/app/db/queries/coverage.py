"""SQL + assembly for the datalake coverage report.

Reads read-only tables in the `hmdl` schema:
  hmdl_datalake_coverage_cluster          — VMware + Nutanix cluster coverage
  hmdl_datalake_coverage_ibm_host         — IBM Power host coverage
  hmdl_datalake_coverage_vcenter          — vCenter / Prism parent rollup
  hmdl_datalake_coverage_backup_endpoint  — NetBackup / Veeam / Zerto endpoints
  hmdl_datalake_coverage_target           — NiFi collector connectivity (why missing)
  collector_target (+ collector_definition) — parent (vCenter / Prism / HMC) name+IP
  hmdl_datalake_collector_probe_log       — per-parent collector script smoke (badge)

`coverage_vcenter` only stores an opaque `parent_name` (an FQDN such as
`vc2dc16.blt.vc`, or a bare IP). Operators know parents by their collector entity
name, so parents are matched against `collector_target` to attach the real name,
IP and connectivity status. IBM hosts get the same treatment through their HMC.

Mirrors the query style of `collectors.py`: `_SCHEMA` f-string interpolation,
`pool.fetch_all`, `%s` positional params. Per-row status/reason derivation lives in
`app.services.coverage`.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any

from app.config import settings
from app.db import pool
from app.db.queries import collectors as coll_q
from app.db.queries import probe as probe_q
from app.services import coverage as cov

_logger = logging.getLogger(__name__)

_SCHEMA = settings.hmdl_schema

_BACKUP_SOURCES = frozenset({"netbackup", "veeam", "zerto", "nutanix_snapshot"})
_VCENTER_STATUSES = frozenset(
    {"live", "partial", "missing", "extra", "stale", "offline", "unknown"}
)
# NetBox VM aliases on the Nutanix path sometimes still carry a vCenter FQDN parent
# from cluster_description. That is not a Prism — strip before matching.
_VC_FQDN_PARENT_RE = re.compile(r"(?i)^vc\d*dc\d+\.[a-z0-9.-]+$")
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_VC_TOKEN_RE = re.compile(r"(vc\d+)", re.IGNORECASE)
_UNASSIGNED_HMC = "HMC eşleşmedi"
# G2HV12DC13 → G2HV, RHV13DC13 → RHV (sibling hint when metrics omit a host).
_IBM_HOST_FAMILY_RE = re.compile(r"^(.+?)\d*$")
_GENERIC_TOKENS = frozenset({"cls", "cluster", "clusters", "ssd", "nvme", "hybrid", "ahv", "prism"})


def _ibm_host_family(servername: str | None) -> str:
    """Stable name family for sibling HMC inference (RHV*, G2HV*, …)."""
    raw = str(servername or "").strip().upper()
    if not raw:
        return ""
    base = re.sub(r"DC\d+.*$", "", raw)
    m = _IBM_HOST_FAMILY_RE.match(base)
    return (m.group(1) if m else base).strip()

# Coverage tables are upsert-only, so a row outlives its entity: a decommissioned
# cluster or a host NetBox marked `offline` would keep reading as "expected, never
# collected". AWX now retires what a pass no longer sees by stamping `absent_since`,
# and that mark is the authority on what still exists.
#
# The window stays as a backstop for the case the mark cannot cover: a pass that dies
# between tables never runs its sweep, leaving that table on the previous run's rows.
# All rows of one pass share a `checked_at`, so this never drops a live row.
_RUN_WINDOW = "2 hours"


def _present_rows(table: str) -> str:
    return (
        f"absent_since IS NULL AND checked_at >="
        f" (SELECT max(checked_at) FROM {_SCHEMA}.{table} WHERE absent_since IS NULL)"
        f" - interval '{_RUN_WINDOW}'"
    )


def _fetch_clusters() -> list[dict[str, Any]]:
    table = "hmdl_datalake_coverage_cluster"
    return pool.fetch_all(
        f"""
        SELECT source, cluster_name, dc_code, parent_name, parent_conflict_with,
               expected_source, collected, expected, is_live, last_collected, checked_at
        FROM {_SCHEMA}.{table}
        WHERE {_present_rows(table)}
        ORDER BY source, cluster_name
        """
    )


def _fetch_ibm_hosts() -> list[dict[str, Any]]:
    table = "hmdl_datalake_coverage_ibm_host"
    return pool.fetch_all(
        f"""
        SELECT servername, dc_code, expected_source, collected, expected, is_live,
               COALESCE(is_offline, FALSE) AS is_offline, last_collected, checked_at
        FROM {_SCHEMA}.{table}
        WHERE {_present_rows(table)}
        ORDER BY servername
        """
    )


def _fetch_vcenters() -> list[dict[str, Any]]:
    table = "hmdl_datalake_coverage_vcenter"
    return pool.fetch_all(
        f"""
        SELECT source, parent_name, dc_code,
               expected_clusters, collected_clusters, live_clusters,
               status, checked_at
        FROM {_SCHEMA}.{table}
        WHERE {_present_rows(table)}
        ORDER BY source, parent_name
        """
    )


def _fetch_backup_endpoints() -> list[dict[str, Any]]:
    return pool.fetch_all(
        f"""
        SELECT source, endpoint_ip, endpoint_name, dc_code,
               collected, expected, expected_source, network_ok,
               last_collected, is_live, checked_at
        FROM {_SCHEMA}.hmdl_datalake_coverage_backup_endpoint
        ORDER BY source, dc_code, endpoint_ip
        """
    )


def _fetch_target_issues() -> list[dict[str, Any]]:
    """Unreachable / problematic collector targets, keyed later by (dc_code, platform)."""
    return pool.fetch_all(
        f"""
        SELECT dc_code, platform, dns, proxy, check_status, network_access
        FROM {_SCHEMA}.hmdl_datalake_coverage_target
        WHERE network_access IS NOT TRUE OR check_status <> 'ok'
        """
    )


def _fetch_platform_endpoints(patterns: tuple[str, ...]) -> list[dict[str, Any]]:
    """Active collector endpoints for the given platform key patterns."""
    conf_clause = " OR ".join(["lower(coalesce(cd.conf_key, '')) LIKE %s"] * len(patterns))
    manu_clause = " OR ".join(["lower(coalesce(t.manufacturer, '')) LIKE %s"] * len(patterns))
    return pool.fetch_all(
        f"""
        SELECT DISTINCT ON (host(t.ip)::text, lower(coalesce(cd.conf_key, t.manufacturer, '')))
            t.entity_name,
            host(t.ip)::text AS ip,
            t.dc_code,
            t.last_check_status,
            lower(coalesce(cd.conf_key, t.manufacturer, '')) AS platform_key
        FROM {_SCHEMA}.collector_target t
        LEFT JOIN {_SCHEMA}.collector_definition cd ON cd.id = t.collector_id
        WHERE t.status = 'active' AND (({conf_clause}) OR ({manu_clause}))
        ORDER BY host(t.ip)::text, lower(coalesce(cd.conf_key, t.manufacturer, '')), t.entity_name
        """,
        tuple(patterns) * 2,
    )


def _fetch_hmc_host_map() -> dict[str, str]:
    """server_name → HMC IP, from IBM Power metrics. Best effort: topology hint only."""
    try:
        rows = pool.fetch_all(
            "SELECT DISTINCT hmc_hostname, server_name FROM public.ibm_server_performance_metrics"
        )
    except Exception as exc:  # metrics table is outside the hmdl contract
        _logger.warning("IBM HMC host map unavailable: %s", exc)
        return {}
    out: dict[str, str] = {}
    for r in rows:
        server = str(r.get("server_name") or "").strip().upper()
        hmc = str(r.get("hmc_hostname") or "").strip()
        if server and hmc:
            out[server] = hmc
    return out


def _issues_by_key(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        key = ((r.get("dc_code") or "").upper(), (r.get("platform") or ""))
        out.setdefault(key, []).append(r)
    return out


def _resolve_dc(db_dc: Any, *name_fallbacks: Any) -> str:
    raw = str(db_dc or "").strip().upper()
    if raw and raw not in ("UNKNOWN", "NONE", "NULL"):
        return raw
    for name in name_fallbacks:
        derived = cov.derive_dc(name if isinstance(name, str) else None)
        if derived != "Diğer":
            return derived
    return raw or "Diğer"


def _is_ipv4(value: str | None) -> bool:
    return bool(_IPV4_RE.match((value or "").strip()))


def _norm_token(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _endpoint_source(platform_key: str) -> str:
    """Collector platform → coverage source family. Acropolis/AHV *is* Nutanix."""
    pk = (platform_key or "").lower()
    if "vmware" in pk or "esx" in pk:
        return "vmware"
    if "nutanix" in pk or "acropolis" in pk or "ahv" in pk or "prism" in pk:
        return "nutanix"
    return ""


def _raw_tokens(value: str | None) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (value or "").lower()) if t]


def _name_tokens(value: str | None) -> list[str]:
    """Identity-carrying tokens; storage/hypervisor adjectives say nothing about *which*
    cluster this is (`DC11-G3-SSD` and `PremierDC-Nutanix-DC11-G3` are the same thing)."""
    return [t for t in _raw_tokens(value) if t not in _GENERIC_TOKENS]


def _name_is_suffix(cluster_name: str | None, entity_name: str | None) -> bool:
    """`Azin Telecom-Nutanix-AZ11-CLS` is the collector *for* cluster `AZ11-CLS`.

    Entity names are written `<customer>-<platform>-<cluster>`, so a trailing run of
    tokens that reproduces the cluster name exactly is that cluster, not a coincidence.
    Requiring an identity token stops a bare `-CLS` tail from matching the whole DC.
    """
    tokens = _raw_tokens(cluster_name)
    if not tokens or not _name_tokens(cluster_name):
        return False
    entity = _raw_tokens(entity_name)
    return len(entity) > len(tokens) and entity[-len(tokens) :] == tokens


def _token_pool(value: str | None) -> set[str]:
    pool: set[str] = set()
    for token in _name_tokens(value):
        pool.add(token)
        # `DC14-FC1` vs `...-DC14-FC`: keep the de-numbered form, but never down to a
        # single letter (`G11` → `G` would match every group).
        stripped = token.rstrip("0123456789")
        if len(stripped) >= 2:
            pool.add(stripped)
    return pool


def _tokens_match(cluster_name: str | None, entity_name: str | None) -> bool:
    cluster_tokens = _name_tokens(cluster_name)
    if not cluster_tokens:
        return False
    pool = _token_pool(entity_name)
    for token in cluster_tokens:
        stripped = token.rstrip("0123456789")
        if token in pool or (len(stripped) >= 2 and stripped in pool):
            continue
        return False
    return True


def _assign_parent_endpoints(
    vcenter_rows: list[dict[str, Any]],
    cluster_rows: list[dict[str, Any]],
    endpoints: list[dict[str, Any]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Match `coverage_vcenter` parents to collector endpoints, per (source, DC).

    Matching runs in decreasing confidence: exact IP, `vcN`/name token, then a
    single leftover candidate. Endpoints whose name is itself a cluster name are
    dropped first — those are cluster-level collectors, never a parent.
    """
    # Keyed by source only: a cluster collector keeps its cluster name even when the
    # cluster row lands in another DC bucket (e.g. customer clusters resolved to UNKNOWN).
    cluster_names: dict[str, set[str]] = defaultdict(set)
    for c in cluster_rows:
        cluster_names[str(c.get("source") or "").lower()].add(_norm_token(c.get("cluster_name")))

    candidates: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for e in endpoints:
        src = _endpoint_source(str(e.get("platform_key") or ""))
        if not src:
            continue
        dc = str(e.get("dc_code") or "").strip().upper()
        candidates[(src, dc)].append(e)

    parents_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for v in vcenter_rows:
        src = str(v.get("source") or "").lower()
        dc = _resolve_dc(v.get("dc_code"), v.get("parent_name"))
        parents_by_key[(src, dc)].append(v)

    children: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for c in cluster_rows:
        parent = str(c.get("parent_name") or "").strip()
        if parent:
            key = (str(c.get("source") or "").lower(), c["dc"], parent)
            children[key].append(str(c.get("cluster_name") or ""))

    resolved: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, parents in parents_by_key.items():
        pool_all = candidates.get(key, [])
        if key[0] == "vmware":
            pool_parents = [
                e
                for e in pool_all
                if _norm_token(e.get("entity_name")) not in cluster_names.get(key[0], set())
            ]
        else:
            # A Prism endpoint is named after its own cluster, so it is a valid parent.
            pool_parents = list(pool_all)
        # An exact IP hit is unambiguous even for endpoints dropped from the parent pool.
        by_ip = {str(e.get("ip") or "").strip(): e for e in pool_all}
        used_ips: set[str] = set()
        pending: list[dict[str, Any]] = []

        orphan_ips: list[str] = []
        for p in parents:
            name = str(p.get("parent_name") or "").strip()
            if not _is_ipv4(name):
                pending.append(p)
                continue
            hit = by_ip.get(name)
            if hit:
                used_ips.add(name)
                resolved[(key[0], key[1], name)] = hit
            else:
                orphan_ips.append(name)

        for p in list(pending):
            name = str(p.get("parent_name") or "").strip()
            short = name.split(".")[0]
            short_norm = _norm_token(short)
            free = [e for e in pool_parents if str(e.get("ip") or "") not in used_ips]
            hit = next(
                (e for e in free if short_norm and short_norm in _norm_token(e.get("entity_name"))),
                None,
            )
            if hit is None:
                m = _VC_TOKEN_RE.search(short)
                if m:
                    token = m.group(1).lower()
                    hit = next(
                        (e for e in free if token in str(e.get("entity_name") or "").lower()),
                        None,
                    )
            if hit is not None:
                used_ips.add(str(hit.get("ip") or ""))
                resolved[(key[0], key[1], name)] = hit
                pending.remove(p)

        # The inventory IP (Prism VIP) is not always the address we collect from, so an
        # unmatched IP parent is identified through the clusters hanging off it.
        for ip in orphan_ips:
            free = [e for e in pool_parents if str(e.get("ip") or "") not in used_ips]
            hits = [
                e
                for e in free
                if any(_tokens_match(cn, e.get("entity_name")) for cn in children[(*key, ip)])
            ]
            if len(hits) == 1:
                used_ips.add(str(hits[0].get("ip") or ""))
                resolved[(key[0], key[1], ip)] = hits[0]
            else:
                resolved[(key[0], key[1], ip)] = {"ip": ip, "entity_name": None}

        if len(pending) != 1:
            continue
        free = [e for e in pool_parents if str(e.get("ip") or "") not in used_ips]
        if len(free) > 1:
            # Customer cluster collectors are usually unreachable stubs; a reachable
            # endpoint is the credible parent when only one is left.
            free = [e for e in free if str(e.get("last_check_status") or "").lower() == "ok"]
        if len(free) == 1:
            name = str(pending[0].get("parent_name") or "").strip()
            resolved[(key[0], key[1], name)] = free[0]

    return resolved


def _endpoint_parent_row(endpoint: dict[str, Any], clusters: list[dict[str, Any]]) -> dict[str, Any]:
    """Parent rollup for a collector endpoint that `coverage_vcenter` never produced."""
    expected = len(clusters)
    collected = sum(1 for c in clusters if c["collected"])
    live = sum(1 for c in clusters if c["is_live"])
    if collected == 0:
        status = "missing"
    elif live == expected:
        status = "live"
    elif live == 0:
        status = "stale"
    else:
        status = "partial"
    check = str(endpoint.get("last_check_status") or "").strip() or None
    ip = str(endpoint.get("ip") or "").strip() or None
    return {
        "source": endpoint["family"],
        "parent_name": endpoint.get("entity_name"),
        "parent_key": ip or str(endpoint.get("entity_name") or ""),
        "endpoint_ip": ip,
        "endpoint_name": str(endpoint.get("entity_name") or "").strip() or None,
        "collector_check_status": check,
        "collector_network_ok": (check.lower() == "ok") if check else None,
        "dc": str(endpoint.get("dc_code") or "").strip().upper(),
        "expected_clusters": expected,
        "collected_clusters": collected,
        "live_clusters": live,
        "status": status,
        "checked_at": None,
        "origin": "endpoint",
    }


def _apply_parent(cluster: dict[str, Any], endpoint: dict[str, Any]) -> None:
    ip = str(endpoint.get("ip") or "").strip() or None
    name = str(endpoint.get("entity_name") or "").strip() or None
    cluster["parent_key"] = ip or name or cluster.get("parent_name")
    cluster["parent_display"] = name or cluster.get("parent_name")
    cluster["parent_ip"] = ip


def _absorb_cluster(keeper: dict[str, Any], other: dict[str, Any]) -> None:
    """Fold a duplicate inventory row into the row that owns the collector endpoint.

    AWX writes one expected row per inventory source, so an AHV cluster also shows up
    as a never-collected `vmware` row. Both describe the same cluster; keeping them
    apart double-counts it and puts a phantom gap on the wrong product tab.
    """
    keeper["collected"] = keeper["collected"] or other["collected"]
    keeper["expected"] = keeper["expected"] or other["expected"]
    keeper["is_live"] = keeper["is_live"] or other["is_live"]
    dates = [d for d in (keeper.get("last_collected"), other.get("last_collected")) if d]
    keeper["last_collected"] = max(dates) if dates else None
    origins = {s for s in (keeper.get("expected_source"), other.get("expected_source")) if s}
    keeper["expected_source"] = "+".join(sorted(origins)) if origins else None
    keeper["target_issues"] = keeper.get("target_issues") or other.get("target_issues") or []
    keeper["status"] = cov.row_status(keeper["collected"], keeper["expected"], keeper["is_live"])
    keeper["reason"] = cov.reason_text(
        keeper["status"],
        keeper.get("last_collected"),
        keeper["target_issues"],
        source=keeper.get("source"),
    )


def _annotate_unmatched_reasons(
    clusters: list[dict[str, Any]], endpoints: list[dict[str, Any]]
) -> None:
    """Explain orphans using the same DC endpoint pool round 5 would have seen."""
    parents_by_dc: dict[tuple[str, str], int] = defaultdict(int)
    for e in endpoints:
        family = _endpoint_source(str(e.get("platform_key") or ""))
        if not family:
            continue
        dc = str(e.get("dc_code") or "").strip().upper()
        if dc:
            parents_by_dc[(family, dc)] += 1
    for c in clusters:
        if c.get("parent_key"):
            c["unmatched_reason"] = None
            continue
        c["unmatched_reason"] = cov.unmatched_reason_for(
            c,
            parents_in_dc=parents_by_dc.get(
                (str(c.get("source") or "").lower(), str(c.get("dc") or "")), 0
            ),
        )


def _resolve_cluster_parents(
    clusters: list[dict[str, Any]],
    vcenters: list[dict[str, Any]],
    endpoints: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Attach every cluster to the collector endpoint it is really collected from.

    Rounds run in decreasing confidence and never undo an earlier one:

    1. the `coverage_vcenter` parent the row already carries;
    2. its parent IP, then its name, then an entity name ending in it, then its identity
       tokens — within its own platform;
    3. duplicate inventory rows are folded into the row that won the endpoint;
    4. the same name/token match across platforms, which *relabels* the row, because the
       collector target is ground truth for platform (AHV clusters arrive as `vmware`);
    5. the DC's only vCenter, for *collected* VMware clusters left without a parent.

    `source=ibm` rows are inventory gaps with no collector — they stay unmatched on
    purpose (ADR-0031 §14) and never enter these rounds.

    Returns the surviving clusters plus parent rows synthesized for endpoints that have
    no `coverage_vcenter` rollup — today every Nutanix DC except DC13.
    """
    by_dc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in endpoints:
        family = _endpoint_source(str(e.get("platform_key") or ""))
        if not family:
            continue
        by_dc[str(e.get("dc_code") or "").strip().upper()].append({**e, "family": family})

    vcenter_by_parent: dict[tuple[str, str, str], dict[str, Any]] = {}
    for v in vcenters:
        vcenter_by_parent[(v["source"].lower(), v["dc"], str(v.get("parent_name") or ""))] = v
    rollup_ips = {str(v.get("endpoint_ip") or "") for v in vcenters if v.get("endpoint_ip")}

    pending: list[dict[str, Any]] = []
    for c in clusters:
        if c["source"].lower() == "ibm":
            continue
        parent = str(c.get("parent_name") or "").strip()
        hit = vcenter_by_parent.get((c["source"].lower(), c["dc"], parent)) if parent else None
        if hit is None:
            pending.append(c)
            continue
        c["parent_key"] = hit.get("endpoint_ip") or parent
        c["parent_display"] = hit.get("endpoint_name") or parent
        c["parent_ip"] = hit.get("endpoint_ip")

    # A Prism endpoint serves exactly one cluster, so it can only be claimed once;
    # a vCenter is shared by all of its clusters.
    claimed: set[str] = set(rollup_ips)
    attached: set[str] = set()
    endpoint_by_ip: dict[str, dict[str, Any]] = {
        str(e.get("ip") or ""): e for eps in by_dc.values() for e in eps
    }

    def take(cluster: dict[str, Any], endpoint: dict[str, Any]) -> None:
        cluster["source"] = endpoint["family"]
        _apply_parent(cluster, endpoint)
        ip = str(endpoint.get("ip") or "")
        if endpoint["family"] == "nutanix":
            claimed.add(ip)
        attached.add(ip)

    def free_endpoints(dc: str, family: str | None = None) -> list[dict[str, Any]]:
        return [
            e
            for e in by_dc.get(dc, [])
            if (family is None or e["family"] == family)
            and (e["family"] == "vmware" or str(e.get("ip") or "") not in claimed)
        ]

    def match(cluster: dict[str, Any], own_family_only: bool) -> dict[str, Any] | None:
        family = cluster["source"].lower() if own_family_only else None
        name = _norm_token(cluster.get("cluster_name"))
        pool = free_endpoints(cluster["dc"], family)
        hit = next((e for e in pool if _norm_token(e.get("entity_name")) == name), None)
        if hit is not None:
            return hit
        tail = [e for e in pool if _name_is_suffix(cluster.get("cluster_name"), e.get("entity_name"))]
        if len(tail) == 1:
            return tail[0]
        if not own_family_only and len(_name_tokens(cluster.get("cluster_name"))) < 2:
            # Moving a cluster to another platform needs real evidence. A lone site token
            # (`AZ11-CLS`) is shared by every endpoint in the DC and proves nothing.
            return None
        matches = [e for e in pool if _tokens_match(cluster.get("cluster_name"), e.get("entity_name"))]
        if not matches:
            return None
        # Closest name wins: `DC13-G11-HYBRID` belongs to `…-DC13-G11`, not to
        # `…-DC13-G11-HYBRID-NW`, which carries an extra identity token.
        matches.sort(key=lambda e: len(_name_tokens(e.get("entity_name"))))
        return matches[0]

    # A collected row describes reality, so let it claim the endpoint before a row that
    # only ever existed as an expectation.
    pending.sort(key=lambda c: (not c["collected"], not c["is_live"], str(c.get("cluster_name") or "")))

    still: list[dict[str, Any]] = []
    for c in pending:
        parent = str(c.get("parent_name") or "").strip()
        hit = endpoint_by_ip.get(parent) if _is_ipv4(parent) else None
        if hit is not None and str(hit.get("ip") or "") not in claimed:
            take(c, hit)
        else:
            still.append(c)

    # Metrics / NetBox description often store `vc2dc18.blt.vc` while the collector
    # entity is `…_vc2dc18`. Resolve that FQDN to the endpoint even when AWX has not
    # yet written a coverage_vcenter rollup for the same parent_name.
    pending, still = still, []
    for c in pending:
        parent = str(c.get("parent_name") or "").strip()
        short_norm = _norm_token(parent.split(".")[0]) if parent and not _is_ipv4(parent) else ""
        if not short_norm:
            still.append(c)
            continue
        hits = [
            e
            for e in free_endpoints(c["dc"], c["source"].lower())
            if short_norm in _norm_token(e.get("entity_name"))
        ]
        if len(hits) == 1:
            take(c, hits[0])
        else:
            still.append(c)

    pending, still = still, []
    for c in pending:
        hit = match(c, own_family_only=True)
        if hit is not None:
            take(c, hit)
        else:
            still.append(c)

    resolved = [c for c in clusters if c.get("parent_key")]
    dropped: set[int] = set()
    pending, still = still, []
    for c in pending:
        signature = (c["dc"], frozenset(_name_tokens(c.get("cluster_name"))))
        twin = next(
            (
                r
                for r in resolved
                # Same source means two genuinely distinct clusters that happen to share
                # identity tokens; only the cross-platform copy is a duplicate.
                if r["source"].lower() != c["source"].lower()
                and (r["dc"], frozenset(_name_tokens(r.get("cluster_name")))) == signature
            ),
            None,
        )
        if twin is None:
            # The endpoint is named after this row, yet another row already holds it:
            # NetBox lists one Nutanix cluster twice, once as a platform
            # (`Azin Telecom-Nutanix-AZ11-CLS` → `AZ11-CLS`) and once under its own
            # name (`PRISM-AZ11-SSD`). One endpoint means one cluster, two aliases.
            twin = next(
                (
                    r
                    for r in resolved
                    if r["dc"] == c["dc"]
                    and _name_is_suffix(c.get("cluster_name"), r.get("parent_display"))
                ),
                None,
            )
        if twin is not None:
            _absorb_cluster(twin, c)
            dropped.add(id(c))
        else:
            still.append(c)

    pending, still = still, []
    for c in pending:
        hit = match(c, own_family_only=False)
        if hit is not None:
            take(c, hit)
        else:
            still.append(c)

    for c in still:
        # Only a *collected* cluster proves a VMware collector in this DC really delivers
        # it, which is what makes "the DC's only vCenter" an inference rather than a
        # guess. An inventory-only row gets no parent: it is an honest gap, and hanging
        # it off the nearest vCenter is how `DC11-G3-CLS-IBM` ended up under PremierDC.
        if c["source"].lower() != "vmware" or not c["collected"]:
            continue
        vcenters_in_dc = [e for e in by_dc.get(c["dc"], []) if e["family"] == "vmware"]
        if len(vcenters_in_dc) == 1:
            take(c, vcenters_in_dc[0])

    clusters = [c for c in clusters if id(c) not in dropped]
    extra_parents = [
        _endpoint_parent_row(endpoint_by_ip[ip], [c for c in clusters if c.get("parent_key") == ip])
        for ip in sorted(attached)
        if ip and ip not in rollup_ips and ip in endpoint_by_ip
    ]
    parents = [p for p in extra_parents if p["expected_clusters"]]
    _annotate_unmatched_reasons(clusters, endpoints)
    return clusters, parents


def _drop_childless_rollups(
    vcenters: list[dict[str, Any]], clusters: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A rollup whose clusters all left the inventory is an empty shell.

    AWX recomputes `coverage_vcenter` from the cluster table including rows it stopped
    refreshing, so a retired Prism keeps advertising "1 cluster" long after that cluster
    is gone. Rendering the parent without its child only invents a gap.
    """
    keys = {str(c["parent_key"]) for c in clusters if c.get("parent_key")}
    return [v for v in vcenters if str(v.get("parent_key")) in keys]


def _build_cluster_row(r: dict, issues: dict) -> dict[str, Any]:
    source = r.get("source") or ""
    collected = bool(r.get("collected"))
    expected = bool(r.get("expected"))
    is_live = bool(r.get("is_live"))
    dc = _resolve_dc(r.get("dc_code"), r.get("cluster_name"), r.get("parent_name"))
    status = cov.row_status(collected, expected, is_live)
    ti: list[dict] = []
    if status == "missing":
        platform = cov.SOURCE_PLATFORM.get(source.lower())
        if platform:
            ti = issues.get((dc, platform), [])
    parent_name = r.get("parent_name")
    # Defense: Nutanix coverage must not keep a VMware vCenter FQDN as parent
    # (AWX strips this at write time; stale rows until the next pass still need it).
    if str(source).lower() == "nutanix" and _VC_FQDN_PARENT_RE.match(str(parent_name or "").strip()):
        parent_name = None
    return {
        "source": source,
        "cluster_name": r.get("cluster_name"),
        "dc": dc,
        "parent_name": parent_name,
        "parent_key": None,
        "parent_display": None,
        "parent_ip": None,
        "parent_conflict_with": r.get("parent_conflict_with"),
        "unmatched_reason": None,
        "expected_source": r.get("expected_source"),
        "collected": collected,
        "expected": expected,
        "is_live": is_live,
        "last_collected": r.get("last_collected"),
        "status": status,
        "reason": cov.reason_text(status, r.get("last_collected"), ti, source=source),
        "target_issues": ti,
    }


def _build_host_row(r: dict, issues: dict) -> dict[str, Any]:
    collected = bool(r.get("collected"))
    expected = bool(r.get("expected"))
    is_live = bool(r.get("is_live"))
    is_offline = bool(r.get("is_offline"))
    dc = _resolve_dc(r.get("dc_code"), r.get("servername"))
    status = cov.row_status(collected, expected, is_live, is_offline=is_offline)
    ti: list[dict] = []
    if status == "missing":
        ti = issues.get((dc, cov.IBM_PLATFORM), [])
    return {
        "servername": r.get("servername"),
        "dc": dc,
        "parent_name": None,
        "parent_ip": None,
        "expected_source": r.get("expected_source"),
        "collected": collected,
        "expected": expected,
        "is_live": is_live,
        "is_offline": is_offline,
        "last_collected": r.get("last_collected"),
        "status": status,
        "reason": cov.reason_text(status, r.get("last_collected"), ti),
        "target_issues": ti,
    }


def _build_vcenter_row(r: dict, endpoint: dict[str, Any] | None = None) -> dict[str, Any]:
    status = str(r.get("status") or "unknown").lower()
    if status not in _VCENTER_STATUSES:
        status = "unknown"
    parent_name = r.get("parent_name")
    dc = _resolve_dc(r.get("dc_code"), parent_name)
    endpoint = endpoint or {}
    check_status = str(endpoint.get("last_check_status") or "").strip() or None
    endpoint_ip = str(endpoint.get("ip") or "").strip() or None
    return {
        "source": r.get("source") or "",
        "parent_name": parent_name,
        "parent_key": endpoint_ip or str(parent_name or ""),
        "origin": "rollup",
        "endpoint_ip": endpoint_ip,
        "endpoint_name": str(endpoint.get("entity_name") or "").strip() or None,
        "collector_check_status": check_status,
        "collector_network_ok": (check_status.lower() == "ok") if check_status else None,
        "dc": dc,
        "expected_clusters": int(r.get("expected_clusters") or 0),
        "collected_clusters": int(r.get("collected_clusters") or 0),
        "live_clusters": int(r.get("live_clusters") or 0),
        "status": status,
        "checked_at": r.get("checked_at"),
    }


def _attach_hmc_parents(
    hosts: list[dict[str, Any]],
    hmc_endpoints: list[dict[str, Any]],
    host_map: dict[str, str],
) -> list[dict[str, Any]]:
    """Assign each IBM host to an HMC and roll matched hosts up per real HMC.

    Unmatched hosts keep ``parent_name=HMC eşleşmedi`` for the GUI bottom panel
    but are not returned as fake HMC accordion / KPI rows.
    """
    hmc_by_dc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    hmc_by_ip: dict[str, dict[str, Any]] = {}
    for e in hmc_endpoints:
        ip = str(e.get("ip") or "").strip()
        dc = str(e.get("dc_code") or "").strip().upper()
        if ip:
            hmc_by_ip[ip] = e
        if dc:
            hmc_by_dc[dc].append(e)

    mapped_ips_by_dc: dict[str, set[str]] = defaultdict(set)
    family_hmc_by_dc: dict[tuple[str, str], dict[str, Any]] = {}
    for h in hosts:
        ip = host_map.get(str(h.get("servername") or "").strip().upper())
        hit = hmc_by_ip.get(ip or "")
        if not hit:
            continue
        mapped_ips_by_dc[h["dc"]].add(ip)
        family = _ibm_host_family(h.get("servername"))
        if family:
            family_hmc_by_dc.setdefault((h["dc"], family), hit)

    for h in hosts:
        dc = h["dc"]
        ip = host_map.get(str(h.get("servername") or "").strip().upper())
        hit = hmc_by_ip.get(ip or "")
        if hit is None:
            dc_hmcs = hmc_by_dc.get(dc, [])
            if len(dc_hmcs) == 1:
                hit = dc_hmcs[0]
            else:
                family = _ibm_host_family(h.get("servername"))
                sibling = family_hmc_by_dc.get((dc, family)) if family else None
                if sibling is not None:
                    hit = sibling
                else:
                    # Multi-HMC DC: inventory-only hosts land on the HMC that metrics
                    # never mention — but only when exactly one such leftover remains.
                    leftovers = [
                        e
                        for e in dc_hmcs
                        if str(e.get("ip") or "") not in mapped_ips_by_dc.get(dc, set())
                    ]
                    if len(leftovers) == 1:
                        hit = leftovers[0]
        if hit is not None:
            h["parent_name"] = str(hit.get("entity_name") or "").strip() or None
            h["parent_ip"] = str(hit.get("ip") or "").strip() or None
        else:
            h["parent_name"] = _UNASSIGNED_HMC
            h["parent_ip"] = None

    rollup: dict[tuple[str, str], dict[str, Any]] = {}
    for h in hosts:
        name = h.get("parent_name") or _UNASSIGNED_HMC
        if name == _UNASSIGNED_HMC:
            continue
        key = (h["dc"], name)
        row = rollup.setdefault(
            key,
            {
                "hmc_name": name,
                "endpoint_ip": h.get("parent_ip"),
                "dc": h["dc"],
                "expected_hosts": 0,
                "collected_hosts": 0,
                "live_hosts": 0,
                "offline_hosts": 0,
                "status": "unknown",
                "collector_check_status": None,
            },
        )
        # Offline is intentional — not a collection gap against this HMC.
        if h.get("is_offline"):
            row["offline_hosts"] += 1
            continue
        row["expected_hosts"] += 1
        row["collected_hosts"] += 1 if h["collected"] else 0
        row["live_hosts"] += 1 if h["is_live"] else 0

    for (dc, name), row in rollup.items():
        endpoint = next(
            (
                e
                for e in hmc_by_dc.get(dc, [])
                if str(e.get("entity_name") or "").strip() == name
            ),
            None,
        )
        if endpoint is not None:
            row["collector_check_status"] = (
                str(endpoint.get("last_check_status") or "").strip() or None
            )
        expected = row["expected_hosts"]
        live = row["live_hosts"]
        collected = row["collected_hosts"]
        # expected==0 means offline-only (or empty) — never "live".
        if expected == 0:
            row["status"] = "offline" if row.get("offline_hosts") else "unknown"
        elif collected == 0:
            row["status"] = "missing"
        elif live == expected:
            row["status"] = "live"
        elif live == 0:
            row["status"] = "stale"
        else:
            row["status"] = "partial"

    return sorted(rollup.values(), key=lambda r: (r["dc"], r["hmc_name"] or ""))

def _build_backup_row(r: dict) -> dict[str, Any]:
    collected = bool(r.get("collected"))
    expected = bool(r.get("expected"))
    is_live = bool(r.get("is_live"))
    status = cov.row_status(collected, expected, is_live)
    return {
        "source": (r.get("source") or "").lower(),
        "endpoint_ip": r.get("endpoint_ip"),
        "endpoint_name": r.get("endpoint_name"),
        "dc": _resolve_dc(r.get("dc_code"), r.get("endpoint_name")),
        "collected": collected,
        "expected": expected,
        "expected_source": r.get("expected_source"),
        "network_ok": r.get("network_ok") if r.get("network_ok") is None else bool(r.get("network_ok")),
        "is_live": is_live,
        "last_collected": r.get("last_collected"),
        "status": status,
        "reason": cov.reason_text(status, r.get("last_collected"), []),
        "checked_at": r.get("checked_at"),
        "collector_check_status": None,
    }


def _enrich_backup_with_collectors(backups: list[dict[str, Any]]) -> None:
    """Attach collector_target check status by exact source IP (backup's natural key)."""
    if not backups:
        return
    endpoints = _fetch_platform_endpoints(("%netbackup%", "%veeam%", "%zerto%", "%nutanix%"))
    by_ip = {
        str(e.get("ip") or "").strip(): e
        for e in endpoints
        if str(e.get("ip") or "").strip()
    }
    for row in backups:
        ip = str(row.get("endpoint_ip") or "").strip()
        hit = by_ip.get(ip)
        if not hit:
            continue
        if not str(row.get("endpoint_name") or "").strip():
            row["endpoint_name"] = hit.get("entity_name")
        row["collector_check_status"] = hit.get("last_check_status")


def _empty_vcenter_bucket() -> dict[str, int]:
    return {
        "total": 0,
        "live": 0,
        "partial": 0,
        "missing": 0,
        "stale": 0,
        "extra": 0,
        "offline": 0,
    }


def _tally_vcenter(bucket: dict[str, int], status: str) -> None:
    bucket["total"] += 1
    if status in bucket:
        bucket[status] += 1


def _attach_probe_rollup(*row_groups: list[dict[str, Any]]) -> None:
    """Annotate parent rows with their collector script smoke result.

    The endpoint IP resolved for a parent is the same key the probe runner logs as
    `target_host`, so "3 clusters live" and "2 of 3 scripts fail" sit side by side.
    """
    try:
        rollup = probe_q.fetch_probe_rollup_by_host()
    except Exception:  # noqa: BLE001 - probe log is optional; coverage must still render
        return
    for rows in row_groups:
        for row in rows:
            hit = rollup.get(str(row.get("endpoint_ip") or "").strip())
            if hit:
                row.update(hit)


def build_coverage(*, dc: str | None = None, source: str | None = None) -> dict[str, Any]:
    """Assemble the coverage report, optionally filtered by Location (dc) and source."""
    issues = _issues_by_key(_fetch_target_issues())

    clusters = [_build_cluster_row(r, issues) for r in _fetch_clusters()]
    hosts = [_build_host_row(r, issues) for r in _fetch_ibm_hosts()]

    vcenter_raw = [
        r
        for r in _fetch_vcenters()
        if not (
            str(r.get("source") or "").lower() == "nutanix"
            and _VC_FQDN_PARENT_RE.match(str(r.get("parent_name") or "").strip())
        )
    ]
    parent_endpoints = _fetch_platform_endpoints(("%vmware%", "%nutanix%", "%acropolis%"))
    matches = _assign_parent_endpoints(vcenter_raw, clusters, parent_endpoints)
    vcenters = [
        _build_vcenter_row(
            r,
            matches.get(
                (
                    str(r.get("source") or "").lower(),
                    _resolve_dc(r.get("dc_code"), r.get("parent_name")),
                    str(r.get("parent_name") or "").strip(),
                )
            ),
        )
        for r in vcenter_raw
    ]
    clusters, endpoint_parents = _resolve_cluster_parents(clusters, vcenters, parent_endpoints)
    vcenters = _drop_childless_rollups(vcenters, clusters) + endpoint_parents

    hmcs = _attach_hmc_parents(
        hosts,
        _fetch_platform_endpoints(("%hmc%",)),
        _fetch_hmc_host_map(),
    )
    backups = [_build_backup_row(r) for r in _fetch_backup_endpoints()]
    _enrich_backup_with_collectors(backups)
    _attach_probe_rollup(vcenters, hmcs, backups)

    coverage_dcs = (
        {row["dc"] for row in clusters}
        | {row["dc"] for row in hosts}
        | {row["dc"] for row in vcenters}
        | {row["dc"] for row in backups}
    )
    loki_dcs = {
        str(loc.get("dc_code") or "").strip().upper()
        for loc in coll_q.list_root_locations()
        if loc.get("dc_code")
    }
    locations = sorted(loki_dcs | coverage_dcs | {"Diğer"})

    dc_norm = (dc or "").strip().upper() or None
    src_norm = (source or "").strip().lower() or None
    if dc_norm:
        clusters = [c for c in clusters if c["dc"] == dc_norm]
        hosts = [h for h in hosts if h["dc"] == dc_norm]
        vcenters = [v for v in vcenters if v["dc"] == dc_norm]
        hmcs = [m for m in hmcs if m["dc"] == dc_norm]
        backups = [b for b in backups if b["dc"] == dc_norm]

    # `source` doubles as a data-type selector:
    # ibm → hosts only; vmware/nutanix → clusters+vcenters of that source;
    # netbackup/veeam/zerto → backup endpoints of that source; empty → all.
    if src_norm == "ibm":
        clusters = [c for c in clusters if c["source"].lower() == "ibm"]
        vcenters = []
        backups = []
    elif src_norm in ("vmware", "nutanix"):
        clusters = [c for c in clusters if c["source"].lower() == src_norm]
        vcenters = [v for v in vcenters if v["source"].lower() == src_norm]
        hosts = []
        hmcs = []
        backups = []
    elif src_norm in _BACKUP_SOURCES:
        clusters = []
        hosts = []
        hmcs = []
        vcenters = []
        backups = [b for b in backups if b["source"] == src_norm]

    cluster_buckets: dict[str, dict[str, int]] = {"all": cov.empty_bucket()}
    for c in clusters:
        s = c["source"].lower() or "other"
        cluster_buckets.setdefault(s, cov.empty_bucket())
        cov.tally(cluster_buckets["all"], c["collected"], c["expected"], c["is_live"])
        cov.tally(cluster_buckets[s], c["collected"], c["expected"], c["is_live"])

    host_bucket = cov.empty_bucket()
    for h in hosts:
        cov.tally(
            host_bucket,
            h["collected"],
            h["expected"],
            h["is_live"],
            is_offline=bool(h.get("is_offline")),
        )

    vcenter_bucket = _empty_vcenter_bucket()
    for v in vcenters:
        _tally_vcenter(vcenter_bucket, v["status"])

    hmc_bucket = _empty_vcenter_bucket()
    for m in hmcs:
        _tally_vcenter(hmc_bucket, m["status"])

    backup_buckets: dict[str, dict[str, int]] = {"all": cov.empty_bucket()}
    for b in backups:
        s = b["source"] or "other"
        backup_buckets.setdefault(s, cov.empty_bucket())
        cov.tally(backup_buckets["all"], b["collected"], b["expected"], b["is_live"])
        cov.tally(backup_buckets[s], b["collected"], b["expected"], b["is_live"])

    return {
        "summary": {
            "cluster": cluster_buckets,
            "ibm_host": host_bucket,
            "vcenter": vcenter_bucket,
            "ibm_hmc": hmc_bucket,
            "backup_endpoint": backup_buckets,
        },
        "clusters": clusters,
        "ibm_hosts": hosts,
        "vcenters": vcenters,
        "ibm_hmcs": hmcs,
        "backup_endpoints": backups,
        "locations": locations,
        "dc_filter": dc_norm,
        "source_filter": src_norm,
    }
