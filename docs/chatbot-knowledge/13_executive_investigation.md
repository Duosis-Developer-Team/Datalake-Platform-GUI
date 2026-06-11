# 13 — Executive Persona and Investigation Budget

## Audience

Chatbot answers are aimed at **datacenter managers** and **company executives**:

- Business impact and operational risk first
- Technical tables support the narrative; they do not replace analysis
- Recommended actions should be concrete next checks

## Answer flow: question → analysis → answer

Responses must follow this order:

1. **Analiz** — what was checked (`investigation_trace`), findings, interpretation
2. **Sonuç** — direct answer (1–3 sentences)
3. Table/list (when applicable)
4. Risk level + recommended actions
5. Sources + data quality + confidence

Never respond with a bare "I don't have this information" without listing attempted tools/sources.

## Hybrid investigation pipeline

```text
query_planner (catalog)
  → seed tools (primary + fallback)
  → LLM ReAct loop (function-calling, optional)
  → deterministic evidence follow-ups
  → analysis_synthesizer
  → final answer (ReAct draft or synthesis LLM call)
```

All tools remain allowlisted via `tool_registry`; no free-form SQL.

## Budget caps (per user question)

| Env var | Default | Purpose |
|---------|---------|---------|
| `CHATBOT_MAX_TOOL_CALLS_PER_TURN` | `150` | Max tool/API/DB executions |
| `CHATBOT_MAX_LLM_ROUNDS` | `150` | Max LLM↔tool ReAct rounds |
| `CHATBOT_MAX_TOOL_ITERATIONS` | `50` | Deterministic follow-up iterations |
| `CHATBOT_MAX_TOOL_CALLS_PER_ITERATION` | `10` | Tools per deterministic batch |
| `CHATBOT_REQUEST_TIMEOUT_SECONDS` | `600` | Whole-request budget (server) |
| `CHATBOT_CLIENT_TIMEOUT` | `600` | Dash → chatbot-api HTTP timeout |

Early-stop when evidence is sufficient. Dedup: same tool + same params never runs twice.

## Feature flags

| Env var | Default | Purpose |
|---------|---------|---------|
| `CHATBOT_AGENTIC_MODE` | `true` | Multi-step agent vs legacy single-pass |
| `CHATBOT_LLM_REACT_MODE` | `true` | LLM function-calling ReAct after seed |

If the LLM provider rejects `tools`, the service falls back to deterministic-only investigation (still with the 150 tool cap).

## Investigation trace

Every tool run is recorded in `investigation_trace` and surfaced to the model and fallback formatter. When data is missing, the answer must reference this trace.

## Related

- [[07_query_planning_rules]]
- [[08_response_analysis_guidelines]]
- [[09_known_limitations]]
- [[11_api_vs_db_routing]]
- [[12_conversation_session]]
