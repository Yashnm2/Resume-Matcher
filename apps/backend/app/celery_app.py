"""Celery configuration for remote, headless scout workflows."""

from celery import Celery
from celery.schedules import crontab

from app.config import settings


celery_app = Celery(
    "resume_matcher", broker=settings.redis_url, backend=settings.redis_url
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.scout_timezone,
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_routes={
        "app.tasks.scan_all_sources": {"queue": "discovery"},
        "app.tasks.build_daily_queue": {"queue": "llm"},
        "app.tasks.prepare_selected_pack": {"queue": "llm"},
        "app.tasks.render_pack_pdfs": {"queue": "render"},
        "app.tasks.finalize_daily_run": {"queue": "llm"},
    },
    beat_schedule={
        "scan-public-job-sources-every-four-hours": {
            "task": "app.tasks.scan_all_sources",
            "schedule": 4 * 60 * 60,
        },
        "build-daily-application-queue": {
            "task": "app.tasks.build_daily_queue",
            "schedule": crontab(minute="*/15"),
        },
    },
)
