"""Tool orchestration: deterministic intent heuristics -> tool execution.

MVP uses regex/keyword heuristics (CTO pack 05 "Intent Heuristics MVP"); a later
sprint can replace ``select_tools`` with an LLM planner (function-calling / JSON
mode) without touching the executor or registry. Selection is capped by
``settings.max_tool_calls`` and every tool runs through the allowlisted registry.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from app.config import settings
from app.models.schemas import FrontendContext
from app.services import tool_registry
from app.services.tool_registry import ToolResult

logger = logging.getLogger("chatbot-api.orchestrator")

# Datacenter code patterns used across the WebUI (CTO pack 05).
_DC_RE = re.compile(r"\b((?:DC|AZ|ICT|UZ|DH)\d+)\b", re.IGNORECASE)

_KW = {
    "memory": ("memory", "bellek", " ram", "ram "),
    "cluster": ("cluster", "cluster'"),
    "backup": ("backup", "yedek", "zerto", "veeam", "netbackup"),
    "job": ("job", "iş ", "jobs"),
    "s3": ("s3", "object", "nesne", "vault", "pool", "bucket"),
    "crm": ("satılabilir", "satilabilir", "potential", "potansiyel", "crm", "fırsat", "firsat", "sellable"),
    "panel": ("panel",),
    "family": ("family", "aile"),
    "itsm": ("itsm", "ticket", "çağrı", "cagri", "talep", "incident"),
    "customer": ("müşteri", "musteri", "customer"),
    "sla": ("sla", "availability", "erişilebilir", "uptime"),
    "overview": ("genel", "overview", "toplam", "en yoğun", "en yogun", "kapasite", "özet", "ozet"),
    "compute": ("cpu", "ram", "vcpu", "compute", "işlemci", "bellek", "memory"),
    "storage": ("storage", "disk", "depolama", "kapasite"),
    # Avoid over-loose substrings: bare "ağ" matches "bağlantı", bare "port"
    # matches "rapor/transport". Use specific network terms.
    "network": ("network", "trafik", "bandwidth", "bant geniş", "switch port", "ağ trafi", "port-summary"),
    "host": ("host", "hostlar", "sunucu", "sunucular", "node", "nodes"),
    "vm": ("vm", "vm'", "vmler", "vm'ler", "sanal makine", "sanal sunucu", "virtual machine", "lpar"),
    "top": ("en yüksek", "en yuksek", "en çok", "en cok", "top", "yüksek cpu", "yuksek cpu", "en fazla", "listele"),
    "explicit_db": ("direkt db", "direkt database", "veritaban", "postgre", "postgresql", "db'den", "database'den"),
}

_DAYS_RE = re.compile(r"son\s+(\d+)\s*g[üu]n")
_LIMIT_RE = re.compile(r"(\d+)\s*(?:tane|adet|vm|vm'|host|sunucu|lpar)")
_TOPN_RE = re.compile(r"(?:top|ilk|en\s+(?:çok|cok|fazla|yüksek|yuksek))\s+(\d+)")


def _has(text: str, group: str) -> bool:
    return any(kw in text for kw in _KW[group])


def _extract_days(text: str) -> Optional[int]:
    m = _DAYS_RE.search(text)
    if m:
        return max(1, min(int(m.group(1)), 30))
    if "hafta" in text:  # "son bir hafta", "haftalık"
        return 7
    return None


def _extract_limit(text: str) -> Optional[int]:
    for rx in (_LIMIT_RE, _TOPN_RE):
        m = rx.search(text)
        if m:
            return max(1, min(int(m.group(1)), 50))
    return None


@dataclass
class Selection:
    tool: str
    args: dict[str, Any]


def _extract_dc(message: str, ctx: Optional[FrontendContext]) -> Optional[str]:
    if ctx and ctx.selected_datacenter:
        return ctx.selected_datacenter.upper()
    m = _DC_RE.search(message or "")
    if m:
        return m.group(1).upper()
    return None


def _base_args(ctx: Optional[FrontendContext], dc_code: Optional[str], customer: Optional[str]) -> dict[str, Any]:
    return {
        "dc_code": dc_code,
        "customer_name": customer,
        "time_range": (ctx.time_range if ctx else None),
    }


def select_tools(message: str, ctx: Optional[FrontendContext]) -> list[Selection]:
    """Pick up to ``max_tool_calls`` tools by keyword heuristics."""
    text = (message or "").lower()
    dc_code = _extract_dc(message, ctx)
    customer = (ctx.selected_customer if ctx and ctx.selected_customer else None)
    base = _base_args(ctx, dc_code, customer)
    base["days"] = _extract_days(text)  # DB-tool lookback (None => tool default)
    base["limit"] = _extract_limit(text)  # "top 10 / 10 tane" (None => tool default)

    picks: list[Selection] = []
    seen: set[str] = set()

    def add(tool: str) -> None:
        if tool in seen:
            return
        spec = tool_registry.get_tool(tool)
        if spec is None:
            return
        # Skip tools whose required context is unavailable.
        for need in spec.needs:
            if not base.get(need):
                return
        seen.add(tool)
        picks.append(Selection(tool, dict(base)))

    # --- Backup / DR --------------------------------------------------- #
    if _has(text, "backup"):
        add("get_dc_backup_jobs" if _has(text, "job") else "get_dc_backup_summary")

    # --- S3 ------------------------------------------------------------ #
    if _has(text, "s3"):
        if customer:
            add("get_customer_s3_vaults")
        if dc_code:
            add("get_dc_s3_pools")

    # --- CRM / sellable potential -------------------------------------- #
    if _has(text, "crm"):
        if _has(text, "panel"):
            add("get_sellable_by_panel")
        if _has(text, "family"):
            add("get_sellable_by_family")
        add("get_sellable_summary")

    # --- Customer ------------------------------------------------------ #
    if customer or _has(text, "customer"):
        if _has(text, "itsm"):
            add("get_customer_itsm_summary")
        else:
            add("get_customer_resources")

    # --- SLA ----------------------------------------------------------- #
    if _has(text, "sla"):
        add("get_sla")

    # --- Datacenter-scoped compute/storage/network --------------------- #
    if dc_code:
        # VM- and host-level CPU live only in the DB (the APIs expose cluster
        # aggregates). "vm" => VM DB tool; "host" => host DB tool; an explicit
        # "direkt DB / postgresql" ask routes CPU to a DB tool instead of the API.
        cpu_intent = "cpu" in text or _has(text, "compute")
        vm_cpu = _has(text, "vm") and cpu_intent
        host_cpu = _has(text, "host") and cpu_intent and not vm_cpu
        if vm_cpu:
            if _has(text, "top"):
                add("get_dc_vm_cpu_top")
            elif _has(text, "overview"):  # "özetle / durum" → summary
                add("get_dc_vm_cpu_summary")
            else:
                add("get_dc_vm_cpu_latest")
        elif host_cpu:
            if _has(text, "top"):
                add("get_dc_host_cpu_top")
            elif _has(text, "overview"):
                add("get_dc_host_cpu_summary")
            else:
                add("get_dc_host_cpu_latest")
        elif cpu_intent and _has(text, "explicit_db"):
            # "direkt DB" + CPU but neither vm/host specified → DB host CPU, not API.
            add("get_dc_host_cpu_summary")
        elif _has(text, "compute"):
            add("get_dc_compute_classic")
            add("get_dc_compute_hyperconverged")
        if _has(text, "storage"):
            add("get_dc_storage_capacity")
        if _has(text, "network"):
            add("get_dc_network_summary")
        # Generic DC detail — skip for VM/host CPU asks (the DB tools already have
        # the data and /datacenters/{dc} is a slow endpoint here).
        if not (vm_cpu or host_cpu):
            add("get_datacenter_detail")

    # --- Global KM cluster memory top (no per-cluster API; DB only) -------- #
    km_ask = "km" in text or "klasik" in text or "classic" in text
    memory_cluster_top = (
        (_has(text, "memory") or _has(text, "compute"))
        and (_has(text, "cluster") or km_ask)
        and _has(text, "top")
    )
    if memory_cluster_top and not _has(text, "vm") and not _has(text, "host"):
        add("get_global_km_cluster_memory_top")

    # --- Global overview — only when nothing more specific matched, OR a
    #     clearly global ("en yoğun" / compare) ask without DC/customer scope.
    #     (Avoids tacking a slow global overview onto DC-scoped questions.)
    global_ask = "en yoğun" in text or "en yogun" in text or "compare" in text or "karşılaştır" in text
    skip_dashboard = memory_cluster_top or (_has(text, "top") and (_has(text, "vm") or _has(text, "host")))
    overview_intent = any(
        k in text
        for k in (
            "kapasite", "overview", "dashboard", "platform", "genel", "özet", "ozet",
            "dağılım", "dagilim", "kırılım", "kirilim",
        )
    )
    if global_ask and not dc_code and not customer:
        if not skip_dashboard:
            add("get_datacenters_summary")
    elif overview_intent and not picks and not skip_dashboard:
        add("get_dashboard_overview")

    return picks[: settings.max_tool_calls]


def run(message: str, ctx: Optional[FrontendContext], auth_header: Optional[str]) -> list[ToolResult]:
    """Select and execute tools. Per-tool failures are isolated."""
    selections = select_tools(message, ctx)
    results: list[ToolResult] = []
    for sel in selections:
        try:
            results.append(tool_registry.execute_tool(sel.tool, sel.args, auth_header))
        except Exception as exc:  # pragma: no cover - executor already guards
            logger.warning("Orchestrator failed on %s: %s", sel.tool, exc)
            results.append(ToolResult(sel.tool, "error", sel.tool, error="orchestrator_exception"))
    return results
