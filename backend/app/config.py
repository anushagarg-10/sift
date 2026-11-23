from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://sift:sift@localhost:5432/sift"

    # "mock" runs a deterministic offline classifier, so the whole app works without an API key.
    # "anthropic" calls Claude with structured JSON output.
    llm_provider: str = "mock"
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "low"
    llm_max_workers: int = 4
    llm_max_retries: int = 1

    max_upload_bytes: int = 5 * 1024 * 1024
    max_text_chars: int = 4000

    cors_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
