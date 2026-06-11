# Chatbot domain catalog (runtime)

Machine-readable counterpart of `docs/chatbot-knowledge/`. The planner
(`query_planner.py`) uses these compact definitions to map a user question to
allowlisted tools, page-independently. The human-readable MD docs are **never**
injected into the LLM context at runtime — only the resulting plan / evidence /
analysis and the matched metric's `answer_guidance` reach the model.

Files:
- `domain_catalog.py` — `MetricDefinition` entries (aliases, entity, metric,
  calculation, architecture, unit, tools, required/default params, forbidden
  tools, answer guidance) + `ARCHITECTURES` + `find_metric_candidates()`.
- `data_source_catalog.py` — tool→endpoint / tool→query-key maps + provider
  tables (reconciled to what exists).
- `metric_semantics.py` — usage-vs-allocation, calculation, source-preference
  classifiers.
- `generated_catalog.json` — compact JSON snapshot (no secrets).

Rules:
- The catalog only references tools that exist in `tool_registry`. It can never
  grant a tool outside the allowlist.
- It must not contain secrets, environment values, DB passwords, API keys or
  connection strings.
- Regenerate the route sample with `scripts/build_chatbot_catalog.py`
  (build-time only; never scans `.env` / `.env.local`). Runtime does no repo scan.
