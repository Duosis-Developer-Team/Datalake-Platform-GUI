"""Re-export shared tool registry from datalake-tools-core.

Execution may route to local in-process tools or remote datalake-mcp when
``CHATBOT_TOOL_BACKEND=mcp``.
"""

from __future__ import annotations

from typing import Any, Optional

from datalake_tools_core.config import configure
from datalake_tools_core.registry import (  # noqa: F401
    TOOLS,
    ToolResult,
    ToolSpec,
    _normalize,
    _normalize_datacenter_summary_list,
    extract_datacenter_ranking_row,
    get_tool,
    list_tool_names,
    ranking_rows_from_summary,
)

from app.config import settings

configure(settings)


def execute_tool(name: str, args: dict[str, Any], auth_header: Optional[str] = None) -> ToolResult:
    if settings.chatbot_tool_backend == "mcp":
        from app.services.mcp_tool_backend import call_tool

        return call_tool(name, args, auth_header)
    from datalake_tools_core.registry import execute_tool as _local_execute

    return _local_execute(name, args, auth_header)
