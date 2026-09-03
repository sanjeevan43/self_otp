import asyncio
import logging
from typing import Any

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.enums import MessageEventType, MessageStatus, OTPStatus, WebhookProcessingStatus
from app.models.messaging import Message, MessageEvent, WebhookEvent
from app.models.otp import OTPRequest
from app.services.meta_service import MetaService
from app.services.wallet_service import WalletService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _send_otp_async(
    otp_request_db_id: str,
    request_id: str,
    phone_number: str,
    otp_code: str,
    template_name: str,
    language_code: str,
    customer_id: str,
    cost_credits: float,
) -> None:
    """Async execution helper for Celery task."""
    async with AsyncSessionLocal() as session:
        try:
            success, wamid, error_msg = await MetaService.send_whatsapp_otp(
                phone_number, otp_code, template_name, language_code
            )

            stmt = select(OTPRequest).where(OTPRequest.id == otp_request_db_id)
            otp_record = (await session.execute(stmt)).scalar_one_or_none()

            # Create Message record
            msg = Message(
                customer_id=customer_id,
                otp_request_id=otp_request_db_id,
                phone_number=phone_number,
                provider="meta",
                provider_message_id=wamid,
                status=MessageStatus.SENT if success else MessageStatus.FAILED,
                error_message=error_msg if not success else None,
            )
            session.add(msg)

            if otp_record:
                if success:
                    otp_record.status = OTPStatus.SENT
                else:
                    otp_record.status = OTPStatus.FAILED
                    # Refund wallet on failure
                    await WalletService.refund_credits(
                        session=session,
                        customer_id=customer_id,
                        cost=cost_credits,
                        reference_type="otp_request_failure",
                        reference_id=request_id,
                        reason=error_msg or "Meta API delivery failed",
                    )

            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception(f"Error executing _send_otp_async for request {request_id}: {e}")


@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
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
) -> None:
    """Celery task to dispatch WhatsApp OTP message asynchronously."""
    try:
        asyncio.run(
            _send_otp_async(
                otp_request_db_id,
                request_id,
                phone_number,
                otp_code,
                template_name,
                language_code,
                customer_id,
                cost_credits,
            )
        )
    except Exception as exc:
        logger.error(f"Task send_whatsapp_otp_task failed: {exc}")
        raise self.retry(exc=exc)


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


@celery_app.task(bind=True, max_retries=3)
def process_meta_webhook_task(self: Any, event_id: str, wamid: str, status_str: str) -> None:
    """Celery task to process Meta delivery status webhooks asynchronously."""
    try:
        asyncio.run(_process_meta_webhook_async(event_id, wamid, status_str))
    except Exception as exc:
        logger.error(f"Task process_meta_webhook_task failed: {exc}")
        raise self.retry(exc=exc)
