from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_host: str = "10.134.16.6"
    db_port: str = "5000"
    db_name: str = "bulutlake"
    db_user: str = "infra_svc"
    db_pass: str = ""
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    redis_socket_timeout: int = 5
    cache_ttl_seconds: int = 1200
    cache_max_memory_items: int = 200

    # WebUI App DB — read-only access for threshold/calc config used by sales potential.
    webui_db_host: str = "webui-db"
    webui_db_port: str = "5432"
    webui_db_name: str = "bulutwebui"
    webui_db_user: str = "webuiadmin"
    webui_db_pass: str = ""
    webui_db_statement_timeout_ms: int = 15000

    class Config:
        env_file = ".env"


settings = Settings()
