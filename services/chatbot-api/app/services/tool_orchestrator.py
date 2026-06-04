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
    "network": ("network", "ağ", "port", "bant", "bandwidth", "trafik"),
}


def _has(text: str, group: str) -> bool:
    return any(kw in text for kw in _KW[group])


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
        if _has(text, "compute"):
            add("get_dc_compute_classic")
            add("get_dc_compute_hyperconverged")
        if _has(text, "storage"):
            add("get_dc_storage_capacity")
        if _has(text, "network"):
            add("get_dc_network_summary")
        # Generic "summarize this datacenter".
        add("get_datacenter_detail")

    # --- Global overview ----------------------------------------------- #
    if _has(text, "overview") or not picks:
        if "en yoğun" in text or "en yogun" in text or "compare" in text or "karşılaştır" in text:
            add("get_datacenters_summary")
        else:
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
