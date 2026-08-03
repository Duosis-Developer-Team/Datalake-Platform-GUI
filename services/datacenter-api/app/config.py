from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_host: str = "10.134.16.6"
    db_port: str = "5000"
    db_name: str = "bulutlake"
    db_user: str = "infra_svc"
    db_pass: str = ""
    redis_host: str = "localhost"
    redis_port: int = 6379
    # db 0 is the GUI's (REDIS_URL=redis://redis:6379/0). Sharing it meant an
    # admin cache refresh here — which flushes with a bare "*" — wiped the GUI's
    # dl:fecache:* keys as well. Own database, like customer-api (1) and
    # crm-engine (2). The default has to be safe on its own: the k8s manifests
    # do not set REDIS_DB.
    redis_db: int = 3
    redis_password: str = ""
    redis_socket_timeout: int = 5
    cache_ttl_seconds: int = 1200
    cache_max_memory_items: int = 200
    db_pool_minconn: int = 2
    db_pool_maxconn: int = 48

    # WebUI App DB — read-only access for threshold/calc config used by sales potential.
    webui_db_host: str = "webui-db"
    webui_db_port: str = "5432"
    webui_db_name: str = "bulutwebui"
    webui_db_user: str = "webuiadmin"
    webui_db_pass: str = ""
    webui_db_statement_timeout_ms: int = 15000

    # Temporary aggregate energy display override (kW). Set to 0 to use live DB totals.
    static_total_energy_kw: float = 780.0

    class Config:
        env_file = ".env"


settings = Settings()
