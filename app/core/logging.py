"""Structured logging configuration with canonical log support."""
import logging
import sys
import time
from contextvars import ContextVar

import structlog

_canonical_fields: ContextVar[dict | None] = ContextVar(
    "canonical_fields", default=None
)


def setup_logging():
    """Configure structlog for JSON output with canonical logging support."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Redirect stdlib logging through structlog
    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=logging.INFO
    )


def canonical_bind(**kwargs):
    """Add fields to the canonical log for the current task."""
    fields = _canonical_fields.get()
    if fields is not None:
        fields.update(kwargs)


def init_canonical(task_name, task_id, trace_id):
    """Initialize canonical log fields for a new task."""
    _canonical_fields.set({
        "task_name": task_name,
        "task_id": task_id,
        "trace_id": trace_id,
        "start_time": time.monotonic(),
    })


def emit_canonical(status):
    """Emit the canonical log line for the current task and clear state."""
    fields = _canonical_fields.get()
    if fields is None:
        return
    log = structlog.get_logger()
    start = fields.pop("start_time", None)
    if start is not None:
        fields["duration_ms"] = int((time.monotonic() - start) * 1000)
    log.info("task.completed", status=status, **fields)
    _canonical_fields.set(None)


def get_canonical_fields():
    """Return current canonical fields (or empty dict)."""
    return _canonical_fields.get() or {}
