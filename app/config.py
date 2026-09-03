from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PROJECT_NAME: str = "WhatsApp OTP API SaaS Platform"
    SECRET_KEY: str = "super_secret_default_key_change_in_production_12345"
    DATABASE_URL: str = "sqlite+aiosqlite:///./self_otp_dev.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    PEPPER: str = "dev_pepper_secret_12345"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    META_API_VERSION: str = "v20.0"
    META_PHONE_NUMBER_ID: str = "100000000000000"
    META_WABA_ID: str = "200000000000000"
    META_ACCESS_TOKEN: str = "mock_meta_access_token"
    META_APP_SECRET: str = "mock_meta_app_secret"
    META_WEBHOOK_VERIFY_TOKEN: str = "mock_verify_token"

    DEFAULT_API_KEY_RATE_LIMIT_RPS: int = 60
    OTP_EXPIRY_SECONDS: int = 300
    OTP_COOLDOWN_SECONDS: int = 60
    OTP_MAX_VERIFY_ATTEMPTS: int = 3
    OTP_CREDIT_COST: float = 1.0000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
