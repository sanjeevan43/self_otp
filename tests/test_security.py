from app.core.hashing import (
    hash_otp_code,
    hash_phone_number,
    mask_phone_number,
    validate_e164_phone,
    verify_otp_code,
)
from app.core.security import generate_api_key, hash_api_key, hash_password, verify_password


def test_password_hashing() -> None:
    password = "MySuperSecretPassword123!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_api_key_generation_and_hashing() -> None:
    raw_key, prefix, key_hash = generate_api_key()
    assert raw_key.startswith("wotp_live_")
    assert prefix == raw_key[:16]
    assert len(key_hash) == 64
    assert hash_api_key(raw_key) == key_hash


def test_phone_hashing_and_masking() -> None:
    phone = "+14155552671"
    assert validate_e164_phone(phone) is True
    assert validate_e164_phone("14155552671") is False
    assert validate_e164_phone("invalid") is False

    hashed_phone = hash_phone_number(phone)
    assert len(hashed_phone) == 64

    masked = mask_phone_number(phone)
    assert masked == "+1415***2671"


def test_otp_constant_time_verification() -> None:
    code = "839201"
    hashed_otp = hash_otp_code(code)
    assert verify_otp_code("839201", hashed_otp) is True
    assert verify_otp_code("000000", hashed_otp) is False
