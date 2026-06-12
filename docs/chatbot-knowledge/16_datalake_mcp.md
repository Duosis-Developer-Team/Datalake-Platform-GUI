# datalake-mcp

Unified MCP/HTTP tool server exposing all read-only Datalake tools (PostgreSQL templates + GUI microservice APIs).

## Architecture

| Layer | Path | Role |
|-------|------|------|
| `datalake-tools-core` | `services/datalake-tools-core/` | Shared `ToolSpec`, `execute_tool`, DB + API clients |
| `datalake-mcp` | `services/datalake-mcp/` | MCP stdio + HTTP `/mcp/tools` endpoints |
| `chatbot-api` adapter | `CHATBOT_TOOL_BACKEND=local\|mcp` | Routes tool calls in-process or remote |

## Tool inventory

All tools from the chatbot registry (~30+) are exposed with unchanged names (`get_dashboard_overview`, `get_global_km_cluster_memory_top`, …).

Backends:

- **GUI API** — datacenter-api, customer-api, crm-engine, query-api
- **PostgreSQL** — allowlisted read-only SQL templates (`CHATBOT_DB_ENABLED`)

## Deployment

Docker Compose (optional profile):

```bash
docker compose --profile microservice --profile ai-mcp up -d datalake-mcp
```

Environment:

- `CHATBOT_TOOL_BACKEND=mcp` on chatbot-api
- `DATALAKE_MCP_URL=http://datalake-mcp:8010`

## Cursor / local dev

See `services/datalake-mcp/mcp.json.example` for stdio MCP client configuration.

## Security

- Read-only tools only; no arbitrary SQL
- Internal network / ClusterIP in Kubernetes
- JWT forward via `Authorization` header when calling GUI APIs

## Tests

- `test_mcp_tool_parity.py` — registry snapshot parity
- Golden harness can run with `CHATBOT_TOOL_BACKEND=mcp` in integration mode
