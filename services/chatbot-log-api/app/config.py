"""Configuration for chatbot-log-api."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "chatbot-log-api"
    mongo_uri: str = Field(
        default="mongodb://chatbot_log:change_me@mongodb:27017/chatbot_logs?authSource=admin",
        validation_alias="MONGO_URI",
    )
    mongo_db: str = Field(default="chatbot_logs", validation_alias="MONGO_DB")
    mongo_collection: str = Field(default="chat_turns", validation_alias="MONGO_COLLECTION")
    log_retention_days: int = Field(default=90, validation_alias="LOG_RETENTION_DAYS")
    internal_api_key: str = Field(default="", validation_alias="INTERNAL_API_KEY")
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()
