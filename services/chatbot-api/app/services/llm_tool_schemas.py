"""OpenAI-compatible function schemas for allowlisted chatbot tools."""

from __future__ import annotations

import json
from typing import Any

from app.services.tool_registry import TOOLS, ToolSpec, list_tool_names


def _tool_parameters(spec: ToolSpec) -> dict[str, Any]:
    props: dict[str, Any] = {}
    required: list[str] = []

    if "dc_code" in spec.needs or (
        spec.service != "postgres" and spec.path and "{dc_code}" in (spec.path or "")
    ):
        props["dc_code"] = {
            "type": "string",
            "description": "Datacenter code, e.g. DC13",
        }
        if "dc_code" in spec.needs and not spec.db_dc_optional:
            required.append("dc_code")
    elif spec.db_dc_optional:
        props["dc_code"] = {
            "type": "string",
            "description": "Optional datacenter filter",
        }

    if "customer_name" in spec.needs:
        props["customer_name"] = {
            "type": "string",
            "description": "Customer name",
        }
        required.append("customer_name")

    if spec.db_query_key or spec.db_defaults:
        props["days"] = {
            "type": "integer",
            "description": "Lookback window in days (1-30)",
        }
        props["limit"] = {
            "type": "integer",
            "description": "Max rows to return",
        }

    if spec.service == "query-api":
        props["query_key"] = {
            "type": "string",
            "description": "Allowlisted registered query key",
        }
        required.append("query_key")

    if not props:
        props["note"] = {"type": "string", "description": "Unused placeholder"}

    return {"type": "object", "properties": props, "required": required}


def build_openai_tools(tool_names: list[str] | None = None) -> list[dict[str, Any]]:
    """Build OpenAI ``tools`` list from the allowlisted registry."""
    names = tool_names or list_tool_names()
    out: list[dict[str, Any]] = []
    for name in names:
        spec = TOOLS.get(name)
        if spec is None:
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description[:500],
                    "parameters": _tool_parameters(spec),
                },
            }
        )
    return out


def catalog_guidance_summary() -> str:
    """Compact planner hint for the ReAct system message."""
    lines = [
        "Tool selection hints:",
        "- Per-entity CPU ranking: get_dc_vm_cpu_top / get_dc_host_cpu_top (DB).",
        "- Global KM cluster memory: get_global_km_cluster_memory_top (DB).",
        "- DC overview: get_datacenter_detail, get_dc_compute_classic/hyperconverged.",
        "- Storage: get_dc_storage_capacity, get_dc_zabbix_storage_trend.",
        "- Customer scope: get_customer_resources (only for customer questions).",
        "- Try API first for summaries; use DB when per-entity rows are needed.",
    ]
    return "\n".join(lines)


def tool_result_for_llm(result_name: str, result: Any) -> str:
    """Serialize a tool result for the LLM tool message (bounded)."""
    if hasattr(result, "status"):
        payload = {
            "status": result.status,
            "source": result.source,
            "rows": result.rows,
            "error": result.error,
            "summary": result.summary,
        }
    else:
        payload = result
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return text[:8000] + ("…" if len(text) > 8000 else "")
