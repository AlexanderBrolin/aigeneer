"""Celery application and Beat schedule configuration."""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "ops-agent",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "run-all-checks": {
            "task": "app.scheduler.tasks.run_all_checks",
            "schedule": settings.check_interval_minutes * 60,
        },
    },
)
