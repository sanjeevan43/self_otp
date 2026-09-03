from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, status

from app.redis import get_redis
from app.services.worker_monitoring import WorkerMonitoringService

router = APIRouter(prefix="/monitoring", tags=["Monitoring & Operations"])


@router.get("/worker", status_code=status.HTTP_200_OK)
async def get_worker_monitoring_status(
    redis: aioredis.Redis | None = Depends(get_redis),
) -> dict[str, Any]:
    """
    Worker Monitoring Endpoint (TASK-103).
    Returns health status of Celery workers and message queue depths for:
    - otp_messages
    - webhooks
    - dead_letter
    """
    worker_health = await WorkerMonitoringService.get_worker_status()
    queue_depths = await WorkerMonitoringService.get_queue_depths(redis)

    return {
        "status": "success",
        "data": {
            "worker_status": worker_health["status"],
            "active_workers": worker_health["active_workers_count"],
            "workers": worker_health["workers"],
            "queues": queue_depths,
        },
    }
