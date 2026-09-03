import asyncio
import logging
import random
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.enums import MessageEventType, MessageStatus, OTPStatus, WebhookProcessingStatus
from app.models.messaging import Message, MessageEvent, WebhookEvent
from app.models.otp import OTPRequest
from app.services.providers.base import SendMessageResult
from app.services.wallet_service import WalletService
from app.services.whatsapp_service import whatsapp_service
from app.tasks.celery_app import celery_app

logger = logging.getLogger("app.tasks.otp_tasks")


class TemporaryDeliveryError(Exception):
    """Exception raised when message delivery fails with a temporary, retryable error."""

    pass


class PermanentDeliveryError(Exception):
    """Exception raised when message delivery fails with a permanent, non-retryable error."""

    pass


async def _send_otp_async(
    otp_request_db_id: str,
    request_id: str,
    phone_number: str,
    otp_code: str,
    template_name: str,
    language_code: str,
    customer_id: str,
    cost_credits: float,
) -> SendMessageResult:
    """Async execution helper for Celery task using decoupled WhatsAppService."""
    async with AsyncSessionLocal() as session:
        try:
            res = await whatsapp_service.send_otp(
                phone_number=phone_number,
                otp_code=otp_code,
                template_name=template_name,
                language_code=language_code,
            )

            stmt = select(OTPRequest).where(OTPRequest.id == otp_request_db_id)
            otp_record = (await session.execute(stmt)).scalar_one_or_none()

            # Create Message record storing provider_message_id (wamid) (TASK-099)
            msg = Message(
                customer_id=customer_id,
                otp_request_id=otp_request_db_id,
                phone_number=phone_number,
                provider="meta",
                provider_message_id=res.provider_message_id,
                status=MessageStatus.SENT if res.success else MessageStatus.FAILED,
                error_message=res.error_message if not res.success else None,
            )
            session.add(msg)
            await session.flush()

            # Create MessageEvent record (TASK-099)
            msg_event = MessageEvent(
                message_id=msg.id,
                event_type=MessageEventType.SENT if res.success else MessageEventType.FAILED,
                provider_message_id=res.provider_message_id,
            )
            session.add(msg_event)

            if otp_record:
                if res.success:
                    otp_record.status = OTPStatus.SENT
                else:
                    # If permanent failure, update status to FAILED and refund immediately
                    if not res.is_temporary_error:
                        otp_record.status = OTPStatus.FAILED
                        await WalletService.refund_credits(
                            session=session,
                            customer_id=customer_id,
                            cost=cost_credits,
                            reference_type="otp_request_failure",
                            reference_id=request_id,
                            reason=res.error_message or "Meta API permanent failure",
                        )

            await session.commit()
            return res

        except Exception as e:
            await session.rollback()
            logger.exception(f"Error executing _send_otp_async for request {request_id}: {e}")
            raise


@celery_app.task(
    bind=True,
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    name="app.tasks.otp_tasks.send_whatsapp_otp_task",
)
def send_whatsapp_otp_task(
    self: Any,
    otp_request_db_id: str,
    request_id: str,
    phone_number: str,
    otp_code: str,
    template_name: str,
    language_code: str,
    customer_id: str,
    cost_credits: float,
) -> dict[str, Any]:
    """
    Celery task to dispatch WhatsApp OTP message asynchronously.
    Enforces exponential backoff with jitter on temporary errors (TASK-100).
    Routes to dead-letter queue on max retries or catastrophic failures (TASK-101).
    """
    try:
        res = asyncio.run(
            _send_otp_async(
                otp_request_db_id=otp_request_db_id,
                request_id=request_id,
                phone_number=phone_number,
                otp_code=otp_code,
                template_name=template_name,
                language_code=language_code,
                customer_id=customer_id,
                cost_credits=cost_credits,
            )
        )

        if res.success:
            return {
                "status": "success",
                "request_id": request_id,
                "provider_message_id": res.provider_message_id,
            }

        # Handle failure cases
        if res.is_temporary_error:
            raise TemporaryDeliveryError(res.error_message or "Temporary network/rate limit error")
        else:
            raise PermanentDeliveryError(res.error_message or "Permanent Meta delivery rejection")

    except TemporaryDeliveryError as exc:
        if self.request.retries >= self.max_retries:
            logger.error(
                f"[DLQ] Task {self.request.id} reached max retries ({self.max_retries}). Routing to dead-letter queue."
            )
            # Trigger Dead Letter Queue task
            handle_dead_letter_task.delay(
                {
                    "task_id": self.request.id,
                    "otp_request_db_id": otp_request_db_id,
                    "request_id": request_id,
                    "phone_number": phone_number,
                    "customer_id": customer_id,
                    "cost_credits": cost_credits,
                    "reason": f"Max retries exceeded: {str(exc)}",
                    "retries": self.request.retries,
                }
            )
            # Execute refund if not done already
            asyncio.run(_mark_otp_failed_and_refund(otp_request_db_id, request_id, customer_id, cost_credits, str(exc)))
            return {"status": "failed", "dead_letter": True, "error": str(exc)}
        
        # Calculate exponential backoff with jitter (TASK-100)
        backoff_seconds = (2 ** self.request.retries) + random.uniform(0.5, 2.0)
        logger.warning(
            f"Temporary error sending OTP (request {request_id}), retrying in {backoff_seconds:.2f}s (Attempt {self.request.retries + 1}/{self.max_retries}): {exc}"
        )
        raise self.retry(exc=exc, countdown=backoff_seconds)

    except PermanentDeliveryError as exc:
        logger.error(f"Permanent delivery failure for request {request_id}: {exc}")
        return {"status": "failed", "permanent": True, "error": str(exc)}

    except Exception as exc:
        logger.exception(f"Unexpected error in send_whatsapp_otp_task for request {request_id}: {exc}")
        if self.request.retries >= self.max_retries:
            handle_dead_letter_task.delay(
                {
                    "task_id": self.request.id,
                    "otp_request_db_id": otp_request_db_id,
                    "request_id": request_id,
                    "phone_number": phone_number,
                    "customer_id": customer_id,
                    "cost_credits": cost_credits,
                    "reason": f"Unexpected failure: {str(exc)}",
                    "retries": self.request.retries,
                }
            )
            asyncio.run(_mark_otp_failed_and_refund(otp_request_db_id, request_id, customer_id, cost_credits, str(exc)))
            return {"status": "failed", "dead_letter": True, "error": str(exc)}
        
        backoff_seconds = (2 ** self.request.retries) + random.uniform(0.5, 2.0)
        raise self.retry(exc=exc, countdown=backoff_seconds)


async def _mark_otp_failed_and_refund(
    otp_request_db_id: str, request_id: str, customer_id: str, cost_credits: float, reason: str
) -> None:
    """Marks OTP request as FAILED and executes wallet refund if applicable."""
    async with AsyncSessionLocal() as session:
        try:
            stmt = select(OTPRequest).where(OTPRequest.id == otp_request_db_id)
            otp_record = (await session.execute(stmt)).scalar_one_or_none()
            if otp_record and otp_record.status != OTPStatus.FAILED:
                otp_record.status = OTPStatus.FAILED
                await WalletService.refund_credits(
                    session=session,
                    customer_id=customer_id,
                    cost=cost_credits,
                    reference_type="otp_request_failure",
                    reference_id=request_id,
                    reason=reason,
                )
                await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception(f"Error marking OTP request failed for {request_id}: {e}")


@celery_app.task(
    name="app.tasks.otp_tasks.handle_dead_letter_task",
    bind=True,
)
def handle_dead_letter_task(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Task to record and log failed/dead-letter messages (TASK-101).
    """
    logger.error(
        f"[DeadLetterQueue] Failed task recorded: TaskID={payload.get('task_id')} | RequestID={payload.get('request_id')} | CustomerID={payload.get('customer_id')} | Reason={payload.get('reason')}"
    )
    return {"status": "dead_letter_recorded", "payload": payload}


def reprocess_dead_letter_messages(dead_letter_payloads: list[dict[str, Any]]) -> int:
    """
    Helper function to re-enqueue messages from dead-letter queue (TASK-101).
    """
    reprocessed_count = 0
    for item in dead_letter_payloads:
        try:
            send_whatsapp_otp_task.apply_async(
                kwargs={
                    "otp_request_db_id": item.get("otp_request_db_id"),
                    "request_id": item.get("request_id"),
                    "phone_number": item.get("phone_number"),
                    "otp_code": item.get("otp_code", "000000"),
                    "template_name": item.get("template_name", "otp_auth_v1"),
                    "language_code": item.get("language_code", "en_US"),
                    "customer_id": item.get("customer_id"),
                    "cost_credits": item.get("cost_credits", 1.0),
                },
                queue="otp_messages",
            )
            reprocessed_count += 1
        except Exception as e:
            logger.error(f"Failed to reprocess dead-letter message {item.get('request_id')}: {e}")
    return reprocessed_count


async def _process_meta_webhook_async(event_id: str, wamid: str, status_str: str) -> None:
    """Async processing of Meta status callbacks."""
    async with AsyncSessionLocal() as session:
        try:
            # Update Message record
            msg_stmt = select(Message).where(Message.provider_message_id == wamid)
            msg = (await session.execute(msg_stmt)).scalar_one_or_none()

            status_enum_map = {
                "sent": MessageStatus.SENT,
                "delivered": MessageStatus.DELIVERED,
                "read": MessageStatus.READ,
                "failed": MessageStatus.FAILED,
            }
            new_msg_status = status_enum_map.get(status_str.lower(), MessageStatus.SENT)

            if msg:
                msg.status = new_msg_status
                # Create MessageEvent record
                evt_type_map = {
                    "sent": MessageEventType.SENT,
                    "delivered": MessageEventType.DELIVERED,
                    "read": MessageEventType.READ,
                    "failed": MessageEventType.FAILED,
                }
                event_type = evt_type_map.get(status_str.lower(), MessageEventType.SENT)
                msg_event = MessageEvent(
                    message_id=msg.id,
                    event_type=event_type,
                    provider_message_id=wamid,
                )
                session.add(msg_event)

                # Update linked OTPRequest status
                if msg.otp_request_id:
                    otp_stmt = select(OTPRequest).where(OTPRequest.id == msg.otp_request_id)
                    otp_record = (await session.execute(otp_stmt)).scalar_one_or_none()
                    if otp_record and otp_record.status != OTPStatus.VERIFIED:
                        otp_status_map = {
                            "sent": OTPStatus.SENT,
                            "delivered": OTPStatus.DELIVERED,
                            "failed": OTPStatus.FAILED,
                        }
                        if status_str.lower() in otp_status_map:
                            otp_record.status = otp_status_map[status_str.lower()]

            # Mark WebhookEvent as PROCESSED
            w_stmt = select(WebhookEvent).where(WebhookEvent.id == event_id)
            webhook_rec = (await session.execute(w_stmt)).scalar_one_or_none()
            if webhook_rec:
                webhook_rec.processing_status = WebhookProcessingStatus.PROCESSED

            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception(f"Error processing webhook event {event_id}: {e}")


@celery_app.task(
    name="app.tasks.otp_tasks.process_meta_webhook_task",
    bind=True,
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
)
def process_meta_webhook_task(self: Any, event_id: str, wamid: str, status_str: str) -> None:
    """Celery task to process Meta delivery status webhooks asynchronously."""
    try:
        asyncio.run(_process_meta_webhook_async(event_id, wamid, status_str))
    except Exception as exc:
        logger.error(f"Task process_meta_webhook_task failed: {exc}")
        backoff_seconds = (2 ** self.request.retries) + random.uniform(0.5, 2.0)
        raise self.retry(exc=exc, countdown=backoff_seconds)
