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
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 1
    redis_password: str = ""
    redis_socket_timeout: int = 5
    cache_ttl_seconds: int = 900
    cache_max_memory_items: int = 200


settings = Settings()
