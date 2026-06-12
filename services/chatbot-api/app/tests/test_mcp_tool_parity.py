"""MCP vs local tool registry parity (structure-level)."""

from __future__ import annotations

from datalake_tools_core.registry import TOOLS, list_tool_names


def test_mcp_tool_list_matches_registry():
    names = list_tool_names()
    assert "get_dashboard_overview" in names
    assert "get_datacenters_summary" in names
    assert len(names) == len(TOOLS)
