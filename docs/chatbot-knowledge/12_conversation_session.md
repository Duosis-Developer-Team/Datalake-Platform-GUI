# 12 — Conversation Session and Context Budget

## Session lifecycle

| Action | Panel | History (`chatbot-history-store`) |
|--------|-------|-----------------------------------|
| Open via FAB | Visible | Preserved (or empty on first open) |
| Minimize via FAB | Hidden | **Preserved** |
| Close via **X** (`chatbot-close-button`) | Hidden | **Cleared** |
| Page navigation while open | Visible/hidden unchanged | **Preserved** (session storage) |

Stores (in `app.layout`): `chatbot-open-store`, `chatbot-history-store`, `chatbot-context-store`, `chatbot-pending-store` — all `storage_type="session"` except page context synced from URL.

## API payload

Each message POST sends:

```json
{
  "message": "current user text",
  "conversation": [{"role": "user|assistant", "content": "..."}],
  "frontend_context": {"pathname", "selected_datacenter", "selected_customer", "time_range", ...}
}
```

The planner resolves `dc_code` / `customer_name` from message → frontend context → **conversation memory** (e.g. follow-up *"bunlardan hangisi…"* after a DC13 question).

## Context budget and summarization

Before the main LLM call, `conversation_manager.prepare_conversation()`:

1. Estimates prompt size (system + developer/tool block + history + new message).
2. Keeps the last **4 turns** verbatim (`chatbot_conversation_keep_recent`).
3. If budget exceeded, summarizes older turns via a short LLM call (or deterministic truncate on failure).
4. Injects summary as a system message: *Earlier conversation summary…*

Config (`chatbot-api`):

| Env | Default |
|-----|---------|
| `CHATBOT_CONVERSATION_SUMMARY_ENABLED` | `true` |
| `CHATBOT_CONVERSATION_KEEP_RECENT` | `4` |
| `CHATBOT_CONVERSATION_SUMMARY_MAX_TOKENS` | `400` |
| `MAX_CONTEXT_CHARS` | `20000` |
| `MAX_HISTORY_MESSAGES` | `8` |
| `MAX_HISTORY_CHARS` | `8000` |

## Related

- API/DB routing: [[11_api_vs_db_routing]]
- Query planning: [[07_query_planning_rules]]
