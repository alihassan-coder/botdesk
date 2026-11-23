"""App settings, read from environment variables and `apps/api/.env`.

Every setting has a safe local default, so `pnpm dev:api` starts before you fill in `.env`.
`.env.example` explains each one.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Who may create an account (SIGNUP_MODE); see `Settings.signup_mode`.
SignUpMode = Literal["open", "invite-only", "closed"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Only an explicit ENVIRONMENT=development or test relaxes the secret rules (see
    # `relaxed_secrets`); left unset it reads as development but is treated like production.
    environment: Literal["development", "test", "production"] = "development"

    # Postgres (Neon) in real use. The SQLite default lets the API start with no setup.
    database_url: str = "sqlite+aiosqlite:///./botdesk.db"

    # The direct (unpooled) Postgres address, for run checkpoints and memory, which keep their own
    # connections. Empty = use DATABASE_URL. On Neon: the same URL without `-pooler` in the host.
    database_url_direct: str = ""

    # Where background jobs (bot runs, approval expiry, timers) run (ADR 0013). embedded: a worker
    # inside the API process (development, small installs). separate: the API only adds jobs;
    # run `python -m src.worker` as its own process (and as many copies as you like). Postgres only:
    # on SQLite jobs always run inside the API process.
    worker_mode: Literal["embedded", "separate"] = "embedded"
    # Jobs one worker runs at once (bot runs mostly wait on the model, so this can be generous).
    worker_concurrency: int = 10

    # A separate, throwaway Postgres database for the Postgres tests. Never your dev database:
    # the tests wipe it. Empty = those tests are skipped.
    test_database_url: str = ""

    # Bots: the model when a bot doesn't name one ("provider:model"), and instance-wide provider
    # keys. Organizations add their own keys in Settings → Models & keys; those come first, these
    # are the fallback for self-hosting. A provider with neither gets a stand-in model.
    default_model_id: str = "anthropic:claude-sonnet-4-5"
    # SecretStr, so a key never shows up in a repr, a log line or an error page by accident.
    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    openrouter_api_key: SecretStr = SecretStr("")
    groq_api_key: SecretStr = SecretStr("")

    # Encrypts organizations' provider keys at rest: at least 32 characters, and required unless
    # ENVIRONMENT is explicitly development or test (those fall back to a public development key).
    secret_key: SecretStr | None = None
    # Earlier SECRET_KEYs, comma-separated, while rotating: keys saved under them still decrypt,
    # and are encrypted with SECRET_KEY the next time they're saved.
    secret_key_old: SecretStr | None = None
    # Custom model servers on private, loopback or link-local addresses (the SSRF guard). Refused
    # by default everywhere; set to true on a machine whose model server is on its own network
    # (Ollama on localhost in development, a self-hosted vLLM next to the API).
    allow_private_model_urls: bool = False
    # MCP servers (ADR 0012) on private, loopback or link-local addresses: its own switch, refused
    # by default. Set to true in development to try an MCP server running on your own machine.
    allow_private_mcp_urls: bool = False

    # Bots' files (ADR 0017). An organization that hasn't chosen a storage provider keeps its
    # files on this server in FILES_DIR/<organization id>/botdesk/, unless LOCAL_FILES=false
    # (a host whose disk is wiped on every deploy). Each organization gets LOCAL_FILES_QUOTA_MB there.
    files_dir: str = "data/files"
    local_files: bool = True
    local_files_quota_mb: int = 5120
    file_max_mb: int = 25
    # S3-compatible storage on a private address (MinIO on your own network): refused by default.
    allow_private_storage_urls: bool = False

    # Bots' browsers (ADR 0017). Local: Chromium on this server, one per bot, its sign-ins kept in
    # BROWSER_PROFILES_DIR/<organization id>/<bot id>/. LOCAL_BROWSER_CHANNEL="" uses Playwright's
    # Chromium (`uv run playwright install chromium`); "chrome" or "msedge" use the installed browser.
    local_browser: bool = True
    local_browser_channel: str = ""
    browser_profiles_dir: str = "data/browser-profiles"
    browser_idle_minutes: int = 10
    browser_max_sessions: int = 3
    # Pages on private addresses (the server's own network): refused by default.
    allow_private_browser_urls: bool = False

    # Run limits (agents-and-plugins.md §4.2) and how many runs one bot may have going at once.
    run_max_steps: int = 25
    run_max_seconds: int = 900
    bot_max_running_runs: int = 2
    # Bots @mentioning bots (ADR 0009): how many hops a chain of bot replies may go from a
    # person's message before it stops (and the chat says so).
    bot_hop_limit: int = 3
    # Handoffs (ADR 0014): tasks one run may hand off over its whole life, open tasks per
    # organization (a soft cap), and how long a task may take before it fails as timed out.
    handoff_max_tasks_per_run: int = 5
    handoff_max_open_tasks_per_org: int = 20
    handoff_timeout_minutes: int = 60

    # Tools. PLUGINS is the allowlist of built-in plugins to load (ADR 0006); "demo" adds fake
    # tools (notes, a fake outbox) so approvals can be tried with no outside account; "gmail"
    # connects Google accounts once the Google client below is set (`.env.example` lists both).
    plugins: str = "demo"
    tool_timeout_seconds: int = 30
    # An approval nobody answers in this time counts as "no" (approvals fail closed).
    approval_expiry_hours: int = 72

    # Memory (mem0 on pgvector). Needs MEMORY_ENABLED=true, Postgres and OPENAI_API_KEY.
    memory_enabled: bool = False

    # Comma-separated origins allowed to call the API with cookies (the web app).
    web_origins: str = "http://localhost:3000"

    # Where the web app lives; invite links point here.
    web_app_url: str = "http://localhost:3000"

    # The API's own public address. OAuth providers send people back to
    # {API_PUBLIC_URL}/api/v1/oauth/callback (ADR 0010 §5), so it must be reachable from their browser.
    api_public_url: str = "http://localhost:8000"

    # The server's own Google OAuth client (ADR 0011 §6, docs/self-hosting/google-oauth.md). Both
    # are needed before anyone can connect a Google account (Gmail).
    google_oauth_client_id: str = ""
    google_oauth_client_secret: SecretStr = SecretStr("")
    # Tests only (ignored unless ENVIRONMENT=test): send Google's sign-in, token and revoke calls,
    # and Gmail API calls, to a fake server instead ("http://127.0.0.1:9100").
    google_oauth_base_url: str = ""
    gmail_api_base_url: str = ""

    session_cookie_name: str = "botdesk_session"
    session_days: int = 30
    invitation_days: int = 7

    # Who may create an account: open (anyone who reaches the server), invite-only (only with an
    # unused invite link for that email; they join the inviting organization) or closed (nobody
    # new; existing accounts still sign in and accept invites).
    signup_mode: SignUpMode = "open"

    # Proxies whose X-Forwarded-For / X-Forwarded-Proto are believed (comma-separated IPs or
    # CIDRs, "*" = any). The same variable uvicorn reads. Rate limits key on the client address,
    # so behind a reverse proxy this must include it; anyone else's header is ignored.
    forwarded_allow_ips: str = "127.0.0.1,::1"

    # Email through Brevo's transactional API. Without a key, emails are only logged (dev, tests).
    brevo_api_key: SecretStr | None = None
    email_from_address: str = ""  # a sender verified in Brevo
    email_from_name: str = "BotDesk"
    password_reset_minutes: int = 60

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def relaxed_secrets(self) -> bool:
        """True only when ENVIRONMENT was set to development or test on purpose. An unset
        ENVIRONMENT defaults to development for everything else, but a server someone forgot to
        configure must not run with the public development SECRET_KEY: it fails closed."""
        return "environment" in self.model_fields_set and self.environment in ("development", "test")

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
    def plugin_ids(self) -> list[str]:
        return [plugin.strip() for plugin in self.plugins.split(",") if plugin.strip()]

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.web_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
