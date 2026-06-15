"""Remote tool execution via datalake-mcp HTTP API."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import settings
from datalake_tools_core.registry import ToolResult

logger = logging.getLogger("chatbot-api.mcp")


def call_tool(name: str, args: dict[str, Any], auth_header: Optional[str] = None) -> ToolResult:
    url = f"{settings.datalake_mcp_url.rstrip('/')}/mcp/tools/call"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header
    payload = {"name": name, "arguments": args}
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=settings.datalake_mcp_timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
        return ToolResult(
            name=data.get("name") or name,
            status=data.get("status") or "error",
            source=data.get("source") or "mcp",
            summary=data.get("summary"),
            rows=data.get("rows"),
            error=data.get("error"),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("MCP tool call failed for %s: %s", name, exc)
        return ToolResult(name, "error", "mcp", error="mcp_call_failed")
