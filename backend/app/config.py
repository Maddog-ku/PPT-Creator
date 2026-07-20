from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PPT Creator API"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://ppt_creator:ppt_creator@localhost:5432/ppt_creator"
    database_required_on_startup: bool = False
    web_origin: str = "http://localhost:3000"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gpt-oss:20b"
    ollama_timeout_seconds: float = 300.0
    ai_config_secret: str = "ppt-creator-local-development-secret"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
