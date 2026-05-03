from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_host: str = "10.134.16.6"
    db_port: str = "5000"
    db_name: str = "bulutlake"
    db_user: str = "customer_svc"
    db_pass: str = ""
    # 0 = omit client-side statement_timeout (align with datacenter-api pool; server default applies).
    db_statement_timeout_ms: int = Field(default=60000)

    # WebUI App DB — separate Postgres holding GUI configuration (gui_crm_* tables).
    # Datalake DB stays read-only for raw vendor data.
    webui_db_host: str = "webui-db"
    webui_db_port: str = "5432"
    webui_db_name: str = "bulutwebui"
    webui_db_user: str = "webuiadmin"
    webui_db_pass: str = ""
    webui_db_statement_timeout_ms: int = Field(default=15000)
    # When false, `/ready` does not fail closed if the WebUI DB is unreachable (dev/tests).
    webui_db_required: bool = Field(default=False)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 1
    redis_password: str = ""
    redis_socket_timeout: int = 5
    cache_ttl_seconds: int = 900
    cache_max_memory_items: int = 200


settings = Settings()
