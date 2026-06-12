"""datalake-mcp — unified MCP/HTTP tool server for PostgreSQL + GUI API tools."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Optional

from pydantic import BaseModel, Field

from datalake_tools_core.config import configure_from_env, get_settings
from datalake_tools_core.registry import TOOLS, ToolResult, execute_tool, list_tool_names

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("datalake-mcp")


class ToolCallBody(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


def _tool_schema(name: str) -> dict[str, Any]:
    spec = TOOLS[name]
    return {
        "name": spec.name,
        "description": spec.description,
        "inputSchema": {
            "type": "object",
            "properties": {
                "dc_code": {"type": "string"},
                "customer_name": {"type": "string"},
                "days": {"type": "integer"},
                "limit": {"type": "integer"},
                "query_key": {"type": "string"},
                "time_range": {"type": "object"},
            },
        },
    }


def _result_payload(result: ToolResult) -> dict[str, Any]:
    return {
        "name": result.name,
        "status": result.status,
        "source": result.source,
        "summary": result.summary,
        "rows": result.rows,
        "error": result.error,
    }


def run_stdio() -> None:
    """Minimal MCP-style stdio loop (JSON lines)."""
    configure_from_env()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        req_id = msg.get("id")
        if method == "tools/list":
            tools = [_tool_schema(n) for n in list_tool_names()]
            out = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name", "")
            args = params.get("arguments") or {}
            auth = params.get("authorization")
            result = execute_tool(name, args, auth)
            out = {"jsonrpc": "2.0", "id": req_id, "result": _result_payload(result)}
        else:
            out = {"jsonrpc": "2.0", "id": req_id, "error": {"message": "unknown method"}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def create_http_app():
    from fastapi import FastAPI, Header

    configure_from_env()

    app = FastAPI(title="datalake-mcp", version="0.1.0")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "datalake-mcp"}

    @app.get("/mcp/tools")
    def list_tools():
        return {"tools": [_tool_schema(n) for n in list_tool_names()]}

    @app.post("/mcp/tools/call")
    def mcp_call_tool(
        payload: ToolCallBody,
        authorization: Optional[str] = Header(default=None),
    ):
        result = execute_tool(payload.name, payload.arguments, authorization)
        return _result_payload(result)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="datalake-mcp tool server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="http")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    if args.transport == "stdio":
        run_stdio()
    else:
        import uvicorn

        uvicorn.run(create_http_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
