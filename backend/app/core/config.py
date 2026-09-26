from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"

    database_url: str
    # Set to 0 when connecting through a transaction-mode pooler (e.g. Neon pooled URL);
    # asyncpg's prepared-statement cache is incompatible with it.
    db_statement_cache_size: int = 100

    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    cors_origins: list[str] = ["http://localhost:5173"]
    cookie_secure: bool = False

    rate_limit_enabled: bool = True
    login_rate_limit: int = 10  # attempts per window per IP+email
    login_rate_window_seconds: int = 900

    # --- AI -----------------------------------------------------------------
    # Keys are optional: without one the provider is simply not in the pool.
    groq_api_key: SecretStr | None = None
    groq_chat_model: str = "openai/gpt-oss-120b"
    groq_fast_model: str = "openai/gpt-oss-20b"
    openrouter_api_key: SecretStr | None = None
    openrouter_chat_model: str | None = None  # e.g. a ":free" model id you have checked
    # Extra providers as JSON (see docs/ai-providers.md), for any OpenAI-compatible API.
    ai_extra_providers: str | None = None
    ai_daily_token_quota: int = 60_000  # per user
    ai_max_model_calls: int = 3  # per chat turn
    ai_request_token_budget: int = 6_000  # prompt tokens per call on the free tier

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
