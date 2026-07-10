from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "admin_backend",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# Route worker tasks to the standard "celery" queue
celery_app.conf.task_routes = {
    "app.worker.tasks.*": {"queue": "celery"},
}

# Weekly donor sync: Sunday 00:07 UTC (03:07 MSK)
celery_app.conf.beat_schedule = {
    "labirint-weekly-sync": {
        "task": "app.worker.tasks.labirint_weekly_sync_task",
        "schedule": crontab(minute=7, hour=0, day_of_week="sunday"),
    },
    "bunker-weekly-sync": {
        "task": "app.worker.tasks.bunker_weekly_sync_task",
        "schedule": crontab(minute=7, hour=1, day_of_week="sunday"),
    },
}
