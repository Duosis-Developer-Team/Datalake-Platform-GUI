"""Deterministic, allowlisted read-only tool registry (CTO pack 05).

The LLM never picks an arbitrary endpoint or writes SQL. Each tool is a fixed,
declarative wrapper around a *known* backend endpoint. The orchestrator selects
tools by heuristic, executes them here, normalizes the payload to a compact
summary, and only that summary is handed to the model.

Every tool is read-only (GET). Row-heavy endpoints declare ``cap_rows``. The
``query-api`` passthrough is locked to an explicit ``allowed_query_keys`` list
(empty by default — the model can never invent a query key).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings
from app.services import api_clients
from app.services.api_clients import InternalAPIError

logger = logging.getLogger("chatbot-api.tools")

# --------------------------------------------------------------------------- #
# Result type
# --------------------------------------------------------------------------- #


@dataclass
class ToolResult:
    name: str
    status: str  # "success" | "error" | "skipped"
    source: str
    summary: Any = None
    rows: Optional[int] = None
    error: Optional[str] = None


# --------------------------------------------------------------------------- #
# Tool specification
# --------------------------------------------------------------------------- #


@dataclass
class ToolSpec:
    name: str
    description: str
    service: str
    # Either a single path template OR a {label: path_template} map (multi-fetch).
    path: Optional[str] = None
    multi: dict[str, str] = field(default_factory=dict)
    needs: tuple[str, ...] = ()  # required context keys to fill the template
    use_time: bool = False
    cap_rows: Optional[int] = None
    allowed_query_keys: tuple[str, ...] = ()  # only for query-api passthrough
    db_query_key: Optional[str] = None  # set => read-only DB tool (source=postgres)
    db_defaults: dict[str, Any] = field(default_factory=dict)  # default days/limit for DB tools
    list_items: bool = False  # API returns list[str]; keep the full (capped) list, not a 3-sample
    allowed_roles: Optional[tuple[str, ...]] = None  # None => any authenticated user
    db_dc_optional: bool = False  # True => dc_code not required; %(dc)s may be NULL

    def source_label(self, path: str) -> str:
        return f"{self.service}:{path}"


# --------------------------------------------------------------------------- #
# Payload normalization — keep the LLM context small (CTO pack 05)
# --------------------------------------------------------------------------- #


def _normalize(value: Any, _depth: int = 0) -> Any:
    """Collapse big payloads into compact, scalar-heavy summaries.

    Scalars pass through; lists become ``{_count, _sample}``; nested dicts are
    summarized one level deeper only. This bounds the characters sent to the LLM.
    """
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, str):
        return value if len(value) <= 300 else value[:300] + "…"
    if isinstance(value, list):
        sample = [_normalize(v, _depth + 1) for v in value[:3]]
        return {"_count": len(value), "_sample": sample}
    if isinstance(value, dict):
        if _depth >= 2:
            return {"_keys": list(value.keys())[:20]}
        return {k: _normalize(v, _depth + 1) for k, v in list(value.items())[:40]}
    return str(value)[:300]


def _row_count(payload: Any) -> Optional[int]:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("items", "rows", "data", "results", "tickets", "vaults", "datacenters"):
            v = payload.get(key)
            if isinstance(v, list):
                return len(v)
    return None


# --------------------------------------------------------------------------- #
# Registry — initial read-only tool coverage
# --------------------------------------------------------------------------- #

TOOLS: dict[str, ToolSpec] = {
    # ---- Dashboard / overview -------------------------------------------- #
    "get_dashboard_overview": ToolSpec(
        "get_dashboard_overview",
        "Global capacity overview (CPU/RAM/storage totals).",
        "datacenter-api",
        path="/api/v1/dashboard/overview",
        use_time=True,
    ),
    "get_datacenters_summary": ToolSpec(
        "get_datacenters_summary",
        "Per-datacenter summary list (compare / busiest DC).",
        "datacenter-api",
        path="/api/v1/datacenters/summary",
        use_time=True,
    ),
    "get_sla": ToolSpec(
        "get_sla",
        "SLA availability across datacenters.",
        "datacenter-api",
        path="/api/v1/sla",
        use_time=True,
    ),
    # ---- Datacenter detail ----------------------------------------------- #
    "get_datacenter_detail": ToolSpec(
        "get_datacenter_detail",
        "Single datacenter detail metrics.",
        "datacenter-api",
        path="/api/v1/datacenters/{dc_code}",
        needs=("dc_code",),
        use_time=True,
    ),
    "get_dc_classic_clusters": ToolSpec(
        "get_dc_classic_clusters",
        "Classic (KM/VMware) cluster names for a datacenter (API).",
        "datacenter-api",
        path="/api/v1/datacenters/{dc_code}/clusters/classic",
        needs=("dc_code",),
        list_items=True,
    ),
    "get_dc_hyperconverged_clusters": ToolSpec(
        "get_dc_hyperconverged_clusters",
        "Hyperconverged (Nutanix) cluster names for a datacenter (API).",
        "datacenter-api",
        path="/api/v1/datacenters/{dc_code}/clusters/hyperconverged",
        needs=("dc_code",),
        list_items=True,
    ),
    "get_dc_compute_classic": ToolSpec(
        "get_dc_compute_classic",
        "Classic (VMware) compute metrics for a datacenter.",
        "datacenter-api",
        path="/api/v1/datacenters/{dc_code}/compute/classic",
        needs=("dc_code",),
        use_time=True,
    ),
    "get_dc_compute_hyperconverged": ToolSpec(
        "get_dc_compute_hyperconverged",
        "Hyperconverged (Nutanix) compute metrics for a datacenter.",
        "datacenter-api",
        path="/api/v1/datacenters/{dc_code}/compute/hyperconverged",
        needs=("dc_code",),
        use_time=True,
    ),
    "get_dc_storage_capacity": ToolSpec(
        "get_dc_storage_capacity",
        "Storage capacity metrics for a datacenter.",
        "datacenter-api",
        path="/api/v1/datacenters/{dc_code}/storage/capacity",
        needs=("dc_code",),
        use_time=True,
    ),
    "get_dc_zabbix_storage_trend": ToolSpec(
        "get_dc_zabbix_storage_trend",
        "Zabbix-monitored storage usage trend for a datacenter.",
        "datacenter-api",
        path="/api/v1/datacenters/{dc_code}/zabbix-storage/trend",
        needs=("dc_code",),
        use_time=True,
    ),
    "get_dc_storage_performance": ToolSpec(
        "get_dc_storage_performance",
        "Storage performance metrics for a datacenter.",
        "datacenter-api",
        path="/api/v1/datacenters/{dc_code}/storage/performance",
        needs=("dc_code",),
        use_time=True,
    ),
    "get_dc_network_summary": ToolSpec(
        "get_dc_network_summary",
        "Network port summary + 95th percentile for a datacenter.",
        "datacenter-api",
        multi={
            "port_summary": "/api/v1/datacenters/{dc_code}/network/port-summary",
            "p95": "/api/v1/datacenters/{dc_code}/network/95th-percentile",
        },
        needs=("dc_code",),
        use_time=True,
    ),
    # ---- Backup / DR ------------------------------------------------------ #
    "get_dc_backup_summary": ToolSpec(
        "get_dc_backup_summary",
        "Backup/DR summary across NetBackup, Zerto and Veeam.",
        "datacenter-api",
        multi={
            "netbackup": "/api/v1/datacenters/{dc_code}/backup/netbackup",
            "zerto": "/api/v1/datacenters/{dc_code}/backup/zerto",
            "veeam": "/api/v1/datacenters/{dc_code}/backup/veeam",
        },
        needs=("dc_code",),
        use_time=True,
    ),
    "get_dc_backup_jobs": ToolSpec(
        "get_dc_backup_jobs",
        "Backup job stats across NetBackup, Zerto and Veeam.",
        "datacenter-api",
        multi={
            "netbackup": "/api/v1/datacenters/{dc_code}/backup/netbackup/jobs",
            "zerto": "/api/v1/datacenters/{dc_code}/backup/zerto/jobs",
            "veeam": "/api/v1/datacenters/{dc_code}/backup/veeam/jobs",
        },
        needs=("dc_code",),
        use_time=True,
    ),
    # ---- S3 --------------------------------------------------------------- #
    "get_dc_s3_pools": ToolSpec(
        "get_dc_s3_pools",
        "Object storage (S3) pool metrics for a datacenter.",
        "datacenter-api",
        path="/api/v1/datacenters/{dc_code}/s3/pools",
        needs=("dc_code",),
        use_time=True,
    ),
    "get_customer_s3_vaults": ToolSpec(
        "get_customer_s3_vaults",
        "S3 vaults for a customer.",
        "customer-api",
        path="/api/v1/customers/{customer_name}/s3/vaults",
        needs=("customer_name",),
        use_time=True,
    ),
    # ---- Customer --------------------------------------------------------- #
    "list_customers": ToolSpec(
        "list_customers",
        "List of customers.",
        "customer-api",
        path="/api/v1/customers",
        cap_rows=200,
    ),
    "get_customer_resources": ToolSpec(
        "get_customer_resources",
        "Resource usage for a customer.",
        "customer-api",
        path="/api/v1/customers/{customer_name}/resources",
        needs=("customer_name",),
        use_time=True,
    ),
    "get_customer_itsm_summary": ToolSpec(
        "get_customer_itsm_summary",
        "ITSM ticket summary for a customer.",
        "customer-api",
        path="/api/v1/customers/{customer_name}/itsm/summary",
        needs=("customer_name",),
        use_time=True,
    ),
    "get_customer_itsm_extremes": ToolSpec(
        "get_customer_itsm_extremes",
        "ITSM extremes for a customer.",
        "customer-api",
        path="/api/v1/customers/{customer_name}/itsm/extremes",
        needs=("customer_name",),
        use_time=True,
    ),
    "get_customer_itsm_tickets": ToolSpec(
        "get_customer_itsm_tickets",
        "ITSM ticket list for a customer (row-capped).",
        "customer-api",
        path="/api/v1/customers/{customer_name}/itsm/tickets",
        needs=("customer_name",),
        use_time=True,
        cap_rows=25,
    ),
    # ---- CRM / sellable potential ---------------------------------------- #
    "get_sellable_summary": ToolSpec(
        "get_sellable_summary",
        "Sellable-potential summary (optionally per datacenter).",
        "crm-engine",
        path="/api/v1/crm/sellable-potential/summary",
    ),
    "get_sellable_by_panel": ToolSpec(
        "get_sellable_by_panel",
        "Sellable potential grouped by panel.",
        "crm-engine",
        path="/api/v1/crm/sellable-potential/by-panel",
    ),
    "get_sellable_by_family": ToolSpec(
        "get_sellable_by_family",
        "Sellable potential grouped by family.",
        "crm-engine",
        path="/api/v1/crm/sellable-potential/by-family",
    ),
    # ---- Query API passthrough (locked) ---------------------------------- #
    "run_registered_query": ToolSpec(
        "run_registered_query",
        "Run a pre-approved registered query by key (allowlist only).",
        "query-api",
        path="/api/v1/queries/{query_key}",
        needs=("query_key",),
        allowed_query_keys=(),  # intentionally empty — no key is approved yet
    ),
    # ---- Read-only DB tools (host-level CPU not exposed by the APIs) ------ #
    "get_dc_host_cpu_latest": ToolSpec(
        "get_dc_host_cpu_latest",
        "Per-host latest CPU usage in a datacenter (read-only DB: VMware/Nutanix/IBM).",
        "postgres",
        db_query_key="db_get_dc_host_cpu_latest",
        needs=("dc_code",),
    ),
    "get_dc_host_cpu_top": ToolSpec(
        "get_dc_host_cpu_top",
        "Highest-CPU hosts in a datacenter (read-only DB).",
        "postgres",
        db_query_key="db_get_dc_host_cpu_top",
        needs=("dc_code",),
    ),
    "get_dc_host_cpu_summary": ToolSpec(
        "get_dc_host_cpu_summary",
        "Per-source host CPU summary for a datacenter (read-only DB).",
        "postgres",
        db_query_key="db_get_dc_host_cpu_summary",
        needs=("dc_code",),
    ),
    # ---- Read-only DB tools: VM-level CPU (not exposed by the APIs) ------- #
    "get_dc_vm_cpu_top": ToolSpec(
        "get_dc_vm_cpu_top",
        "Top VMs by CPU over the last N days in a datacenter (read-only DB).",
        "postgres",
        db_query_key="db_get_dc_vm_cpu_top",
        needs=("dc_code",),
        db_defaults={"days": 7, "limit": 10},
    ),
    "get_dc_vm_cpu_latest": ToolSpec(
        "get_dc_vm_cpu_latest",
        "Most recent per-VM CPU snapshot in a datacenter (read-only DB).",
        "postgres",
        db_query_key="db_get_dc_vm_cpu_latest",
        needs=("dc_code",),
        db_defaults={"days": 1, "limit": 50},
    ),
    "get_dc_vm_cpu_summary": ToolSpec(
        "get_dc_vm_cpu_summary",
        "Per-source VM CPU summary for a datacenter (read-only DB).",
        "postgres",
        db_query_key="db_get_dc_vm_cpu_summary",
        needs=("dc_code",),
        db_defaults={"days": 7},
    ),
    "get_dc_classic_host_cpu_allocation_variability": ToolSpec(
        "get_dc_classic_host_cpu_allocation_variability",
        "Top classic (KM) hosts by allocated-vCPU variability over N days (read-only DB).",
        "postgres",
        db_query_key="db_get_dc_classic_host_cpu_allocation_variability",
        needs=("dc_code",),
        db_defaults={"days": 7, "limit": 3},
    ),
    "get_dc_vmware_clusters_from_db": ToolSpec(
        "get_dc_vmware_clusters_from_db",
        "VMware cluster inventory for a datacenter from the DB (classic + hyperconverged-named).",
        "postgres",
        db_query_key="db_get_dc_vmware_clusters",
        needs=("dc_code",),
        db_defaults={"limit": 200},
    ),
    "get_global_km_cluster_memory_top": ToolSpec(
        "get_global_km_cluster_memory_top",
        "Top classic (KM) clusters by memory usage across all datacenters (read-only DB).",
        "postgres",
        db_query_key="db_get_global_km_cluster_memory_top",
        needs=(),
        db_defaults={"limit": 5},
        db_dc_optional=True,
    ),
}


def get_tool(name: str) -> Optional[ToolSpec]:
    return TOOLS.get(name)


def list_tool_names() -> list[str]:
    return list(TOOLS.keys())


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #


def _fill_path(template: str, args: dict[str, Any]) -> Optional[str]:
    try:
        # Only allow whitelisted placeholders.
        return template.format(
            dc_code=args.get("dc_code", ""),
            customer_name=args.get("customer_name", ""),
            query_key=args.get("query_key", ""),
        )
    except Exception:
        return None


def _clean_db_value(value: Any) -> Any:
    from decimal import Decimal

    if isinstance(value, Decimal):
        return float(value)
    return value


def _normalize_db_rows(rows: list[dict[str, Any]], cap: int = 40) -> dict[str, Any]:
    cleaned = [{k: _clean_db_value(v) for k, v in r.items()} for r in rows[:cap]]
    out: dict[str, Any] = {"row_count": len(rows), "rows": cleaned}
    if len(rows) > cap:
        out["_note"] = f"showing first {cap} of {len(rows)} rows"
    return out


def _execute_db_tool(name: str, spec: ToolSpec, args: dict[str, Any]) -> ToolResult:
    """Run a read-only DB tool via the allowlisted query registry."""
    from app.services import db_query_registry
    from app.services.db_readonly import ReadOnlyViolation, get_db

    source = f"postgres:{spec.db_query_key}"
    if not get_db().enabled:
        return ToolResult(name, "skipped", source="postgres", error="db_disabled")
    dc = args.get("dc_code")
    query = db_query_registry.DB_QUERIES.get(spec.db_query_key or "")
    tparams = query.params if query else ()
    if spec.needs and "dc_code" in spec.needs:
        if not dc:
            return ToolResult(name, "skipped", source="postgres", error="missing:dc_code")
    elif not spec.db_dc_optional and "dc" in tparams and not dc:
        return ToolResult(name, "skipped", source="postgres", error="missing:dc_code")

    params: dict[str, Any] = {}
    if "dc" in tparams:
        params["dc"] = f"%{dc}%" if dc else None
    defaults = spec.db_defaults or {}
    if "days" in tparams:
        try:
            days = int(args.get("days") or defaults.get("days") or 7)
        except (TypeError, ValueError):
            days = int(defaults.get("days") or 7)
        params["days"] = max(1, min(days, 30))  # bound the lookback window
    if "limit" in tparams:
        try:
            requested = int(args.get("limit") or defaults.get("limit") or settings.db_max_rows)
        except (TypeError, ValueError):
            requested = int(defaults.get("limit") or settings.db_max_rows)
        params["limit"] = max(1, min(requested, settings.db_max_rows))

    try:
        rows = db_query_registry.run_query(spec.db_query_key, params)
    except ReadOnlyViolation as exc:
        return ToolResult(name, "error", source=source, error=str(exc)[:120])
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("DB tool %s failed: %s", name, type(exc).__name__)
        return ToolResult(name, "error", source=source, error="db_error")
    return ToolResult(name, "success", source=source, summary=_normalize_db_rows(rows), rows=len(rows))


def execute_tool(name: str, args: dict[str, Any], auth_header: Optional[str] = None) -> ToolResult:
    """Run one tool by name. Never raises — failures become ``status='error'``."""
    spec = TOOLS.get(name)
    if spec is None:
        return ToolResult(name, "skipped", source=name, error="unknown_tool")

    # Validate required context.
    for key in spec.needs:
        if not args.get(key):
            return ToolResult(name, "skipped", source=spec.service, error=f"missing:{key}")

    # Read-only DB tools route to the allowlisted query registry.
    if spec.db_query_key:
        return _execute_db_tool(name, spec, args)

    # query-api passthrough: enforce allowlist.
    if spec.service == "query-api":
        qk = str(args.get("query_key", ""))
        if qk not in spec.allowed_query_keys:
            return ToolResult(name, "skipped", source=spec.service, error="query_key_not_allowed")

    time_params = api_clients.build_time_params(args.get("time_range")) if spec.use_time else {}

    attempted_path = spec.service  # used for the source label, incl. on error
    try:
        if spec.multi:
            merged: dict[str, Any] = {}
            first_path = ""
            for label, tmpl in spec.multi.items():
                path = _fill_path(tmpl, args)
                if not path:
                    continue
                first_path = first_path or path
                try:
                    payload = api_clients.get_json(spec.service, path, time_params, auth_header)
                    merged[label] = _normalize(payload)
                except InternalAPIError as exc:
                    merged[label] = {"_error": exc.detail}
            # All sub-calls errored => treat as error.
            if merged and all(isinstance(v, dict) and "_error" in v for v in merged.values()):
                return ToolResult(name, "error", spec.source_label(first_path), error="all_subcalls_failed")
            return ToolResult(name, "success", spec.source_label(first_path), summary=merged)

        path = _fill_path(spec.path or "", args)
        if not path:
            return ToolResult(name, "skipped", spec.service, error="bad_path")
        attempted_path = path
        payload = api_clients.get_json(spec.service, path, time_params, auth_header)
        rows = _row_count(payload)
        if spec.list_items and isinstance(payload, list):
            # Keep the full (capped) list — needed for set comparisons.
            cap = spec.cap_rows or 200
            summary = {"_count": len(payload), "items": [str(x) for x in payload[:cap]]}
        else:
            summary = _normalize(payload)
        # Defensive note when an endpoint returns more rows than we cap.
        if spec.cap_rows is not None and rows is not None and rows > spec.cap_rows:
            summary = {"_note": f"showing first {spec.cap_rows} of {rows}", "data": summary}
        return ToolResult(name, "success", spec.source_label(path), summary=summary, rows=rows)
    except InternalAPIError as exc:
        return ToolResult(name, "error", spec.source_label(attempted_path), error=exc.detail)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Tool %s crashed: %s", name, exc)
        return ToolResult(name, "error", spec.service, error="tool_exception")
