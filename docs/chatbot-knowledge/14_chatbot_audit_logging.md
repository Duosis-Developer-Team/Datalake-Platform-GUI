# 14 — Chatbot Audit Logging (MongoDB)

## Architecture

`chatbot-api` emits metadata to stdout (`audit_service`) and, when enabled, posts **full turn** payloads (redacted) to `chatbot-log-api`, which persists documents in MongoDB collection `chat_turns`.

```text
Dash → chatbot-api → (async) chatbot-log-api → MongoDB
                  ↘ stdout metadata audit
```

## Env vars

| Variable | Service | Purpose |
|----------|---------|---------|
| `CHATBOT_LOG_API_ENABLED` | chatbot-api | Enable async turn logging |
| `CHATBOT_LOG_API_URL` | chatbot-api | Internal log API base URL |
| `CHATBOT_LOG_API_KEY` | both | Shared secret (`X-Internal-Api-Key`) |
| `CHATBOT_LOG_RETENTION_DAYS` | both | TTL for stored turns |
| `MONGO_URI` | chatbot-log-api | Mongo connection string |
| `CHATBOT_LOG_MONGO_USER` / `PASS` | compose | Mongo root credentials |

## Document fields

Each turn stores: `request_id`, `user_id`, `status`, redacted `user_message` / `assistant_answer`, `response_type`, optional `clarification` block, `frontend_context`, `tools`, `investigation_trace`, token usage, latency.

## Security

- Never log raw secrets; `redact_text` runs before POST.
- `chatbot-log-api` is internal-only (Docker network / ClusterIP).
- Read/query UI and RBAC (`action:chatbot:audit:read`) are a follow-up.

## Related

- [[12_conversation_session]]
- [[13_executive_investigation]]
