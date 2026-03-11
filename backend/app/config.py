from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_host: str = "10.134.16.6"
    db_port: str = "5000"
    db_name: str = "bulutlake"
    db_user: str = "datalakeui"
    db_pass: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
