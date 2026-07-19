from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PPT Creator API"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://ppt_creator:ppt_creator@localhost:5432/ppt_creator"
    web_origin: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
