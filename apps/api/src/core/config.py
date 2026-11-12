"""App settings, read from environment variables and `apps/api/.env`.

Every setting has a safe local default, so `pnpm dev:api` starts before you fill in `.env`.
`.env.example` explains each one.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"

    # Postgres (Neon) in real use. The SQLite default lets the API start with no setup.
    database_url: str = "sqlite+aiosqlite:///./botdesk.db"

    # The direct (unpooled) Postgres address, for run checkpoints and memory, which keep their own
    # connections. Empty = use DATABASE_URL. On Neon: the same URL without `-pooler` in the host.
    database_url_direct: str = ""

    # A separate, throwaway Postgres database for the Postgres tests. Never your dev database:
    # the tests wipe it. Empty = those tests are skipped.
    test_database_url: str = ""

    # Bots: the model when a bot doesn't name one ("provider:model"), and provider keys.
    # A provider with no key gets a stand-in model that replies with a canned message.
    default_model_id: str = "anthropic:claude-sonnet-4-5"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Run limits (agents-and-plugins.md §4.2) and how many runs one bot may have going at once.
    run_max_steps: int = 25
    run_max_seconds: int = 900
    bot_max_running_runs: int = 2

    # Memory (mem0 on pgvector). Needs MEMORY_ENABLED=true, Postgres and OPENAI_API_KEY.
    memory_enabled: bool = False

    # Comma-separated origins allowed to call the API with cookies (the web app).
    web_origins: str = "http://localhost:3000"

    # Where the web app lives; invite links point here.
    web_app_url: str = "http://localhost:3000"

    session_cookie_name: str = "botdesk_session"
    session_days: int = 30
    invitation_days: int = 7

    # Email through Brevo's transactional API. Without a key, emails are only logged (dev, tests).
    brevo_api_key: SecretStr | None = None
    email_from_address: str = ""  # a sender verified in Brevo
    email_from_name: str = "BotDesk"
    password_reset_minutes: int = 60

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def sends_real_email(self) -> bool:
        return bool(self.brevo_api_key and self.brevo_api_key.get_secret_value() and self.email_from_address)

    @property
    def sqlalchemy_url(self) -> str:
        """Plain Postgres URLs (what Neon gives you) get the async psycopg driver."""
        for prefix in ("postgres://", "postgresql://"):
            if self.database_url.startswith(prefix):
                return "postgresql+psycopg://" + self.database_url.removeprefix(prefix)
        return self.database_url

    @property
    def uses_postgres(self) -> bool:
        return self.database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://"))

    @property
    def direct_url(self) -> str:
        """A plain `postgresql://` address for psycopg itself (checkpoints, memory)."""
        url = self.database_url_direct or self.database_url
        return url.replace("postgresql+psycopg://", "postgresql://", 1)

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.web_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
