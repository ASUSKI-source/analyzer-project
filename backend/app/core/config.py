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
    AI_DEBUG_VERBOSE_LOGS: bool = False
    # Reliability-first default: now ENABLED — per-source timeouts in _assemble_data_context
    # guard against slow Finnhub calls without blowing the total budget.
    AI_INCLUDE_NEWS_SENTIMENT: bool = True

    # Pipeline budget breakdown (total: 24s, Railway proxy kills at 25s):
    #   Assembly: 4s  — per-source caps (quotes:2s, indicators:3.5s, fundamentals:2s, news:2s) run concurrently
    #   Model:   18s  — reduced max_tokens + streamlined prompt buys ~2-4s vs old 17s budget
    #   Parse:   1.5s — JSON extraction is deterministic and fast
    # Net effect: news is now enabled with the same safety margin as before.
    AI_TOTAL_BUDGET_SECONDS: float = 24.0
    AI_ASSEMBLY_BUDGET_SECONDS: float = 4.0
    AI_MODEL_BUDGET_SECONDS: float = 18.0
    AI_PARSE_BUDGET_SECONDS: float = 1.5
    AI_STRICT_JSON_ENFORCEMENT: bool = True
    # When False (default), model/network failures should prefer last-good/error paths
    # over simulated narrative reports.
    AI_ALLOW_SIMULATED_FALLBACK: bool = False
    AI_ASYNC_JOBS_ENABLED: bool = True
    AI_LOGIN_PREWARM_ENABLED: bool = True
    AI_LAST_GOOD_TTL_SECONDS: int = 86_400
    AI_LAST_ATTEMPT_TTL_SECONDS: int = 21_600
    AI_JOB_TTL_SECONDS: int = 1_200
    AI_PREWARM_COOLDOWN_SECONDS: int = 900
    AI_SNAPSHOT_READS_ENABLED: bool = True
    AI_PROVIDER_FALLBACK_ENABLED: bool = True
    REQUIRE_DB_BASELINE_MIGRATIONS: bool = True

    SNAPSHOT_TECHNICAL_TTL_SECONDS: int = 21_600
    SNAPSHOT_FUNDAMENTAL_TTL_SECONDS: int = 86_400
    SNAPSHOT_EVENT_TTL_SECONDS: int = 21_600
    SNAPSHOT_COVERAGE_TTL_SECONDS: int = 21_600

    # Celery scheduler controls for robust background enrichment.
    CELERY_SNAPSHOT_TECHNICAL_CRON: str = "7 * * * *"
    CELERY_SNAPSHOT_FUNDAMENTAL_CRON: str = "20 */6 * * *"
    CELERY_SNAPSHOT_EVENT_CRON: str = "35 */2 * * *"

    # Config ensures Pydantic looks for a .env file and errors out if critical vars (like DATABASE_URL) are missing
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_ignore_empty=True,
        extra="ignore",  # Ignore external env vars that aren't defined here
    )


settings = Settings()
