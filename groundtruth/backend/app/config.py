"""Application configuration loaded from environment / .env file."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    app_name: str = "Groundtruth"
    public_base_url: str = "http://localhost:8000"
    secret_key: str = "change-me-to-a-long-random-string"
    access_token_expire_minutes: int = 10080  # 7 days

    # Database
    database_url: str = "sqlite:///./groundtruth.db"

    # LLM
    gemini_api_key: str = ""
    openai_api_key: str = ""
    default_model_id: str = "gemini-3.5-flash"

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_publishable_key: str = ""
    stripe_price_starter: str = ""
    stripe_price_pro: str = ""
    stripe_price_business: str = ""
    stripe_price_overage_metered: str = ""

    @property
    def llm_enabled(self) -> bool:
        return bool(self.gemini_api_key or self.openai_api_key)

    @property
    def billing_enabled(self) -> bool:
        return bool(self.stripe_secret_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
