"""
Celery configuration for the audio worker.

This worker processes audio analysis tasks from the 'audio' queue.

AGPL-3.0 License - See LICENSE file for details.
"""
import os

import structlog
from celery import Celery
from celery.signals import task_prerun, task_postrun, task_failure

from app.core.logging import setup_logging, init_canonical, emit_canonical

setup_logging()

# Get Redis URL from env or default to localhost
BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "dansbart_audio_worker",
    broker=BROKER_URL,
    backend=BROKER_URL,
    include=["app.workers.tasks_audio"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Stockholm",
    enable_utc=True,

    # Task routing - all tasks go to audio queue
    task_routes={
        'app.workers.tasks_audio.analyze_track_task': {'queue': 'audio'},
    },

    # Default queue
    task_default_queue='audio',
)


@task_prerun.connect
def on_task_start(sender=None, task_id=None, task=None, args=None,
                  kwargs=None, **kw):
    headers = getattr(task.request, "headers", None) or {}
    trace_id = headers.get("trace_id") or task_id
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        trace_id=trace_id, task_id=task_id, task_name=sender.name
    )
    init_canonical(sender.name, task_id, trace_id)


@task_postrun.connect
def on_task_end(sender=None, task_id=None, task=None, retval=None,
                state=None, **kw):
    emit_canonical(state)
    structlog.contextvars.clear_contextvars()


@task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None,
                    traceback=None, **kw):
    log = structlog.get_logger()
    log.error("task.failed", exception=str(exception), exc_info=True)
