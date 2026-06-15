# MCP Deploy Verification — 2026-06-12

Test server: `10.134.52.250`  
Branch: `feature/ai-assistant-qa-ux-mcp` (commit `886997b`)  
Mode: `CHATBOT_TOOL_BACKEND=mcp`

## Deploy status

| Service | URL | Status |
|---------|-----|--------|
| datalake-mcp | `:8010/health` | OK |
| chatbot-api | `:8080/health` | OK |
| datacenter-api | `:8000/health` | OK |
| GUI app | `:8050` | Running |

## MCP integration tests

| Check | Result |
|-------|--------|
| MCP tool registry count | **34 tools** |
| `POST /mcp/tools/call` → `get_dashboard_overview` | **success** |
| chatbot-api → MCP backend (`call_tool`) | **success** |
| agent_loop smoke (3 tools) | **all success via MCP** |
| Container pytest (golden + format + parity) | **12/12 passed** |
| `format_dashboard_overview` blocks | **3 blocks, includes table** |

## Live dashboard data (via MCP)

From `get_dashboard_overview` on test server:

- Datacenters: **12**
- Hosts: **354**
- VMs: **16,896**
- Classic CPU used/cap: **4320.83 / 10097.1**
- Hyperconverged CPU used/cap: **15978.95 / 25956.74**

## Issues found and fixed during deploy

1. **422 on `/mcp/tools/call`** — FastAPI body binding; fixed with explicit Pydantic model at module scope (`886997b`).
2. **500 Pydantic ForwardRef** — nested model inside `create_http_app()`; moved `ToolCallBody` to module level.
3. **Partial stack recreate** — first redeploy recreated network; recovered with full `microservice` profile up.

## Observations / follow-ups

1. **Platform table density:** MCP returns `platforms` with `_keys` normalization (3-sample collapse). `format_dashboard_overview` table rows may show sparse platform metrics until registry normalization preserves platform breakdown fields (same as pre-MCP limitation).
2. **ReAct smoke:** log shows `ReAct LLM round failed: empty` during agent smoke — tools still succeed; LLM synthesis path should be validated with a full GUI chat turn + `BULUTISTAN_LLM_API_KEY`.
3. **Log-api:** sample query returned HTTP 200 with 5 recent turns — logging pipeline healthy.

## Manual GUI check recommended

1. Open http://10.134.52.250:8050 → AI Assistant
2. Ask: *"Genel kapasite durumunu özetle"* or *"Platform-bazlı dağılım"*
3. Click **Genişlet** — verify table scroll/readability
4. Admin logs: `/administration/integrations/chatbot/logs`

## Raw artifacts

- `mcp_deploy_verification.json`
- `mcp_deploy_analysis.json`
