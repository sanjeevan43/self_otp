from datetime import timedelta
from typing import Annotated, Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_api_key_context
from app.config import settings
from app.core.hashing import hash_otp_code, hash_phone_number, mask_phone_number
from app.database import get_db
from app.models.api_key import APIKey
from app.models.base import utc_now
from app.models.application import Application
from app.models.customer import Customer
from app.models.enums import OTPStatus
from app.models.otp import OTPRequest
from app.redis import get_redis
from app.schemas.otp import (
    OTPResendRequest,
    OTPResendResponse,
    OTPSendRequest,
    OTPSendResponse,
    OTPStatusResponse,
    OTPVerifyRequest,
    OTPVerifyResponse,
)
from app.core.idempotency import get_idempotent_response, save_idempotent_response
from app.core.rate_limit import (
    is_customer_blocked,
    is_phone_blocked,
    is_rate_limited,
)
from app.services.meta_service import MetaService
from app.services.otp_service import OTPService
from app.services.wallet_service import WalletService
from app.tasks.otp_tasks import send_whatsapp_otp_task

router = APIRouter(prefix="/otp", tags=["OTP Operations"])


@router.post("/send", response_model=OTPSendResponse, status_code=status.HTTP_202_ACCEPTED)
async def send_otp(
    request: OTPSendRequest,
    req_obj: Request,
    api_auth: Annotated[tuple[APIKey, Application, Customer], Depends(get_api_key_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: aioredis.Redis | None = Depends(get_redis),
) -> dict[str, str | dict[str, Any]]:
    """
    Triggers OTP delivery to the customer's WhatsApp phone number.
    Deducts wallet balance atomically and queues async Meta delivery.
    Enforces multi-tier rate limits, phone/customer blocking, and idempotency.
    """
    api_key, application, customer = api_auth
    phone_hash = hash_phone_number(request.phone_number)
    masked_phone = mask_phone_number(request.phone_number)
    client_ip = req_obj.client.host if req_obj.client else "127.0.0.1"
    idempotency_key = req_obj.headers.get("idempotency-key")

    # 1. Customer Abuse Protection (TASK-080)
    customer_blocked = await is_customer_blocked(redis, customer.id)
    if customer_blocked or customer.status.value != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "CUSTOMER_BLOCKED",
                "message": "Customer account is suspended or blocked due to policy violations.",
            },
        )

    # 2. Temporary Phone Blocking (TASK-079)
    phone_blocked = await is_phone_blocked(redis, phone_hash)
    if phone_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PHONE_BLOCKED",
                "message": "This phone number is temporarily blocked due to excessive failed attempts or abuse.",
            },
        )

    # 3. Duplicate Request / Idempotency Check (TASK-077)
    if idempotency_key:
        cached = await get_idempotent_response(
            redis=redis,
            session=db,
            application_id=application.id,
            idempotency_key=idempotency_key,
            endpoint="/v1/otp/send",
        )
        if cached:
            return cached

    # 4. IP Rate Limiting (TASK-072) - Max 10 per minute
    ip_limited, _ = await is_rate_limited(
        redis=redis,
        key=f"ip:{client_ip}:otp:send",
        max_requests=10,
        window_seconds=60,
    )
    if ip_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "IP_RATE_LIMITED",
                "message": "Too many requests from this IP address. Please slow down.",
            },
        )

    # 5. Phone-Number Rate Limiting (TASK-073) - Max 3 per 10 minutes
    phone_limited, _ = await is_rate_limited(
        redis=redis,
        key=f"phone:{phone_hash}:otp:send",
        max_requests=3,
        window_seconds=600,
    )
    if phone_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "PHONE_RATE_LIMITED",
                "message": "Too many OTP requests for this phone number. Please wait.",
            },
        )

    # 6. Customer Rate Limiting (TASK-074) - Max 60 per minute
    cust_limited, _ = await is_rate_limited(
        redis=redis,
        key=f"customer:{customer.id}:otp:send",
        max_requests=60,
        window_seconds=60,
    )
    if cust_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "CUSTOMER_RATE_LIMITED",
                "message": "Customer rate limit exceeded.",
            },
        )

    # 7. API-Key Rate Limiting (TASK-075) - Rate Limit RPS
    key_limited, _ = await is_rate_limited(
        redis=redis,
        key=f"api_key:{api_key.id}:otp:send",
        max_requests=getattr(api_key, "rate_limit_rps", settings.DEFAULT_API_KEY_RATE_LIMIT_RPS),
        window_seconds=1,
    )
    if key_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "API_KEY_RATE_LIMITED",
                "message": "API key rate limit exceeded.",
            },
        )

    # 8. Enforce 60-second cooldown per target phone number (TASK-076)
    in_cooldown = await OTPService.check_phone_cooldown(redis, phone_hash)
    if in_cooldown:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "COOLDOWN_ACTIVE",
                "message": "An OTP was recently requested for this phone number. Please wait 60 seconds.",
            },
        )

    # 2. Determine OTP code and request_id
    otp_code = request.otp if request.otp else OTPService.generate_otp_digits(6)
    request_id = OTPService.generate_request_id()
    cost = settings.OTP_CREDIT_COST
    expires_at = utc_now() + timedelta(seconds=request.ttl_seconds)

    # 3. Create OTPRequest record first
    otp_record = OTPRequest(
        customer_id=customer.id,
        application_id=application.id,
        api_key_id=api_key.id,
        request_id=request_id,
        phone_number=request.phone_number,
        otp_hash=hash_otp_code(otp_code),
        status=OTPStatus.CREATED,
        expires_at=expires_at,
        attempts=0,
        max_attempts=settings.OTP_MAX_VERIFY_ATTEMPTS,
    )
    db.add(otp_record)
    await db.flush()

    # 4. Atomic Wallet Debit (Throws HTTP 402 if balance insufficient)
    await WalletService.deduct_credits_atomic(
        session=db,
        customer_id=customer.id,
        cost=cost,
        reference_type="otp_request",
        reference_id=request_id,
    )

    # 5. Store OTP hash in Redis/Memory
    await OTPService.store_otp(
        redis=redis,
        phone_hash=phone_hash,
        otp_code=otp_code,
        request_id=request_id,
        application_id=application.id,
        ttl_seconds=request.ttl_seconds,
    )

    # 6. Set 60-second phone cooldown
    await OTPService.set_phone_cooldown(redis, phone_hash)

    # 7. Dispatch to Meta WhatsApp Cloud API asynchronously via Celery (TASK-097)
    try:
        send_whatsapp_otp_task.apply_async(
            kwargs={
                "otp_request_db_id": otp_record.id,
                "request_id": request_id,
                "phone_number": request.phone_number,
                "otp_code": otp_code,
                "template_name": request.template_name,
                "language_code": request.language_code,
                "customer_id": customer.id,
                "cost_credits": cost,
            },
            queue="otp_messages",
        )
    except Exception:
        # Fallback for dev mode when Celery broker is not running
        success, _wamid, error_msg = await MetaService.send_whatsapp_otp(
            request.phone_number, otp_code, request.template_name, request.language_code
        )
        if success:
            otp_record.status = OTPStatus.SENT
        else:
            otp_record.status = OTPStatus.FAILED
            await WalletService.refund_credits(
                session=db,
                customer_id=customer.id,
                cost=cost,
                reference_type="otp_request_failure",
                reference_id=request_id,
                reason=error_msg or "Delivery failed",
            )

    await db.commit()

    response_data = {
        "status": "success",
        "data": {
            "request_id": request_id,
            "phone_number": masked_phone,
            "delivery_status": otp_record.status.value,
            "expires_at": expires_at.isoformat(),
            "cost_credits": cost,
        },
    }

    if idempotency_key:
        await save_idempotent_response(
            redis=redis,
            session=db,
            application_id=application.id,
            customer_id=customer.id,
            idempotency_key=idempotency_key,
            endpoint="/v1/otp/send",
            request_body=request.model_dump(),
            response_body=response_data,
        )
        await db.commit()

    return response_data


@router.post("/verify", response_model=OTPVerifyResponse, status_code=status.HTTP_200_OK)
async def verify_otp(
    request: OTPVerifyRequest,
    req_obj: Request,
    api_auth: Annotated[tuple[APIKey, Application, Customer], Depends(get_api_key_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: aioredis.Redis | None = Depends(get_redis),
) -> dict[str, str | dict[str, Any]]:
    """Verifies a submitted OTP code against stored hash in constant-time."""
    client_ip = req_obj.client.host if req_obj.client else None
    user_agent = req_obj.headers.get("user-agent")

    result = await OTPService.verify_otp(
        session=db,
        redis=redis,
        phone_number=request.phone_number,
        submitted_code=request.code,
        application_id=application.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    await db.commit()
    return {
        "status": "success",
        "data": result,
    }


@router.post("/resend", response_model=OTPResendResponse, status_code=status.HTTP_202_ACCEPTED)
async def resend_otp(
    request: OTPResendRequest,
    api_auth: Annotated[tuple[APIKey, Application, Customer], Depends(get_api_key_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: aioredis.Redis | None = Depends(get_redis),
) -> dict[str, str | dict[str, Any]]:
    """
    Resends OTP for an active OTP request_id. Enforces 60-second cooldown per phone number.
    """
    api_key, application, customer = api_auth

    # 1. Fetch OTP Request
    from sqlalchemy import select

    stmt = select(OTPRequest).where(
        OTPRequest.request_id == request.request_id,
        OTPRequest.application_id == application.id,
    )
    otp_record = (await db.execute(stmt)).scalar_one_or_none()

    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "OTP_NOT_FOUND",
                "message": f"OTP request with ID '{request.request_id}' was not found.",
            },
        )

    if otp_record.status == OTPStatus.VERIFIED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "ALREADY_VERIFIED",
                "message": "This OTP has already been successfully verified.",
            },
        )

    now = utc_now()
    if now > otp_record.expires_at:
        otp_record.status = OTPStatus.EXPIRED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "OTP_EXPIRED",
                "message": "The OTP request has expired. Please request a new OTP.",
            },
        )

    # 2. Check phone cooldown
    phone_hash = hash_phone_number(otp_record.phone_number)
    in_cooldown = await OTPService.check_phone_cooldown(redis, phone_hash)
    if in_cooldown:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "COOLDOWN_ACTIVE",
                "message": "An OTP was recently sent to this phone number. Please wait 60 seconds.",
            },
        )

    # 3. Generate fresh OTP code and extend TTL
    new_otp_code = OTPService.generate_otp_digits(6)
    otp_record.otp_hash = hash_otp_code(new_otp_code)
    cost = settings.OTP_CREDIT_COST

    # Deduct wallet credits for resend
    await WalletService.deduct_credits_atomic(
        session=db,
        customer_id=customer.id,
        cost=cost,
        reference_type="otp_resend",
        reference_id=otp_record.request_id,
    )

    # 4. Store in Redis/Memory
    ttl_seconds = int((otp_record.expires_at - now).total_seconds())
    if ttl_seconds < 60:
        ttl_seconds = 300
        otp_record.expires_at = now + timedelta(seconds=300)

    await OTPService.store_otp(
        redis=redis,
        phone_hash=phone_hash,
        otp_code=new_otp_code,
        request_id=otp_record.request_id,
        application_id=application.id,
        ttl_seconds=ttl_seconds,
    )
    await OTPService.set_phone_cooldown(redis, phone_hash)

    # 5. Dispatch async Meta message
    try:
        send_whatsapp_otp_task.apply_async(
            kwargs={
                "otp_request_db_id": otp_record.id,
                "request_id": otp_record.request_id,
                "phone_number": otp_record.phone_number,
                "otp_code": new_otp_code,
                "template_name": "otp_auth_v1",
                "language_code": "en_US",
                "customer_id": customer.id,
                "cost_credits": cost,
            },
            queue="otp_messages",
        )
    except Exception:
        success, _wamid, _err = await MetaService.send_whatsapp_otp(
            otp_record.phone_number, new_otp_code, "otp_auth_v1", "en_US"
        )
        if success:
            otp_record.status = OTPStatus.SENT

    await db.commit()

    return {
        "status": "success",
        "data": {
            "request_id": otp_record.request_id,
            "phone_number": mask_phone_number(otp_record.phone_number),
            "delivery_status": otp_record.status.value,
            "expires_at": otp_record.expires_at.isoformat(),
            "cost_credits": cost,
            "resend_count": 1,
        },
    }


@router.get("/{request_id}", response_model=OTPStatusResponse, status_code=status.HTTP_200_OK)
async def get_otp_status(
    request_id: str,
    api_auth: Annotated[tuple[APIKey, Application, Customer], Depends(get_api_key_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str | dict[str, Any]]:
    """Retrieves OTP request status, attempt count, and expiration timing."""
    _api_key, application, customer = api_auth

    result = await OTPService.get_otp_status(
        session=db,
        request_id=request_id,
        application_id=application.id,
    )
    await db.commit()
    return {
        "status": "success",
        "data": result,
    }

