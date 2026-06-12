# 14 — Chatbot Audit Logging (MongoDB)

## Architecture

`chatbot-api` emits metadata to stdout (`audit_service`) and, when enabled, posts **full turn** payloads (redacted) to `chatbot-log-api`, which persists documents in MongoDB collection `chat_turns`.

```text
Dash chatbot → chatbot-api → (async) chatbot-log-api → MongoDB
Dash admin UI → chatbot_log_client → chatbot-log-api GET → MongoDB
                  ↘ stdout metadata audit
```

## Env vars

| Variable | Service | Purpose |
|----------|---------|---------|
| `CHATBOT_LOG_API_ENABLED` | chatbot-api | Enable async turn logging |
| `CHATBOT_LOG_API_URL` | chatbot-api, GUI `app` | Internal log API base URL |
| `CHATBOT_LOG_API_KEY` | chatbot-api, GUI `app`, log-api | Shared secret (`X-Internal-Api-Key`) |
| `CHATBOT_LOG_RETENTION_DAYS` | chatbot-api, log-api | TTL for stored turns |
| `MONGO_URI` | chatbot-log-api | Mongo connection string |
| `CHATBOT_LOG_MONGO_USER` / `PASS` | compose | Mongo root credentials |

## Read API (internal)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/logs/turns` | Paginated list (`skip`, `limit`, filters) |
| `GET` | `/api/v1/logs/turns/{request_id}` | Single turn detail |

Auth: `X-Internal-Api-Key` (same as write). Not exposed to the browser.

## Admin UI

Route: `/administration/integrations/chatbot/logs`

| Permission | Purpose |
|------------|---------|
| `page:settings_chatbot_logs` | Page access |
| `action:chatbot:audit:read` | View turn logs (child action) |

Server-side client: `src/services/chatbot_log_client.py`. Page: `src/pages/settings/integrations/chatbot_logs.py`.

## Document fields

Each turn stores: `request_id`, `user_id`, `status`, redacted `user_message` / `assistant_answer`, `response_type`, optional `clarification` block, `frontend_context`, `tools`, `investigation_trace`, token usage, latency.

## Security

- Never log raw secrets; `redact_text` runs before POST.
- `chatbot-log-api` is internal-only (Docker network / ClusterIP).
- Admin log viewer uses server-side internal key; page gated by RBAC.

## Related

- [[12_conversation_session]]
- [[13_executive_investigation]]
