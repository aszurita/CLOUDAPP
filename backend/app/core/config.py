from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Enterprise CloudOps & DataOps Autopilot"
    environment: str = "local"
    api_prefix: str = "/api"
    database_url: str = "sqlite:///./cloudapp.db"
    frontend_origins: str = "http://localhost:5173"
    ai_provider: str = "gemini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    databricks_host: str | None = None
    datahub_server: str | None = None

    @property
    def ai_configured(self) -> bool:
        if self.ai_provider != "gemini" or not self.gemini_api_key:
            return False
        return not self.gemini_api_key.startswith("phase-")

    @property
    def frontend_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]

    @field_validator("ai_provider")
    @classmethod
    def normalize_ai_provider(cls, value: str) -> str:
        return value.strip().lower()


@lru_cache
def get_settings() -> Settings:
    return Settings()
