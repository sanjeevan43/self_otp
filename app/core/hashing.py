import hashlib
import hmac
import re

from app.config import settings


def hash_phone_number(phone_number: str) -> str:
    """Computes a deterministic HMAC-SHA256 hash of an E.164 phone number."""
    key = settings.PEPPER.encode("utf-8")
    msg = phone_number.strip().encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def mask_phone_number(phone_number: str) -> str:
    """
    Masks an E.164 phone number for logging and UI display.
    Example: +14155552671 -> +1415***2671
    """
    clean_phone = phone_number.strip()
    if len(clean_phone) <= 7:
        return clean_phone[:3] + "***"
    prefix = clean_phone[:5]
    suffix = clean_phone[-4:]
    return f"{prefix}***{suffix}"


def hash_otp_code(otp_code: str) -> str:
    """Computes HMAC-SHA256 of an OTP code."""
    key = settings.PEPPER.encode("utf-8")
    msg = otp_code.strip().encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def verify_otp_code(submitted_otp: str, stored_otp_hash: str) -> bool:
    """Constant-time timing-attack safe comparison of OTP hashes."""
    submitted_hash = hash_otp_code(submitted_otp)
    return hmac.compare_digest(submitted_hash, stored_otp_hash)


def validate_e164_phone(phone_number: str) -> bool:
    """Validates international E.164 phone format (+123456789012)."""
    pattern = r"^\+[1-9]\d{1,14}$"
    return bool(re.match(pattern, phone_number.strip()))
