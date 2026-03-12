from celery import Celery
from celery.schedules import crontab
from app.core.config import settings


def _parse_cron(expr: str):
    """
    Parse 5-part cron expression: minute hour day month day_of_week.
    Fallback to hourly if malformed to keep worker resilient.
    """
    try:
        minute, hour, day_of_month, month_of_year, day_of_week = expr.split()
        return crontab(
            minute=minute,
            hour=hour,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            day_of_week=day_of_week,
        )
    except Exception:
        return crontab(minute=0, hour="*")

# Initialize Celery explicitly pointing to our fast Redis instance
celery_app = Celery(
    "analyzer_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# Config constraints: UTC timezone, strict JSON serialization (security & reversibility)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    imports=["app.tasks.market_tasks", "app.tasks.snapshot_tasks"], # Important to explicitly load the tasks
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_routes={
        "app.tasks.market_tasks.*": {"queue": "market_sync"},
        "app.tasks.snapshot_tasks.*": {"queue": "snapshot_sync"},
    },
)

# Background scheduler execution
celery_app.conf.beat_schedule = {
    # Fires daily shortly after the US Market closes. 4:30 PM EST = 21:30 UTC
    "daily-market-sync": {
        "task": "app.tasks.market_tasks.sync_all_assets_task",
        "schedule": crontab(hour=21, minute=30),
    },
    "snapshot-technical-sync": {
        "task": "app.tasks.snapshot_tasks.sync_technical_snapshots_task",
        "schedule": _parse_cron(settings.CELERY_SNAPSHOT_TECHNICAL_CRON),
    },
    "snapshot-fundamental-sync": {
        "task": "app.tasks.snapshot_tasks.sync_fundamental_snapshots_task",
        "schedule": _parse_cron(settings.CELERY_SNAPSHOT_FUNDAMENTAL_CRON),
    },
    "snapshot-event-sync": {
        "task": "app.tasks.snapshot_tasks.sync_event_snapshots_task",
        "schedule": _parse_cron(settings.CELERY_SNAPSHOT_EVENT_CRON),
    },
}
