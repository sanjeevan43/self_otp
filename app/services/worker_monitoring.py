import logging
from typing import Any

import redis.asyncio as aioredis

from app.tasks.celery_app import celery_app

logger = logging.getLogger("app.services.worker_monitoring")


class WorkerMonitoringService:
    """Service to monitor Celery workers and inspect queue metrics (TASK-103)."""

    @staticmethod
    async def get_worker_status() -> dict[str, Any]:
        """Inspect Celery workers status, active tasks, and registered tasks."""
        try:
            inspect = celery_app.control.inspect(timeout=1.0)
            ping_res = inspect.ping() if inspect else None
            active_tasks = inspect.active() if inspect else None

            workers_info = []
            if ping_res:
                for worker_name, status in ping_res.items():
                    w_active = len(active_tasks.get(worker_name, [])) if active_tasks else 0
                    workers_info.append(
                        {
                            "name": worker_name,
                            "status": status.get("ok", "online") if isinstance(status, dict) else "online",
                            "active_tasks": w_active,
                        }
                    )

            is_healthy = len(workers_info) > 0 or ping_res is not None

            return {
                "status": "healthy" if is_healthy else "degraded",
                "active_workers_count": len(workers_info),
                "workers": workers_info,
            }
        except Exception as e:
            logger.warning(f"Unable to inspect Celery worker status: {e}")
            return {
                "status": "offline_or_unreachable",
                "active_workers_count": 0,
                "workers": [],
                "error": str(e),
            }

    @staticmethod
    async def get_queue_depths(redis_client: aioredis.Redis | None = None) -> dict[str, int]:
        """Inspect message queue lengths in Redis for otp_messages, webhooks, and dead_letter queues."""
        queues = {"otp_messages": 0, "webhooks": 0, "dead_letter": 0}
        if not redis_client:
            return queues

        for queue_name in queues:
            try:
                length = await redis_client.llen(queue_name)
                queues[queue_name] = int(length)
            except Exception as e:
                logger.warning(f"Error checking depth for queue '{queue_name}': {e}")
                queues[queue_name] = 0

        return queues
