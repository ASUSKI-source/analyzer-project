from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Stocks/Crypto AI Analyzer"
    DATABASE_URL: str
    REDIS_URL: str
    ANTHROPIC_API_KEY: str | None = None
    POLYGON_API_KEY: str | None = None
    FINNHUB_API_KEY: str | None = None
    FRONTEND_URL: str | None = "http://localhost:3000"

    # Advanced Security: JWT and User Session Config
    SECRET_KEY: str = "supersecretkey_change_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days limit

    # Comma-separated list of admin user emails.
    # Defaults to the owner account; can be overridden via environment.
    ADMIN_EMAILS: str | None = "drewsuski@gmail.com"

    # Enable extra timing/debug metadata in AI responses (non-prod debugging).
    AI_DEBUG_TIMING: bool = False

    # Config ensures Pydantic looks for a .env file and errors out if critical vars (like DATABASE_URL) are missing
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_ignore_empty=True,
        extra="ignore",  # Ignore external env vars that aren't defined here
    )


settings = Settings()
