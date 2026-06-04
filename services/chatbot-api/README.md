# chatbot-api

Internal FastAPI microservice that powers the **Bulutistan AI Assistant** widget in
the Datalake Platform WebUI. It is the only component that talks to the Bulutistan
LLMaaS, so the LLM token never reaches the browser.

```
Dash WebUI ──(server-side callback, forwards user JWT)──▶ chatbot-api
   chatbot-api ──▶ datacenter-api / customer-api / query-api / crm-engine   (read-only tools)
   chatbot-api ──▶ allowlisted read-only DB templates                       (disabled by default)
   chatbot-api ──▶ Bulutistan LLMaaS  POST /v1/chat/completions             (OpenAI-compatible)
```

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Liveness — `{"status":"ok","service":"chatbot-api"}` |
| GET | `/ready` | Readiness — config presence only (no secret values, no external call) |
| POST | `/api/v1/chatbot/messages` | Main chat endpoint (alias: `/api/v1/chatbot/chat`) |

Request / response contract: see `app/models/schemas.py` and CTO pack `08_API_CONTRACTS.md`.

## Configuration (env)

Secrets come from the environment / Kubernetes Secret only — **never commit a real token.**

| Var | Default | Purpose |
|---|---|---|
| `BULUTISTAN_LLM_API_KEY` | `""` | **Secret.** LLMaaS token. |
| `BULUTISTAN_LLM_BASE_URL` | `https://api.bulutistan.ai/v1` | OpenAI-compatible base URL. |
| `CHATBOT_MODEL` / `BULUTISTAN_LLM_MODEL` | `gpt-oss-120b` | Primary model (both names accepted). |
| `CHATBOT_FALLBACK_MODEL` / `BULUTISTAN_LLM_FALLBACK_MODEL` | `qwen3-next-80b-instruct` | Used on recoverable failures. |
| `CHATBOT_TEMPERATURE` / `CHATBOT_MAX_TOKENS` / `CHATBOT_TIMEOUT_SECONDS` / `CHATBOT_MAX_RETRIES` | `0.2 / 900 / 60 / 2` | LLM params. |
| `API_AUTH_REQUIRED` | `false` | Enforce Bearer JWT (set `true` in prod). |
| `API_JWT_SECRET` → `SECRET_KEY` | — | JWT verification secret (shared with the other services). |
| `DATACENTER_API_URL` / `CUSTOMER_API_URL` / `QUERY_API_URL` / `CRM_ENGINE_URL` / `ADMIN_API_URL` | service DNS | Downstream services. |
| `CHATBOT_DB_ENABLED` | `false` | Enable read-only DB tools. |
| `CHATBOT_DB_HOST` / `_PORT` / `_NAME` / `_USER` / `_PASS` | — | Read-only DB connection (namespaced so the main stack's `DB_*` cannot leak in). |
| `CHATBOT_DB_STATEMENT_TIMEOUT_MS` / `CHATBOT_DB_MAX_ROWS` | `10000 / 50` | DB guardrails. |

## Run locally

```bash
pip install -r requirements.txt
export BULUTISTAN_LLM_API_KEY='<token>'        # shell only — .env is git-tracked here, don't put it there
uvicorn app.main:app --host 0.0.0.0 --port 8000
curl localhost:8000/health
```

## Test

```bash
pytest app/tests -v          # 51 tests, no real LLM/DB needed (mock mode)
ruff check app/ --select E,F,W --ignore E501
```

## Docker / Compose

The compose service reads the token from the **gitignored** `.env.local` at the
repo root (optional `env_file`) — never from a tracked file.

```bash
# repo root .env.local (gitignored):  BULUTISTAN_LLM_API_KEY=<token>
docker compose --profile microservice up -d --build chatbot-api
curl localhost:8080/health
```

## Kubernetes

```bash
kubectl create secret generic bulutistan-llm-secret \
  --from-literal=BULUTISTAN_LLM_API_KEY='<token>'      # do NOT use the committed reference file
kubectl apply -f k8s/chatbot-api/
kubectl rollout status deploy/bulutistan-chatbot-api
```

## Security model (enforced in code, independent of the LLM)

- LLM token only via env/secret; redaction scrubs logs, audit and LLM context.
- Read-only DB: `SELECT`/`WITH` only, forbidden-keyword + sensitive-column + multi-statement
  rejection, **template-only** execution, row cap + statement timeout, disabled by default.
- `query-api` passthrough locked to an explicit (empty) allowlist.
- Forbidden-intent (secret / prompt-injection / destructive-SQL) requests are refused
  deterministically before any LLM call; benign questions are not over-blocked.
- Per-user in-memory rate limiting; audit logs metadata only (no raw prompts by default).
