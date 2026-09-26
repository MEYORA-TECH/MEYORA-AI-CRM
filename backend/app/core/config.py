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

    # --- Memory & knowledge -----------------------------------------------
    embedding_backend: Literal["fastembed", "hash"] = "fastembed"  # "hash" is for tests only
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    memory_min_similarity: float = 0.55
    memory_dedup_similarity: float = 0.92
    jobs_worker_enabled: bool = True

    # --- Web research ------------------------------------------------------
    tavily_api_key: SecretStr | None = None
    web_search_monthly_limit: int = 900  # per organization; Tavily's free plan is ~1,000 credits
    web_search_daily_user_limit: int = 40
    web_cache_hours: int = 24
    # Optional public-only model for research briefs (Gemini free tier trains on prompts).
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"

    # --- Google sign-in & Gmail (toggle layers; off by default) -------------------
    google_auth_enabled: bool = False
    gmail_enabled: bool = False
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    # Public URL of this app as the browser sees it; OAuth redirect URIs are built from it.
    public_url: str = "http://localhost:5173"
    gmail_sync_interval_minutes: int = 5
    gmail_initial_sync_days: int = 90
    gmail_initial_sync_max_messages: int = 500
    # 32-byte key, base64. Encrypts stored OAuth tokens. Required in production.
    encryption_key: SecretStr | None = None

    @property
    def google_ready(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
