"""Runtime configuration for datalake-tools-core (shared by chatbot-api and datalake-mcp)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

_settings: Optional["ToolRuntimeSettings"] = None


@dataclass
class ToolRuntimeSettings:
    datacenter_api_url: str = "http://datacenter-api:8000"
    customer_api_url: str = "http://customer-api:8000"
    query_api_url: str = "http://query-api:8000"
    crm_engine_url: str = "http://crm-engine:8000"
    admin_api_url: str = "http://admin-api:8000"
    internal_api_timeout_seconds: float = 20.0
    chatbot_db_enabled: bool = False
    db_host: str = ""
    db_port: str = "5000"
    db_name: str = "bulutlake"
    db_user: str = "chatbot_readonly"
    db_pass: str = ""
    db_statement_timeout_ms: int = 10000
    db_max_rows: int = 50


def configure(settings_obj: Any) -> None:
    """Bind chatbot-api Settings or env-derived ToolRuntimeSettings."""
    global _settings
    _settings = ToolRuntimeSettings(
        datacenter_api_url=getattr(settings_obj, "datacenter_api_url", "http://datacenter-api:8000"),
        customer_api_url=getattr(settings_obj, "customer_api_url", "http://customer-api:8000"),
        query_api_url=getattr(settings_obj, "query_api_url", "http://query-api:8000"),
        crm_engine_url=getattr(settings_obj, "crm_engine_url", "http://crm-engine:8000"),
        admin_api_url=getattr(settings_obj, "admin_api_url", "http://admin-api:8000"),
        internal_api_timeout_seconds=float(
            getattr(settings_obj, "internal_api_timeout_seconds", 20.0)
        ),
        chatbot_db_enabled=bool(getattr(settings_obj, "chatbot_db_enabled", False)),
        db_host=str(getattr(settings_obj, "db_host", "")),
        db_port=str(getattr(settings_obj, "db_port", "5000")),
        db_name=str(getattr(settings_obj, "db_name", "bulutlake")),
        db_user=str(getattr(settings_obj, "db_user", "chatbot_readonly")),
        db_pass=str(getattr(settings_obj, "db_pass", "")),
        db_statement_timeout_ms=int(getattr(settings_obj, "db_statement_timeout_ms", 10000)),
        db_max_rows=int(getattr(settings_obj, "db_max_rows", 50)),
    )


def configure_from_env() -> None:
    import os

    configure(
        type(
            "EnvSettings",
            (),
            {
                "datacenter_api_url": os.getenv("DATACENTER_API_URL", "http://datacenter-api:8000"),
                "customer_api_url": os.getenv("CUSTOMER_API_URL", "http://customer-api:8000"),
                "query_api_url": os.getenv("QUERY_API_URL", "http://query-api:8000"),
                "crm_engine_url": os.getenv("CRM_ENGINE_URL", "http://crm-engine:8000"),
                "admin_api_url": os.getenv("ADMIN_API_URL", "http://admin-api:8000"),
                "internal_api_timeout_seconds": float(
                    os.getenv("INTERNAL_API_TIMEOUT_SECONDS", "20")
                ),
                "chatbot_db_enabled": os.getenv("CHATBOT_DB_ENABLED", "false").lower() == "true",
                "db_host": os.getenv("CHATBOT_DB_HOST", os.getenv("DB_HOST", "")),
                "db_port": os.getenv("CHATBOT_DB_PORT", os.getenv("DB_PORT", "5000")),
                "db_name": os.getenv("CHATBOT_DB_NAME", os.getenv("DB_NAME", "bulutlake")),
                "db_user": os.getenv("CHATBOT_DB_USER", os.getenv("DB_USER", "chatbot_readonly")),
                "db_pass": os.getenv("CHATBOT_DB_PASS", os.getenv("DB_PASS", "")),
                "db_statement_timeout_ms": int(os.getenv("CHATBOT_DB_STATEMENT_TIMEOUT_MS", "10000")),
                "db_max_rows": int(os.getenv("CHATBOT_DB_MAX_ROWS", "50")),
            },
        )()
    )


def get_settings() -> ToolRuntimeSettings:
    if _settings is None:
        configure_from_env()
    return _settings  # type: ignore[return-value]
