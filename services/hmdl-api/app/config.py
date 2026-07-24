"""HMDL API configuration — bulutlake PostgreSQL (hmdl schema) read path."""

from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


def _env(*names: str, default: str = "") -> str:
    for name in names:
        val = os.getenv(name)
        if val is not None and val != "":
            return val
    return default


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_host: str = _env("HMDL_DB_HOST", "DB_HOST", default="10.134.16.6")
    db_port: str = _env("HMDL_DB_PORT", "DB_PORT", default="5000")
    db_name: str = _env("HMDL_DB_NAME", "DB_NAME", default="bulutlake")
    db_user: str = _env("HMDL_DB_USER", "DB_USER", default="infra_svc")
    db_pass: str = _env("HMDL_DB_PASSWORD", "DB_PASS", default="")
    hmdl_schema: str = _env("HMDL_SCHEMA", default="hmdl")
    db_pool_minconn: int = 1
    # Headroom for concurrent topology/coverage requests + the 5s health probe.
    # The pool is non-blocking (getconn raises when full), so this is the hard
    # burst ceiling; keep above the expected simultaneous request count.
    db_pool_maxconn: int = 16
    db_statement_timeout_ms: int = 30000

    # Automation-health freshness thresholds (hours). warn = a run was missed;
    # dead = automation effectively stopped. Overridable per deployment via env.
    ah_zabbix_warn_hours: float = float(_env("HMDL_AH_ZABBIX_WARN_H", default="12"))
    ah_zabbix_dead_hours: float = float(_env("HMDL_AH_ZABBIX_DEAD_H", default="24"))
    ah_collector_warn_hours: float = float(_env("HMDL_AH_COLLECTOR_WARN_H", default="26"))
    ah_collector_dead_hours: float = float(_env("HMDL_AH_COLLECTOR_DEAD_H", default="50"))
    ah_checks_warn_hours: float = float(_env("HMDL_AH_CHECKS_WARN_H", default="26"))
    ah_checks_dead_hours: float = float(_env("HMDL_AH_CHECKS_DEAD_H", default="50"))
    ah_recon_warn_hours: float = float(_env("HMDL_AH_RECON_WARN_H", default="48"))
    ah_recon_dead_hours: float = float(_env("HMDL_AH_RECON_DEAD_H", default="120"))

    hub_dc_code: str = _env("HMDL_HUB_DC", default="DC13")
    proxy_assignment_path: str = _env(
        "HMDL_PROXY_ASSIGNMENT_PATH",
        default="/app/data/proxy_assignment.yml",
    )

    api_auth_required: bool = _env("API_AUTH_REQUIRED", default="false").lower() in (
        "1",
        "true",
        "yes",
    )
    api_jwt_secret: str = _env("API_JWT_SECRET", "SECRET_KEY", default="change_me_secret_key")

    awx_enabled: bool = _env("AWX_ENABLED", default="false").lower() in ("1", "true", "yes")
    awx_api_url: str = _env("AWX_API_URL", default="")
    awx_token: str = _env("AWX_TOKEN", default="")
    awx_netbox_zabbix_jt_id: str = _env("AWX_NETBOX_ZABBIX_JT_ID", default="")
    awx_verify_ssl: bool = _env("AWX_VERIFY_SSL", default="false").lower() in ("1", "true", "yes")


settings = Settings()
