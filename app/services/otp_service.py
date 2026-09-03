import json
import logging
import secrets
import time
from typing import Any

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.hashing import hash_otp_code, hash_phone_number, mask_phone_number, verify_otp_code
from app.models.base import utc_now
from app.models.enums import OTPStatus, OTPVerificationResult
from app.models.otp import OTPRequest, OTPVerification

logger = logging.getLogger(__name__)

# Fallback in-memory OTP cache when Redis is disabled/unavailable
_in_memory_otp_store: dict[str, dict[str, Any]] = {}
_in_memory_cooldown_store: dict[str, float] = {}


class OTPService:
    @staticmethod
    def generate_otp_digits(length: int = 6) -> str:
        """Generates a cryptographically secure random numeric OTP."""
        digits = "0123456789"
        return "".join(secrets.choice(digits) for _ in range(length))

    @staticmethod
    def generate_request_id() -> str:
        """Generates a unique request_id reference string."""
        return f"req_{secrets.token_hex(12)}"

    @staticmethod
    async def check_phone_cooldown(redis: aioredis.Redis | None, phone_hash: str) -> bool:
        """Enforces a 60-second cooldown per target phone number."""
        key = f"otp:cooldown:{phone_hash}"
        now = time.time()

        if redis is not None:
            try:
                exists = await redis.get(key)
                return bool(exists)
            except Exception:
                pass

        last_time = _in_memory_cooldown_store.get(phone_hash, 0.0)
        return now - last_time < settings.OTP_COOLDOWN_SECONDS

    @staticmethod
    async def set_phone_cooldown(redis: aioredis.Redis | None, phone_hash: str) -> None:
        """Sets phone cooldown timer."""
        key = f"otp:cooldown:{phone_hash}"
        now = time.time()

        if redis is not None:
            try:
                await redis.set(key, "1", ex=settings.OTP_COOLDOWN_SECONDS)
                return
            except Exception:
                pass

        _in_memory_cooldown_store[phone_hash] = now

    @staticmethod
    async def store_otp(
        redis: aioredis.Redis | None,
        phone_hash: str,
        otp_code: str,
        request_id: str,
        ttl_seconds: int,
    ) -> None:
        """Hashes OTP code and stores in Redis/Memory with expiration TTL."""
        key = f"otp:store:{phone_hash}"
        hashed_otp = hash_otp_code(otp_code)
        data = {
            "otp_hash": hashed_otp,
            "request_id": request_id,
            "attempts": 0,
            "created_at": time.time(),
        }

        if redis is not None:
            try:
                await redis.set(key, json.dumps(data), ex=ttl_seconds)
                return
            except Exception:
                pass

        data["expires_at"] = time.time() + ttl_seconds
        _in_memory_otp_store[key] = data

    @staticmethod
    async def verify_otp(
        session: AsyncSession,
        redis: aioredis.Redis | None,
        phone_number: str,
        submitted_code: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """
        Verifies submitted OTP code against stored hash.
        Handles attempt counter, logs OTPVerification attempt, and invalidates on max attempts.
        """
        phone_hash = hash_phone_number(phone_number)
        key = f"otp:store:{phone_hash}"

        stored_data = None

        if redis is not None:
            try:
                raw_json = await redis.get(key)
                if raw_json:
                    stored_data = json.loads(raw_json)
            except Exception:
                pass

        if stored_data is None:
            data = _in_memory_otp_store.get(key)
            if data and time.time() <= data.get("expires_at", 0):
                stored_data = data

        if not stored_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "OTP_EXPIRED",
                    "message": "The verification code has expired or was not requested.",
                },
            )

        stored_otp_hash = stored_data["otp_hash"]
        request_id = stored_data["request_id"]
        attempts = stored_data.get("attempts", 0) + 1

        # Fetch DB OTPRequest
        stmt = select(OTPRequest).where(OTPRequest.request_id == request_id)
        otp_record = (await session.execute(stmt)).scalar_one_or_none()

        # Constant-time comparison
        is_valid = verify_otp_code(submitted_code, stored_otp_hash)

        if not is_valid:
            stored_data["attempts"] = attempts

            # Log verification attempt in DB
            if otp_record:
                otp_record.attempts = attempts
                verification = OTPVerification(
                    otp_request_id=otp_record.id,
                    attempt_number=attempts,
                    result=OTPVerificationResult.INCORRECT,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                session.add(verification)

            if attempts >= settings.OTP_MAX_VERIFY_ATTEMPTS:
                if otp_record:
                    otp_record.status = OTPStatus.EXPIRED

                if redis is not None:
                    try:
                        await redis.delete(key)
                    except Exception:
                        pass
                _in_memory_otp_store.pop(key, None)

                await session.flush()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "MAX_ATTEMPTS_EXCEEDED",
                        "message": "Maximum verification attempts exceeded. Please request a new OTP.",
                    },
                )

            # Update attempts in Redis
            if redis is not None:
                try:
                    ttl = await redis.ttl(key)
                    if ttl > 0:
                        await redis.set(key, json.dumps(stored_data), ex=ttl)
                except Exception:
                    pass

            await session.flush()
            remaining = settings.OTP_MAX_VERIFY_ATTEMPTS - attempts
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_OTP",
                    "message": "The verification code is incorrect.",
                    "details": {"remaining_attempts": remaining},
                },
            )

        # Verification Successful!
        if redis is not None:
            try:
                await redis.delete(key)
            except Exception:
                pass
        _in_memory_otp_store.pop(key, None)

        verified_time = utc_now()
        if otp_record:
            otp_record.status = OTPStatus.VERIFIED
            otp_record.attempts = attempts
            otp_record.verified_at = verified_time

            verification = OTPVerification(
                otp_request_id=otp_record.id,
                attempt_number=attempts,
                result=OTPVerificationResult.CORRECT,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            session.add(verification)
            await session.flush()

        return {
            "verified": True,
            "request_id": request_id,
            "phone_number": mask_phone_number(phone_number),
            "verified_at": verified_time.isoformat(),
            "message": "OTP verified successfully",
        }

    @staticmethod
    async def get_otp_status(
        session: AsyncSession,
        request_id: str,
        customer_id: str,
    ) -> dict[str, Any]:
        """
        Retrieves current OTP status by request_id for a given customer.
        Handles checking for expiration and updating DB status if expired.
        """
        stmt = select(OTPRequest).where(
            OTPRequest.request_id == request_id,
            OTPRequest.customer_id == customer_id,
        )
        otp_record = (await session.execute(stmt)).scalar_one_or_none()

        if not otp_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "OTP_NOT_FOUND",
                    "message": f"OTP request with ID '{request_id}' was not found.",
                },
            )

        now = utc_now()
        # Expired check
        if (
            otp_record.status not in (OTPStatus.VERIFIED, OTPStatus.EXPIRED, OTPStatus.FAILED)
            and now > otp_record.expires_at
        ):
            otp_record.status = OTPStatus.EXPIRED
            await session.flush()

        return {
            "request_id": otp_record.request_id,
            "phone_number": mask_phone_number(otp_record.phone_number),
            "status": otp_record.status.value,
            "attempts": otp_record.attempts,
            "max_attempts": otp_record.max_attempts,
            "expires_at": otp_record.expires_at.isoformat(),
            "created_at": otp_record.created_at.isoformat(),
            "verified_at": otp_record.verified_at.isoformat() if otp_record.verified_at else None,
        }

