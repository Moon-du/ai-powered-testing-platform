from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AI Powered Test Engineering Platform"
    app_env: Literal["development", "test", "production"] = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = (
        "postgresql+psycopg://test_platform:test_platform@localhost:5432/test_platform"
    )
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    ai_task_mode: Literal["inline", "celery"] = "inline"
    llm_provider: Literal["fake"] = "fake"
    llm_model: str = "fake-electronic-pipette-v1"
    prompt_version: str = "p0-fake-v1"
    validator_version: str = "p0-domain-v1"
    policy_version: str = "p0-guardrail-v1"
    dev_auth_enabled: bool = True
    seed_demo: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @model_validator(mode="after")
    def block_development_identity_in_production(self) -> "Settings":
        if self.app_env == "production" and self.dev_auth_enabled:
            raise ValueError("DEV_AUTH_ENABLED must be false in production")
        if self.app_env == "production" and self.seed_demo:
            raise ValueError("SEED_DEMO must be false in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
