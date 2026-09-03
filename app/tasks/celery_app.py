import logging
import time
from typing import Any

from celery import Celery
from celery.signals import task_failure, task_postrun, task_prerun, task_retry
from kombu import Exchange, Queue

from app.config import settings

logger = logging.getLogger("app.tasks.worker")

celery_app = Celery(
    "self_otp_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Kombu Queue & Exchange Definitions (TASK-095)
otp_exchange = Exchange("otp", type="direct")
webhook_exchange = Exchange("webhooks", type="direct")
dlq_exchange = Exchange("dead_letter", type="direct")

task_queues = (
    Queue("otp_messages", otp_exchange, routing_key="otp.send"),
    Queue("webhooks", webhook_exchange, routing_key="webhook.process"),
    Queue("dead_letter", dlq_exchange, routing_key="dlq"),
)

task_routes = {
    "app.tasks.otp_tasks.send_whatsapp_otp_task": {"queue": "otp_messages"},
    "app.tasks.otp_tasks.process_meta_webhook_task": {"queue": "webhooks"},
    "app.tasks.otp_tasks.handle_dead_letter_task": {"queue": "dead_letter"},
}

celery_app.conf.update(
    task_queues=task_queues,
    task_routes=task_routes,
    task_default_queue="otp_messages",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_prefetch_multiplier=1,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    broker_transport_options={"visibility_timeout": 3600},
)

# TASK-102: Worker Logging & Signals
_task_start_times: dict[str, float] = {}


@task_prerun.connect
def task_prerun_handler(task_id: str, task: Any, args: tuple[Any, ...], kwargs: dict[str, Any], **_: Any) -> None:
    _task_start_times[task_id] = time.time()
    # Mask PII in kwargs if present
    safe_kwargs = dict(kwargs)
    if "phone_number" in safe_kwargs and isinstance(safe_kwargs["phone_number"], str):
        p = safe_kwargs["phone_number"]
        safe_kwargs["phone_number"] = p[:4] + "***" + p[-4:] if len(p) >= 8 else "***"
    if "otp_code" in safe_kwargs:
        safe_kwargs["otp_code"] = "******"
    
    logger.info(
        f"[Worker] Task START - ID: {task_id} | Name: {task.name} | Args: {args} | Kwargs: {safe_kwargs}"
    )


@task_postrun.connect
def task_postrun_handler(
    task_id: str, task: Any, retval: Any, state: str, **_: Any
) -> None:
    start_time = _task_start_times.pop(task_id, time.time())
    latency_ms = round((time.time() - start_time) * 1000, 2)
    logger.info(
        f"[Worker] Task END - ID: {task_id} | Name: {task.name} | State: {state} | Latency: {latency_ms}ms"
    )


@task_retry.connect
def task_retry_handler(
    request: Any, reason: Any, einfo: Any, **_: Any
) -> None:
    logger.warning(
        f"[Worker] Task RETRY - ID: {request.id} | Name: {request.name} | Attempt: {request.retries} | Reason: {reason}"
    )


@task_failure.connect
def task_failure_handler(
    task_id: str, exception: Exception, traceback: Any, einfo: Any, **_: Any
) -> None:
    logger.error(
        f"[Worker] Task FAILURE - ID: {task_id} | Exception: {exception} | Traceback: {einfo}"
    )
