from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "admin_backend",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# Вариант 1: Изменить маршрутизацию на стандартную очередь
celery_app.conf.task_routes = {
    "app.worker.tasks.*": {"queue": "celery"},  # Изменить на 'celery' вместо 'default'
}