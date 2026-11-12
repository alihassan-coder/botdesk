"""App settings, read from environment variables and `apps/api/.env`.

Every setting has a safe local default, so `pnpm dev:api` starts before you fill in `.env`.
`.env.example` explains each one.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"

    # Postgres (Neon) in real use. The SQLite default lets the API start with no setup.
    database_url: str = "sqlite+aiosqlite:///./botdesk.db"

    # Comma-separated origins allowed to call the API with cookies (the web app).
    web_origins: str = "http://localhost:3000"

    # Where the web app lives; invite links point here.
    web_app_url: str = "http://localhost:3000"

    session_cookie_name: str = "botdesk_session"
    session_days: int = 30
    invitation_days: int = 7

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def sqlalchemy_url(self) -> str:
        """Plain Postgres URLs (what Neon gives you) get the async psycopg driver."""
        for prefix in ("postgres://", "postgresql://"):
            if self.database_url.startswith(prefix):
                return "postgresql+psycopg://" + self.database_url.removeprefix(prefix)
        return self.database_url

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.web_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
