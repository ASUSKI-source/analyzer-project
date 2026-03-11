from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

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
    imports=["app.tasks.market_tasks"] # Important to explicitly load the tasks
)

# Background scheduler execution
celery_app.conf.beat_schedule = {
    # Fires daily shortly after the US Market closes. 4:30 PM EST = 21:30 UTC
    "daily-market-sync": {
        "task": "app.tasks.market_tasks.sync_all_assets_task",
        "schedule": crontab(hour=21, minute=30),
    },
}
