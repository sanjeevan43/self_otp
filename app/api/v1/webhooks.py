import hashlib
import hmac
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.enums import WebhookProcessingStatus
from app.models.messaging import WebhookEvent
from app.tasks.otp_tasks import process_meta_webhook_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.get("/meta")
async def verify_meta_webhook(request: Request) -> Response:
    """Meta WhatsApp Webhook verification challenge handler."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.META_WEBHOOK_VERIFY_TOKEN:
        logger.info("Meta webhook verification challenge succeeded.")
        return Response(content=challenge, media_type="text/plain", status_code=200)

    logger.warning("Meta webhook verification challenge failed: token mismatch.")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="Verification token mismatch."
    )


@router.post("/meta")
async def process_meta_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_hub_signature_256: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
) -> dict[str, str]:
    """
    Ingests inbound Meta WhatsApp delivery and read status webhooks.
    Validates HMAC-SHA256 signature, records event, and dispatches async task.
    """
    body_bytes = await request.body()

    # 1. Verify X-Hub-Signature-256 signature if app secret configured and signature present
    if (
        settings.META_APP_SECRET
        and not settings.META_APP_SECRET.startswith("mock_")
        and x_hub_signature_256
    ):
        expected_sig = (
            "sha256="
            + hmac.new(
                settings.META_APP_SECRET.encode("utf-8"),
                body_bytes,
                hashlib.sha256,
            ).hexdigest()
        )

        if not hmac.compare_digest(x_hub_signature_256, expected_sig):
            logger.error("Meta webhook signature mismatch!")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature."
            )

    # 2. Parse payload
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ignored"}

    entries = payload.get("entry", [])
    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            statuses = value.get("statuses", [])
            for status_item in statuses:
                wamid = status_item.get("id")
                status_str = status_item.get("status")

                if wamid and status_str:
                    event_idempotency_key = f"{wamid}_{status_str}"
                    webhook_event = WebhookEvent(
                        provider="meta",
                        event_type=status_str,
                        external_event_id=event_idempotency_key,
                        payload=status_item,
                        processing_status=WebhookProcessingStatus.RECEIVED,
                    )
                    db.add(webhook_event)
                    
                    try:
                        from sqlalchemy.exc import IntegrityError
                        await db.flush()
                        
                        # Dispatch async Celery task only if successfully saved
                        try:
                            process_meta_webhook_task.delay(
                                event_id=webhook_event.id,
                                wamid=wamid,
                                status_str=status_str,
                            )
                        except Exception:
                            pass
                    except IntegrityError:
                        await db.rollback()
                        logger.info(f"Duplicate webhook event ignored: {event_idempotency_key}")
                        continue

    await db.commit()
    return {"status": "ok"}

