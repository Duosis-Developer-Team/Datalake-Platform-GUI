"""Configuration for the chatbot-api service.

Mirrors the pydantic-settings convention used by the other microservices
(``services/datacenter-api/app/config.py``): a single ``Settings`` instance,
all fields with safe defaults, env overrides via the process environment.

Secrets (``BULUTISTAN_LLM_API_KEY``, ``DB_PASS``, ``API_JWT_SECRET``) are read
from the environment / Kubernetes Secret only and must never be hardcoded.
"""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "chatbot-api"

    # ------------------------------------------------------------------ #
    # API auth (identical scheme to the other FastAPI services)
    # ------------------------------------------------------------------ #
    api_auth_required: bool = False
    api_jwt_secret: str = ""
    secret_key: str = "change_me_secret_key"

    # ------------------------------------------------------------------ #
    # Bulutistan LLMaaS (OpenAI-compatible)
    # ------------------------------------------------------------------ #
    bulutistan_llm_base_url: str = "https://api.bulutistan.ai/v1"
    bulutistan_llm_api_key: str = ""  # secret — env/secret only, never committed
    # Accept BOTH naming schemes: BULUTISTAN_LLM_MODEL (task prompt) and
    # CHATBOT_MODEL (CTO pack docs). Whichever is set wins.
    chatbot_model: str = Field(
        default="gpt-oss-120b",
        validation_alias=AliasChoices("BULUTISTAN_LLM_MODEL", "CHATBOT_MODEL"),
    )
    chatbot_fallback_model: str = Field(
        default="qwen3-next-80b-instruct",
        validation_alias=AliasChoices(
            "BULUTISTAN_LLM_FALLBACK_MODEL", "CHATBOT_FALLBACK_MODEL"
        ),
    )
    chatbot_temperature: float = 0.2
    chatbot_max_tokens: int = 1800
    chatbot_synthesis_max_tokens: int = Field(
        default=1800,
        validation_alias=AliasChoices("CHATBOT_SYNTHESIS_MAX_TOKENS", "CHATBOT_MAX_TOKENS"),
    )
    chatbot_top_p: float = 1.0
    chatbot_timeout_seconds: float = 120.0
    chatbot_max_retries: int = 2
    chatbot_request_timeout_seconds: float = 600.0

    # ------------------------------------------------------------------ #
    # Internal backend service URLs (Docker/K8s service DNS)
    # ------------------------------------------------------------------ #
    datacenter_api_url: str = "http://datacenter-api:8000"
    customer_api_url: str = "http://customer-api:8000"
    query_api_url: str = "http://query-api:8000"
    crm_engine_url: str = "http://crm-engine:8000"
    admin_api_url: str = "http://admin-api:8000"
    internal_api_timeout_seconds: float = 20.0

    # ------------------------------------------------------------------ #
    # Read-only DB tooling (disabled by default — opt-in only)
    #
    # DB env vars are CHATBOT_DB_*-namespaced so the main stack's generic DB_*
    # values (shared via the env_file) can never silently leak in and change the
    # chatbot's stricter read-only tuning. Connection params accept the generic
    # DB_* as a fallback (the chatbot connects to the same DB with a read-only
    # user); the *tuning* params are strict-namespaced (no generic fallback).
    # ------------------------------------------------------------------ #
    chatbot_db_enabled: bool = False
    db_host: str = Field(default="", validation_alias=AliasChoices("CHATBOT_DB_HOST", "DB_HOST"))
    db_port: str = Field(default="5000", validation_alias=AliasChoices("CHATBOT_DB_PORT", "DB_PORT"))
    db_name: str = Field(default="bulutlake", validation_alias=AliasChoices("CHATBOT_DB_NAME", "DB_NAME"))
    db_user: str = Field(default="chatbot_readonly", validation_alias=AliasChoices("CHATBOT_DB_USER", "DB_USER"))
    db_pass: str = Field(default="", validation_alias=AliasChoices("CHATBOT_DB_PASS", "DB_PASS"))  # secret
    db_statement_timeout_ms: int = Field(
        default=10000, validation_alias=AliasChoices("CHATBOT_DB_STATEMENT_TIMEOUT_MS")
    )
    db_max_rows: int = Field(default=50, validation_alias=AliasChoices("CHATBOT_DB_MAX_ROWS"))

    # ------------------------------------------------------------------ #
    # Orchestration budgets (keep context small + deterministic)
    # ------------------------------------------------------------------ #
    max_tool_calls: int = 4
    max_context_chars: int = 20000
    max_history_messages: int = 8
    max_history_chars: int = 8000
    max_message_chars: int = 4000

    # ------------------------------------------------------------------ #
    # In-memory rate limiting (MVP — per user)
    # ------------------------------------------------------------------ #
    rate_limit_per_minute: int = 20
    rate_limit_per_hour: int = 100

    # ------------------------------------------------------------------ #
    # Agentic analysis loop (multi-step tool iteration + evaluation)
    # ------------------------------------------------------------------ #
    chatbot_agentic_mode: bool = True  # False => legacy single-pass behaviour
    chatbot_llm_react_mode: bool = True  # LLM function-calling ReAct loop (falls back if unsupported)
    chatbot_max_tool_iterations: int = 50
    chatbot_max_tool_calls_per_turn: int = 150
    chatbot_max_tool_calls_per_iteration: int = 10
    chatbot_max_llm_rounds: int = 150
    chatbot_analysis_mode: str = "operational"
    chatbot_map_reduce_enabled: bool = True
    chatbot_parallel_workers: int = 5
    chatbot_clarification_on_ambiguous_ranking: bool = True
    chatbot_log_api_enabled: bool = True
    chatbot_log_api_url: str = "http://chatbot-log-api:8000"
    chatbot_log_api_key: str = ""
    chatbot_log_retention_days: int = 90
    chatbot_log_tool_summary_max_chars: int = 16384
    chatbot_tool_backend: str = "local"  # local | mcp
    datalake_mcp_url: str = "http://datalake-mcp:8010"
    datalake_mcp_timeout_seconds: float = 30.0

    # CPU analysis thresholds (percent) — tunable via env.
    chatbot_cpu_avg_warning_threshold: float = 70.0
    chatbot_cpu_avg_critical_threshold: float = 85.0
    chatbot_cpu_peak_warning_threshold: float = 90.0
    chatbot_stale_hours: int = 24  # data older than this triggers a freshness note

    # ------------------------------------------------------------------ #
    # Conversation history budgeting (rolling summary)
    # ------------------------------------------------------------------ #
    chatbot_conversation_summary_enabled: bool = True
    chatbot_conversation_keep_recent: int = 4  # full user/assistant turn pairs kept verbatim
    chatbot_conversation_summary_max_tokens: int = 400

    # ------------------------------------------------------------------ #
    # Logging / audit
    # ------------------------------------------------------------------ #
    log_full_prompt: bool = False  # never log raw prompts by default

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def llm_configured(self) -> bool:
        return bool(self.bulutistan_llm_api_key.strip())


settings = Settings()
