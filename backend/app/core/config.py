from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    app_name: str = "competitive-agent-system"

    database_url: str
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    firecrawl_api_key: str | None = None
    milvus_uri: str | None = None
    milvus_token: str | None = None
    milvus_collection: str = "evidence_chunks"

    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "gpt-4.1-mini"
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    run_tasks_inline: bool = False
    fallback_to_local_thread_on_celery_error: bool = True
    fallback_to_local_thread_when_worker_unavailable: bool = True
    celery_worker_heartbeat_ttl_seconds: int = 45
    celery_worker_heartbeat_interval_seconds: int = 10
    celery_visibility_timeout_seconds: int = 120
    celery_queued_recovery_max_age_seconds: int = 1800

    @field_validator("database_url")
    @classmethod
    def strip_database_url(cls, value: str) -> str:
        return value.strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
